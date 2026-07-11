from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from api.database import (
    SYNC_SCHEMA_VERSION,
    ensure_local_sync_node,
    get_local_sync_node,
    last_insert_id,
    new_uuid,
    register_sync_change,
    row_to_dict,
    rows_to_dicts,
    utcnow_iso,
)
from api.services import (
    _build_timesheet_payroll_records,
    _find_timesheet_payroll_duplicates,
    _resolve_work_price,
    _sync_daily_report_lines,
    _sync_estimate_lines,
    _sync_timesheet_lines,
    get_daily_report,
    get_estimate,
    get_timesheet,
)
from api.goods_services import get_goods_issue, get_goods_receipt
from api.payment_services import _sync_schedule_lines, get_payment_schedule, get_payment_transaction
from api.work_services import _sync_specifications


ENTITY_PRIORITY = {
    "units": 10,
    "materials": 20,
    "persons": 30,
    "counterparties": 40,
    "organizations": 50,
    "contracts": 55,
    "objects": 60,
    "works": 70,
    "estimates": 80,
    "daily_reports": 90,
    "timesheets": 100,
    "payment_schedules": 110,
    "goods_receipts": 113,
    "goods_issues": 116,
    "payment_transactions": 120,
}

ENTITY_TABLE_MAP = {
    "units": "units",
    "materials": "materials",
    "counterparties": "counterparties",
    "objects": "objects",
    "works": "works",
    "persons": "persons",
    "organizations": "organizations",
    "contracts": "contracts",
    "estimates": "estimates",
    "daily_reports": "daily_reports",
    "timesheets": "timesheets",
    "payment_schedules": "payment_schedules",
    "goods_receipts": "goods_receipts",
    "goods_issues": "goods_issues",
    "payment_transactions": "payment_transactions",
}

REFERENCE_SYNC_CONFIG: dict[str, dict[str, Any]] = {
    "counterparties": {
        "table": "counterparties",
        "fields": ["name", "inn", "contact_person", "phone", "marked_for_deletion", "is_group"],
        "relations": {"parent_id": ("counterparties", "parent_uuid")},
    },
    "objects": {
        "table": "objects",
        "fields": ["name", "address", "marked_for_deletion", "is_group"],
        "relations": {
            "owner_id": ("counterparties", "owner_uuid"),
            "parent_id": ("objects", "parent_uuid"),
        },
    },
    "persons": {
        "table": "persons",
        "fields": ["full_name", "position", "phone", "hourly_rate", "marked_for_deletion", "is_group"],
        "relations": {"parent_id": ("persons", "parent_uuid")},
    },
    "organizations": {
        "table": "organizations",
        "fields": ["name", "inn", "marked_for_deletion", "is_group"],
        "relations": {
            "default_responsible_id": ("persons", "default_responsible_uuid"),
            "parent_id": ("organizations", "parent_uuid"),
        },
    },
}


def _normalize_entity_type(entity_type: str) -> str:
    normalized = entity_type.strip()
    if normalized not in ENTITY_TABLE_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported sync entity type: {entity_type}")
    return normalized


def _to_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def _node_to_dict(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    node = row_to_dict(row) if isinstance(row, sqlite3.Row) else (dict(row) if row else {})
    if not node:
        return {}
    node["is_local"] = _to_bool(node.get("is_local"))
    node["sent_packet_no"] = int(node.get("sent_packet_no") or 0)
    node["received_packet_no"] = int(node.get("received_packet_no") or 0)
    return node


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _current_updated_at(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    return (
        row.get("updated_at")
        or row.get("modified_at")
        or row.get("created_at")
    )


def _remote_timestamp(payload: dict[str, Any]) -> str:
    return str(payload.get("updated_at") or payload.get("modified_at") or payload.get("created_at") or utcnow_iso())


def _coerce_common_fields(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["uuid"] = str(normalized.get("uuid") or "").strip() or new_uuid()
    normalized["created_at"] = str(normalized.get("created_at") or normalized.get("updated_at") or utcnow_iso())
    normalized["modified_at"] = str(
        normalized.get("modified_at") or normalized.get("updated_at") or normalized["created_at"]
    )
    normalized["updated_at"] = str(normalized.get("updated_at") or normalized["modified_at"])
    normalized["is_deleted"] = int(bool(normalized.get("is_deleted", normalized.get("marked_for_deletion", 0))))
    if "marked_for_deletion" in normalized:
        normalized["marked_for_deletion"] = int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"])))
    return normalized


def _resolve_entity_id(connection: sqlite3.Connection, entity_type: str, entity_uuid: str | None) -> int | None:
    if not entity_uuid:
        return None
    table_name = ENTITY_TABLE_MAP[_normalize_entity_type(entity_type)]
    row = connection.execute(f"SELECT id FROM {table_name} WHERE uuid = ?", (entity_uuid,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail=f"Missing related entity for sync: {entity_type} {entity_uuid}",
        )
    return int(row["id"])


def _get_entity_row(connection: sqlite3.Connection, table_name: str, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(f"SELECT * FROM {table_name} WHERE uuid = ?", (entity_uuid,)).fetchone()
    return row_to_dict(row) if row is not None else None


def _should_apply_remote(
    existing_row: dict[str, Any] | None,
    remote_payload: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    if existing_row is None:
        return True, None

    local_updated_at = _current_updated_at(existing_row)
    remote_updated_at = _remote_timestamp(remote_payload)
    if _parse_timestamp(local_updated_at) >= _parse_timestamp(remote_updated_at):
        return False, {
            "entity_type": "",
            "entity_uuid": str(remote_payload["uuid"]),
            "resolution": "local-wins",
            "local_updated_at": local_updated_at,
            "remote_updated_at": remote_updated_at,
        }
    return True, None


def _store_conflict(
    connection: sqlite3.Connection,
    *,
    entity_type: str,
    entity_uuid: str,
    source_node_id: str,
    payload: dict[str, Any],
    resolution: str,
    local_updated_at: str | None,
    remote_updated_at: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO object_version_history (
            id, entity_uuid, entity_type, source_node_id, arrival_time, serialized_data, conflict_resolution
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_uuid(),
            entity_uuid,
            entity_type,
            source_node_id,
            utcnow_iso(),
            json.dumps(
                {
                    "payload": payload,
                    "local_updated_at": local_updated_at,
                    "remote_updated_at": remote_updated_at,
                },
                ensure_ascii=False,
            ),
            resolution,
        ),
    )


def _register_remote_apply(connection: sqlite3.Connection, entity_type: str, entity_uuid: str, operation: str) -> None:
    register_sync_change(connection, entity_type=entity_type, entity_uuid=entity_uuid, operation=operation)


def _serialize_units(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    return _get_entity_row(connection, "units", entity_uuid)


def _serialize_materials(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT m.*, u.uuid AS unit_uuid, u.name AS unit_name
        FROM materials m
        LEFT JOIN units u ON u.id = m.unit_id
        WHERE m.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    return row_to_dict(row) if row is not None else None


def _serialize_counterparties(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT c.*, parent.uuid AS parent_uuid
        FROM counterparties c
        LEFT JOIN counterparties parent ON parent.id = c.parent_id
        WHERE c.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    return row_to_dict(row) if row is not None else None


def _serialize_objects(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT o.*, owner.uuid AS owner_uuid, parent.uuid AS parent_uuid
        FROM objects o
        LEFT JOIN counterparties owner ON owner.id = o.owner_id
        LEFT JOIN objects parent ON parent.id = o.parent_id
        WHERE o.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    return row_to_dict(row) if row is not None else None


def _serialize_persons(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT p.*, parent.uuid AS parent_uuid
        FROM persons p
        LEFT JOIN persons parent ON parent.id = p.parent_id
        WHERE p.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    if row is None:
        return None
    item = row_to_dict(row) or {}
    item.pop("user_id", None)
    return item


def _serialize_organizations(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
            org.*,
            resp.uuid AS default_responsible_uuid,
            parent.uuid AS parent_uuid
        FROM organizations org
        LEFT JOIN persons resp ON resp.id = org.default_responsible_id
        LEFT JOIN organizations parent ON parent.id = org.parent_id
        WHERE org.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    return row_to_dict(row) if row is not None else None


def _serialize_work_specifications(connection: sqlite3.Connection, work_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            ws.*,
            w.uuid AS work_uuid,
            u.uuid AS unit_uuid,
            u.name AS unit_name,
            m.uuid AS material_uuid
        FROM work_specifications ws
        JOIN works w ON w.id = ws.work_id
        LEFT JOIN units u ON u.id = ws.unit_id
        LEFT JOIN materials m ON m.id = ws.material_id
        WHERE ws.work_id = ?
          AND COALESCE(ws.marked_for_deletion, 0) = 0
          AND COALESCE(ws.is_deleted, 0) = 0
        ORDER BY ws.id
        """,
        (work_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def _serialize_works(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT w.*, parent.uuid AS parent_uuid
        FROM works w
        LEFT JOIN works parent ON parent.id = w.parent_id
        WHERE w.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    if row is None:
        return None
    work = row_to_dict(row) or {}
    work["specifications"] = _serialize_work_specifications(connection, int(work["id"])) if not work.get("is_deleted") else []
    return work


def _serialize_estimate_lines(connection: sqlite3.Connection, estimate_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT el.*, w.uuid AS work_uuid, w.name AS work_name
        FROM estimate_lines el
        LEFT JOIN works w ON w.id = el.work_id
        WHERE el.estimate_id = ?
          AND COALESCE(el.marked_for_deletion, 0) = 0
          AND COALESCE(el.is_deleted, 0) = 0
        ORDER BY el.line_number, el.id
        """,
        (estimate_id,),
    ).fetchall()
    items = rows_to_dicts(rows)
    line_uuid_map = {int(item["id"]): str(item["uuid"]) for item in items if item.get("uuid")}
    for item in items:
        parent_group_id = item.get("parent_group_id")
        item["parent_group_uuid"] = line_uuid_map.get(int(parent_group_id)) if parent_group_id is not None else None
    return items


def _serialize_estimates(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
            e.*,
            cp.uuid AS customer_uuid,
            o.uuid AS object_uuid,
            org.uuid AS contractor_uuid,
            p.uuid AS responsible_uuid,
            cp.name AS customer_name,
            o.name AS object_name,
            org.name AS contractor_name,
            p.full_name AS responsible_name
        FROM estimates e
        LEFT JOIN counterparties cp ON cp.id = e.customer_id
        LEFT JOIN objects o ON o.id = e.object_id
        LEFT JOIN organizations org ON org.id = e.contractor_id
        LEFT JOIN persons p ON p.id = e.responsible_id
        WHERE e.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    if row is None:
        return None
    estimate = row_to_dict(row) or {}
    estimate["lines"] = _serialize_estimate_lines(connection, int(estimate["id"])) if not estimate.get("is_deleted") else []
    return estimate


def _serialize_daily_report_lines(connection: sqlite3.Connection, report_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT drl.*, w.uuid AS work_uuid, w.name AS work_name
        FROM daily_report_lines drl
        LEFT JOIN works w ON w.id = drl.work_id
        WHERE drl.report_id = ?
          AND COALESCE(drl.marked_for_deletion, 0) = 0
          AND COALESCE(drl.is_deleted, 0) = 0
        ORDER BY drl.line_number, drl.id
        """,
        (report_id,),
    ).fetchall()
    items = rows_to_dicts(rows)
    line_uuid_map = {int(item["id"]): str(item["uuid"]) for item in items if item.get("uuid")}
    for item in items:
        parent_group_id = item.get("parent_group_id")
        item["parent_group_uuid"] = line_uuid_map.get(int(parent_group_id)) if parent_group_id is not None else None
        executor_rows = connection.execute(
            """
            SELECT p.id AS executor_id, p.uuid AS executor_uuid, p.full_name
            FROM daily_report_executors dre
            JOIN persons p ON p.id = dre.executor_id
            WHERE dre.report_line_id = ?
            ORDER BY p.full_name
            """,
            (item["id"],),
        ).fetchall()
        item["executor_ids"] = [int(row["executor_id"]) for row in executor_rows]
        item["executor_uuids"] = [str(row["executor_uuid"]) for row in executor_rows if row["executor_uuid"]]
        item["executor_names"] = [str(row["full_name"]) for row in executor_rows]
    return items


def _serialize_daily_reports(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
            dr.*,
            e.uuid AS estimate_uuid,
            e.number AS estimate_number,
            p.uuid AS foreman_uuid,
            p.full_name AS foreman_name
        FROM daily_reports dr
        LEFT JOIN estimates e ON e.id = dr.estimate_id
        LEFT JOIN persons p ON p.id = dr.foreman_id
        WHERE dr.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    if row is None:
        return None
    report = row_to_dict(row) or {}
    report["lines"] = _serialize_daily_report_lines(connection, int(report["id"])) if not report.get("is_deleted") else []
    return report


def _serialize_timesheets(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT id FROM timesheets WHERE uuid = ?", (entity_uuid,)).fetchone()
    if row is None:
        return None
    return get_timesheet(connection, int(row["id"]))


def _serialize_payment_schedule_lines(connection: sqlite3.Connection, schedule_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT psl.*,
            cp.uuid AS counterparty_uuid, cp.name AS counterparty_name,
            ct.uuid AS contract_uuid, ct.number AS contract_number,
            e.uuid AS estimate_uuid, e.number AS estimate_number,
            o.uuid AS object_uuid, o.name AS object_name
        FROM payment_schedule_lines psl
        LEFT JOIN counterparties cp ON cp.id = psl.counterparty_id
        LEFT JOIN contracts ct ON ct.id = psl.contract_id
        LEFT JOIN estimates e ON e.id = psl.estimate_id
        LEFT JOIN objects o ON o.id = psl.object_id
        WHERE psl.schedule_id = ?
          AND COALESCE(psl.marked_for_deletion, 0) = 0
          AND COALESCE(psl.is_deleted, 0) = 0
        ORDER BY psl.line_number, psl.id
        """,
        (schedule_id,),
    ).fetchall()
    items = rows_to_dicts(rows)
    line_uuid_map = {int(item["id"]): str(item["uuid"]) for item in items if item.get("uuid")}
    for item in items:
        parent_group_id = item.get("parent_group_id")
        item["parent_group_uuid"] = line_uuid_map.get(int(parent_group_id)) if parent_group_id is not None else None
    return items


def _serialize_payment_schedules(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT ps.*,
            o.uuid AS object_uuid, o.name AS object_name,
            ct.uuid AS contract_uuid, ct.number AS contract_number,
            p.uuid AS responsible_uuid, p.full_name AS responsible_name
        FROM payment_schedules ps
        LEFT JOIN objects o ON o.id = ps.object_id
        LEFT JOIN contracts ct ON ct.id = ps.contract_id
        LEFT JOIN persons p ON p.id = ps.responsible_id
        WHERE ps.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    if row is None:
        return None
    schedule = row_to_dict(row) or {}
    schedule["lines"] = (
        _serialize_payment_schedule_lines(connection, int(schedule["id"]))
        if not schedule.get("is_deleted")
        else []
    )
    return schedule


def _serialize_payment_transactions(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT pt.*,
            cp.uuid AS counterparty_uuid, cp.name AS counterparty_name,
            ct.uuid AS contract_uuid, ct.number AS contract_number,
            e.uuid AS estimate_uuid, e.number AS estimate_number,
            o.uuid AS object_uuid, o.name AS object_name,
            psl.uuid AS linked_line_uuid
        FROM payment_transactions pt
        LEFT JOIN counterparties cp ON cp.id = pt.counterparty_id
        LEFT JOIN contracts ct ON ct.id = pt.contract_id
        LEFT JOIN estimates e ON e.id = pt.estimate_id
        LEFT JOIN objects o ON o.id = pt.object_id
        LEFT JOIN payment_schedule_lines psl ON psl.id = pt.linked_line_id
        WHERE pt.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    if row is None:
        return None
    return row_to_dict(row) or {}


def _serialize_contracts(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT c.*,
            cp.uuid AS counterparty_uuid, cp.name AS counterparty_name,
            org.uuid AS organization_uuid, org.name AS organization_name,
            parent.uuid AS parent_uuid
        FROM contracts c
        LEFT JOIN counterparties cp ON cp.id = c.counterparty_id
        LEFT JOIN organizations org ON org.id = c.organization_id
        LEFT JOIN contracts parent ON parent.id = c.parent_id
        WHERE c.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    return row_to_dict(row) if row is not None else None


def _serialize_goods_receipt_lines(connection: sqlite3.Connection, receipt_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT grl.*,
            m.uuid AS material_uuid, m.name AS material_name,
            u.uuid AS unit_uuid, u.name AS unit_name,
            o.uuid AS object_uuid, o.name AS object_name
        FROM goods_receipt_lines grl
        LEFT JOIN materials m ON m.id = grl.material_id
        LEFT JOIN units u ON u.id = grl.unit_id
        LEFT JOIN objects o ON o.id = grl.object_id
        WHERE grl.receipt_id = ?
          AND COALESCE(grl.marked_for_deletion, 0) = 0
          AND COALESCE(grl.is_deleted, 0) = 0
        ORDER BY grl.line_number, grl.id
        """,
        (receipt_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def _serialize_goods_receipts(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT gr.*,
            org.uuid AS organization_uuid, org.name AS organization_name,
            cp.uuid AS counterparty_uuid, cp.name AS counterparty_name,
            ct.uuid AS contract_uuid, ct.number AS contract_number,
            o.uuid AS object_uuid, o.name AS object_name,
            e.uuid AS estimate_uuid, e.number AS estimate_number,
            p.uuid AS responsible_uuid, p.full_name AS responsible_name
        FROM goods_receipts gr
        LEFT JOIN organizations org ON org.id = gr.organization_id
        LEFT JOIN counterparties cp ON cp.id = gr.counterparty_id
        LEFT JOIN contracts ct ON ct.id = gr.contract_id
        LEFT JOIN objects o ON o.id = gr.object_id
        LEFT JOIN estimates e ON e.id = gr.estimate_id
        LEFT JOIN persons p ON p.id = gr.responsible_id
        WHERE gr.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    if row is None:
        return None
    receipt = row_to_dict(row) or {}
    receipt["lines"] = (
        _serialize_goods_receipt_lines(connection, int(receipt["id"]))
        if not receipt.get("is_deleted")
        else []
    )
    return receipt


def _serialize_goods_issue_lines(connection: sqlite3.Connection, issue_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT gil.*,
            m.uuid AS material_uuid, m.name AS material_name,
            u.uuid AS unit_uuid, u.name AS unit_name,
            o.uuid AS object_uuid, o.name AS object_name
        FROM goods_issue_lines gil
        LEFT JOIN materials m ON m.id = gil.material_id
        LEFT JOIN units u ON u.id = gil.unit_id
        LEFT JOIN objects o ON o.id = gil.object_id
        WHERE gil.issue_id = ?
          AND COALESCE(gil.marked_for_deletion, 0) = 0
          AND COALESCE(gil.is_deleted, 0) = 0
        ORDER BY gil.line_number, gil.id
        """,
        (issue_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def _serialize_goods_issues(connection: sqlite3.Connection, entity_uuid: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT gi.*,
            org.uuid AS organization_uuid, org.name AS organization_name,
            cp.uuid AS counterparty_uuid, cp.name AS counterparty_name,
            ct.uuid AS contract_uuid, ct.number AS contract_number,
            o.uuid AS object_uuid, o.name AS object_name,
            e.uuid AS estimate_uuid, e.number AS estimate_number,
            p.uuid AS responsible_uuid, p.full_name AS responsible_name
        FROM goods_issues gi
        LEFT JOIN organizations org ON org.id = gi.organization_id
        LEFT JOIN counterparties cp ON cp.id = gi.counterparty_id
        LEFT JOIN contracts ct ON ct.id = gi.contract_id
        LEFT JOIN objects o ON o.id = gi.object_id
        LEFT JOIN estimates e ON e.id = gi.estimate_id
        LEFT JOIN persons p ON p.id = gi.responsible_id
        WHERE gi.uuid = ?
        """,
        (entity_uuid,),
    ).fetchone()
    if row is None:
        return None
    issue = row_to_dict(row) or {}
    issue["lines"] = (
        _serialize_goods_issue_lines(connection, int(issue["id"]))
        if not issue.get("is_deleted")
        else []
    )
    return issue


SERIALIZER_MAP = {
    "units": _serialize_units,
    "materials": _serialize_materials,
    "counterparties": _serialize_counterparties,
    "objects": _serialize_objects,
    "persons": _serialize_persons,
    "organizations": _serialize_organizations,
    "contracts": _serialize_contracts,
    "works": _serialize_works,
    "estimates": _serialize_estimates,
    "daily_reports": _serialize_daily_reports,
    "timesheets": _serialize_timesheets,
    "payment_schedules": _serialize_payment_schedules,
    "goods_receipts": _serialize_goods_receipts,
    "goods_issues": _serialize_goods_issues,
    "payment_transactions": _serialize_payment_transactions,
}


def serialize_entity(connection: sqlite3.Connection, entity_type: str, entity_uuid: str) -> dict[str, Any] | None:
    normalized = _normalize_entity_type(entity_type)
    payload = SERIALIZER_MAP[normalized](connection, entity_uuid)
    if payload is None:
        return None
    return payload


def register_sync_node(
    connection: sqlite3.Connection,
    *,
    code: str,
    name: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    ensure_local_sync_node(connection)
    local_node = get_local_sync_node(connection)
    existing = None
    if node_id:
        existing_row = connection.execute("SELECT * FROM sync_nodes WHERE id = ?", (node_id,)).fetchone()
        if existing_row is not None:
            existing = _node_to_dict(existing_row)
    if existing is None:
        existing_row = connection.execute("SELECT * FROM sync_nodes WHERE code = ?", (code,)).fetchone()
        if existing_row is not None:
            existing = _node_to_dict(existing_row)

    if existing and existing.get("is_local"):
        if existing["id"] != local_node["id"]:
            raise HTTPException(status_code=409, detail="Node code conflicts with local sync node")
        return existing

    now = utcnow_iso()
    if existing is None:
        remote_id = node_id or new_uuid()
        connection.execute(
            """
            INSERT INTO sync_nodes (
                id, code, name, is_local, created_at, updated_at
            ) VALUES (?, ?, ?, 0, ?, ?)
            """,
            (remote_id, code, name, now, now),
        )
        row = connection.execute("SELECT * FROM sync_nodes WHERE id = ?", (remote_id,)).fetchone()
        return _node_to_dict(row)

    connection.execute(
        "UPDATE sync_nodes SET code = ?, name = ?, updated_at = ? WHERE id = ?",
        (code, name, now, existing["id"]),
    )
    row = connection.execute("SELECT * FROM sync_nodes WHERE id = ?", (existing["id"],)).fetchone()
    return _node_to_dict(row)


def _upsert_reference_entity(
    connection: sqlite3.Connection,
    *,
    entity_type: str,
    payload: dict[str, Any],
) -> int:
    config = REFERENCE_SYNC_CONFIG[entity_type]
    table_name = config["table"]
    normalized = _coerce_common_fields(payload)
    data: dict[str, Any] = {}
    for field in config["fields"]:
        default = normalized["is_deleted"] if field == "marked_for_deletion" else None
        data[field] = normalized.get(field, default)
    for local_field, (related_type, uuid_field) in config["relations"].items():
        data[local_field] = _resolve_entity_id(connection, related_type, normalized.get(uuid_field))
    data["created_at"] = normalized["created_at"]
    data["modified_at"] = normalized["modified_at"]
    data["uuid"] = normalized["uuid"]
    data["updated_at"] = normalized["updated_at"]
    data["is_deleted"] = normalized["is_deleted"]

    existing = _get_entity_row(connection, table_name, normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        return last_insert_id(connection)

    assignments = ", ".join(f"{column} = ?" for column in data.keys())
    connection.execute(
        f"UPDATE {table_name} SET {assignments} WHERE id = ?",
        [*data.values(), existing["id"]],
    )
    return int(existing["id"])


def _upsert_unit_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "name": normalized.get("name"),
        "short_name": normalized.get("short_name"),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "units", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO units ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        return last_insert_id(connection)

    assignments = ", ".join(f"{column} = ?" for column in data.keys())
    connection.execute(
        f"UPDATE units SET {assignments} WHERE id = ?",
        [*data.values(), existing["id"]],
    )
    return int(existing["id"])


def _upsert_material_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "code": normalized.get("code"),
        "name": normalized.get("name"),
        "unit_id": _resolve_entity_id(connection, "units", normalized.get("unit_uuid")),
        "price": float(normalized.get("price") or 0),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "materials", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO materials ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        return last_insert_id(connection)

    assignments = ", ".join(f"{column} = ?" for column in data.keys())
    connection.execute(
        f"UPDATE materials SET {assignments} WHERE id = ?",
        [*data.values(), existing["id"]],
    )
    return int(existing["id"])


def _upsert_work_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "name": normalized.get("name"),
        "code": normalized.get("code"),
        "unit": normalized.get("unit"),
        "price": float(normalized.get("price") or 0),
        "labor_rate": float(normalized.get("labor_rate") or 0),
        "parent_id": _resolve_entity_id(connection, "works", normalized.get("parent_uuid")),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "is_group": int(bool(normalized.get("is_group", 0))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "works", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO works ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        work_id = last_insert_id(connection)
    else:
        assignments = ", ".join(f"{column} = ?" for column in data.keys())
        connection.execute(
            f"UPDATE works SET {assignments} WHERE id = ?",
            [*data.values(), existing["id"]],
        )
        work_id = int(existing["id"])

    specifications: list[dict[str, Any]] = []
    for raw_spec in normalized.get("specifications", []) or []:
        spec = dict(raw_spec)
        unit_uuid = str(spec.get("unit_uuid") or "").strip() or None
        material_uuid = str(spec.get("material_uuid") or "").strip() or None
        if unit_uuid:
            spec["unit_id"] = _resolve_entity_id(connection, "units", unit_uuid)
        if material_uuid:
            spec["material_id"] = _resolve_entity_id(connection, "materials", material_uuid)
        spec["uuid"] = str(spec.get("uuid") or "").strip() or new_uuid()
        spec["created_at"] = str(spec.get("created_at") or spec.get("updated_at") or normalized["created_at"])
        spec["modified_at"] = str(spec.get("modified_at") or spec.get("updated_at") or normalized["updated_at"])
        spec["updated_at"] = str(spec.get("updated_at") or spec["modified_at"])
        spec["is_deleted"] = int(bool(spec.get("is_deleted", 0)))
        specifications.append(spec)
    _sync_specifications(connection, work_id=work_id, specifications=specifications)
    return work_id


def _upsert_estimate_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "number": normalized.get("number"),
        "date": str(normalized.get("date")),
        "customer_id": _resolve_entity_id(connection, "counterparties", normalized.get("customer_uuid")),
        "object_id": _resolve_entity_id(connection, "objects", normalized.get("object_uuid")),
        "contractor_id": _resolve_entity_id(connection, "organizations", normalized.get("contractor_uuid")),
        "responsible_id": _resolve_entity_id(connection, "persons", normalized.get("responsible_uuid")),
        "total_sum": float(normalized.get("total_sum") or 0),
        "total_labor": float(normalized.get("total_labor") or 0),
        "is_posted": int(bool(normalized.get("is_posted", 0))),
        "posted_at": normalized.get("posted_at"),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "estimates", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO estimates ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        estimate_id = last_insert_id(connection)
    else:
        assignments = ", ".join(f"{column} = ?" for column in data.keys())
        connection.execute(
            f"UPDATE estimates SET {assignments} WHERE id = ?",
            [*data.values(), existing["id"]],
        )
        estimate_id = int(existing["id"])

    lines: list[dict[str, Any]] = []
    for raw_line in normalized.get("lines", []) or []:
        line = dict(raw_line)
        work_uuid = str(line.get("work_uuid") or "").strip() or None
        if work_uuid:
            line["work_id"] = _resolve_entity_id(connection, "works", work_uuid)
        line["uuid"] = str(line.get("uuid") or "").strip() or new_uuid()
        line["created_at"] = str(line.get("created_at") or line.get("updated_at") or normalized["created_at"])
        line["modified_at"] = str(line.get("modified_at") or line.get("updated_at") or normalized["updated_at"])
        line["updated_at"] = str(line.get("updated_at") or line["modified_at"])
        line["marked_for_deletion"] = int(bool(line.get("marked_for_deletion", line.get("is_deleted", 0))))
        line["is_deleted"] = int(bool(line.get("is_deleted", 0)))
        lines.append(line)
    _sync_estimate_lines(connection, estimate_id=estimate_id, lines=lines)
    _rebuild_estimate_register(connection, estimate_id)
    return estimate_id


def _upsert_daily_report_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "number": normalized.get("number"),
        "date": str(normalized.get("date")),
        "estimate_id": _resolve_entity_id(connection, "estimates", normalized.get("estimate_uuid")),
        "foreman_id": _resolve_entity_id(connection, "persons", normalized.get("foreman_uuid")),
        "is_posted": int(bool(normalized.get("is_posted", 0))),
        "posted_at": normalized.get("posted_at"),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "daily_reports", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO daily_reports ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        report_id = last_insert_id(connection)
    else:
        assignments = ", ".join(f"{column} = ?" for column in data.keys())
        connection.execute(
            f"UPDATE daily_reports SET {assignments} WHERE id = ?",
            [*data.values(), existing["id"]],
        )
        report_id = int(existing["id"])

    lines: list[dict[str, Any]] = []
    for raw_line in normalized.get("lines", []) or []:
        line = dict(raw_line)
        work_uuid = str(line.get("work_uuid") or "").strip() or None
        if work_uuid:
            line["work_id"] = _resolve_entity_id(connection, "works", work_uuid)
        executor_uuids = [str(item) for item in line.get("executor_uuids", []) if item]
        if executor_uuids and not line.get("executor_ids"):
            line["executor_ids"] = [_resolve_entity_id(connection, "persons", item) for item in executor_uuids]
        line["uuid"] = str(line.get("uuid") or "").strip() or new_uuid()
        line["created_at"] = str(line.get("created_at") or line.get("updated_at") or normalized["created_at"])
        line["modified_at"] = str(line.get("modified_at") or line.get("updated_at") or normalized["updated_at"])
        line["updated_at"] = str(line.get("updated_at") or line["modified_at"])
        line["marked_for_deletion"] = int(bool(line.get("marked_for_deletion", line.get("is_deleted", 0))))
        line["is_deleted"] = int(bool(line.get("is_deleted", 0)))
        lines.append(line)
    _sync_daily_report_lines(connection, report_id=report_id, lines=lines)
    _rebuild_daily_report_register(connection, report_id)
    return report_id


def _upsert_timesheet_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "number": normalized.get("number"),
        "date": str(normalized.get("date")),
        "object_id": _resolve_entity_id(connection, "objects", normalized.get("object_uuid")),
        "estimate_id": _resolve_entity_id(connection, "estimates", normalized.get("estimate_uuid")),
        "foreman_id": _resolve_entity_id(connection, "persons", normalized.get("foreman_uuid")),
        "month_year": str(normalized.get("month_year")),
        "is_posted": int(bool(normalized.get("is_posted", 0))),
        "posted_at": normalized.get("posted_at"),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "timesheets", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO timesheets ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        timesheet_id = last_insert_id(connection)
    else:
        assignments = ", ".join(f"{column} = ?" for column in data.keys())
        connection.execute(
            f"UPDATE timesheets SET {assignments} WHERE id = ?",
            [*data.values(), existing["id"]],
        )
        timesheet_id = int(existing["id"])

    lines: list[dict[str, Any]] = []
    for raw_line in normalized.get("lines", []) or []:
        line = dict(raw_line)
        employee_uuid = str(line.get("employee_uuid") or "").strip() or None
        if employee_uuid:
            line["employee_id"] = _resolve_entity_id(connection, "persons", employee_uuid)
        line["uuid"] = str(line.get("uuid") or "").strip() or new_uuid()
        line["created_at"] = str(line.get("created_at") or line.get("updated_at") or normalized["created_at"])
        line["modified_at"] = str(line.get("modified_at") or line.get("updated_at") or normalized["updated_at"])
        line["updated_at"] = str(line.get("updated_at") or line["modified_at"])
        line["is_deleted"] = int(bool(line.get("is_deleted", 0)))
        lines.append(line)
    _sync_timesheet_lines(
        connection,
        timesheet_id=timesheet_id,
        month_year=str(normalized["month_year"]),
        lines=lines,
    )
    _rebuild_timesheet_payroll_register(connection, timesheet_id)
    return timesheet_id


def _mark_reference_deleted(connection: sqlite3.Connection, entity_type: str, entity_uuid: str, updated_at: str) -> bool:
    table_name = REFERENCE_SYNC_CONFIG[entity_type]["table"]
    existing = _get_entity_row(connection, table_name, entity_uuid)
    if existing is None:
        return False
    connection.execute(
        f"""
        UPDATE {table_name}
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    return True


def _mark_unit_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "units", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE units
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    return True


def _mark_material_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "materials", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE materials
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    return True


def _mark_work_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "works", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE works
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        """
        UPDATE work_specifications
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE work_id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    return True


def _mark_estimate_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "estimates", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE estimates
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?,
            is_posted = 0,
            posted_at = NULL
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        """
        UPDATE estimate_lines
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE estimate_id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "DELETE FROM work_execution_register WHERE recorder_type = 'estimate' AND recorder_id = ?",
        (existing["id"],),
    )
    return True


def _mark_daily_report_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "daily_reports", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE daily_reports
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?,
            is_posted = 0,
            posted_at = NULL
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "DELETE FROM daily_report_executors WHERE report_line_id IN (SELECT id FROM daily_report_lines WHERE report_id = ?)",
        (existing["id"],),
    )
    connection.execute(
        """
        UPDATE daily_report_lines
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE report_id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "DELETE FROM work_execution_register WHERE recorder_type = 'daily_report' AND recorder_id = ?",
        (existing["id"],),
    )
    return True


def _mark_timesheet_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "timesheets", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE timesheets
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?,
            is_posted = 0,
            posted_at = NULL
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        """
        UPDATE timesheet_lines
        SET is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE timesheet_id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "DELETE FROM payroll_register WHERE recorder_type = 'timesheet' AND recorder_id = ?",
        (existing["id"],),
    )
    return True


def _mark_payment_schedule_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "payment_schedules", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE payment_schedules
        SET marked_for_deletion = 1, is_deleted = 1,
            modified_at = ?, updated_at = ?, is_posted = 0, posted_at = NULL
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        """
        UPDATE payment_schedule_lines
        SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ?
        WHERE schedule_id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "DELETE FROM payment_schedule_register WHERE recorder_type = 'payment_schedule' AND recorder_id = ?",
        (existing["id"],),
    )
    return True


def _mark_payment_transaction_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "payment_transactions", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE payment_transactions
        SET marked_for_deletion = 1, is_deleted = 1,
            modified_at = ?, updated_at = ?, is_posted = 0, posted_at = NULL
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "DELETE FROM payment_schedule_register WHERE recorder_type = 'payment_transaction' AND recorder_id = ?",
        (existing["id"],),
    )
    return True


def _mark_contract_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "contracts", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE contracts
        SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    return True


def _mark_goods_receipt_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "goods_receipts", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE goods_receipts
        SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ?, is_posted = 0, posted_at = NULL
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "UPDATE goods_receipt_lines SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ? WHERE receipt_id = ?",
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "DELETE FROM inventory_register WHERE recorder_type = 'goods_receipt' AND recorder_id = ?",
        (existing["id"],),
    )
    connection.execute(
        "DELETE FROM mutual_settlements_register WHERE recorder_type = 'goods_receipt' AND recorder_id = ?",
        (existing["id"],),
    )
    return True


def _mark_goods_issue_deleted(connection: sqlite3.Connection, entity_uuid: str, updated_at: str) -> bool:
    existing = _get_entity_row(connection, "goods_issues", entity_uuid)
    if existing is None:
        return False
    connection.execute(
        """
        UPDATE goods_issues
        SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ?, is_posted = 0, posted_at = NULL
        WHERE id = ?
        """,
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "UPDATE goods_issue_lines SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ? WHERE issue_id = ?",
        (updated_at, updated_at, existing["id"]),
    )
    connection.execute(
        "DELETE FROM inventory_register WHERE recorder_type = 'goods_issue' AND recorder_id = ?",
        (existing["id"],),
    )
    connection.execute(
        "DELETE FROM mutual_settlements_register WHERE recorder_type = 'goods_issue' AND recorder_id = ?",
        (existing["id"],),
    )
    return True


DELETE_HANDLER_MAP = {
    "units": _mark_unit_deleted,
    "materials": _mark_material_deleted,
    "counterparties": lambda c, u, t: _mark_reference_deleted(c, "counterparties", u, t),
    "objects": lambda c, u, t: _mark_reference_deleted(c, "objects", u, t),
    "persons": lambda c, u, t: _mark_reference_deleted(c, "persons", u, t),
    "organizations": lambda c, u, t: _mark_reference_deleted(c, "organizations", u, t),
    "works": _mark_work_deleted,
    "contracts": _mark_contract_deleted,
    "estimates": _mark_estimate_deleted,
    "daily_reports": _mark_daily_report_deleted,
    "timesheets": _mark_timesheet_deleted,
    "payment_schedules": _mark_payment_schedule_deleted,
    "goods_receipts": _mark_goods_receipt_deleted,
    "goods_issues": _mark_goods_issue_deleted,
    "payment_transactions": _mark_payment_transaction_deleted,
}

def _rebuild_payment_schedule_register(connection: sqlite3.Connection, schedule_id: int) -> None:
    connection.execute(
        "DELETE FROM payment_schedule_register WHERE recorder_type = 'payment_schedule' AND recorder_id = ?",
        (schedule_id,),
    )
    schedule = get_payment_schedule(connection, schedule_id)
    if schedule.get("is_deleted") or not schedule.get("is_posted"):
        return
    stamp = str(schedule.get("updated_at") or utcnow_iso())
    for line in schedule["lines"]:
        if line.get("is_group"):
            continue
        connection.execute(
            """
            INSERT INTO payment_schedule_register (
                recorder_type, recorder_id, line_number, period, direction, category,
                counterparty_id, contract_id, estimate_id, object_id,
                planned_amount, fact_amount, linked_line_id,
                created_at, modified_at, uuid, updated_at, is_deleted
            )
            VALUES ('payment_schedule', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, 0)
            """,
            (
                schedule_id,
                int(line["line_number"]),
                str(line["planned_date"]),
                line["direction"],
                line["category"],
                line.get("counterparty_id"),
                line.get("contract_id"),
                line.get("estimate_id"),
                line.get("object_id"),
                round(float(line.get("planned_amount") or 0), 2),
                int(line["id"]),
                stamp,
                stamp,
                new_uuid(),
                stamp,
            ),
        )


def _rebuild_payment_transaction_register(connection: sqlite3.Connection, tx_id: int) -> None:
    connection.execute(
        "DELETE FROM payment_schedule_register WHERE recorder_type = 'payment_transaction' AND recorder_id = ?",
        (tx_id,),
    )
    tx = get_payment_transaction(connection, tx_id)
    if tx.get("is_deleted") or not tx.get("is_posted"):
        return
    stamp = str(tx.get("updated_at") or utcnow_iso())
    connection.execute(
        """
        INSERT INTO payment_schedule_register (
            recorder_type, recorder_id, line_number, period, direction, category,
            counterparty_id, contract_id, estimate_id, object_id,
            planned_amount, fact_amount, linked_line_id,
            created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES ('payment_transaction', ?, 1, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            tx_id,
            str(tx["date"]),
            tx["direction"],
            tx["category"],
            tx.get("counterparty_id"),
            tx.get("contract_id"),
            tx.get("estimate_id"),
            tx.get("object_id"),
            round(float(tx.get("amount") or 0), 2),
            tx.get("linked_line_id"),
            stamp,
            stamp,
            new_uuid(),
            stamp,
        ),
    )


def _upsert_payment_schedule_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "number": normalized.get("number"),
        "date_from": str(normalized.get("date_from")),
        "date_to": str(normalized.get("date_to")),
        "object_id": _resolve_entity_id(connection, "objects", normalized.get("object_uuid")),
        "contract_id": _resolve_entity_id(connection, "contracts", normalized.get("contract_uuid")),
        "responsible_id": _resolve_entity_id(connection, "persons", normalized.get("responsible_uuid")),
        "is_posted": int(bool(normalized.get("is_posted", 0))),
        "posted_at": normalized.get("posted_at"),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "payment_schedules", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO payment_schedules ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        schedule_id = last_insert_id(connection)
    else:
        assignments = ", ".join(f"{column} = ?" for column in data.keys())
        connection.execute(
            f"UPDATE payment_schedules SET {assignments} WHERE id = ?",
            [*data.values(), existing["id"]],
        )
        schedule_id = int(existing["id"])

    lines: list[dict[str, Any]] = []
    for raw_line in normalized.get("lines", []) or []:
        line = dict(raw_line)
        for uuid_field, entity_type in (
            ("counterparty_uuid", "counterparties"),
            ("contract_uuid", "contracts"),
            ("estimate_uuid", "estimates"),
            ("object_uuid", "objects"),
        ):
            ref_uuid = str(line.get(uuid_field) or "").strip() or None
            if ref_uuid:
                local_field = uuid_field.replace("_uuid", "_id")
                line[local_field] = _resolve_entity_id(connection, entity_type, ref_uuid)
        line["uuid"] = str(line.get("uuid") or "").strip() or new_uuid()
        line["created_at"] = str(line.get("created_at") or line.get("updated_at") or normalized["created_at"])
        line["modified_at"] = str(line.get("modified_at") or line.get("updated_at") or normalized["updated_at"])
        line["updated_at"] = str(line.get("updated_at") or line["modified_at"])
        line["marked_for_deletion"] = int(bool(line.get("marked_for_deletion", line.get("is_deleted", 0))))
        line["is_deleted"] = int(bool(line.get("is_deleted", 0)))
        lines.append(line)
    _sync_schedule_lines(connection, schedule_id=schedule_id, lines=lines)
    _rebuild_payment_schedule_register(connection, schedule_id)
    return schedule_id


def _upsert_payment_transaction_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    linked_line_id = None
    linked_line_uuid = str(normalized.get("linked_line_uuid") or "").strip() or None
    if linked_line_uuid:
        row = connection.execute(
            "SELECT id FROM payment_schedule_lines WHERE uuid = ?", (linked_line_uuid,)
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=409,
                detail=f"Missing linked payment_schedule_line for sync: {linked_line_uuid}",
            )
        linked_line_id = int(row["id"])

    linked_schedule_id = None
    linked_schedule_uuid = str(normalized.get("linked_schedule_uuid") or "").strip() or None
    if linked_schedule_uuid:
        linked_schedule_id = _resolve_entity_id(connection, "payment_schedules", linked_schedule_uuid)

    data = {
        "number": normalized.get("number"),
        "date": str(normalized.get("date")),
        "direction": normalized.get("direction") or "outgoing",
        "category": normalized.get("category") or "other",
        "counterparty_id": _resolve_entity_id(connection, "counterparties", normalized.get("counterparty_uuid")),
        "contract_id": _resolve_entity_id(connection, "contracts", normalized.get("contract_uuid")),
        "estimate_id": _resolve_entity_id(connection, "estimates", normalized.get("estimate_uuid")),
        "object_id": _resolve_entity_id(connection, "objects", normalized.get("object_uuid")),
        "linked_schedule_id": linked_schedule_id,
        "linked_line_id": linked_line_id,
        "amount": float(normalized.get("amount") or 0),
        "description": normalized.get("description"),
        "is_posted": int(bool(normalized.get("is_posted", 0))),
        "posted_at": normalized.get("posted_at"),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "payment_transactions", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO payment_transactions ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        tx_id = last_insert_id(connection)
    else:
        assignments = ", ".join(f"{column} = ?" for column in data.keys())
        connection.execute(
            f"UPDATE payment_transactions SET {assignments} WHERE id = ?",
            [*data.values(), existing["id"]],
        )
        tx_id = int(existing["id"])
    _rebuild_payment_transaction_register(connection, tx_id)
    return tx_id


def _sync_goods_receipt_lines(connection: sqlite3.Connection, *, receipt_id: int, lines: list[dict[str, Any]]) -> None:
    connection.execute(
        "DELETE FROM goods_receipt_lines WHERE receipt_id = ?",
        (receipt_id,),
    )
    for line in lines:
        normalized = dict(line)
        connection.execute(
            """
            INSERT INTO goods_receipt_lines (
                receipt_id, line_number, material_id, name, unit_id, unit,
                quantity, price_without_vat, vat_rate, vat_amount, sum_without_vat, sum_with_vat,
                object_id, drawing_code, note,
                marked_for_deletion, created_at, modified_at, uuid, updated_at, is_deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 0)
            """,
            (
                receipt_id,
                int(normalized.get("line_number", 0)),
                _resolve_entity_id(connection, "materials", normalized.get("material_uuid")),
                normalized.get("name", ""),
                _resolve_entity_id(connection, "units", normalized.get("unit_uuid")),
                normalized.get("unit"),
                round(float(normalized.get("quantity", 0)), 6),
                round(float(normalized.get("price_without_vat", 0)), 2),
                round(float(normalized.get("vat_rate", 20.0)), 2),
                round(float(normalized.get("vat_amount", 0)), 2),
                round(float(normalized.get("sum_without_vat", 0)), 2),
                round(float(normalized.get("sum_with_vat", 0)), 2),
                _resolve_entity_id(connection, "objects", normalized.get("object_uuid")),
                normalized.get("drawing_code"),
                normalized.get("note"),
                str(normalized.get("created_at") or utcnow_iso()),
                str(normalized.get("modified_at") or normalized.get("updated_at") or utcnow_iso()),
                str(normalized.get("uuid") or new_uuid()),
                str(normalized.get("updated_at") or normalized.get("modified_at") or utcnow_iso()),
            ),
        )


def _sync_goods_issue_lines(connection: sqlite3.Connection, *, issue_id: int, lines: list[dict[str, Any]]) -> None:
    connection.execute(
        "DELETE FROM goods_issue_lines WHERE issue_id = ?",
        (issue_id,),
    )
    for line in lines:
        normalized = dict(line)
        connection.execute(
            """
            INSERT INTO goods_issue_lines (
                issue_id, line_number, material_id, name, unit_id, unit,
                quantity, price_without_vat, vat_rate, vat_amount, sum_without_vat, sum_with_vat,
                object_id, drawing_code, note,
                marked_for_deletion, created_at, modified_at, uuid, updated_at, is_deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 0)
            """,
            (
                issue_id,
                int(normalized.get("line_number", 0)),
                _resolve_entity_id(connection, "materials", normalized.get("material_uuid")),
                normalized.get("name", ""),
                _resolve_entity_id(connection, "units", normalized.get("unit_uuid")),
                normalized.get("unit"),
                round(float(normalized.get("quantity", 0)), 6),
                round(float(normalized.get("price_without_vat", 0)), 2),
                round(float(normalized.get("vat_rate", 20.0)), 2),
                round(float(normalized.get("vat_amount", 0)), 2),
                round(float(normalized.get("sum_without_vat", 0)), 2),
                round(float(normalized.get("sum_with_vat", 0)), 2),
                _resolve_entity_id(connection, "objects", normalized.get("object_uuid")),
                normalized.get("drawing_code"),
                normalized.get("note"),
                str(normalized.get("created_at") or utcnow_iso()),
                str(normalized.get("modified_at") or normalized.get("updated_at") or utcnow_iso()),
                str(normalized.get("uuid") or new_uuid()),
                str(normalized.get("updated_at") or normalized.get("modified_at") or utcnow_iso()),
            ),
        )


def _rebuild_goods_document_register(connection: sqlite3.Connection, kind: str, document_id: int) -> None:
    recorder_type = "goods_receipt" if kind == "receipt" else "goods_issue"
    connection.execute(
        "DELETE FROM inventory_register WHERE recorder_type = ? AND recorder_id = ?",
        (recorder_type, document_id),
    )
    connection.execute(
        "DELETE FROM mutual_settlements_register WHERE recorder_type = ? AND recorder_id = ?",
        (recorder_type, document_id),
    )
    doc = get_goods_receipt(connection, document_id) if kind == "receipt" else get_goods_issue(connection, document_id)
    if doc.get("is_deleted") or not doc.get("is_posted"):
        return
    stamp = str(doc.get("updated_at") or utcnow_iso())
    for line in doc.get("lines", []):
        line_object_id = line.get("object_id") or doc.get("object_id")
        connection.execute(
            """
            INSERT INTO inventory_register (
                recorder_type, recorder_id, line_number, period,
                material_id, object_id, unit_id,
                quantity_income, quantity_expense, sum_income, sum_expense,
                created_at, uuid, updated_at, is_deleted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                recorder_type,
                document_id,
                int(line["line_number"]),
                str(doc["date"]),
                line.get("material_id"),
                line_object_id,
                line.get("unit_id"),
                round(float(line.get("quantity") or 0), 6) if kind == "receipt" else 0.0,
                round(float(line.get("quantity") or 0), 6) if kind == "issue" else 0.0,
                round(float(line.get("sum_without_vat") or 0), 2) if kind == "receipt" else 0.0,
                round(float(line.get("sum_without_vat") or 0), 2) if kind == "issue" else 0.0,
                stamp,
                new_uuid(),
                stamp,
            ),
        )
    direction = "payable" if kind == "receipt" else "receivable"
    connection.execute(
        """
        INSERT INTO mutual_settlements_register (
            recorder_type, recorder_id, line_number, period,
            organization_id, counterparty_id, contract_id, object_id, estimate_id,
            direction, accrual_amount, payment_amount, planned_amount,
            linked_line_id, created_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?, ?, 0)
        """,
        (
            recorder_type,
            document_id,
            str(doc["date"]),
            int(doc["organization_id"]),
            doc.get("counterparty_id"),
            doc.get("contract_id"),
            doc.get("object_id"),
            doc.get("estimate_id"),
            direction,
            round(float(doc.get("sum_with_vat", 0)), 2),
            stamp,
            new_uuid(),
            stamp,
        ),
    )


def _upsert_contract_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "number": normalized.get("number"),
        "date": str(normalized.get("date") or ""),
        "counterparty_id": _resolve_entity_id(connection, "counterparties", normalized.get("counterparty_uuid")),
        "organization_id": _resolve_entity_id(connection, "organizations", normalized.get("organization_uuid")),
        "parent_id": _resolve_entity_id(connection, "contracts", normalized.get("parent_uuid")),
        "amount": round(float(normalized.get("amount") or 0), 2),
        "kind": normalized.get("kind") or "supply",
        "currency": normalized.get("currency") or "RUB",
        "vat_rate": round(float(normalized.get("vat_rate") or 20.0), 2),
        "payment_deferral_days": int(normalized.get("payment_deferral_days") or 0),
        "agreement_date": str(normalized.get("agreement_date") or ""),
        "valid_until": str(normalized.get("valid_until") or ""),
        "description": normalized.get("description"),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "is_group": int(bool(normalized.get("is_group", 0))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "contracts", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO contracts ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        return last_insert_id(connection)
    assignments = ", ".join(f"{column} = ?" for column in data.keys())
    connection.execute(
        f"UPDATE contracts SET {assignments} WHERE id = ?",
        [*data.values(), existing["id"]],
    )
    return int(existing["id"])


def _upsert_goods_receipt_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "number": normalized.get("number"),
        "date": str(normalized.get("date")),
        "organization_id": _resolve_entity_id(connection, "organizations", normalized.get("organization_uuid")),
        "counterparty_id": _resolve_entity_id(connection, "counterparties", normalized.get("counterparty_uuid")),
        "contract_id": _resolve_entity_id(connection, "contracts", normalized.get("contract_uuid")),
        "object_id": _resolve_entity_id(connection, "objects", normalized.get("object_uuid")),
        "estimate_id": _resolve_entity_id(connection, "estimates", normalized.get("estimate_uuid")),
        "responsible_id": _resolve_entity_id(connection, "persons", normalized.get("responsible_uuid")),
        "sum_without_vat": round(float(normalized.get("sum_without_vat") or 0), 2),
        "vat_amount": round(float(normalized.get("vat_amount") or 0), 2),
        "sum_with_vat": round(float(normalized.get("sum_with_vat") or 0), 2),
        "due_date": str(normalized.get("due_date") or ""),
        "description": normalized.get("description"),
        "is_posted": int(bool(normalized.get("is_posted", 0))),
        "posted_at": normalized.get("posted_at"),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "goods_receipts", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO goods_receipts ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        doc_id = last_insert_id(connection)
    else:
        assignments = ", ".join(f"{column} = ?" for column in data.keys())
        connection.execute(
            f"UPDATE goods_receipts SET {assignments} WHERE id = ?",
            [*data.values(), existing["id"]],
        )
        doc_id = int(existing["id"])
    lines: list[dict[str, Any]] = []
    for raw_line in normalized.get("lines", []) or []:
        line = dict(raw_line)
        for uuid_field, entity_type in (
            ("material_uuid", "materials"),
            ("unit_uuid", "units"),
            ("object_uuid", "objects"),
        ):
            ref_uuid = str(line.get(uuid_field) or "").strip() or None
            if ref_uuid:
                local_field = uuid_field.replace("_uuid", "_id")
                line[local_field] = _resolve_entity_id(connection, entity_type, ref_uuid)
        line["uuid"] = str(line.get("uuid") or "").strip() or new_uuid()
        line["created_at"] = str(line.get("created_at") or line.get("updated_at") or normalized["created_at"])
        line["modified_at"] = str(line.get("modified_at") or line.get("updated_at") or normalized["updated_at"])
        line["updated_at"] = str(line.get("updated_at") or line["modified_at"])
        line["is_deleted"] = int(bool(line.get("is_deleted", 0)))
        lines.append(line)
    _sync_goods_receipt_lines(connection, receipt_id=doc_id, lines=lines)
    _rebuild_goods_document_register(connection, kind="receipt", document_id=doc_id)
    return doc_id


def _upsert_goods_issue_entity(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    normalized = _coerce_common_fields(payload)
    data = {
        "number": normalized.get("number"),
        "date": str(normalized.get("date")),
        "organization_id": _resolve_entity_id(connection, "organizations", normalized.get("organization_uuid")),
        "counterparty_id": _resolve_entity_id(connection, "counterparties", normalized.get("counterparty_uuid")),
        "contract_id": _resolve_entity_id(connection, "contracts", normalized.get("contract_uuid")),
        "object_id": _resolve_entity_id(connection, "objects", normalized.get("object_uuid")),
        "estimate_id": _resolve_entity_id(connection, "estimates", normalized.get("estimate_uuid")),
        "responsible_id": _resolve_entity_id(connection, "persons", normalized.get("responsible_uuid")),
        "sum_without_vat": round(float(normalized.get("sum_without_vat") or 0), 2),
        "vat_amount": round(float(normalized.get("vat_amount") or 0), 2),
        "sum_with_vat": round(float(normalized.get("sum_with_vat") or 0), 2),
        "due_date": str(normalized.get("due_date") or ""),
        "description": normalized.get("description"),
        "is_posted": int(bool(normalized.get("is_posted", 0))),
        "posted_at": normalized.get("posted_at"),
        "marked_for_deletion": int(bool(normalized.get("marked_for_deletion", normalized["is_deleted"]))),
        "created_at": normalized["created_at"],
        "modified_at": normalized["modified_at"],
        "uuid": normalized["uuid"],
        "updated_at": normalized["updated_at"],
        "is_deleted": normalized["is_deleted"],
    }
    existing = _get_entity_row(connection, "goods_issues", normalized["uuid"])
    if existing is None:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        connection.execute(
            f"INSERT INTO goods_issues ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        doc_id = last_insert_id(connection)
    else:
        assignments = ", ".join(f"{column} = ?" for column in data.keys())
        connection.execute(
            f"UPDATE goods_issues SET {assignments} WHERE id = ?",
            [*data.values(), existing["id"]],
        )
        doc_id = int(existing["id"])
    lines: list[dict[str, Any]] = []
    for raw_line in normalized.get("lines", []) or []:
        line = dict(raw_line)
        for uuid_field, entity_type in (
            ("material_uuid", "materials"),
            ("unit_uuid", "units"),
            ("object_uuid", "objects"),
        ):
            ref_uuid = str(line.get(uuid_field) or "").strip() or None
            if ref_uuid:
                local_field = uuid_field.replace("_uuid", "_id")
                line[local_field] = _resolve_entity_id(connection, entity_type, ref_uuid)
        line["uuid"] = str(line.get("uuid") or "").strip() or new_uuid()
        line["created_at"] = str(line.get("created_at") or line.get("updated_at") or normalized["created_at"])
        line["modified_at"] = str(line.get("modified_at") or line.get("updated_at") or normalized["updated_at"])
        line["updated_at"] = str(line.get("updated_at") or line["modified_at"])
        line["is_deleted"] = int(bool(line.get("is_deleted", 0)))
        lines.append(line)
    _sync_goods_issue_lines(connection, issue_id=doc_id, lines=lines)
    _rebuild_goods_document_register(connection, kind="issue", document_id=doc_id)
    return doc_id


UPSERT_HANDLER_MAP = {
    "units": _upsert_unit_entity,
    "materials": _upsert_material_entity,
    "counterparties": lambda c, p: _upsert_reference_entity(c, entity_type="counterparties", payload=p),
    "objects": lambda c, p: _upsert_reference_entity(c, entity_type="objects", payload=p),
    "persons": lambda c, p: _upsert_reference_entity(c, entity_type="persons", payload=p),
    "organizations": lambda c, p: _upsert_reference_entity(c, entity_type="organizations", payload=p),
    "works": _upsert_work_entity,
    "contracts": _upsert_contract_entity,
    "estimates": _upsert_estimate_entity,
    "daily_reports": _upsert_daily_report_entity,
    "timesheets": _upsert_timesheet_entity,
    "payment_schedules": _upsert_payment_schedule_entity,
    "goods_receipts": _upsert_goods_receipt_entity,
    "goods_issues": _upsert_goods_issue_entity,
    "payment_transactions": _upsert_payment_transaction_entity,
}


def _rebuild_estimate_register(connection: sqlite3.Connection, estimate_id: int) -> None:
    connection.execute(
        "DELETE FROM work_execution_register WHERE recorder_type = 'estimate' AND recorder_id = ?",
        (estimate_id,),
    )
    estimate = get_estimate(connection, estimate_id)
    if estimate["is_deleted"] or not estimate["is_posted"]:
        return
    stamp = str(estimate.get("updated_at") or utcnow_iso())
    for line in estimate["lines"]:
        if line["is_group"] or not line["work_id"]:
            continue
        connection.execute(
            """
            INSERT INTO work_execution_register (
                recorder_type, recorder_id, line_number, period, object_id, estimate_id, work_id,
                quantity_income, quantity_expense, sum_income, sum_expense, created_at, modified_at, uuid, updated_at, is_deleted
            )
            VALUES ('estimate', ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, ?, 0)
            """,
            (
                estimate_id,
                line["line_number"],
                estimate["date"],
                estimate["object_id"],
                estimate_id,
                line["work_id"],
                line["quantity"],
                line["sum"],
                stamp,
                stamp,
                new_uuid(),
                stamp,
            ),
        )


def _rebuild_daily_report_register(connection: sqlite3.Connection, report_id: int) -> None:
    connection.execute(
        "DELETE FROM work_execution_register WHERE recorder_type = 'daily_report' AND recorder_id = ?",
        (report_id,),
    )
    report = get_daily_report(connection, report_id)
    if report["is_deleted"] or not report["is_posted"]:
        return
    estimate = get_estimate(connection, report["estimate_id"]) if report["estimate_id"] else None
    object_id = estimate["object_id"] if estimate else None
    stamp = str(report.get("updated_at") or utcnow_iso())
    for line in report["lines"]:
        if line["is_group"] or not line["work_id"]:
            continue
        price = _resolve_work_price(connection, report["estimate_id"], line["work_id"])
        connection.execute(
            """
            INSERT INTO work_execution_register (
                recorder_type, recorder_id, line_number, period, object_id, estimate_id, work_id,
                quantity_income, quantity_expense, sum_income, sum_expense, created_at, modified_at, uuid, updated_at, is_deleted
            )
            VALUES ('daily_report', ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, ?, 0)
            """,
            (
                report_id,
                line["line_number"],
                report["date"],
                object_id,
                report["estimate_id"],
                line["work_id"],
                line["actual_labor"],
                round(float(line["actual_labor"]) * price, 2),
                stamp,
                stamp,
                new_uuid(),
                stamp,
            ),
        )


def _rebuild_timesheet_payroll_register(connection: sqlite3.Connection, timesheet_id: int) -> None:
    connection.execute(
        "DELETE FROM payroll_register WHERE recorder_type = 'timesheet' AND recorder_id = ?",
        (timesheet_id,),
    )
    timesheet = get_timesheet(connection, timesheet_id)
    if timesheet["is_deleted"] or not timesheet["is_posted"]:
        return
    records = _build_timesheet_payroll_records(timesheet)
    duplicates = _find_timesheet_payroll_duplicates(connection, timesheet_id=timesheet_id, records=records)
    if duplicates:
        raise HTTPException(
            status_code=409,
            detail="Payroll duplicates detected while rebuilding posted timesheet during sync",
        )
    stamp = str(timesheet.get("updated_at") or utcnow_iso())
    for record in records:
        connection.execute(
            """
            INSERT INTO payroll_register (
                recorder_type, recorder_id, line_number, period, object_id, estimate_id, employee_id,
                work_date, hours_worked, amount, created_at, modified_at, uuid, updated_at, is_deleted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                record["recorder_type"],
                record["recorder_id"],
                record["line_number"],
                record["period"],
                record["object_id"],
                record["estimate_id"],
                record["employee_id"],
                record["work_date"],
                record["hours_worked"],
                record["amount"],
                stamp,
                stamp,
                new_uuid(),
                stamp,
            ),
        )


def apply_sync_change(
    connection: sqlite3.Connection,
    *,
    source_node_id: str,
    change: dict[str, Any],
) -> dict[str, Any]:
    entity_type = _normalize_entity_type(str(change["entity_type"]))
    entity_uuid = str(change["entity_uuid"])
    operation = str(change["operation"]).upper()
    payload = dict(change.get("payload") or {})
    payload["uuid"] = payload.get("uuid") or entity_uuid
    if operation == "DELETE":
        payload["is_deleted"] = 1
        payload["marked_for_deletion"] = 1
    if change.get("updated_at") and not payload.get("updated_at"):
        payload["updated_at"] = change["updated_at"]
    if change.get("created_at") and not payload.get("modified_at"):
        payload["modified_at"] = change["created_at"]

    existing = _get_entity_row(connection, ENTITY_TABLE_MAP[entity_type], entity_uuid)
    should_apply, conflict = _should_apply_remote(existing, payload)
    if not should_apply:
        assert conflict is not None
        conflict["entity_type"] = entity_type
        _store_conflict(
            connection,
            entity_type=entity_type,
            entity_uuid=entity_uuid,
            source_node_id=source_node_id,
            payload=payload,
            resolution=conflict["resolution"],
            local_updated_at=conflict["local_updated_at"],
            remote_updated_at=conflict["remote_updated_at"],
        )
        return {"status": "skipped", "conflict": conflict}

    if operation == "DELETE":
        deleted = DELETE_HANDLER_MAP[entity_type](connection, entity_uuid, _remote_timestamp(payload))
        if not deleted:
            return {"status": "skipped", "reason": "missing-local-entity"}
        _register_remote_apply(connection, entity_type, entity_uuid, "DELETE")
        return {"status": "applied"}

    UPSERT_HANDLER_MAP[entity_type](connection, payload)
    _register_remote_apply(connection, entity_type, entity_uuid, "UPDATE" if existing else "INSERT")
    return {"status": "applied"}


def _serialize_change_row(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any] | None:
    payload = serialize_entity(connection, str(row["entity_type"]), str(row["entity_uuid"]))
    if payload is None:
        return None
    return {
        "change_id": int(row["id"]),
        "entity_type": str(row["entity_type"]),
        "entity_uuid": str(row["entity_uuid"]),
        "operation": str(row["operation"]),
        "created_at": row["created_at"],
        "updated_at": payload.get("updated_at"),
        "payload": payload,
    }


def collect_outgoing_changes(
    connection: sqlite3.Connection,
    *,
    since_change_id: int,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    rows = connection.execute(
        """
        SELECT id, entity_type, entity_uuid, operation, created_at
        FROM sync_changes
        WHERE id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (since_change_id, limit),
    ).fetchall()
    changes: list[dict[str, Any]] = []
    last_sent_change_id = since_change_id
    for row in rows:
        serialized = _serialize_change_row(connection, row)
        last_sent_change_id = max(last_sent_change_id, int(row["id"]))
        if serialized is None:
            continue
        changes.append(serialized)
    changes.sort(key=lambda item: (ENTITY_PRIORITY.get(item["entity_type"], 999), item["change_id"] or 0))
    return changes, last_sent_change_id


def process_sync_exchange(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    schema_version = str(payload.get("schema_version") or "").strip()
    if schema_version != SYNC_SCHEMA_VERSION:
        raise HTTPException(
            status_code=409,
            detail=f"Sync schema mismatch: local={SYNC_SCHEMA_VERSION}, remote={schema_version or 'unknown'}",
        )

    remote_node = register_sync_node(
        connection,
        code=str(payload["node_code"]).strip(),
        name=str(payload["node_name"]).strip(),
        node_id=str(payload["node_id"]).strip() if payload.get("node_id") else None,
    )
    local_node = _node_to_dict(get_local_sync_node(connection))

    processed_count = 0
    skipped_count = 0
    error_count = 0
    conflicts: list[dict[str, Any]] = []
    errors: list[str] = []

    incoming_changes = [dict(item) for item in payload.get("changes", [])]
    incoming_changes.sort(key=lambda item: (ENTITY_PRIORITY.get(str(item.get("entity_type")), 999), int(item.get("change_id") or 0)))

    max_remote_change_id = int(remote_node.get("received_packet_no") or 0)
    for change in incoming_changes:
        max_remote_change_id = max(max_remote_change_id, int(change.get("change_id") or 0))
        try:
            result = apply_sync_change(connection, source_node_id=str(remote_node["id"]), change=change)
        except HTTPException as exc:
            error_count += 1
            errors.append(f"{change.get('entity_type')}:{change.get('entity_uuid')} -> {exc.detail}")
            continue
        if result["status"] == "applied":
            processed_count += 1
            continue
        skipped_count += 1
        if result.get("conflict"):
            conflicts.append(result["conflict"])

    now = utcnow_iso()
    connection.execute(
        """
        UPDATE sync_nodes
        SET last_sync_in = ?,
            received_packet_no = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, max_remote_change_id, now, remote_node["id"]),
    )

    outgoing_changes, last_sent_change_id = collect_outgoing_changes(
        connection,
        since_change_id=int(payload.get("last_received_change_id") or 0),
        limit=int(payload.get("batch_size") or 100),
    )
    connection.execute(
        """
        UPDATE sync_nodes
        SET last_sync_out = ?,
            sent_packet_no = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, last_sent_change_id, now, remote_node["id"]),
    )
    connection.commit()

    refreshed_remote = connection.execute("SELECT * FROM sync_nodes WHERE id = ?", (remote_node["id"],)).fetchone()
    refreshed_local = connection.execute("SELECT * FROM sync_nodes WHERE id = ?", (local_node["id"],)).fetchone()
    return {
        "schema_version": SYNC_SCHEMA_VERSION,
        "local_node": _node_to_dict(refreshed_local),
        "remote_node": _node_to_dict(refreshed_remote),
        "processed_count": processed_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "outgoing_count": len(outgoing_changes),
        "last_sent_change_id": last_sent_change_id,
        "changes": outgoing_changes,
        "conflicts": conflicts,
        "errors": errors,
    }


def get_sync_status(connection: sqlite3.Connection, *, node_id: str | None = None) -> dict[str, Any]:
    ensure_local_sync_node(connection)
    local_node = _node_to_dict(get_local_sync_node(connection))
    if node_id:
        rows = connection.execute("SELECT * FROM sync_nodes WHERE id = ?", (node_id,)).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM sync_nodes WHERE is_local = 0 ORDER BY updated_at DESC, code ASC"
        ).fetchall()
    pending_changes = int(connection.execute("SELECT COUNT(*) FROM sync_changes").fetchone()[0])
    return {
        "schema_version": SYNC_SCHEMA_VERSION,
        "local_node": local_node,
        "nodes": [_node_to_dict(row) for row in rows],
        "pending_changes": pending_changes,
    }


def prune_sync_changes(
    connection: sqlite3.Connection,
    *,
    safety_margin: int = 0,
) -> dict[str, Any]:
    """Delete local change-journal rows that every known peer has received.

    The safe threshold is ``MIN(sync_nodes.sent_packet_no)`` across all remote
    (non-local) nodes — that is the highest ``sync_changes.id`` acknowledged as
    received by the slowest peer. Anything at or below it is safe to delete.

    When no remote peers are registered, nothing is pruned: a peer might
    register later and need the full history.

    ``safety_margin`` keeps N extra rows above the threshold as a buffer.

    Returns ``{"pruned_count": int, "threshold": int}``.
    """
    row = connection.execute(
        "SELECT MIN(sent_packet_no) FROM sync_nodes WHERE is_local = 0"
    ).fetchone()
    min_acked = int(row[0]) if row and row[0] is not None else None

    if min_acked is None:
        return {"pruned_count": 0, "threshold": 0}

    threshold = max(0, min_acked - safety_margin)
    if threshold == 0:
        return {"pruned_count": 0, "threshold": 0}

    cursor = connection.execute(
        "DELETE FROM sync_changes WHERE id <= ?", (threshold,)
    )
    connection.commit()
    return {"pruned_count": cursor.rowcount, "threshold": threshold}


def list_conflicts(
    connection: sqlite3.Connection,
    *,
    include_resolved: bool = False,
) -> list[dict[str, Any]]:
    """List archived conflict rows from ``object_version_history``.

    By default only unresolved conflicts (``resolved_at IS NULL``) are returned.
    Each row includes the parsed remote payload for inspection.
    """
    clause = "" if include_resolved else "WHERE resolved_at IS NULL"
    rows = connection.execute(
        f"""
        SELECT id, entity_uuid, entity_type, source_node_id, arrival_time,
               serialized_data, conflict_resolution, resolved_at
        FROM object_version_history
        {clause}
        ORDER BY arrival_time DESC
        """
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row["serialized_data"]) if row["serialized_data"] else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        result.append(
            {
                "id": str(row["id"]),
                "entity_uuid": str(row["entity_uuid"]),
                "entity_type": str(row["entity_type"]),
                "source_node_id": str(row["source_node_id"]),
                "arrival_time": row["arrival_time"],
                "conflict_resolution": row["conflict_resolution"],
                "resolved_at": row["resolved_at"],
                "payload": data.get("payload") or {},
                "local_updated_at": data.get("local_updated_at"),
                "remote_updated_at": data.get("remote_updated_at"),
            }
        )
    return result


def resolve_conflict(connection: sqlite3.Connection, conflict_id: str) -> dict[str, Any]:
    """Force-apply the archived remote payload for a conflict, overwriting local.

    This bypasses the timestamp comparison that originally skipped the change —
    the human operator has decided the remote version should win.

    Returns ``{"status": "resolved", "entity_type": ..., "entity_uuid": ...}``.

    Raises HTTPException 404 if the conflict row doesn't exist, or 409 if it
    was already resolved.
    """
    row = connection.execute(
        "SELECT * FROM object_version_history WHERE id = ?", (conflict_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    if row["resolved_at"] is not None:
        raise HTTPException(status_code=409, detail="Conflict already resolved")

    try:
        data = json.loads(row["serialized_data"]) if row["serialized_data"] else {}
    except (json.JSONDecodeError, TypeError):
        data = {}
    payload = dict(data.get("payload") or {})

    entity_type = _normalize_entity_type(str(row["entity_type"]))
    entity_uuid = str(row["entity_uuid"])
    payload["uuid"] = payload.get("uuid") or entity_uuid

    # Force a fresh updated_at so the overwritten row propagates back out.
    payload["updated_at"] = utcnow_iso()

    # Use the upsert or delete handler directly, bypassing _should_apply_remote.
    remote_ts = data.get("remote_updated_at") or payload.get("updated_at") or utcnow_iso()
    if payload.get("is_deleted"):
        DELETE_HANDLER_MAP[entity_type](connection, entity_uuid, remote_ts)
    else:
        UPSERT_HANDLER_MAP[entity_type](connection, payload)

    # Mark resolved and re-queue for relay so peers see the resolution.
    connection.execute(
        "UPDATE object_version_history SET resolved_at = ?, conflict_resolution = ? WHERE id = ?",
        (utcnow_iso(), "remote-wins-manual", conflict_id),
    )
    _register_remote_apply(connection, entity_type, entity_uuid, "UPDATE")
    connection.commit()

    return {"status": "resolved", "entity_type": entity_type, "entity_uuid": entity_uuid}
