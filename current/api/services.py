from __future__ import annotations

import calendar
import io
import json
import re
import sqlite3
from copy import copy
from datetime import date, datetime
from math import ceil
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from api.config import settings
from api.database import last_insert_id, new_uuid, register_sync_change, row_to_dict, rows_to_dicts, utcnow_iso
from api.models.auth import UserInfo
from api.models.common import Pagination
from api.models.references import validate_reference_payload
from api.printing import build_excel_xml, build_pdf


REFERENCE_CONFIG = {
    "counterparties": {
        "table": "counterparties",
        "alias": "c",
        "label_field": "name",
        "search_fields": ("name", "inn", "contact_person"),
        "sortable": {"id", "name", "inn", "contact_person"},
        "joined_select": "",
        "joined_clause": "",
    },
    "objects": {
        "table": "objects",
        "alias": "o",
        "label_field": "name",
        "search_fields": ("name", "address"),
        "sortable": {"id", "name", "address"},
        "joined_select": ", c.name AS owner_name",
        "joined_clause": "LEFT JOIN counterparties c ON c.id = o.owner_id",
    },
    "works": {
        "table": "works",
        "alias": "w",
        "label_field": "name",
        "search_fields": ("name", "code"),
        "sortable": {"id", "name", "code", "price", "labor_rate", "specification_review_status"},
        "joined_select": "",
        "joined_clause": "",
    },
    "persons": {
        "table": "persons",
        "alias": "p",
        "label_field": "full_name",
        "search_fields": ("full_name", "personnel_number", "position"),
        "sortable": {"id", "full_name", "personnel_number", "position", "hourly_rate"},
        "joined_select": ", u.username AS username",
        "joined_clause": "LEFT JOIN users u ON u.id = p.user_id",
    },
    "organizations": {
        "table": "organizations",
        "alias": "org",
        "label_field": "name",
        "search_fields": ("name", "inn"),
        "sortable": {"id", "name", "inn"},
        "joined_select": ", p.full_name AS default_responsible_name",
        "joined_clause": "LEFT JOIN persons p ON p.id = org.default_responsible_id",
    },
    "contracts": {
        "table": "contracts",
        "alias": "ct",
        "label_field": "number",
        "search_fields": ("number", "description"),
        "sortable": {"id", "number", "date", "amount", "kind", "payment_deferral_days", "vat_rate", "organization_id"},
        "joined_select": ", cp.name AS counterparty_name, parent.number AS parent_number, org.name AS organization_name",
        "joined_clause": (
            "LEFT JOIN counterparties cp ON cp.id = ct.counterparty_id "
            "LEFT JOIN contracts parent ON parent.id = ct.parent_id "
            "LEFT JOIN organizations org ON org.id = ct.organization_id"
        ),
    },
    "materials": {
        "table": "materials",
        "alias": "m",
        "label_field": "name",
        "search_fields": ("name", "code"),
        "sortable": {"id", "name", "code", "price"},
        "joined_select": ", u.name AS unit_name",
        "joined_clause": "LEFT JOIN units u ON u.id = m.unit_id",
    },
}


def build_pagination(page: int, page_size: int, total: int) -> Pagination:
    pages = ceil(total / page_size) if total else 1
    return Pagination(page=page, page_size=page_size, total=total, pages=pages)


def _normalize_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 50)
    return page, page_size


def _coerce_bools(payload: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(payload.items()):
        if isinstance(value, bool):
            payload[key] = int(value)
    return payload


def _cast_flags(item: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        if key in item and item[key] is not None:
            item[key] = bool(item[key])
    return item


def _now_iso() -> str:
    return utcnow_iso()


def _sync_stamp_for_create(payload: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    stamped = dict(payload)
    stamped.setdefault("created_at", now)
    stamped.setdefault("modified_at", now)
    stamped["uuid"] = stamped.get("uuid") or new_uuid()
    stamped["updated_at"] = now
    stamped["is_deleted"] = 0
    return stamped


def _sync_stamp_for_update(payload: dict[str, Any], *, current_uuid: str) -> dict[str, Any]:
    now = _now_iso()
    stamped = dict(payload)
    stamped["uuid"] = current_uuid
    stamped["modified_at"] = now
    stamped["updated_at"] = now
    stamped["is_deleted"] = int(bool(stamped.get("is_deleted", 0)))
    return stamped


def list_references(
    connection: sqlite3.Connection,
    *,
    kind: str,
    page: int,
    page_size: int,
    search: str | None,
    sort_by: str | None,
    sort_order: str,
    review_status: str | None = None,
) -> tuple[list[dict[str, Any]], Pagination]:
    if kind not in REFERENCE_CONFIG:
        raise HTTPException(status_code=404, detail="Unknown reference")

    config = REFERENCE_CONFIG[kind]
    page, page_size = _normalize_page(page, page_size)
    sort_column = sort_by if sort_by in config["sortable"] else "id"
    order = "DESC" if sort_order.lower() == "desc" else "ASC"
    offset = (page - 1) * page_size
    alias = config["alias"]
    label_field = config["label_field"]

    where_parts = [f"{alias}.marked_for_deletion = 0"]
    params: list[Any] = []
    if search:
        search_value = f"%{search.strip()}%"
        clauses = [f"COALESCE({alias}.{field}, '') LIKE ?" for field in config.get("search_fields", (label_field,))]
        where_parts.append(f"({' OR '.join(clauses)})")
        params.extend([search_value] * len(clauses))
    if kind == "works" and review_status and review_status != "all":
        where_parts.append(f"COALESCE({alias}.specification_review_status, 'ok') = ?")
        params.append(review_status)

    where_sql = " AND ".join(where_parts)
    total = connection.execute(
        f"SELECT COUNT(*) FROM {config['table']} {alias} {config['joined_clause']} WHERE {where_sql}",
        params,
    ).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT
            {alias}.*,
            {alias}.{label_field} AS display_name
            {config['joined_select']}
        FROM {config['table']} {alias}
        {config['joined_clause']}
        WHERE {where_sql}
        ORDER BY {alias}.{sort_column} {order}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()
    items = [_cast_flags(item, "marked_for_deletion", "is_group") for item in rows_to_dicts(rows)]
    return items, build_pagination(page, page_size, total)


def get_reference(connection: sqlite3.Connection, *, kind: str, item_id: int) -> dict[str, Any]:
    if kind not in REFERENCE_CONFIG:
        raise HTTPException(status_code=404, detail="Unknown reference")
    config = REFERENCE_CONFIG[kind]
    alias = config["alias"]
    row = connection.execute(
        f"""
        SELECT
            {alias}.*,
            {alias}.{config['label_field']} AS display_name
            {config['joined_select']}
        FROM {config['table']} {alias}
        {config['joined_clause']}
        WHERE {alias}.id = ? AND {alias}.marked_for_deletion = 0
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Reference item not found")
    return _cast_flags(row_to_dict(row) or {}, "marked_for_deletion", "is_group")


def get_reference_by_uuid(connection: sqlite3.Connection, *, kind: str, item_uuid: str) -> dict[str, Any]:
    if kind not in REFERENCE_CONFIG:
        raise HTTPException(status_code=404, detail="Unknown reference")
    config = REFERENCE_CONFIG[kind]
    alias = config["alias"]
    row = connection.execute(
        f"""
        SELECT
            {alias}.*,
            {alias}.{config['label_field']} AS display_name
            {config['joined_select']}
        FROM {config['table']} {alias}
        {config['joined_clause']}
        WHERE {alias}.uuid = ? AND COALESCE({alias}.is_deleted, 0) = 0
        """,
        (item_uuid,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Reference item not found")
    return _cast_flags(row_to_dict(row) or {}, "marked_for_deletion", "is_group")


def create_reference(connection: sqlite3.Connection, *, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    validated = _sync_stamp_for_create(_coerce_bools(validate_reference_payload(kind, payload)))
    columns = ", ".join(validated.keys())
    placeholders = ", ".join(["?"] * len(validated))
    connection.execute(
        f"INSERT INTO {REFERENCE_CONFIG[kind]['table']} ({columns}) VALUES ({placeholders})",
        list(validated.values()),
    )
    item_id = last_insert_id(connection)
    register_sync_change(connection, entity_type=kind, entity_uuid=str(validated["uuid"]), operation="INSERT")
    connection.commit()
    return get_reference(connection, kind=kind, item_id=item_id)


def update_reference(
    connection: sqlite3.Connection,
    *,
    kind: str,
    item_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    existing = get_reference(connection, kind=kind, item_id=item_id)
    validated = _sync_stamp_for_update(
        _coerce_bools(validate_reference_payload(kind, payload)),
        current_uuid=str(existing["uuid"]),
    )
    assignments = ", ".join([f"{column} = ?" for column in validated.keys()])
    cursor = connection.execute(
        f"UPDATE {REFERENCE_CONFIG[kind]['table']} SET {assignments} WHERE id = ?",
        [*validated.values(), item_id],
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Reference item not found")
    register_sync_change(connection, entity_type=kind, entity_uuid=str(existing["uuid"]), operation="UPDATE")
    connection.commit()
    return get_reference(connection, kind=kind, item_id=item_id)


def soft_delete_reference(connection: sqlite3.Connection, *, kind: str, item_id: int) -> None:
    existing = get_reference(connection, kind=kind, item_id=item_id)
    cursor = connection.execute(
        f"""
        UPDATE {REFERENCE_CONFIG[kind]['table']}
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (_now_iso(), _now_iso(), item_id),
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Reference item not found")
    register_sync_change(connection, entity_type=kind, entity_uuid=str(existing["uuid"]), operation="DELETE")
    connection.commit()


def _hydrate_estimate_line(connection: sqlite3.Connection, line: dict[str, Any]) -> dict[str, Any]:
    if line.get("work_id") and not line.get("is_group"):
        work = connection.execute(
            "SELECT code, unit, price, labor_rate FROM works WHERE id = ?",
            (line["work_id"],),
        ).fetchone()
        if work:
            line["work_code"] = line.get("work_code") or work["code"]
            line["unit"] = line.get("unit") or work["unit"]
            if float(line.get("price", 0) or 0) == 0:
                line["price"] = float(work["price"] or 0)
            if float(line.get("labor_rate", 0) or 0) == 0:
                line["labor_rate"] = float(work["labor_rate"] or 0)
    if line.get("is_group"):
        line["sum"] = 0
        line["planned_labor"] = 0
    else:
        line["sum"] = round(float(line["quantity"]) * float(line["price"]), 2)
        line["planned_labor"] = round(float(line["quantity"]) * float(line["labor_rate"]), 2)
    return line


def _estimate_totals(lines: list[dict[str, Any]]) -> tuple[float, float]:
    total_sum = round(sum(line["sum"] for line in lines if not line["is_group"]), 2)
    total_labor = round(sum(line["planned_labor"] for line in lines if not line["is_group"]), 2)
    return total_sum, total_labor


def list_estimates(
    connection: sqlite3.Connection,
    *,
    page: int,
    page_size: int,
    search: str | None,
    sort_by: str | None,
    sort_order: str,
    object_id: int | None = None,
) -> tuple[list[dict[str, Any]], Pagination]:
    page, page_size = _normalize_page(page, page_size)
    sort_column = sort_by if sort_by in {"id", "number", "date", "total_sum"} else "date"
    order = "DESC" if sort_order.lower() == "desc" else "ASC"
    params: list[Any] = []
    where_parts = ["e.marked_for_deletion = 0"]
    if search:
        where_parts.append("(e.number LIKE ? OR cp.name LIKE ? OR o.name LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    if object_id:
        where_parts.append("e.object_id = ?")
        params.append(object_id)
    where_sql = " AND ".join(where_parts)
    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM estimates e
        LEFT JOIN counterparties cp ON cp.id = e.customer_id
        LEFT JOIN objects o ON o.id = e.object_id
        WHERE {where_sql}
        """,
        params,
    ).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT
            e.*,
            cp.uuid AS customer_uuid,
            cp.name AS customer_name,
            o.uuid AS object_uuid,
            o.name AS object_name,
            org.uuid AS contractor_uuid,
            org.name AS contractor_name,
            p.uuid AS responsible_uuid,
            p.full_name AS responsible_name,
            ct.uuid AS contract_uuid,
            ct.number AS contract_number
        FROM estimates e
        LEFT JOIN counterparties cp ON cp.id = e.customer_id
        LEFT JOIN objects o ON o.id = e.object_id
        LEFT JOIN organizations org ON org.id = e.contractor_id
        LEFT JOIN persons p ON p.id = e.responsible_id
        LEFT JOIN contracts ct ON ct.id = e.contract_id
        WHERE {where_sql}
        ORDER BY e.{sort_column} {order}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    items = [_cast_flags(item, "is_posted", "marked_for_deletion") for item in rows_to_dicts(rows)]
    return items, build_pagination(page, page_size, total)


def get_estimate(connection: sqlite3.Connection, estimate_id: int) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            e.*,
            cp.uuid AS customer_uuid,
            cp.name AS customer_name,
            o.uuid AS object_uuid,
            o.name AS object_name,
            org.uuid AS contractor_uuid,
            org.name AS contractor_name,
            p.uuid AS responsible_uuid,
            p.full_name AS responsible_name,
            ct.uuid AS contract_uuid,
            ct.number AS contract_number
        FROM estimates e
        LEFT JOIN counterparties cp ON cp.id = e.customer_id
        LEFT JOIN objects o ON o.id = e.object_id
        LEFT JOIN organizations org ON org.id = e.contractor_id
        LEFT JOIN persons p ON p.id = e.responsible_id
        LEFT JOIN contracts ct ON ct.id = e.contract_id
        WHERE e.id = ? AND e.marked_for_deletion = 0
        """,
        (estimate_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    estimate = _cast_flags(row_to_dict(row) or {}, "is_posted", "marked_for_deletion")
    line_rows = connection.execute(
        """
        SELECT el.*, e.uuid AS estimate_uuid, w.uuid AS work_uuid, w.name AS work_name, w.code AS work_code
        FROM estimate_lines el
        JOIN estimates e ON e.id = el.estimate_id
        LEFT JOIN works w ON w.id = el.work_id
        WHERE el.estimate_id = ?
          AND COALESCE(el.marked_for_deletion, 0) = 0
          AND COALESCE(el.is_deleted, 0) = 0
        ORDER BY el.line_number
        """,
        (estimate_id,),
    ).fetchall()
    line_items = [_cast_flags(item, "is_group", "is_collapsed") for item in rows_to_dicts(line_rows)]
    line_uuid_map = {int(item["id"]): str(item["uuid"]) for item in line_items if item.get("uuid")}
    for item in line_items:
        parent_group_id = item.get("parent_group_id")
        item["parent_group_uuid"] = line_uuid_map.get(int(parent_group_id)) if parent_group_id is not None else None
    estimate["lines"] = line_items
    return estimate


def get_estimate_by_uuid(connection: sqlite3.Connection, estimate_uuid: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT id FROM estimates WHERE uuid = ? AND COALESCE(is_deleted, 0) = 0",
        (estimate_uuid,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return get_estimate(connection, int(row["id"]))


def _sync_estimate_lines(
    connection: sqlite3.Connection,
    *,
    estimate_id: int,
    lines: list[dict[str, Any]],
) -> None:
    existing_rows = connection.execute(
        """
        SELECT id, uuid
        FROM estimate_lines
        WHERE estimate_id = ?
          AND COALESCE(marked_for_deletion, 0) = 0
          AND COALESCE(is_deleted, 0) = 0
        """,
        (estimate_id,),
    ).fetchall()
    existing_map = {int(row["id"]): str(row["uuid"]) for row in existing_rows}
    existing_uuid_map = {str(row["uuid"]): int(row["id"]) for row in existing_rows}
    incoming_ids: set[int] = set()
    line_uuid_map = dict(existing_uuid_map)
    parent_links: list[tuple[int, int | None, str | None]] = []

    for raw_line in lines:
        line = dict(raw_line)
        line_uuid = str(line.get("uuid") or "").strip() or None
        line_id = int(line["id"]) if line.get("id") is not None else None
        if line_uuid and line_uuid in existing_uuid_map:
            line_id = existing_uuid_map[line_uuid]
        now = _now_iso()
        created_at = str(line.get("created_at") or now)
        modified_at = str(line.get("modified_at") or line.get("updated_at") or now)
        updated_at = str(line.get("updated_at") or modified_at or now)
        explicit_parent_id = int(line["parent_group_id"]) if line.get("parent_group_id") is not None else None
        parent_group_uuid = str(line.get("parent_group_uuid") or "").strip() or None
        if line_id is not None and line_id in existing_map:
            incoming_ids.add(line_id)
            resolved_uuid = line_uuid or existing_map[line_id]
            update_payload = {
                "line_number": line["line_number"],
                "work_id": line["work_id"],
                "quantity": line["quantity"],
                "unit": line.get("unit"),
                "price": line["price"],
                "labor_rate": line["labor_rate"],
                "sum": line["sum"],
                "planned_labor": line["planned_labor"],
                "is_group": int(bool(line.get("is_group"))),
                "group_name": line.get("group_name"),
                "parent_group_id": explicit_parent_id if parent_group_uuid is None else None,
                "is_collapsed": int(bool(line.get("is_collapsed"))),
                "modified_at": modified_at,
                "updated_at": updated_at,
                "uuid": resolved_uuid,
                "marked_for_deletion": 0,
                "is_deleted": 0,
            }
            assignments = ", ".join(f"{column} = ?" for column in update_payload)
            connection.execute(
                f"""
                UPDATE estimate_lines
                SET {assignments}
                WHERE id = ? AND estimate_id = ?
                """,
                [*update_payload.values(), line_id, estimate_id],
            )
            line_uuid_map[resolved_uuid] = line_id
            parent_links.append((line_id, explicit_parent_id, parent_group_uuid))
            continue

        insert_payload = {
            "estimate_id": estimate_id,
            "line_number": line["line_number"],
            "work_id": line["work_id"],
            "quantity": line["quantity"],
            "unit": line.get("unit"),
            "price": line["price"],
            "labor_rate": line["labor_rate"],
            "sum": line["sum"],
            "planned_labor": line["planned_labor"],
            "is_group": int(bool(line.get("is_group"))),
            "group_name": line.get("group_name"),
            "parent_group_id": explicit_parent_id if parent_group_uuid is None else None,
            "is_collapsed": int(bool(line.get("is_collapsed"))),
            "created_at": created_at,
            "modified_at": modified_at,
            "uuid": line_uuid or new_uuid(),
            "updated_at": updated_at,
            "marked_for_deletion": 0,
            "is_deleted": 0,
        }
        columns = ", ".join(insert_payload.keys())
        placeholders = ", ".join(["?"] * len(insert_payload))
        connection.execute(
            f"INSERT INTO estimate_lines ({columns}) VALUES ({placeholders})",
            list(insert_payload.values()),
        )
        new_line_id = last_insert_id(connection)
        incoming_ids.add(new_line_id)
        line_uuid_map[str(insert_payload["uuid"])] = new_line_id
        parent_links.append((new_line_id, explicit_parent_id, parent_group_uuid))

    for line_id, explicit_parent_id, parent_group_uuid in parent_links:
        resolved_parent_id = explicit_parent_id
        if parent_group_uuid is not None:
            resolved_parent_id = line_uuid_map.get(parent_group_uuid)
        connection.execute(
            """
            UPDATE estimate_lines
            SET parent_group_id = ?
            WHERE id = ? AND estimate_id = ?
            """,
            (resolved_parent_id, line_id, estimate_id),
        )

    for existing_id in existing_map:
        if existing_id in incoming_ids:
            continue
        now = _now_iso()
        connection.execute(
            """
            UPDATE estimate_lines
            SET marked_for_deletion = 1,
                is_deleted = 1,
                modified_at = ?,
                updated_at = ?
            WHERE id = ? AND estimate_id = ?
            """,
            (now, now, existing_id, estimate_id),
        )


_ESTIMATE_FK_FIELDS: dict[str, str] = {
    "customer_id": "counterparties",
    "object_id": "objects",
    "contractor_id": "organizations",
    "responsible_id": "persons",
    "contract_id": "contracts",
}


def _validate_estimate_fk(connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
    """Проверяет, что все FK-ссылки шапки сметы указывают на существующие записи."""
    for field, table in _ESTIMATE_FK_FIELDS.items():
        value = payload.get(field)
        if value is None:
            continue
        row = connection.execute(f"SELECT 1 FROM {table} WHERE id = ?", (value,)).fetchone()
        if not row:
            label = {
                "customer_id": "Заказчик",
                "object_id": "Объект",
                "contractor_id": "Подрядчик",
                "responsible_id": "Ответственный",
                "contract_id": "Договор",
            }[field]
            raise HTTPException(status_code=400, detail=f"{label} (id={value}) не найден в справочнике")


def save_estimate(connection: sqlite3.Connection, *, payload: dict[str, Any], estimate_id: int | None = None) -> dict[str, Any]:
    lines = [_hydrate_estimate_line(connection, dict(line)) for line in payload.pop("lines", [])]
    total_sum, total_labor = _estimate_totals(lines)
    payload["total_sum"] = total_sum
    payload["total_labor"] = total_labor
    payload["date"] = str(payload["date"])
    if not payload.get("number"):
        payload["number"] = _next_estimate_number(connection, datetime.fromisoformat(payload["date"]).date())

    _validate_estimate_fk(connection, payload)

    if estimate_id is None:
        sync_operation = "INSERT"
        insert_payload = _sync_stamp_for_create(payload)
        columns = ", ".join(insert_payload.keys())
        placeholders = ", ".join(["?"] * len(insert_payload))
        connection.execute(
            f"INSERT INTO estimates ({columns}) VALUES ({placeholders})",
            list(insert_payload.values()),
        )
        estimate_id = last_insert_id(connection)
        estimate_uuid = str(insert_payload["uuid"])
    else:
        sync_operation = "UPDATE"
        existing = get_estimate(connection, estimate_id)
        if existing["is_posted"]:
            raise HTTPException(status_code=400, detail="Posted estimate cannot be modified")
        estimate_uuid = str(existing["uuid"])
        update_payload = _sync_stamp_for_update(payload, current_uuid=estimate_uuid)
        assignments = ", ".join([f"{column} = ?" for column in update_payload.keys()])
        connection.execute(
            f"UPDATE estimates SET {assignments} WHERE id = ?",
            [*update_payload.values(), estimate_id],
        )

    _sync_estimate_lines(connection, estimate_id=estimate_id, lines=lines)
    register_sync_change(
        connection,
        entity_type="estimates",
        entity_uuid=estimate_uuid,
        operation=sync_operation,
    )
    connection.commit()
    return get_estimate(connection, estimate_id)


def delete_estimate(connection: sqlite3.Connection, estimate_id: int) -> None:
    estimate = get_estimate(connection, estimate_id)
    if estimate["is_posted"]:
        raise HTTPException(status_code=400, detail="Posted estimate cannot be deleted")
    now = _now_iso()
    connection.execute(
        """
        UPDATE estimates
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, estimate_id),
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
        (now, now, estimate_id),
    )
    register_sync_change(connection, entity_type="estimates", entity_uuid=str(estimate["uuid"]), operation="DELETE")
    connection.commit()


def restore_estimate(connection: sqlite3.Connection, estimate_id: int) -> None:
    estimate = get_estimate(connection, estimate_id)
    now = _now_iso()
    connection.execute(
        """
        UPDATE estimates
        SET marked_for_deletion = 0,
            is_deleted = 0,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, estimate_id),
    )
    connection.execute(
        """
        UPDATE estimate_lines
        SET marked_for_deletion = 0,
            is_deleted = 0,
            modified_at = ?,
            updated_at = ?
        WHERE estimate_id = ?
        """,
        (now, now, estimate_id),
    )
    register_sync_change(connection, entity_type="estimates", entity_uuid=str(estimate["uuid"]), operation="RESTORE")
    connection.commit()


def _require_admin(user: UserInfo) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can post documents")


def post_estimate(connection: sqlite3.Connection, *, estimate_id: int, user: UserInfo) -> None:
    _require_admin(user)
    estimate = get_estimate(connection, estimate_id)
    if estimate["is_posted"]:
        raise HTTPException(status_code=400, detail="Estimate is already posted")
    connection.execute(
        "DELETE FROM work_execution_register WHERE recorder_type = 'estimate' AND recorder_id = ?",
        (estimate_id,),
    )
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
                _now_iso(),
                _now_iso(),
                new_uuid(),
                _now_iso(),
            ),
        )
    _post_estimate_to_planned_costs(connection, estimate)
    connection.execute(
        "UPDATE estimates SET is_posted = 1, posted_at = ?, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), _now_iso(), estimate_id),
    )
    register_sync_change(connection, entity_type="estimates", entity_uuid=str(estimate["uuid"]), operation="UPDATE")
    connection.commit()


def unpost_estimate(connection: sqlite3.Connection, *, estimate_id: int, user: UserInfo) -> None:
    _require_admin(user)
    estimate = get_estimate(connection, estimate_id)
    if not estimate["is_posted"]:
        raise HTTPException(status_code=400, detail="Estimate is not posted")
    _unpost_estimate_from_planned_costs(connection, estimate_id)
    connection.execute(
        "DELETE FROM work_execution_register WHERE recorder_type = 'estimate' AND recorder_id = ?",
        (estimate_id,),
    )
    connection.execute(
        "UPDATE estimates SET is_posted = 0, posted_at = NULL, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), estimate_id),
    )
    register_sync_change(connection, entity_type="estimates", entity_uuid=str(estimate["uuid"]), operation="UPDATE")
    connection.commit()


def _daily_report_lines_from_estimate(connection: sqlite3.Connection, estimate_id: int) -> list[dict[str, Any]]:
    estimate = get_estimate(connection, estimate_id)
    lines: list[dict[str, Any]] = []
    for line in estimate["lines"]:
        is_group = bool(line["is_group"])
        lines.append(
            {
                "line_number": line["line_number"],
                "work_id": line["work_id"],
                "planned_labor": line["planned_labor"],
                "actual_labor": 0.0,
                "deviation_percent": -100.0 if not is_group and line["planned_labor"] else 0.0,
                "quantity": 0.0 if is_group else float(line.get("quantity") or 0),
                "unit": line.get("unit"),
                "price": 0.0 if is_group else float(line.get("price") or 0),
                "actual_sum": 0.0 if is_group else float(line.get("sum") or 0),
                "executor_ids": [],
                "is_group": is_group,
                "group_name": line["group_name"],
                "parent_group_id": line["parent_group_id"],
                "is_collapsed": bool(line["is_collapsed"]),
            }
        )
    return lines


def _hydrate_daily_report_line(line: dict[str, Any]) -> dict[str, Any]:
    planned = float(line["planned_labor"])
    actual = float(line["actual_labor"])
    if line.get("is_group"):
        line["deviation_percent"] = 0.0
    elif planned == 0:
        line["deviation_percent"] = 0.0 if actual == 0 else 100.0
    else:
        line["deviation_percent"] = round(((actual - planned) / planned) * 100, 2)
    if not line.get("is_group"):
        quantity = float(line.get("quantity") or 0)
        price = float(line.get("price") or 0)
        line["actual_sum"] = round(quantity * price, 2)
    else:
        line["actual_sum"] = 0.0
    return line


def list_daily_reports(
    connection: sqlite3.Connection,
    *,
    user: UserInfo,
    page: int,
    page_size: int,
    search: str | None,
    sort_by: str | None,
    sort_order: str,
) -> tuple[list[dict[str, Any]], Pagination]:
    page, page_size = _normalize_page(page, page_size)
    sort_column = sort_by if sort_by in {"id", "number", "date"} else "date"
    order = "DESC" if sort_order.lower() == "desc" else "ASC"
    params: list[Any] = []
    where_parts = ["dr.marked_for_deletion = 0"]
    if search:
        where_parts.append("(dr.number LIKE ? OR e.number LIKE ?)")
        params.extend([f"%{search}%"] * 2)
    if user.role == "foreman" and user.person_id:
        where_parts.append("dr.foreman_id = ?")
        params.append(user.person_id)
    where_sql = " AND ".join(where_parts)
    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM daily_reports dr
        LEFT JOIN estimates e ON e.id = dr.estimate_id
        WHERE {where_sql}
        """,
        params,
    ).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT
            dr.*,
            e.uuid AS estimate_uuid,
            e.number AS estimate_number,
            p.uuid AS foreman_uuid,
            p.full_name AS foreman_name,
            sa.uuid AS supplementary_agreement_uuid,
            sa.number AS supplementary_agreement_number
        FROM daily_reports dr
        LEFT JOIN estimates e ON e.id = dr.estimate_id
        LEFT JOIN persons p ON p.id = dr.foreman_id
        LEFT JOIN contracts sa ON sa.id = dr.supplementary_agreement_id
        WHERE {where_sql}
        ORDER BY dr.{sort_column} {order}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    items = [_cast_flags(item, "is_posted", "marked_for_deletion") for item in rows_to_dicts(rows)]
    return items, build_pagination(page, page_size, total)


def get_daily_report(connection: sqlite3.Connection, report_id: int, user: UserInfo | None = None) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            dr.*,
            e.uuid AS estimate_uuid,
            e.number AS estimate_number,
            p.uuid AS foreman_uuid,
            p.full_name AS foreman_name,
            sa.uuid AS supplementary_agreement_uuid,
            sa.number AS supplementary_agreement_number
        FROM daily_reports dr
        LEFT JOIN estimates e ON e.id = dr.estimate_id
        LEFT JOIN persons p ON p.id = dr.foreman_id
        LEFT JOIN contracts sa ON sa.id = dr.supplementary_agreement_id
        WHERE dr.id = ? AND dr.marked_for_deletion = 0
        """,
        (report_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Daily report not found")
    report = _cast_flags(row_to_dict(row) or {}, "is_posted", "marked_for_deletion")
    if user and user.role == "foreman" and user.person_id and report["foreman_id"] != user.person_id:
        raise HTTPException(status_code=403, detail="Access denied")

    line_rows = connection.execute(
        """
        SELECT drl.*, dr.uuid AS report_uuid, w.uuid AS work_uuid, w.name AS work_name
        FROM daily_report_lines drl
        JOIN daily_reports dr ON dr.id = drl.report_id
        LEFT JOIN works w ON w.id = drl.work_id
        WHERE drl.report_id = ?
          AND COALESCE(drl.marked_for_deletion, 0) = 0
          AND COALESCE(drl.is_deleted, 0) = 0
        ORDER BY drl.line_number
        """,
        (report_id,),
        ).fetchall()
    lines = [_cast_flags(item, "is_group", "is_collapsed") for item in rows_to_dicts(line_rows)]
    line_uuid_map = {int(item["id"]): str(item["uuid"]) for item in lines if item.get("uuid")}
    for line in lines:
        parent_group_id = line.get("parent_group_id")
        line["parent_group_uuid"] = line_uuid_map.get(int(parent_group_id)) if parent_group_id is not None else None
        executor_rows = connection.execute(
            """
            SELECT dre.executor_id, p.uuid AS executor_uuid, p.full_name
            FROM daily_report_executors dre
            JOIN persons p ON p.id = dre.executor_id
            WHERE dre.report_line_id = ?
            ORDER BY p.full_name
            """,
            (line["id"],),
        ).fetchall()
        line["executor_ids"] = [row["executor_id"] for row in executor_rows]
        line["executor_uuids"] = [row["executor_uuid"] for row in executor_rows]
        line["executor_names"] = [row["full_name"] for row in executor_rows]
    report["lines"] = lines
    return report


def get_daily_report_by_uuid(connection: sqlite3.Connection, report_uuid: str, user: UserInfo | None = None) -> dict[str, Any]:
    row = connection.execute(
        "SELECT id FROM daily_reports WHERE uuid = ? AND COALESCE(is_deleted, 0) = 0",
        (report_uuid,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Daily report not found")
    return get_daily_report(connection, int(row["id"]), user)


def _sync_daily_report_lines(
    connection: sqlite3.Connection,
    *,
    report_id: int,
    lines: list[dict[str, Any]],
) -> None:
    existing_rows = connection.execute(
        """
        SELECT id, uuid
        FROM daily_report_lines
        WHERE report_id = ?
          AND COALESCE(marked_for_deletion, 0) = 0
          AND COALESCE(is_deleted, 0) = 0
        """,
        (report_id,),
    ).fetchall()
    existing_map = {int(row["id"]): str(row["uuid"]) for row in existing_rows}
    existing_uuid_map = {str(row["uuid"]): int(row["id"]) for row in existing_rows}
    incoming_ids: set[int] = set()
    line_uuid_map = dict(existing_uuid_map)
    parent_links: list[tuple[int, int | None, str | None]] = []

    for raw_line in lines:
        line = dict(raw_line)
        executor_ids = [int(item) for item in line.pop("executor_ids", [])]
        line_uuid = str(line.get("uuid") or "").strip() or None
        line_id = int(line["id"]) if line.get("id") is not None else None
        if line_uuid and line_uuid in existing_uuid_map:
            line_id = existing_uuid_map[line_uuid]
        now = _now_iso()
        created_at = str(line.get("created_at") or now)
        modified_at = str(line.get("modified_at") or line.get("updated_at") or now)
        updated_at = str(line.get("updated_at") or modified_at or now)
        explicit_parent_id = int(line["parent_group_id"]) if line.get("parent_group_id") is not None else None
        parent_group_uuid = str(line.get("parent_group_uuid") or "").strip() or None
        if line_id is not None and line_id in existing_map:
            incoming_ids.add(line_id)
            resolved_uuid = line_uuid or existing_map[line_id]
            update_payload = {
                "line_number": line["line_number"],
                "work_id": line["work_id"],
                "planned_labor": line["planned_labor"],
                "actual_labor": line["actual_labor"],
                "deviation_percent": line["deviation_percent"],
                "quantity": line.get("quantity", 0),
                "unit": line.get("unit"),
                "price": line.get("price", 0),
                "actual_sum": line.get("actual_sum", 0),
                "is_group": int(bool(line.get("is_group"))),
                "group_name": line.get("group_name"),
                "parent_group_id": explicit_parent_id if parent_group_uuid is None else None,
                "is_collapsed": int(bool(line.get("is_collapsed"))),
                "modified_at": modified_at,
                "updated_at": updated_at,
                "uuid": resolved_uuid,
                "marked_for_deletion": 0,
                "is_deleted": 0,
            }
            assignments = ", ".join(f"{column} = ?" for column in update_payload)
            connection.execute(
                f"""
                UPDATE daily_report_lines
                SET {assignments}
                WHERE id = ? AND report_id = ?
                """,
                [*update_payload.values(), line_id, report_id],
            )
            connection.execute("DELETE FROM daily_report_executors WHERE report_line_id = ?", (line_id,))
            for executor_id in executor_ids:
                connection.execute(
                    "INSERT OR IGNORE INTO daily_report_executors (report_line_id, executor_id) VALUES (?, ?)",
                    (line_id, executor_id),
                )
            line_uuid_map[resolved_uuid] = line_id
            parent_links.append((line_id, explicit_parent_id, parent_group_uuid))
            continue

        insert_payload = {
            "report_id": report_id,
            "line_number": line["line_number"],
            "work_id": line["work_id"],
            "planned_labor": line["planned_labor"],
            "actual_labor": line["actual_labor"],
            "deviation_percent": line["deviation_percent"],
            "quantity": line.get("quantity", 0),
            "unit": line.get("unit"),
            "price": line.get("price", 0),
            "actual_sum": line.get("actual_sum", 0),
            "is_group": int(bool(line.get("is_group"))),
            "group_name": line.get("group_name"),
            "parent_group_id": explicit_parent_id if parent_group_uuid is None else None,
            "is_collapsed": int(bool(line.get("is_collapsed"))),
            "created_at": created_at,
            "modified_at": modified_at,
            "uuid": line_uuid or new_uuid(),
            "updated_at": updated_at,
            "marked_for_deletion": 0,
            "is_deleted": 0,
        }
        columns = ", ".join(insert_payload.keys())
        placeholders = ", ".join(["?"] * len(insert_payload))
        connection.execute(
            f"INSERT INTO daily_report_lines ({columns}) VALUES ({placeholders})",
            list(insert_payload.values()),
        )
        new_line_id = last_insert_id(connection)
        incoming_ids.add(new_line_id)
        for executor_id in executor_ids:
            connection.execute(
                "INSERT OR IGNORE INTO daily_report_executors (report_line_id, executor_id) VALUES (?, ?)",
                (new_line_id, executor_id),
            )
        line_uuid_map[str(insert_payload["uuid"])] = new_line_id
        parent_links.append((new_line_id, explicit_parent_id, parent_group_uuid))

    for line_id, explicit_parent_id, parent_group_uuid in parent_links:
        resolved_parent_id = explicit_parent_id
        if parent_group_uuid is not None:
            resolved_parent_id = line_uuid_map.get(parent_group_uuid)
        connection.execute(
            """
            UPDATE daily_report_lines
            SET parent_group_id = ?
            WHERE id = ? AND report_id = ?
            """,
            (resolved_parent_id, line_id, report_id),
        )

    for existing_id in existing_map:
        if existing_id in incoming_ids:
            continue
        now = _now_iso()
        connection.execute("DELETE FROM daily_report_executors WHERE report_line_id = ?", (existing_id,))
        connection.execute(
            """
            UPDATE daily_report_lines
            SET marked_for_deletion = 1,
                is_deleted = 1,
                modified_at = ?,
                updated_at = ?
            WHERE id = ? AND report_id = ?
            """,
            (now, now, existing_id, report_id),
        )


def _next_estimate_number(connection: sqlite3.Connection, estimate_date: date) -> str:
    prefix = estimate_date.strftime("СМ-%Y%m%d")
    count = connection.execute(
        "SELECT COUNT(*) FROM estimates WHERE number LIKE ?",
        (f"{prefix}%",),
    ).fetchone()[0]
    return f"{prefix}-{count + 1:02d}"


def _next_daily_report_number(connection: sqlite3.Connection, report_date: date) -> str:
    prefix = report_date.strftime("ЕР-%Y%m%d")
    count = connection.execute(
        "SELECT COUNT(*) FROM daily_reports WHERE number LIKE ?",
        (f"{prefix}%",),
    ).fetchone()[0]
    return f"{prefix}-{count + 1:02d}"


def save_daily_report(
    connection: sqlite3.Connection,
    *,
    payload: dict[str, Any],
    user: UserInfo,
    report_id: int | None = None,
) -> dict[str, Any]:
    lines = payload.pop("lines", [])
    if not lines and payload.get("estimate_id"):
        lines = _daily_report_lines_from_estimate(connection, payload["estimate_id"])
    hydrated_lines = [_hydrate_daily_report_line(dict(line)) for line in lines]

    if user.role == "foreman" and user.person_id:
        payload["foreman_id"] = user.person_id
    payload["date"] = str(payload["date"])
    if not payload.get("number"):
        payload["number"] = _next_daily_report_number(connection, datetime.fromisoformat(payload["date"]).date())

    if report_id is None:
        sync_operation = "INSERT"
        insert_payload = _sync_stamp_for_create(payload)
        columns = ", ".join(insert_payload.keys())
        placeholders = ", ".join(["?"] * len(insert_payload))
        connection.execute(
            f"INSERT INTO daily_reports ({columns}) VALUES ({placeholders})",
            list(insert_payload.values()),
        )
        report_id = last_insert_id(connection)
        report_uuid = str(insert_payload["uuid"])
    else:
        sync_operation = "UPDATE"
        existing = get_daily_report(connection, report_id, user)
        if existing["is_posted"]:
            raise HTTPException(status_code=400, detail="Posted daily report cannot be modified")
        report_uuid = str(existing["uuid"])
        update_payload = _sync_stamp_for_update(payload, current_uuid=report_uuid)
        assignments = ", ".join([f"{column} = ?" for column in update_payload.keys()])
        connection.execute(
            f"UPDATE daily_reports SET {assignments} WHERE id = ?",
            [*update_payload.values(), report_id],
        )

    _sync_daily_report_lines(connection, report_id=report_id, lines=hydrated_lines)
    register_sync_change(
        connection,
        entity_type="daily_reports",
        entity_uuid=report_uuid,
        operation=sync_operation,
    )
    connection.commit()
    return get_daily_report(connection, report_id, user)


def delete_daily_report(connection: sqlite3.Connection, report_id: int, user: UserInfo) -> None:
    report = get_daily_report(connection, report_id, user)
    if report["is_posted"]:
        raise HTTPException(status_code=400, detail="Posted daily report cannot be deleted")
    now = _now_iso()
    connection.execute(
        """
        UPDATE daily_reports
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, report_id),
    )
    connection.execute(
        "DELETE FROM daily_report_executors WHERE report_line_id IN (SELECT id FROM daily_report_lines WHERE report_id = ?)",
        (report_id,),
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
        (now, now, report_id),
    )
    register_sync_change(connection, entity_type="daily_reports", entity_uuid=str(report["uuid"]), operation="DELETE")
    connection.commit()


def restore_daily_report(connection: sqlite3.Connection, report_id: int, user: UserInfo) -> None:
    report = get_daily_report(connection, report_id, user)
    now = _now_iso()
    connection.execute(
        """
        UPDATE daily_reports
        SET marked_for_deletion = 0,
            is_deleted = 0,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, report_id),
    )
    connection.execute(
        """
        UPDATE daily_report_lines
        SET marked_for_deletion = 0,
            is_deleted = 0,
            modified_at = ?,
            updated_at = ?
        WHERE report_id = ?
        """,
        (now, now, report_id),
    )
    register_sync_change(connection, entity_type="daily_reports", entity_uuid=str(report["uuid"]), operation="RESTORE")
    connection.commit()


def _resolve_work_price(connection: sqlite3.Connection, estimate_id: int | None, work_id: int | None) -> float:
    if estimate_id and work_id:
        row = connection.execute(
            """
            SELECT price
            FROM estimate_lines
            WHERE estimate_id = ? AND work_id = ? AND is_group = 0
            ORDER BY line_number
            LIMIT 1
            """,
            (estimate_id, work_id),
        ).fetchone()
        if row:
            return float(row["price"] or 0)
    if work_id:
        row = connection.execute("SELECT price FROM works WHERE id = ?", (work_id,)).fetchone()
        if row:
            return float(row["price"] or 0)
    return 0.0


def post_daily_report(connection: sqlite3.Connection, *, report_id: int, user: UserInfo) -> None:
    _require_admin(user)
    report = get_daily_report(connection, report_id)
    if report["is_posted"]:
        raise HTTPException(status_code=400, detail="Daily report is already posted")
    estimate = get_estimate(connection, report["estimate_id"]) if report["estimate_id"] else None
    object_id = estimate["object_id"] if estimate else None
    connection.execute(
        "DELETE FROM work_execution_register WHERE recorder_type = 'daily_report' AND recorder_id = ?",
        (report_id,),
    )
    for line in report["lines"]:
        if line["is_group"] or not line["work_id"]:
            continue
        price = _resolve_work_price(connection, report["estimate_id"], line["work_id"])
        actual_labor = float(line.get("actual_labor") or 0)
        connection.execute(
            """
            INSERT INTO work_execution_register (
                recorder_type, recorder_id, line_number, period, object_id, estimate_id, work_id,
                quantity_income, quantity_expense, sum_income, sum_expense, created_at, modified_at, uuid, updated_at, is_deleted
            )
            VALUES ('daily_report', ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, ?, ?, 0)
            """,
            (
                report_id,
                line["line_number"],
                report["date"],
                object_id,
                report["estimate_id"],
                line["work_id"],
                actual_labor,
                round(actual_labor * price, 2),
                _now_iso(),
                _now_iso(),
                new_uuid(),
                _now_iso(),
            ),
        )
    _post_daily_report_to_actual_costs(connection, report)
    connection.execute(
        "UPDATE daily_reports SET is_posted = 1, posted_at = ?, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), _now_iso(), report_id),
    )
    register_sync_change(connection, entity_type="daily_reports", entity_uuid=str(report["uuid"]), operation="UPDATE")
    connection.commit()


def unpost_daily_report(connection: sqlite3.Connection, *, report_id: int, user: UserInfo) -> None:
    _require_admin(user)
    report = get_daily_report(connection, report_id)
    if not report["is_posted"]:
        raise HTTPException(status_code=400, detail="Daily report is not posted")
    _unpost_daily_report_from_actual_costs(connection, report_id)
    connection.execute(
        "DELETE FROM work_execution_register WHERE recorder_type = 'daily_report' AND recorder_id = ?",
        (report_id,),
    )
    connection.execute(
        "UPDATE daily_reports SET is_posted = 0, posted_at = NULL, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), report_id),
    )
    register_sync_change(connection, entity_type="daily_reports", entity_uuid=str(report["uuid"]), operation="UPDATE")
    connection.commit()


def query_work_execution(
    connection: sqlite3.Connection,
    *,
    page: int,
    page_size: int,
    period_from: str | None,
    period_to: str | None,
    object_id: int | None,
    estimate_id: int | None,
    work_id: int | None,
    customer_id: int | None = None,
    contract_id: int | None = None,
    group_by: list[str] | None,
) -> tuple[list[dict[str, Any]], Pagination, dict[str, float]]:
    page, page_size = _normalize_page(page, page_size)
    params: list[Any] = []
    where_parts = ["1 = 1"]
    if period_from:
        where_parts.append("wer.period >= ?")
        params.append(period_from)
    if period_to:
        where_parts.append("wer.period <= ?")
        params.append(period_to)
    if object_id:
        where_parts.append("wer.object_id = ?")
        params.append(object_id)
    if estimate_id:
        where_parts.append("wer.estimate_id = ?")
        params.append(estimate_id)
    if work_id:
        where_parts.append("wer.work_id = ?")
        params.append(work_id)
    if customer_id:
        where_parts.append("e.customer_id = ?")
        params.append(customer_id)
    if contract_id:
        where_parts.append("e.contract_id = ?")
        params.append(contract_id)

    rows = connection.execute(
        f"""
        SELECT
            wer.*,
            o.name AS object_name,
            e.number AS estimate_number,
            w.name AS work_name,
            e.customer_id AS customer_id,
            cust.name AS customer_name,
            e.contract_id AS contract_id,
            ct.number AS contract_number,
            CASE
                WHEN wer.recorder_type = 'estimate' THEN re.number
                WHEN wer.recorder_type = 'daily_report' THEN dr.number
            END AS recorder_number
        FROM work_execution_register wer
        LEFT JOIN objects o ON o.id = wer.object_id
        LEFT JOIN estimates e ON e.id = wer.estimate_id
        LEFT JOIN works w ON w.id = wer.work_id
        LEFT JOIN counterparties cust ON cust.id = e.customer_id
        LEFT JOIN contracts ct ON ct.id = e.contract_id
        LEFT JOIN estimates re ON wer.recorder_type = 'estimate' AND re.id = wer.recorder_id
        LEFT JOIN daily_reports dr ON wer.recorder_type = 'daily_report' AND dr.id = wer.recorder_id
        WHERE {' AND '.join(where_parts)}
        ORDER BY wer.period DESC, wer.id DESC
        """,
        params,
    ).fetchall()
    items = rows_to_dicts(rows)
    for item in items:
        item["balance_quantity"] = round(float(item["quantity_income"]) - float(item["quantity_expense"]), 2)
        item["balance_sum"] = round(float(item["sum_income"]) - float(item["sum_expense"]), 2)

    if group_by:
        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in items:
            key = tuple(
                item.get(f"{field}_name")
                or item.get(f"{field}_number")
                or item.get(f"{field}_id")
                for field in group_by
            )
            if key not in grouped:
                grouped[key] = {
                    "recorder_type": "grouped",
                    "recorder_id": 0,
                    "line_number": 0,
                    "period": item["period"],
                    "object_id": item["object_id"],
                    "object_name": item["object_name"],
                    "estimate_id": item["estimate_id"],
                    "estimate_number": item["estimate_number"],
                    "work_id": item["work_id"],
                    "work_name": item["work_name"],
                    "customer_id": item.get("customer_id"),
                    "customer_name": item.get("customer_name"),
                    "contract_id": item.get("contract_id"),
                    "contract_number": item.get("contract_number"),
                    "recorder_number": None,
                    "quantity_income": 0.0,
                    "quantity_expense": 0.0,
                    "sum_income": 0.0,
                    "sum_expense": 0.0,
                }
            group = grouped[key]
            group["quantity_income"] += float(item["quantity_income"])
            group["quantity_expense"] += float(item["quantity_expense"])
            group["sum_income"] += float(item["sum_income"])
            group["sum_expense"] += float(item["sum_expense"])
        items = list(grouped.values())
        for item in items:
            item["balance_quantity"] = round(item["quantity_income"] - item["quantity_expense"], 2)
            item["balance_sum"] = round(item["sum_income"] - item["sum_expense"], 2)

    total = len(items)
    totals = {
        "quantity_income": round(sum(float(item["quantity_income"]) for item in items), 2),
        "quantity_expense": round(sum(float(item["quantity_expense"]) for item in items), 2),
        "sum_income": round(sum(float(item["sum_income"]) for item in items), 2),
        "sum_expense": round(sum(float(item["sum_expense"]) for item in items), 2),
    }
    totals["balance_quantity"] = round(totals["quantity_income"] - totals["quantity_expense"], 2)
    totals["balance_sum"] = round(totals["sum_income"] - totals["sum_expense"], 2)
    return (
        items[(page - 1) * page_size : (page - 1) * page_size + page_size],
        build_pagination(page, page_size, total),
        totals,
    )


def dashboard_summary(connection: sqlite3.Connection, user: UserInfo) -> dict[str, Any]:
    reports_sql = "SELECT COUNT(*) FROM daily_reports WHERE marked_for_deletion = 0"
    reports_params: tuple[Any, ...] = ()
    if user.role == "foreman" and user.person_id:
        reports_sql += " AND foreman_id = ?"
        reports_params = (user.person_id,)

    timesheets_sql = "SELECT COUNT(*) FROM timesheets WHERE marked_for_deletion = 0"
    timesheets_params: tuple[Any, ...] = ()
    if user.role == "foreman" and user.person_id:
        timesheets_sql += " AND foreman_id = ?"
        timesheets_params = (user.person_id,)

    documents = {
        "estimates": connection.execute(
            "SELECT COUNT(*) FROM estimates WHERE marked_for_deletion = 0"
        ).fetchone()[0],
        "daily_reports": connection.execute(reports_sql, reports_params).fetchone()[0],
        "timesheets": connection.execute(timesheets_sql, timesheets_params).fetchone()[0],
    }
    references = {
        "counterparties": connection.execute(
            "SELECT COUNT(*) FROM counterparties WHERE marked_for_deletion = 0"
        ).fetchone()[0],
        "objects": connection.execute(
            "SELECT COUNT(*) FROM objects WHERE marked_for_deletion = 0"
        ).fetchone()[0],
        "works": connection.execute(
            "SELECT COUNT(*) FROM works WHERE marked_for_deletion = 0"
        ).fetchone()[0],
        "persons": connection.execute(
            "SELECT COUNT(*) FROM persons WHERE marked_for_deletion = 0"
        ).fetchone()[0],
        "organizations": connection.execute(
            "SELECT COUNT(*) FROM organizations WHERE marked_for_deletion = 0"
        ).fetchone()[0],
    }
    register_totals = connection.execute(
        """
        SELECT
            COALESCE(SUM(quantity_income), 0) AS quantity_income,
            COALESCE(SUM(quantity_expense), 0) AS quantity_expense,
            COALESCE(SUM(sum_income), 0) AS sum_income,
            COALESCE(SUM(sum_expense), 0) AS sum_expense
        FROM work_execution_register
        """
    ).fetchone()
    return {
        "documents": documents,
        "references": references,
        "register_totals": {
            "quantity_income": register_totals["quantity_income"],
            "quantity_expense": register_totals["quantity_expense"],
            "sum_income": register_totals["sum_income"],
            "sum_expense": register_totals["sum_expense"],
        },
    }


ESTIMATE_PRINT_OVERHEAD_RATE = 0.22
ESTIMATE_PRINT_PROFIT_RATE = 0.12
ESTIMATE_PRINT_VAT_RATE = 0.0
ESTIMATE_PRINT_COLUMN_WIDTHS = (
    4.34,
    11.71,
    51.89,
    7.66,
    8.96,
    10.41,
    13.15,
    12.29,
    7.08,
    10.41,
    12.86,
    12.29,
    8.09,
)


def _format_estimate_print_date(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, datetime):
        return raw_value.date().strftime("%d.%m.%Y")
    if isinstance(raw_value, date):
        return raw_value.strftime("%d.%m.%Y")
    text = str(raw_value).strip()
    if not text:
        return ""
    for parser in (datetime.fromisoformat,):
        try:
            return parser(text).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return text


def _estimate_resource_rows(connection: sqlite3.Connection, estimate_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            ws.component_type,
            COALESCE(m.code, '') AS component_code,
            ws.component_name,
            COALESCE(u.short_name, u.name, '') AS unit_name,
            ws.unit_price,
            SUM(ws.consumption_rate * el.quantity) AS quantity,
            SUM(ws.consumption_rate * el.quantity * ws.unit_price) AS total_cost
        FROM estimate_lines el
        JOIN work_specifications ws ON ws.work_id = el.work_id
        LEFT JOIN materials m ON m.id = ws.material_id
        LEFT JOIN units u ON u.id = ws.unit_id
        WHERE el.estimate_id = ?
          AND COALESCE(el.marked_for_deletion, 0) = 0
          AND COALESCE(el.is_deleted, 0) = 0
          AND COALESCE(el.is_group, 0) = 0
          AND COALESCE(ws.marked_for_deletion, 0) = 0
          AND COALESCE(ws.is_deleted, 0) = 0
          AND ws.component_type <> 'Labor'
        GROUP BY
            ws.component_type,
            COALESCE(m.code, ''),
            ws.component_name,
            COALESCE(u.short_name, u.name, ''),
            ws.unit_price
        ORDER BY
            CASE ws.component_type
                WHEN 'Material' THEN 1
                WHEN 'Equipment' THEN 2
                WHEN 'Other' THEN 3
                ELSE 4
            END,
            COALESCE(m.code, ''),
            ws.component_name
        """,
        (estimate_id,),
    ).fetchall()

    resource_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        code = str(row["component_code"] or "").strip()
        name = str(row["component_name"] or "").strip()
        label = f"{code} - {name}" if code else name
        resource_rows.append(
            {
                "line_number": index,
                "component_type": str(row["component_type"] or ""),
                "name": label or "-",
                "unit_name": str(row["unit_name"] or ""),
                "quantity": round(float(row["quantity"] or 0), 3),
                "unit_price": round(float(row["unit_price"] or 0), 2),
                "total_cost": round(float(row["total_cost"] or 0), 2),
            }
        )
    return resource_rows


def _estimate_print_totals(estimate: dict[str, Any], resource_rows: list[dict[str, Any]]) -> dict[str, float]:
    direct_cost = round(float(estimate.get("total_sum") or 0), 2)
    total_labor = round(float(estimate.get("total_labor") or 0), 2)
    materials_cost = round(sum(float(row["total_cost"]) for row in resource_rows), 2)
    overhead = round(direct_cost * ESTIMATE_PRINT_OVERHEAD_RATE, 2)
    profit = round((direct_cost + overhead) * ESTIMATE_PRINT_PROFIT_RATE, 2)
    vat = round((direct_cost + overhead + profit) * ESTIMATE_PRINT_VAT_RATE, 2)
    grand_total = round(direct_cost + overhead + profit + vat, 2)
    return {
        "direct_cost": direct_cost,
        "total_labor": total_labor,
        "materials_cost": materials_cost,
        "overhead": overhead,
        "profit": profit,
        "vat": vat,
        "grand_total": grand_total,
    }


def _build_estimate_excel_content(connection: sqlite3.Connection, estimate: dict[str, Any], *, title: str = "Смета", include_resources: bool = True) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.freeze_panes = "A17"

    for column_index, width in enumerate(ESTIMATE_PRINT_COLUMN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(column_index)].width = width

    thin_side = Side(style="thin", color="000000")
    table_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    title_font = Font(name="Arial", size=13, bold=True)
    header_font = Font(name="Arial", size=10, bold=True)
    data_font = Font(name="Arial", size=9)
    small_font = Font(name="Arial", size=8)
    italic_font = Font(name="Arial", size=8, italic=True)
    group_fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
    header_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center", wrap_text=True)
    header_left = Alignment(horizontal="left", vertical="center", wrap_text=False)
    number_format = '#,##0.00'
    quantity_format = '#,##0.000'

    resource_rows = _estimate_resource_rows(connection, int(estimate["id"]))
    totals = _estimate_print_totals(estimate, resource_rows)

    sheet.row_dimensions[4].height = 20
    sheet.row_dimensions[5].height = 20
    sheet.row_dimensions[6].height = 18
    sheet.row_dimensions[7].height = 18
    sheet["A4"] = "Согласовано:"
    sheet["H4"] = "Утверждаю:"
    sheet["A5"] = f"Заказчик: {estimate.get('customer_name') or '________________'}"
    sheet["H5"] = f"Подрядчик: {estimate.get('contractor_name') or '________________'}"
    sheet["A6"] = "____________________"
    sheet["H6"] = "____________________"
    sheet["A7"] = "(подпись)"
    sheet["H7"] = "(подпись)"
    for cell_ref in ("A4", "H4", "A5", "H5", "A6", "H6"):
        sheet[cell_ref].font = header_font if cell_ref.endswith("4") else data_font
        sheet[cell_ref].alignment = header_left
    for cell_ref in ("A7", "H7"):
        sheet[cell_ref].font = small_font
        sheet[cell_ref].alignment = header_left

    sheet.merge_cells("A9:M9")
    if title == "Акт":
        sheet["A9"] = f"АКТ №{estimate['number']} О ВЫПОЛНЕННЫХ РАБОТАХ"
    else:
        sheet["A9"] = f"ЛОКАЛЬНЫЙ СМЕТНЫЙ РАСЧЕТ №{estimate['number']}"
    sheet["A9"].font = title_font
    sheet["A9"].alignment = center

    sheet.merge_cells("A10:M10")
    sheet["A10"] = "(локальная смета)" if title != "Акт" else "(по форме КС-2)"
    sheet["A10"].font = data_font
    sheet["A10"].alignment = center

    sheet.merge_cells("A12:M12")
    sheet["A12"] = estimate.get("object_name") or "Объект не указан"
    sheet["A12"].font = header_font
    sheet["A12"].alignment = center

    sheet.merge_cells("A13:M13")
    sheet["A13"] = f"Дата сметы: {_format_estimate_print_date(estimate.get('date'))}"
    sheet["A13"].font = data_font
    sheet["A13"].alignment = center

    sheet.merge_cells("A14:M14")
    sheet["A14"] = "(наименование работ и затрат, наименование объекта)"
    sheet["A14"].font = italic_font
    sheet["A14"].alignment = center

    sheet.merge_cells("F16:I16")
    sheet.merge_cells("J16:M16")
    sheet["F16"] = "на единицу работ"
    sheet["J16"] = "на полный объём работ"
    for column in range(1, 14):
        cell = sheet.cell(row=16, column=column)
        cell.font = header_font
        cell.alignment = center
        cell.border = table_border
        cell.fill = header_fill

    headers = [
        "N",
        "Код",
        "Наименование работ и затрат",
        "ЕдИзм",
        "Кол-во",
        "Зарплата",
        "Материалы,\nмеханизмы",
        "Всего",
        "ТЗ",
        "Зарплата",
        "Материалы,\nмеханизмы",
        "Всего",
        "ТЗ",
    ]
    sheet.row_dimensions[17].height = 34
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=17, column=column, value=header)
        cell.font = header_font
        cell.alignment = center
        cell.border = table_border
        cell.fill = header_fill

    current_row = 18
    for line in estimate["lines"]:
        if line["is_group"]:
            sheet.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=13)
            sheet.cell(row=current_row, column=1, value=line["line_number"])
            sheet.cell(row=current_row, column=2, value=line.get("group_name") or line.get("work_name") or "Группа")
            for column in range(1, 14):
                cell = sheet.cell(row=current_row, column=column)
                cell.font = header_font
                cell.alignment = left if column == 2 else center
                cell.border = table_border
                cell.fill = group_fill
            current_row += 1
            continue

        row_values: dict[int, Any] = {
            1: line["line_number"],
            2: line.get("work_code") or "",
            3: line.get("work_name") or "-",
            4: line.get("unit") or "",
            5: float(line.get("quantity") or 0),
            8: float(line.get("price") or 0),
            9: float(line.get("labor_rate") or 0),
            12: float(line.get("sum") or 0),
            13: float(line.get("planned_labor") or 0),
        }
        for column in range(1, 14):
            cell = sheet.cell(row=current_row, column=column, value=row_values.get(column, ""))
            cell.font = data_font
            cell.border = table_border
            if column == 3:
                cell.alignment = left
            elif column in {1, 4}:
                cell.alignment = center
            else:
                cell.alignment = right
            if column == 5:
                cell.number_format = quantity_format
            elif column in {8, 9, 12, 13}:
                cell.number_format = number_format
        current_row += 1

    def write_summary_row(
        row: int,
        label: str,
        amount: float | str,
        *,
        labor: float | str = "",
        bold: bool = False,
    ) -> None:
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=11)
        label_cell = sheet.cell(row=row, column=1, value=label)
        label_cell.font = header_font if bold else data_font
        label_cell.alignment = left
        label_cell.border = table_border
        value_cell = sheet.cell(row=row, column=12, value=amount)
        value_cell.font = header_font if bold else data_font
        value_cell.alignment = right
        value_cell.border = table_border
        if isinstance(amount, (int, float)):
            value_cell.number_format = number_format
        labor_cell = sheet.cell(row=row, column=13, value=labor)
        labor_cell.font = header_font if bold else data_font
        labor_cell.alignment = right
        labor_cell.border = table_border
        if isinstance(labor, (int, float)):
            labor_cell.number_format = number_format
        for column in range(1, 14):
            cell = sheet.cell(row=row, column=column)
            cell.fill = header_fill if bold else PatternFill(fill_type=None)

    write_summary_row(current_row, "Итого прямые затраты:", totals["direct_cost"], labor=totals["total_labor"], bold=True)
    current_row += 1
    write_summary_row(
        current_row,
        f"Накладные расходы ({int(ESTIMATE_PRINT_OVERHEAD_RATE * 100)}%):",
        totals["overhead"],
    )
    current_row += 1
    write_summary_row(
        current_row,
        f"Плановые накопления ({int(ESTIMATE_PRINT_PROFIT_RATE * 100)}%):",
        totals["profit"],
    )
    current_row += 1
    write_summary_row(
        current_row,
        f"НДС ({int(ESTIMATE_PRINT_VAT_RATE * 100)}%):" if ESTIMATE_PRINT_VAT_RATE else "НДС:",
        totals["vat"] if ESTIMATE_PRINT_VAT_RATE else "-",
    )
    current_row += 1
    write_summary_row(current_row, "Всего:", totals["grand_total"], labor=totals["total_labor"], bold=True)
    current_row += 1
    if include_resources:
        write_summary_row(
            current_row,
            "в том числе материалы и работа механизмов:",
            totals["materials_cost"],
        )
        current_row += 2

        sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=13)
        sheet.cell(row=current_row, column=1, value="РЕСУРСНАЯ ВЕДОМОСТЬ").font = header_font
        sheet.cell(row=current_row, column=1).alignment = center
        current_row += 1

        sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=8)
        sheet.cell(row=current_row, column=1, value="Наименование")
        sheet.cell(row=current_row, column=9, value="ЕдИзм.")
        sheet.cell(row=current_row, column=10, value="Кол-во")
        sheet.cell(row=current_row, column=11, value="Цена")
        sheet.cell(row=current_row, column=12, value="Стоимость")
        for column in range(1, 13):
            cell = sheet.cell(row=current_row, column=column)
            cell.font = header_font
            cell.alignment = center
            cell.border = table_border
            cell.fill = header_fill
        current_row += 1

        if resource_rows:
            for resource in resource_rows:
                sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=8)
                name_cell = sheet.cell(row=current_row, column=1, value=resource["name"])
                name_cell.font = data_font
                name_cell.alignment = left
                name_cell.border = table_border
                unit_cell = sheet.cell(row=current_row, column=9, value=resource["unit_name"])
                quantity_cell = sheet.cell(row=current_row, column=10, value=float(resource["quantity"]))
                price_cell = sheet.cell(row=current_row, column=11, value=float(resource["unit_price"]))
                cost_cell = sheet.cell(row=current_row, column=12, value=float(resource["total_cost"]))
                for cell in (unit_cell, quantity_cell, price_cell, cost_cell):
                    cell.font = data_font
                    cell.alignment = right if cell.column != 9 else center
                    cell.border = table_border
                quantity_cell.number_format = quantity_format
                price_cell.number_format = number_format
                cost_cell.number_format = number_format
                current_row += 1
        else:
            sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=12)
            note_cell = sheet.cell(row=current_row, column=1, value="Спецификации материалов и механизмов для строк сметы не заполнены.")
            note_cell.font = data_font
            note_cell.alignment = left
            note_cell.border = table_border
            current_row += 1

        sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=11)
        total_materials_cell = sheet.cell(row=current_row, column=1, value="Итого материалы:")
        total_materials_cell.font = header_font
        total_materials_cell.alignment = left
        total_materials_cell.border = table_border
        total_materials_value = sheet.cell(row=current_row, column=12, value=totals["materials_cost"])
        total_materials_value.font = header_font
        total_materials_value.alignment = right
        total_materials_value.border = table_border
        total_materials_value.number_format = number_format
        current_row += 3
    else:
        current_row += 2

    sheet.cell(row=current_row, column=1, value="Составил:").font = header_font
    sheet.cell(row=current_row, column=8, value="Проверил:").font = header_font
    sheet.cell(row=current_row + 1, column=1, value=estimate.get("responsible_name") or "________________").font = data_font
    sheet.cell(row=current_row + 1, column=8, value="________________").font = data_font

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.read()


def build_estimate_print(
    connection: sqlite3.Connection,
    estimate: dict[str, Any],
    output_format: str,
) -> tuple[bytes, str, str]:
    resource_rows = _estimate_resource_rows(connection, int(estimate["id"]))
    totals = _estimate_print_totals(estimate, resource_rows)
    lines = [
        f"Номер: {estimate['number']}",
        f"Дата: {estimate['date']}",
        f"Заказчик: {estimate.get('customer_name') or '-'}",
        f"Объект: {estimate.get('object_name') or '-'}",
        f"Подрядчик: {estimate.get('contractor_name') or '-'}",
        f"Ответственный: {estimate.get('responsible_name') or '-'}",
        "",
        "Работы:",
    ]
    for line in estimate["lines"]:
        label = line.get("group_name") if line["is_group"] else line.get("work_name") or "-"
        lines.append(
            f"{line['line_number']}. {label} | кол-во {line['quantity']} | цена {line['price']} | "
            f"сумма {line['sum']} | план {line['planned_labor']}"
        )
    lines.extend(
        [
            "",
            f"Итого прямые затраты: {totals['direct_cost']}",
            f"Накладные расходы ({int(ESTIMATE_PRINT_OVERHEAD_RATE * 100)}%): {totals['overhead']}",
            f"Плановые накопления ({int(ESTIMATE_PRINT_PROFIT_RATE * 100)}%): {totals['profit']}",
            f"НДС: {totals['vat']}",
            f"Всего: {totals['grand_total']}",
            f"Материалы и механизмы по спецификациям: {totals['materials_cost']}",
        ]
    )
    if resource_rows:
        lines.append("")
        lines.append("Ресурсная ведомость:")
        for resource in resource_rows:
            lines.append(
                f"{resource['line_number']}. {resource['name']} | ед. {resource['unit_name'] or '-'} | "
                f"кол-во {resource['quantity']} | цена {resource['unit_price']} | сумма {resource['total_cost']}"
            )
    if output_format == "excel":
        return (
            _build_estimate_excel_content(connection, estimate),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"estimate_{estimate['id']}.xlsx",
        )
    return build_pdf("Estimate Print Form", lines), "application/pdf", f"estimate_{estimate['id']}.pdf"


def build_act_print(
    connection: sqlite3.Connection,
    estimate: dict[str, Any],
    output_format: str,
) -> tuple[bytes, str, str]:
    resource_rows = _estimate_resource_rows(connection, int(estimate["id"]))
    totals = _estimate_print_totals(estimate, resource_rows)
    lines = [
        f"АКТ №{estimate['number']} о выполненных работах",
        f"Дата: {estimate['date']}",
        f"Заказчик: {estimate.get('customer_name') or '-'}",
        f"Объект: {estimate.get('object_name') or '-'}",
        f"Подрядчик: {estimate.get('contractor_name') or '-'}",
        f"Договор: {estimate.get('contract_number') or '-'}",
        "",
        "Выполненные работы:",
    ]
    for line in estimate["lines"]:
        label = line.get("group_name") if line["is_group"] else line.get("work_name") or "-"
        lines.append(
            f"{line['line_number']}. {label} | кол-во {line['quantity']} | цена {line['price']} | "
            f"сумма {line['sum']} | план {line['planned_labor']}"
        )
    lines.extend(
        [
            "",
            f"Итого прямые затраты: {totals['direct_cost']}",
            f"Накладные расходы ({int(ESTIMATE_PRINT_OVERHEAD_RATE * 100)}%): {totals['overhead']}",
            f"Плановые накопления ({int(ESTIMATE_PRINT_PROFIT_RATE * 100)}%): {totals['profit']}",
            f"НДС: {totals['vat']}",
            f"Всего: {totals['grand_total']}",
        ]
    )
    if output_format == "excel":
        return (
            _build_estimate_excel_content(connection, estimate, title="Акт"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"act_{estimate['id']}.xlsx",
        )
    return build_pdf("Act Print Form", lines), "application/pdf", f"act_{estimate['id']}.pdf"


def build_daily_report_print(report: dict[str, Any], output_format: str) -> tuple[bytes, str, str]:
    lines = [
        f"Номер: {report['number']}",
        f"Дата: {report['date']}",
        f"Смета: {report.get('estimate_number') or '-'}",
        f"Прораб: {report.get('foreman_name') or '-'}",
        "",
    ]
    grid: list[list[str]] = []
    for line in report["lines"]:
        label = line.get("group_name") if line["is_group"] else line.get("work_name") or "-"
        executors = ", ".join(line.get("executor_names", []))
        lines.append(
            f"{line['line_number']}. {label} | план {line['planned_labor']} | факт {line['actual_labor']} | "
            f"откл. {line['deviation_percent']}% | исп.: {executors}"
        )
        grid.append(
            [
                str(line["line_number"]),
                str(label),
                str(line["planned_labor"]),
                str(line["actual_labor"]),
                str(line["deviation_percent"]),
                executors,
            ]
        )
    if output_format == "excel":
        return (
            build_excel_xml(
                "DailyReport",
                ["№", "Работа", "План", "Факт", "Отклонение %", "Исполнители"],
                grid,
            ),
            "application/vnd.ms-excel",
            f"daily_report_{report['id']}.xls",
        )
    return build_pdf("Daily Report Print Form", lines), "application/pdf", f"daily_report_{report['id']}.pdf"


def build_daily_report_act_print(
    connection: sqlite3.Connection,
    report: dict[str, Any],
    output_format: str,
) -> tuple[bytes, str, str]:
    estimate = get_estimate(connection, int(report["estimate_id"])) if report.get("estimate_id") else {}

    act_lines: list[dict[str, Any]] = []
    total_actual_sum = 0.0
    total_labor = 0.0
    for line in report["lines"]:
        is_group = bool(line.get("is_group"))
        actual_sum = 0.0 if is_group else float(line.get("actual_sum") or 0)
        # Трудозатраты: при заполнении из сметы попадают в planned_labor отчёта;
        # используем именно их, чтобы ТЗ выводились в акте.
        line_labor = 0.0 if is_group else float(line.get("planned_labor") or line.get("actual_labor") or 0)
        total_actual_sum += actual_sum
        total_labor += line_labor
        act_lines.append(
            {
                "line_number": line["line_number"],
                "is_group": is_group,
                "group_name": line.get("group_name"),
                "work_name": line.get("work_name"),
                "work_code": "",
                "unit": line.get("unit"),
                "quantity": 0.0 if is_group else float(line.get("quantity") or 0),
                "price": 0.0 if is_group else float(line.get("price") or 0),
                "labor_rate": 0.0,
                "sum": actual_sum,
                "planned_labor": line_labor,
            }
        )

    direct_cost = round(total_actual_sum, 2)
    overhead = round(direct_cost * ESTIMATE_PRINT_OVERHEAD_RATE, 2)
    profit = round((direct_cost + overhead) * ESTIMATE_PRINT_PROFIT_RATE, 2)
    vat = round((direct_cost + overhead + profit) * ESTIMATE_PRINT_VAT_RATE, 2)
    grand_total = round(direct_cost + overhead + profit + vat, 2)

    pseudo_estimate = {
        "id": 0,
        "number": report.get("number") or "",
        "date": report.get("date") or "",
        "customer_name": estimate.get("customer_name") if estimate else None,
        "object_name": estimate.get("object_name") if estimate else None,
        "contractor_name": estimate.get("contractor_name") if estimate else None,
        "responsible_name": report.get("foreman_name"),
        "contract_number": estimate.get("contract_number") if estimate else None,
        "total_sum": direct_cost,
        "total_labor": round(total_labor, 2),
        "lines": act_lines,
    }
    totals = {
        "direct_cost": direct_cost,
        "total_labor": round(total_labor, 2),
        "materials_cost": 0.0,
        "overhead": overhead,
        "profit": profit,
        "vat": vat,
        "grand_total": grand_total,
    }

    if output_format == "excel":
        return (
            _build_estimate_excel_content(
                connection,
                pseudo_estimate,
                title="Акт",
                include_resources=False,
            ),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"act_report_{report['id']}.xlsx",
        )

    lines = [
        f"АКТ №{pseudo_estimate['number']} о выполненных работах",
        f"Дата: {pseudo_estimate['date']}",
        f"Заказчик: {pseudo_estimate.get('customer_name') or '-'}",
        f"Объект: {pseudo_estimate.get('object_name') or '-'}",
        f"Подрядчик: {pseudo_estimate.get('contractor_name') or '-'}",
        f"Договор: {pseudo_estimate.get('contract_number') or '-'}",
        "",
        "Выполненные работы:",
    ]
    for line in act_lines:
        label = line.get("group_name") if line["is_group"] else line.get("work_name") or "-"
        lines.append(
            f"{line['line_number']}. {label} | кол-во {line['quantity']} | цена {line['price']} | "
            f"сумма {line['sum']} | факт.ТЗ {line['planned_labor']}"
        )
    lines.extend(
        [
            "",
            f"Итого прямые затраты: {totals['direct_cost']}",
            f"Накладные расходы ({int(ESTIMATE_PRINT_OVERHEAD_RATE * 100)}%): {totals['overhead']}",
            f"Плановые накопления ({int(ESTIMATE_PRINT_PROFIT_RATE * 100)}%): {totals['profit']}",
            f"НДС: {totals['vat']}",
            f"Всего: {totals['grand_total']}",
        ]
    )
    return build_pdf("Act Print Form", lines), "application/pdf", f"act_report_{report['id']}.pdf"


TIMESHEET_DAY_FIELDS = tuple(f"day_{day:02d}" for day in range(1, 32))


def _timesheet_period_bounds(month_year: str) -> tuple[date, date]:
    try:
        year, month = (int(part) for part in month_year.split("-", 1))
        first_day = date(year, month, 1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Month period must be in YYYY-MM format") from exc
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    return first_day, last_day


def _timesheet_days_in_month(month_year: str) -> int:
    first_day, _ = _timesheet_period_bounds(month_year)
    return calendar.monthrange(first_day.year, first_day.month)[1]


def _normalize_timesheet_days(days: dict[Any, Any] | None, month_year: str) -> dict[int, float]:
    last_day = _timesheet_days_in_month(month_year)
    normalized = {day: 0.0 for day in range(1, last_day + 1)}
    for raw_day, raw_hours in (days or {}).items():
        try:
            day = int(raw_day)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid day value: {raw_day}") from exc
        if day < 1 or day > 31:
            raise HTTPException(status_code=400, detail=f"Day {day} is out of range")
        try:
            hours = round(float(raw_hours or 0), 2)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid hours for day {day}") from exc
        if hours < 0 or hours > 24:
            raise HTTPException(status_code=400, detail=f"Hours for day {day} must be between 0 and 24")
        if day > last_day:
            if hours > 0:
                raise HTTPException(status_code=400, detail=f"Day {day} is outside the selected month")
            continue
        normalized[day] = hours
    return normalized


def _hydrate_timesheet_line(
    connection: sqlite3.Connection,
    *,
    line: dict[str, Any],
    month_year: str,
) -> dict[str, Any]:
    employee_id = int(line.get("employee_id") or 0)
    if employee_id <= 0:
        raise HTTPException(status_code=400, detail="Each timesheet line must contain an employee")
    employee_row = connection.execute(
        """
        SELECT id, hourly_rate
        FROM persons
        WHERE id = ? AND marked_for_deletion = 0 AND COALESCE(is_deleted, 0) = 0
        """,
        (employee_id,),
    ).fetchone()
    if employee_row is None:
        raise HTTPException(status_code=400, detail=f"Employee {employee_id} not found")

    raw_hourly_rate = line.get("hourly_rate") if "hourly_rate" in line else None
    try:
        if raw_hourly_rate in (None, ""):
            hourly_rate = round(float(employee_row["hourly_rate"] or 0), 2)
        else:
            hourly_rate = round(float(raw_hourly_rate or 0), 2)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid hourly rate for employee {employee_id}") from exc
    if hourly_rate < 0:
        raise HTTPException(status_code=400, detail="Hourly rate cannot be negative")

    normalized_days = _normalize_timesheet_days(line.get("days"), month_year)
    total_hours = round(sum(normalized_days.values()), 2)
    total_amount = round(total_hours * hourly_rate, 2)
    return {
        "id": line.get("id"),
        "uuid": line.get("uuid"),
        "line_number": int(line["line_number"]),
        "employee_id": employee_id,
        "hourly_rate": hourly_rate,
        "days": normalized_days,
        "total_hours": total_hours,
        "total_amount": total_amount,
    }


def _timesheet_totals(lines: list[dict[str, Any]]) -> tuple[float, float]:
    total_hours = round(sum(float(line.get("total_hours", 0) or 0) for line in lines), 2)
    total_amount = round(sum(float(line.get("total_amount", 0) or 0) for line in lines), 2)
    return total_hours, total_amount


def _timesheet_day_columns(days: dict[int, float]) -> dict[str, float]:
    columns: dict[str, float] = {}
    for day in range(1, 32):
        columns[f"day_{day:02d}"] = round(float(days.get(day, 0) or 0), 2)
    return columns


def _timesheet_days_from_row(row: dict[str, Any], month_year: str) -> dict[int, float]:
    last_day = _timesheet_days_in_month(month_year)
    return {
        day: round(float(row.get(f"day_{day:02d}", 0) or 0), 2)
        for day in range(1, last_day + 1)
    }


def _assert_timesheet_number_available(
    connection: sqlite3.Connection,
    *,
    number: str,
    exclude_timesheet_id: int | None = None,
) -> None:
    params: list[Any] = [number]
    sql = """
        SELECT id
        FROM timesheets
        WHERE number = ?
          AND marked_for_deletion = 0
          AND COALESCE(is_deleted, 0) = 0
    """
    if exclude_timesheet_id is not None:
        sql += " AND id <> ?"
        params.append(exclude_timesheet_id)
    row = connection.execute(sql, params).fetchone()
    if row is not None:
        raise HTTPException(status_code=400, detail="Timesheet number must be unique")


def _next_timesheet_number(connection: sqlite3.Connection) -> str:
    prefix = settings.database_number_prefix
    total_length = settings.timesheet_number_total_length
    numeric_width = max(1, total_length - len(prefix))
    rows = connection.execute(
        """
        SELECT number
        FROM timesheets
        WHERE number LIKE ?
          AND COALESCE(is_deleted, 0) = 0
        """,
        (f"{prefix}%",),
    ).fetchall()
    max_sequence = 0
    for row in rows:
        number = str(row["number"] or "")
        if not number.startswith(prefix):
            continue
        suffix = number[len(prefix) :]
        if suffix.isdigit():
            max_sequence = max(max_sequence, int(suffix))
    next_sequence = max_sequence + 1
    next_suffix = f"{next_sequence:0{numeric_width}d}" if len(str(next_sequence)) <= numeric_width else str(next_sequence)
    candidate = f"{prefix}{next_suffix}"
    if len(candidate) > total_length:
        raise HTTPException(status_code=500, detail="Timesheet numbering sequence exceeded configured length")
    return candidate


def list_timesheets(
    connection: sqlite3.Connection,
    *,
    user: UserInfo,
    page: int,
    page_size: int,
    search: str | None,
    sort_by: str | None,
    sort_order: str,
    object_id: int | None = None,
    estimate_id: int | None = None,
    month_year: str | None = None,
    is_posted: bool | None = None,
) -> tuple[list[dict[str, Any]], Pagination]:
    page, page_size = _normalize_page(page, page_size)
    sort_column = sort_by if sort_by in {"id", "number", "date", "month_year"} else "date"
    order = "DESC" if sort_order.lower() == "desc" else "ASC"
    params: list[Any] = []
    where_parts = ["t.marked_for_deletion = 0"]
    if search:
        where_parts.append("(t.number LIKE ? OR o.name LIKE ? OR COALESCE(e.number, '') LIKE ? OR COALESCE(p.full_name, '') LIKE ?)")
        params.extend([f"%{search}%"] * 4)
    if object_id:
        where_parts.append("t.object_id = ?")
        params.append(object_id)
    if estimate_id:
        where_parts.append("t.estimate_id = ?")
        params.append(estimate_id)
    if month_year:
        where_parts.append("t.month_year = ?")
        params.append(month_year)
    if is_posted is not None:
        where_parts.append("t.is_posted = ?")
        params.append(int(is_posted))
    if user.role == "foreman":
        if not user.person_id:
            raise HTTPException(status_code=403, detail="Foreman account is not linked to a person")
        where_parts.append("t.foreman_id = ?")
        params.append(user.person_id)
    where_sql = " AND ".join(where_parts)
    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM timesheets t
        LEFT JOIN objects o ON o.id = t.object_id
        LEFT JOIN estimates e ON e.id = t.estimate_id
        LEFT JOIN persons p ON p.id = t.foreman_id
        WHERE {where_sql}
        """,
        params,
    ).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT
            t.*,
            o.uuid AS object_uuid,
            o.name AS object_name,
            e.uuid AS estimate_uuid,
            e.number AS estimate_number,
            p.uuid AS foreman_uuid,
            p.full_name AS foreman_name,
            COALESCE(SUM(tl.total_hours), 0) AS total_hours,
            COALESCE(SUM(tl.total_amount), 0) AS total_amount
        FROM timesheets t
        LEFT JOIN objects o ON o.id = t.object_id
        LEFT JOIN estimates e ON e.id = t.estimate_id
        LEFT JOIN persons p ON p.id = t.foreman_id
        LEFT JOIN timesheet_lines tl ON tl.timesheet_id = t.id AND COALESCE(tl.is_deleted, 0) = 0
        WHERE {where_sql}
        GROUP BY t.id, o.uuid, o.name, e.uuid, e.number, p.uuid, p.full_name
        ORDER BY t.{sort_column} {order}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    items = [_cast_flags(item, "is_posted", "marked_for_deletion") for item in rows_to_dicts(rows)]
    return items, build_pagination(page, page_size, total)


def get_timesheet(connection: sqlite3.Connection, timesheet_id: int, user: UserInfo | None = None) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            t.*,
            o.uuid AS object_uuid,
            o.name AS object_name,
            e.uuid AS estimate_uuid,
            e.number AS estimate_number,
            p.uuid AS foreman_uuid,
            p.full_name AS foreman_name
        FROM timesheets t
        LEFT JOIN objects o ON o.id = t.object_id
        LEFT JOIN estimates e ON e.id = t.estimate_id
        LEFT JOIN persons p ON p.id = t.foreman_id
        WHERE t.id = ? AND t.marked_for_deletion = 0
        """,
        (timesheet_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    timesheet = _cast_flags(row_to_dict(row) or {}, "is_posted", "marked_for_deletion")
    if user and user.role == "foreman":
        if not user.person_id:
            raise HTTPException(status_code=403, detail="Foreman account is not linked to a person")
        if timesheet.get("foreman_id") != user.person_id:
            raise HTTPException(status_code=403, detail="Access denied")

    line_rows = connection.execute(
        """
        SELECT
            tl.*,
            t.uuid AS timesheet_uuid,
            p.uuid AS employee_uuid,
            p.full_name AS employee_name
        FROM timesheet_lines tl
        JOIN timesheets t ON t.id = tl.timesheet_id
        JOIN persons p ON p.id = tl.employee_id
        WHERE tl.timesheet_id = ?
          AND COALESCE(tl.is_deleted, 0) = 0
        ORDER BY tl.line_number
        """,
        (timesheet_id,),
    ).fetchall()
    line_items = rows_to_dicts(line_rows)
    for item in line_items:
        item["days"] = _timesheet_days_from_row(item, timesheet["month_year"])
    total_hours, total_amount = _timesheet_totals(line_items)
    timesheet["total_hours"] = total_hours
    timesheet["total_amount"] = total_amount
    timesheet["lines"] = line_items
    return timesheet


def get_timesheet_by_uuid(
    connection: sqlite3.Connection,
    timesheet_uuid: str,
    user: UserInfo | None = None,
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT id FROM timesheets WHERE uuid = ? AND COALESCE(is_deleted, 0) = 0",
        (timesheet_uuid,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    return get_timesheet(connection, int(row["id"]), user)


def _sync_timesheet_lines(
    connection: sqlite3.Connection,
    *,
    timesheet_id: int,
    month_year: str,
    lines: list[dict[str, Any]],
) -> None:
    existing_rows = connection.execute(
        """
        SELECT id, uuid
        FROM timesheet_lines
        WHERE timesheet_id = ?
          AND COALESCE(is_deleted, 0) = 0
        """,
        (timesheet_id,),
    ).fetchall()
    existing_map = {int(row["id"]): str(row["uuid"]) for row in existing_rows}
    existing_uuid_map = {str(row["uuid"]): int(row["id"]) for row in existing_rows}
    incoming_ids: set[int] = set()

    for raw_line in lines:
        line = dict(raw_line)
        line_uuid = str(line.get("uuid") or "").strip() or None
        line_id = int(line["id"]) if line.get("id") is not None else None
        if line_uuid and line_uuid in existing_uuid_map:
            line_id = existing_uuid_map[line_uuid]

        now = _now_iso()
        created_at = str(line.get("created_at") or now)
        modified_at = str(line.get("modified_at") or line.get("updated_at") or now)
        updated_at = str(line.get("updated_at") or modified_at or now)
        day_columns = _timesheet_day_columns(_normalize_timesheet_days(line.get("days"), month_year))

        if line_id is not None and line_id in existing_map:
            incoming_ids.add(line_id)
            update_payload = {
                "line_number": line["line_number"],
                "employee_id": line["employee_id"],
                "hourly_rate": line["hourly_rate"],
                **day_columns,
                "total_hours": line["total_hours"],
                "total_amount": line["total_amount"],
                "modified_at": modified_at,
                "updated_at": updated_at,
                "uuid": line_uuid or existing_map[line_id],
                "is_deleted": 0,
            }
            assignments = ", ".join(f"{column} = ?" for column in update_payload)
            connection.execute(
                f"""
                UPDATE timesheet_lines
                SET {assignments}
                WHERE id = ? AND timesheet_id = ?
                """,
                [*update_payload.values(), line_id, timesheet_id],
            )
            continue

        insert_payload = {
            "timesheet_id": timesheet_id,
            "line_number": line["line_number"],
            "employee_id": line["employee_id"],
            "hourly_rate": line["hourly_rate"],
            **day_columns,
            "total_hours": line["total_hours"],
            "total_amount": line["total_amount"],
            "created_at": created_at,
            "modified_at": modified_at,
            "uuid": line_uuid or new_uuid(),
            "updated_at": updated_at,
            "is_deleted": 0,
        }
        columns = ", ".join(insert_payload.keys())
        placeholders = ", ".join(["?"] * len(insert_payload))
        connection.execute(
            f"INSERT INTO timesheet_lines ({columns}) VALUES ({placeholders})",
            list(insert_payload.values()),
        )
        new_line_id = last_insert_id(connection)
        incoming_ids.add(new_line_id)

    for existing_id in existing_map:
        if existing_id in incoming_ids:
            continue
        now = _now_iso()
        connection.execute(
            """
            UPDATE timesheet_lines
            SET is_deleted = 1,
                modified_at = ?,
                updated_at = ?
            WHERE id = ? AND timesheet_id = ?
            """,
            (now, now, existing_id, timesheet_id),
        )


def save_timesheet(
    connection: sqlite3.Connection,
    *,
    payload: dict[str, Any],
    user: UserInfo,
    timesheet_id: int | None = None,
) -> dict[str, Any]:
    payload = dict(payload)
    lines = payload.pop("lines", [])
    payload["date"] = str(payload["date"])
    payload["month_year"] = str(payload.get("month_year") or payload["date"][:7])
    _timesheet_period_bounds(payload["month_year"])
    if not payload.get("object_id"):
        raise HTTPException(status_code=400, detail="Object is required")
    if user.role == "foreman":
        if not user.person_id:
            raise HTTPException(status_code=403, detail="Foreman account is not linked to a person")
        payload["foreman_id"] = user.person_id
    if not payload.get("number"):
        payload["number"] = _next_timesheet_number(connection)
    _assert_timesheet_number_available(
        connection,
        number=str(payload["number"]),
        exclude_timesheet_id=timesheet_id,
    )

    hydrated_lines: list[dict[str, Any]] = []
    seen_employees: set[int] = set()
    for raw_line in lines:
        hydrated_line = _hydrate_timesheet_line(connection, line=dict(raw_line), month_year=payload["month_year"])
        if hydrated_line["employee_id"] in seen_employees:
            raise HTTPException(status_code=400, detail="Each employee can appear only once in a timesheet")
        seen_employees.add(hydrated_line["employee_id"])
        hydrated_lines.append(hydrated_line)

    if timesheet_id is None:
        sync_operation = "INSERT"
        insert_payload = _sync_stamp_for_create(payload)
        columns = ", ".join(insert_payload.keys())
        placeholders = ", ".join(["?"] * len(insert_payload))
        connection.execute(
            f"INSERT INTO timesheets ({columns}) VALUES ({placeholders})",
            list(insert_payload.values()),
        )
        timesheet_id = last_insert_id(connection)
        timesheet_uuid = str(insert_payload["uuid"])
    else:
        sync_operation = "UPDATE"
        existing = get_timesheet(connection, timesheet_id, user)
        if existing["is_posted"]:
            raise HTTPException(status_code=400, detail="Posted timesheet cannot be modified")
        timesheet_uuid = str(existing["uuid"])
        update_payload = _sync_stamp_for_update(payload, current_uuid=timesheet_uuid)
        assignments = ", ".join([f"{column} = ?" for column in update_payload.keys()])
        connection.execute(
            f"UPDATE timesheets SET {assignments} WHERE id = ?",
            [*update_payload.values(), timesheet_id],
        )

    _sync_timesheet_lines(connection, timesheet_id=timesheet_id, month_year=payload["month_year"], lines=hydrated_lines)
    register_sync_change(connection, entity_type="timesheets", entity_uuid=timesheet_uuid, operation=sync_operation)
    connection.commit()
    return get_timesheet(connection, timesheet_id, user)


def delete_timesheet(connection: sqlite3.Connection, timesheet_id: int, user: UserInfo) -> None:
    timesheet = get_timesheet(connection, timesheet_id, user)
    if timesheet["is_posted"]:
        raise HTTPException(status_code=400, detail="Posted timesheet cannot be deleted")
    now = _now_iso()
    connection.execute(
        """
        UPDATE timesheets
        SET marked_for_deletion = 1,
            is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, timesheet_id),
    )
    connection.execute(
        """
        UPDATE timesheet_lines
        SET is_deleted = 1,
            modified_at = ?,
            updated_at = ?
        WHERE timesheet_id = ?
        """,
        (now, now, timesheet_id),
    )
    register_sync_change(connection, entity_type="timesheets", entity_uuid=str(timesheet["uuid"]), operation="DELETE")
    connection.commit()


def _build_timesheet_payroll_records(timesheet: dict[str, Any]) -> list[dict[str, Any]]:
    period_start, _ = _timesheet_period_bounds(timesheet["month_year"])
    records: list[dict[str, Any]] = []
    for line in timesheet["lines"]:
        for day, hours in (line.get("days") or {}).items():
            if float(hours or 0) <= 0:
                continue
            work_date = date(period_start.year, period_start.month, int(day))
            records.append(
                {
                    "recorder_type": "timesheet",
                    "recorder_id": timesheet["id"],
                    "line_number": line["line_number"],
                    "period": timesheet["date"],
                    "object_id": timesheet.get("object_id"),
                    "estimate_id": timesheet.get("estimate_id"),
                    "employee_id": line["employee_id"],
                    "employee_name": line.get("employee_name"),
                    "work_date": work_date.isoformat(),
                    "hours_worked": round(float(hours), 2),
                    "amount": round(float(hours) * float(line.get("hourly_rate", 0) or 0), 2),
                }
            )
    return records


def _find_timesheet_payroll_duplicates(
    connection: sqlite3.Connection,
    *,
    timesheet_id: int,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    duplicates: list[dict[str, Any]] = []
    for record in records:
        row = connection.execute(
            """
            SELECT id
            FROM payroll_register
            WHERE employee_id = ?
              AND work_date = ?
              AND ((object_id = ?) OR (object_id IS NULL AND ? IS NULL))
              AND ((estimate_id = ?) OR (estimate_id IS NULL AND ? IS NULL))
              AND COALESCE(is_deleted, 0) = 0
              AND NOT (recorder_type = 'timesheet' AND recorder_id = ?)
            LIMIT 1
            """,
            (
                record["employee_id"],
                record["work_date"],
                record["object_id"],
                record["object_id"],
                record["estimate_id"],
                record["estimate_id"],
                timesheet_id,
            ),
        ).fetchone()
        if row is not None:
            duplicates.append(record)
    return duplicates


def post_timesheet(connection: sqlite3.Connection, *, timesheet_id: int, user: UserInfo) -> None:
    timesheet = get_timesheet(connection, timesheet_id, user)
    if timesheet["is_posted"]:
        raise HTTPException(status_code=400, detail="Timesheet is already posted")
    if not timesheet["lines"]:
        raise HTTPException(status_code=400, detail="Cannot post an empty timesheet")
    if not any(float(line.get("total_hours", 0) or 0) > 0 for line in timesheet["lines"]):
        raise HTTPException(status_code=400, detail="At least one line must contain working hours before posting")

    records = _build_timesheet_payroll_records(timesheet)
    if not records:
        raise HTTPException(status_code=400, detail="No payroll movements were produced from this timesheet")

    duplicates = _find_timesheet_payroll_duplicates(connection, timesheet_id=timesheet_id, records=records)
    if duplicates:
        details = ", ".join(
            f"{item.get('employee_name') or ('Employee ' + str(item['employee_id']))} {item['work_date']}"
            for item in duplicates[:3]
        )
        suffix = f" and {len(duplicates) - 3} more" if len(duplicates) > 3 else ""
        raise HTTPException(
            status_code=400,
            detail=f"Payroll duplicates found for the selected object/estimate/employee/date: {details}{suffix}",
        )

    connection.execute(
        "DELETE FROM payroll_register WHERE recorder_type = 'timesheet' AND recorder_id = ?",
        (timesheet_id,),
    )
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
                _now_iso(),
                _now_iso(),
                new_uuid(),
                _now_iso(),
            ),
        )
    _post_timesheet_to_actual_costs(connection, timesheet)
    connection.execute(
        "UPDATE timesheets SET is_posted = 1, posted_at = ?, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), _now_iso(), timesheet_id),
    )
    register_sync_change(connection, entity_type="timesheets", entity_uuid=str(timesheet["uuid"]), operation="UPDATE")
    connection.commit()


def unpost_timesheet(connection: sqlite3.Connection, *, timesheet_id: int, user: UserInfo) -> None:
    timesheet = get_timesheet(connection, timesheet_id, user)
    if not timesheet["is_posted"]:
        raise HTTPException(status_code=400, detail="Timesheet is not posted")
    connection.execute(
        "DELETE FROM payroll_register WHERE recorder_type = 'timesheet' AND recorder_id = ?",
        (timesheet_id,),
    )
    _unpost_timesheet_from_actual_costs(connection, timesheet_id)
    connection.execute(
        "UPDATE timesheets SET is_posted = 0, posted_at = NULL, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), timesheet_id),
    )
    register_sync_change(connection, entity_type="timesheets", entity_uuid=str(timesheet["uuid"]), operation="UPDATE")
    connection.commit()


def _distribute_hours(total_hours: float, count: int) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [round(total_hours, 2)]
    base = round(total_hours / count, 2)
    values = [base] * count
    values[-1] = round(total_hours - base * (count - 1), 2)
    return values


def autofill_timesheet_lines(
    connection: sqlite3.Connection,
    *,
    object_id: int,
    estimate_id: int | None,
    month_year: str,
) -> list[dict[str, Any]]:
    period_from, period_to = _timesheet_period_bounds(month_year)
    params: list[Any] = [object_id, period_from.isoformat(), period_to.isoformat()]
    estimate_filter_sql = ""
    if estimate_id:
        estimate_filter_sql = " AND dr.estimate_id = ?"
        params.append(estimate_id)

    line_rows = connection.execute(
        f"""
        SELECT
            drl.id,
            dr.date AS report_date,
            drl.actual_labor
        FROM daily_reports dr
        JOIN estimates e ON e.id = dr.estimate_id
        JOIN daily_report_lines drl ON drl.report_id = dr.id
        WHERE dr.marked_for_deletion = 0
          AND COALESCE(dr.is_deleted, 0) = 0
          AND COALESCE(drl.is_deleted, 0) = 0
          AND COALESCE(drl.marked_for_deletion, 0) = 0
          AND drl.is_group = 0
          AND drl.actual_labor > 0
          AND e.object_id = ?
          AND dr.date >= ?
          AND dr.date <= ?
          {estimate_filter_sql}
        ORDER BY dr.date, drl.id
        """,
        params,
    ).fetchall()
    if not line_rows:
        return []

    line_ids = [int(row["id"]) for row in line_rows]
    placeholders = ", ".join(["?"] * len(line_ids))
    executor_rows = connection.execute(
        f"""
        SELECT
            dre.report_line_id,
            dre.executor_id,
            p.full_name,
            p.hourly_rate
        FROM daily_report_executors dre
        JOIN persons p ON p.id = dre.executor_id
        WHERE dre.report_line_id IN ({placeholders})
        ORDER BY p.full_name
        """,
        line_ids,
    ).fetchall()
    executors_by_line: dict[int, list[dict[str, Any]]] = {}
    for row in executor_rows:
        executors_by_line.setdefault(int(row["report_line_id"]), []).append(row_to_dict(row) or {})

    employee_days: dict[int, dict[int, float]] = {}
    employee_names: dict[int, str] = {}
    employee_rates: dict[int, float] = {}
    for row in line_rows:
        line_id = int(row["id"])
        executors = executors_by_line.get(line_id, [])
        if not executors:
            continue
        shares = _distribute_hours(float(row["actual_labor"] or 0), len(executors))
        report_day = datetime.fromisoformat(str(row["report_date"])).day
        for index, executor in enumerate(executors):
            employee_id = int(executor["executor_id"])
            employee_days.setdefault(employee_id, {})
            employee_days[employee_id][report_day] = round(
                min(24.0, employee_days[employee_id].get(report_day, 0) + shares[index]),
                2,
            )
            employee_names[employee_id] = str(executor["full_name"])
            employee_rates[employee_id] = round(float(executor["hourly_rate"] or 0), 2)

    lines: list[dict[str, Any]] = []
    for line_number, employee_id in enumerate(sorted(employee_days, key=lambda item: employee_names.get(item, "")), start=1):
        days = _normalize_timesheet_days(employee_days[employee_id], month_year)
        total_hours = round(sum(days.values()), 2)
        hourly_rate = employee_rates.get(employee_id, 0.0)
        lines.append(
            {
                "line_number": line_number,
                "employee_id": employee_id,
                "employee_name": employee_names.get(employee_id),
                "hourly_rate": hourly_rate,
                "days": days,
                "total_hours": total_hours,
                "total_amount": round(total_hours * hourly_rate, 2),
            }
        )
    return lines


def copy_timesheet(connection: sqlite3.Connection, *, timesheet_id: int, user: UserInfo) -> dict[str, Any]:
    source = get_timesheet(connection, timesheet_id, user)
    payload = {
        "number": "",
        "date": date.today().isoformat(),
        "object_id": source.get("object_id"),
        "estimate_id": source.get("estimate_id"),
        "foreman_id": source.get("foreman_id"),
        "month_year": source["month_year"],
        "lines": [
            {
                "line_number": index + 1,
                "employee_id": line["employee_id"],
                "hourly_rate": line["hourly_rate"],
                "days": dict(line.get("days") or {}),
            }
            for index, line in enumerate(source["lines"])
        ],
    }
    return save_timesheet(connection, payload=payload, user=user)


def copy_estimate(connection: sqlite3.Connection, *, estimate_id: int) -> dict[str, Any]:
    source = get_estimate(connection, estimate_id)
    payload = {
        "number": "",
        "date": date.today().isoformat(),
        "customer_id": source.get("customer_id"),
        "object_id": source.get("object_id"),
        "contractor_id": source.get("contractor_id"),
        "responsible_id": source.get("responsible_id"),
        "estimate_type": source.get("estimate_type", "General"),
        "contract_id": source.get("contract_id"),
        "supplementary_agreement_id": source.get("supplementary_agreement_id"),
        "notes": source.get("notes"),
        "lines": [
            {
                "work_id": line.get("work_id"),
                "quantity": line.get("quantity", 0),
                "unit": line.get("unit"),
                "price": line.get("price", 0),
                "labor_rate": line.get("labor_rate"),
                "is_group": line.get("is_group", False),
                "parent_group_id": line.get("parent_group_id"),
                "planned_labor": line.get("planned_labor"),
                "material_id": line.get("material_id"),
                "material_quantity": line.get("material_quantity"),
                "material_price": line.get("material_price"),
            }
            for line in source.get("lines", [])
        ],
    }
    return save_estimate(connection, payload=payload)


def copy_daily_report(connection: sqlite3.Connection, *, report_id: int, user: UserInfo) -> dict[str, Any]:
    source = get_daily_report(connection, report_id, user)
    payload = {
        "number": "",
        "date": date.today().isoformat(),
        "estimate_id": source.get("estimate_id"),
        "foreman_id": source.get("foreman_id"),
        "supplementary_agreement_id": source.get("supplementary_agreement_id"),
        "notes": source.get("notes"),
        "lines": [
            {
                "work_id": line.get("work_id"),
                "planned_labor": line.get("planned_labor", 0),
                "actual_labor": line.get("actual_labor", 0),
                "is_group": line.get("is_group", False),
                "parent_group_id": line.get("parent_group_id"),
                "notes": line.get("notes"),
                "executors": [ex["executor_id"] for ex in line.get("executors", [])],
            }
            for line in source.get("lines", [])
        ],
    }
    return save_daily_report(connection, payload=payload, user=user)


def _timesheet_document_info(timesheet: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "timesheet",
        "version": "2.0",
        "number": timesheet["number"],
        "date": timesheet["date"],
        "month_year": timesheet["month_year"],
        "is_posted": bool(timesheet["is_posted"]),
        "object_name": timesheet.get("object_name"),
        "estimate_number": timesheet.get("estimate_number"),
        "foreman_name": timesheet.get("foreman_name"),
    }


def _timesheet_json_payload(timesheet: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_info": _timesheet_document_info(timesheet),
        "lines": [
            {
                "line_number": line["line_number"],
                "employee_name": line.get("employee_name"),
                "hourly_rate": line["hourly_rate"],
                "days_data": {f"day_{day:02d}": value for day, value in (line.get("days") or {}).items()},
                "total_hours": line["total_hours"],
                "total_amount": line["total_amount"],
            }
            for line in timesheet["lines"]
        ],
    }


def _build_timesheet_excel_content_fallback(timesheet: dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Табель"

    title_font = Font(name="Arial", size=14, bold=True)
    header_font = Font(name="Arial", size=10, bold=True)
    data_font = Font(name="Arial", size=9)
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    header_fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
    weekend_fill = PatternFill(start_color="FDE8E8", end_color="FDE8E8", fill_type="solid")

    last_day = _timesheet_days_in_month(timesheet["month_year"])
    current_row = 1
    sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=last_day + 5)
    title_cell = sheet.cell(row=current_row, column=1)
    title_cell.value = f"ТАБЕЛЬ УЧЕТА РАБОЧЕГО ВРЕМЕНИ №{timesheet['number']}"
    title_cell.font = title_font
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    current_row += 2

    info_data = [
        ("Дата документа:", timesheet["date"]),
        ("Период:", timesheet["month_year"]),
        ("Объект:", timesheet.get("object_name") or ""),
        ("Смета:", timesheet.get("estimate_number") or ""),
        ("Бригадир:", timesheet.get("foreman_name") or ""),
        ("Проведен:", "Да" if timesheet["is_posted"] else "Нет"),
    ]
    for label, value in info_data:
        sheet.cell(row=current_row, column=1, value=label).font = header_font
        sheet.cell(row=current_row, column=2, value=value)
        current_row += 1
    current_row += 1

    headers = ["№", "Сотрудник", "Ставка", *[str(day) for day in range(1, last_day + 1)], "Итого часов", "Сумма"]
    header_row = current_row
    for col_index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=header_row, column=col_index, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    current_row += 1

    period_start, _ = _timesheet_period_bounds(timesheet["month_year"])
    for line in timesheet["lines"]:
        column = 1
        row_number = current_row
        values = [
            line["line_number"],
            line.get("employee_name") or "",
            line["hourly_rate"],
            *[(line.get("days") or {}).get(day, 0) or "" for day in range(1, last_day + 1)],
            line["total_hours"],
            line["total_amount"],
        ]
        for value in values:
            cell = sheet.cell(row=row_number, column=column, value=value)
            cell.font = data_font
            cell.border = border
            if column != 2:
                cell.alignment = Alignment(horizontal="center")
            column += 1
        current_row += 1

    total_hours, total_amount = _timesheet_totals(timesheet["lines"])
    total_row = current_row
    sheet.cell(row=total_row, column=1, value="Итого").font = header_font
    sheet.cell(row=total_row, column=last_day + 4, value=total_hours).font = header_font
    sheet.cell(row=total_row, column=last_day + 5, value=total_amount).font = header_font

    for day in range(1, last_day + 1):
        date_value = date(period_start.year, period_start.month, day)
        if date_value.weekday() >= 5:
            column = 3 + day
            for row_index in range(header_row, total_row + 1):
                sheet.cell(row=row_index, column=column).fill = weekend_fill

    for col in range(1, len(headers) + 1):
        if col == 2:
            width = 28
        elif col == 3:
            width = 10
        elif 4 <= col <= last_day + 3:
            width = 4.5
        else:
            width = 12
        sheet.column_dimensions[get_column_letter(col)].width = width

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.read()


def _timesheet_template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "табель_пример.xlsx"


def _format_timesheet_date_label(raw_value: Any) -> str:
    if not raw_value:
        return ""
    if isinstance(raw_value, date):
        return raw_value.strftime("%d.%m.%Y")
    text = str(raw_value).strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text).strftime("%d.%m.%Y")
    except ValueError:
        return text


def _format_timesheet_period_label(month_year: str) -> str:
    period_start, _ = _timesheet_period_bounds(month_year)
    month_names = [
        "",
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]
    return f"{month_names[period_start.month]} {period_start.year}"


def _decode_possible_cp1251_mojibake(value: str) -> str:
    try:
        decoded = value.encode("latin1").decode("cp1251")
    except UnicodeError:
        return value
    return decoded if decoded else value


def _parse_timesheet_period_import_value(raw_value: Any) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""
    if len(text) == 7 and text[4] == "-":
        _timesheet_period_bounds(text)
        return text

    normalized_text = _decode_possible_cp1251_mojibake(text).strip().lower()
    normalized_text = normalized_text.replace(".", " ")
    parts = [part for part in normalized_text.split() if part]
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Month period must be in YYYY-MM format")

    months = {
        "январь": 1,
        "января": 1,
        "февраль": 2,
        "февраля": 2,
        "март": 3,
        "марта": 3,
        "апрель": 4,
        "апреля": 4,
        "май": 5,
        "мая": 5,
        "июнь": 6,
        "июня": 6,
        "июль": 7,
        "июля": 7,
        "август": 8,
        "августа": 8,
        "сентябрь": 9,
        "сентября": 9,
        "октябрь": 10,
        "октября": 10,
        "ноябрь": 11,
        "ноября": 11,
        "декабрь": 12,
        "декабря": 12,
    }
    month = months.get(parts[0])
    year = int(parts[-1]) if parts[-1].isdigit() else 0
    if not month or year <= 0:
        raise HTTPException(status_code=400, detail="Month period must be in YYYY-MM format")
    return f"{year:04d}-{month:02d}"


def _parse_timesheet_date_import_value(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, datetime):
        return raw_value.date().isoformat()
    if isinstance(raw_value, date):
        return raw_value.isoformat()
    text = str(raw_value).strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _normalize_timesheet_import_header(value: Any) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def _try_parse_timesheet_import_date(raw_value: Any) -> date | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value.date()
    if isinstance(raw_value, date):
        return raw_value

    text = str(raw_value).strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _try_parse_timesheet_period_from_range_header(raw_value: Any) -> str:
    text = _decode_possible_cp1251_mojibake(str(raw_value or "")).strip()
    if not text:
        return ""

    matches = re.findall(r"(\d{2}[.\-]\d{2}[.\-]\d{2,4})", text)
    if len(matches) < 2:
        return ""

    start_date = _try_parse_timesheet_import_date(matches[0])
    end_date = _try_parse_timesheet_import_date(matches[1])
    if start_date is None or end_date is None:
        return ""

    if start_date.year != end_date.year or start_date.month != end_date.month:
        raise HTTPException(
            status_code=400,
            detail="The import file spans multiple months. Split it into a single month before importing.",
        )

    return f"{start_date.year:04d}-{start_date.month:02d}"


def _extract_timesheet_day_columns_from_date_headers(
    sheet: Any,
    *,
    header_row: int,
    start_column: int,
) -> tuple[str, dict[int, int]]:
    month_year = ""
    day_columns: dict[int, int] = {}
    started = False

    for column in range(start_column, sheet.max_column + 1):
        header_value = sheet.cell(row=header_row, column=column).value
        parsed_date = _try_parse_timesheet_import_date(header_value)
        if parsed_date is not None:
            started = True
            current_month_year = f"{parsed_date.year:04d}-{parsed_date.month:02d}"
            if not month_year:
                month_year = current_month_year
            elif month_year != current_month_year:
                raise HTTPException(
                    status_code=400,
                    detail="The import file spans multiple months. Split it into a single month before importing.",
                )
            day_columns[parsed_date.day] = column
            continue

        normalized_header = _normalize_timesheet_import_header(header_value)
        if started and normalized_header in {"итого", "сумма", "итого часы", "итого на выходе"}:
            break

    return month_year, day_columns


def _copy_excel_row_style(sheet: Any, *, source_row: int, target_row: int, max_column: int) -> None:
    source_height = sheet.row_dimensions[source_row].height
    if source_height is not None:
        sheet.row_dimensions[target_row].height = source_height
    for column in range(1, max_column + 1):
        source_cell = sheet.cell(row=source_row, column=column)
        target_cell = sheet.cell(row=target_row, column=column)
        if source_cell.has_style:
            target_cell._style = copy(source_cell._style)


def _build_timesheet_excel_content(timesheet: dict[str, Any]) -> bytes:
    from openpyxl import load_workbook

    template_path = _timesheet_template_path()
    if not template_path.exists():
        return _build_timesheet_excel_content_fallback(timesheet)

    workbook = load_workbook(template_path)
    sheet = workbook.active

    max_days = 31
    data_start_row = 10
    inserted_row_anchor = 11
    total_template_row = 12
    signature_template_row = 14
    signature_caption_template_row = 15

    lines = timesheet["lines"] or [
        {
            "line_number": 1,
            "employee_name": "",
            "hourly_rate": "",
            "days": {},
            "total_hours": "",
            "total_amount": "",
        }
    ]

    extra_rows = max(0, len(lines) - 1)
    if extra_rows:
        sheet.insert_rows(inserted_row_anchor, extra_rows)
        for row_index in range(inserted_row_anchor, inserted_row_anchor + extra_rows):
            _copy_excel_row_style(sheet, source_row=data_start_row, target_row=row_index, max_column=36)

    total_row = total_template_row + extra_rows
    signature_row = signature_template_row + extra_rows
    signature_caption_row = signature_caption_template_row + extra_rows

    merged_total_range = "A12:C12"
    if merged_total_range in {str(item) for item in sheet.merged_cells.ranges}:
        sheet.unmerge_cells(merged_total_range)
    sheet.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=3)

    sheet["A1"] = f"ТАБЕЛЬ УЧЕТА РАБОЧЕГО ВРЕМЕНИ №{timesheet['number']}"
    sheet["A3"] = "Дата:"
    sheet["B3"] = _format_timesheet_date_label(timesheet["date"])
    sheet["A4"] = "Период:"
    sheet["B4"] = _format_timesheet_period_label(timesheet["month_year"])
    sheet["A5"] = "Объект:"
    sheet["B5"] = timesheet.get("object_name") or ""
    sheet["A6"] = "Смета №:"
    sheet["B6"] = timesheet.get("estimate_number") or ""
    sheet["A7"] = "Бригадир:"
    sheet["B7"] = timesheet.get("foreman_name") or ""

    last_day = _timesheet_days_in_month(timesheet["month_year"])
    for day in range(1, max_days + 1):
        sheet.cell(row=9, column=3 + day, value=day)

    for row_offset, line in enumerate(lines):
        row_number = data_start_row + row_offset
        days = line.get("days") or {}
        sheet.cell(row=row_number, column=1, value=line.get("line_number") or row_offset + 1)
        sheet.cell(row=row_number, column=2, value=line.get("employee_name") or "")
        hourly_rate = line.get("hourly_rate")
        sheet.cell(row=row_number, column=3, value=hourly_rate if hourly_rate not in ("", None) else "")
        for day in range(1, max_days + 1):
            value = ""
            if day <= last_day:
                hours = days.get(day, 0)
                value = hours if float(hours or 0) > 0 else ""
            sheet.cell(row=row_number, column=3 + day, value=value)
        total_hours = line.get("total_hours")
        total_amount = line.get("total_amount")
        sheet.cell(row=row_number, column=35, value=total_hours if total_hours not in ("", None) else "")
        sheet.cell(row=row_number, column=36, value=total_amount if total_amount not in ("", None) else "")

    total_hours, total_amount = _timesheet_totals(timesheet["lines"])
    sheet.cell(row=total_row, column=1, value="ИТОГО:")
    sheet.cell(row=total_row, column=35, value=total_hours)
    sheet.cell(row=total_row, column=36, value=total_amount)

    sheet.cell(row=signature_row, column=1, value="Бригадир:")
    sheet.cell(row=signature_row, column=2, value="_______________")
    sheet.cell(row=signature_row, column=4, value="____________________")
    sheet.cell(row=signature_caption_row, column=4, value="(подпись)")

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.read()


def build_timesheet_print(timesheet: dict[str, Any], output_format: str) -> tuple[bytes, str, str]:
    if output_format == "excel":
        return (
            _build_timesheet_excel_content(timesheet),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"timesheet_{timesheet['id']}.xlsx",
        )

    lines = [
        f"Номер: {timesheet['number']}",
        f"Дата: {timesheet['date']}",
        f"Период: {timesheet['month_year']}",
        f"Объект: {timesheet.get('object_name') or '-'}",
        f"Смета: {timesheet.get('estimate_number') or '-'}",
        f"Бригадир: {timesheet.get('foreman_name') or '-'}",
        "",
    ]
    for line in timesheet["lines"]:
        day_values = ", ".join(
            f"{day}:{hours}"
            for day, hours in (line.get("days") or {}).items()
            if float(hours or 0) > 0
        )
        lines.append(
            f"{line['line_number']}. {line.get('employee_name') or '-'} | ставка {line['hourly_rate']} | "
            f"часы {line['total_hours']} | сумма {line['total_amount']} | дни {day_values or '-'}"
        )
    return build_pdf("Timesheet Print Form", lines), "application/pdf", f"timesheet_{timesheet['id']}.pdf"


def export_timesheet_data(timesheet: dict[str, Any], output_format: str) -> tuple[bytes, str, str]:
    if output_format == "json":
        payload = json.dumps(_timesheet_json_payload(timesheet), ensure_ascii=False, indent=2).encode("utf-8")
        return payload, "application/json; charset=utf-8", f"timesheet_{timesheet['id']}.json"
    if output_format == "excel":
        return build_timesheet_print(timesheet, "excel")
    raise HTTPException(status_code=400, detail="Unsupported export format")


def _get_employee_id_by_name(connection: sqlite3.Connection, employee_name: str) -> int | None:
    normalized_name = employee_name.strip()
    row = connection.execute(
        """
        SELECT id
        FROM persons
        WHERE lower(trim(full_name)) = lower(trim(?))
          AND marked_for_deletion = 0
          AND COALESCE(is_deleted, 0) = 0
        LIMIT 1
        """,
        (normalized_name,),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def _find_employee_id_by_name(connection: sqlite3.Connection, employee_name: str) -> int:
    employee_id = _get_employee_id_by_name(connection, employee_name)
    if employee_id is None:
        raise HTTPException(status_code=400, detail=f"Employee '{employee_name}' was not found")
    return employee_id


def _normalize_import_hourly_rate(value: Any) -> float:
    try:
        return max(0.0, round(float(value or 0), 2))
    except (TypeError, ValueError):
        return 0.0


def _optional_import_hourly_rate(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return _normalize_import_hourly_rate(value)


def _normalize_import_employee_name(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_import_text(value: Any) -> str | None:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized or None


def _normalize_personnel_number(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, float):
        raw_value = str(int(value)) if value.is_integer() else format(value, "f").rstrip("0").rstrip(".")
    else:
        raw_value = str(value)
    compact = "".join(raw_value.replace("\u00a0", " ").split())
    if not compact:
        return ""
    if compact.isdigit():
        compact = compact.lstrip("0") or "0"
    return compact.upper()


def _find_person_rows_by_name(connection: sqlite3.Connection, employee_name: str) -> list[dict[str, Any]]:
    normalized_name = _normalize_import_employee_name(employee_name)
    if not normalized_name:
        return []
    rows = connection.execute(
        """
        SELECT id, full_name, personnel_number
        FROM persons
        WHERE lower(trim(full_name)) = lower(trim(?))
          AND marked_for_deletion = 0
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY id
        """,
        (normalized_name,),
    ).fetchall()
    return rows_to_dicts(rows)


def _find_person_rows_by_personnel_number(connection: sqlite3.Connection, personnel_number: Any) -> list[dict[str, Any]]:
    normalized_number = _normalize_personnel_number(personnel_number)
    if not normalized_number:
        return []
    rows = connection.execute(
        """
        SELECT id, full_name, personnel_number
        FROM persons
        WHERE COALESCE(personnel_number, '') <> ''
          AND marked_for_deletion = 0
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY id
        """
    ).fetchall()
    return [
        item
        for item in rows_to_dicts(rows)
        if _normalize_personnel_number(item.get("personnel_number")) == normalized_number
    ]


def _resolve_timesheet_import_employee(
    connection: sqlite3.Connection,
    *,
    employee_name: str,
    personnel_number: Any = None,
) -> tuple[int | None, str | None, str | None]:
    number_matches = _find_person_rows_by_personnel_number(connection, personnel_number)
    name_matches = _find_person_rows_by_name(connection, employee_name)

    if number_matches:
        if len(number_matches) != 1:
            return None, None, None
        number_match = number_matches[0]
        if name_matches:
            if len(name_matches) != 1 or int(name_matches[0]["id"]) != int(number_match["id"]):
                return None, None, None
        return int(number_match["id"]), str(number_match["full_name"]), "personnel_number"

    if name_matches:
        if len(name_matches) != 1:
            return None, None, None
        name_match = name_matches[0]
        return int(name_match["id"]), str(name_match["full_name"]), "full_name"

    return None, None, None


def _build_imported_timesheet_row(
    connection: sqlite3.Connection,
    *,
    source_line_number: int,
    employee_name: str,
    month_year: str,
    days: dict[int, Any],
    hourly_rate: Any = None,
    personnel_number: Any = None,
    position: Any = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    normalized_name = _normalize_import_employee_name(employee_name)
    normalized_days = _normalize_timesheet_days(days, month_year)
    normalized_hourly_rate = _optional_import_hourly_rate(hourly_rate)
    normalized_personnel_number = _normalize_import_text(personnel_number)
    normalized_position = _normalize_import_text(position)
    matched_employee_id, matched_employee_name, matched_by = _resolve_timesheet_import_employee(
        connection,
        employee_name=normalized_name,
        personnel_number=normalized_personnel_number,
    )

    matched_line = None
    total_hours = round(sum(normalized_days.values()), 2)
    total_amount = round(total_hours * float(normalized_hourly_rate or 0), 2)
    if matched_employee_id is not None:
        line_payload: dict[str, Any] = {
            "line_number": source_line_number,
            "employee_id": matched_employee_id,
            "days": normalized_days,
        }
        if normalized_hourly_rate is not None:
            line_payload["hourly_rate"] = normalized_hourly_rate
        matched_line = _hydrate_timesheet_line(
            connection,
            line=line_payload,
            month_year=month_year,
        )
        matched_line["employee_name"] = matched_employee_name or normalized_name
        total_hours = float(matched_line["total_hours"] or 0)
        total_amount = float(matched_line["total_amount"] or 0)

    return (
        {
            "source_line_number": source_line_number,
            "employee_name": normalized_name,
            "personnel_number": normalized_personnel_number,
            "position": normalized_position,
            "hourly_rate": normalized_hourly_rate,
            "days": normalized_days,
            "total_hours": total_hours,
            "total_amount": total_amount,
            "matched_employee_id": matched_employee_id,
            "matched_employee_name": matched_employee_name,
            "matched_by": matched_by,
        },
        matched_line,
    )


def _register_missing_timesheet_employee(
    missing_by_name: dict[str, dict[str, Any]],
    *,
    employee_name: str,
    hourly_rate: Any,
    source_line_number: int,
) -> None:
    normalized_name = " ".join(employee_name.split()).strip()
    if not normalized_name:
        return

    item = missing_by_name.get(normalized_name.casefold())
    normalized_rate = _normalize_import_hourly_rate(hourly_rate)
    if item is None:
        missing_by_name[normalized_name.casefold()] = {
            "employee_name": normalized_name,
            "hourly_rate": normalized_rate,
            "source_line_numbers": [source_line_number],
        }
        return

    if source_line_number not in item["source_line_numbers"]:
        item["source_line_numbers"].append(source_line_number)
    if float(item.get("hourly_rate") or 0) == 0 and normalized_rate > 0:
        item["hourly_rate"] = normalized_rate


def _parse_timesheet_json_import(connection: sqlite3.Connection, content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON import file") from exc

    if payload.get("document_info", {}).get("type") != "timesheet":
        raise HTTPException(status_code=400, detail="The imported JSON file is not a timesheet")

    document_info = dict(payload.get("document_info") or {})
    month_year = str(document_info.get("month_year") or "")
    _timesheet_period_bounds(month_year)
    lines: list[dict[str, Any]] = []
    imported_rows: list[dict[str, Any]] = []
    missing_by_name: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(payload.get("lines", []), start=1):
        employee_name = str(item.get("employee_name") or "").strip()
        if not employee_name:
            continue
        days_data = {}
        for raw_key, raw_hours in (item.get("days_data") or {}).items():
            if not str(raw_key).startswith("day_"):
                continue
            try:
                day = int(str(raw_key).split("_", 1)[1])
            except ValueError:
                continue
            days_data[day] = raw_hours
        source_line_number = int(item.get("line_number") or index)
        imported_row, matched_line = _build_imported_timesheet_row(
            connection,
            source_line_number=source_line_number,
            employee_name=employee_name,
            month_year=month_year,
            days=days_data,
            hourly_rate=item.get("hourly_rate") if "hourly_rate" in item else None,
            personnel_number=item.get("personnel_number"),
            position=item.get("position") or item.get("profession"),
        )
        imported_rows.append(imported_row)
        if matched_line is None:
            _register_missing_timesheet_employee(
                missing_by_name,
                employee_name=employee_name,
                hourly_rate=item.get("hourly_rate"),
                source_line_number=source_line_number,
            )
            continue
        lines.append(matched_line)
    missing_employees = list(missing_by_name.values())
    return {
        "document_info": document_info,
        "lines": lines,
        "imported_rows": imported_rows,
        "missing_employees": missing_employees,
        "requires_employee_creation": bool(missing_employees),
    }


def _parse_alternative_timesheet_excel_import(
    connection: sqlite3.Connection,
    *,
    sheet: Any,
    document_info: dict[str, Any],
    header_row: int,
) -> dict[str, Any]:
    detected_month_year, day_columns = _extract_timesheet_day_columns_from_date_headers(
        sheet,
        header_row=header_row,
        start_column=6,
    )
    month_year = str(document_info.get("month_year") or detected_month_year or "")
    _timesheet_period_bounds(month_year)
    if not day_columns:
        raise HTTPException(status_code=400, detail="The import file does not contain recognizable day columns")

    lines: list[dict[str, Any]] = []
    imported_rows: list[dict[str, Any]] = []
    missing_by_name: dict[str, dict[str, Any]] = {}
    current_row = header_row + 1

    while current_row <= sheet.max_row:
        source_index = sheet.cell(row=current_row, column=1).value
        employee_name = str(sheet.cell(row=current_row, column=3).value or "").strip()
        source_line_number = len(lines) + sum(len(item["source_line_numbers"]) for item in missing_by_name.values()) + 1
        try:
            if source_index not in (None, ""):
                source_line_number = int(float(source_index))
        except (TypeError, ValueError):
            pass

        if not employee_name:
            current_row += 1
            continue

        days: dict[int, Any] = {}
        for day, column in day_columns.items():
            value = sheet.cell(row=current_row, column=column).value
            if value not in (None, ""):
                days[day] = value

        imported_row, matched_line = _build_imported_timesheet_row(
            connection,
            source_line_number=source_line_number,
            employee_name=employee_name,
            month_year=month_year,
            days=days,
            hourly_rate=sheet.cell(row=current_row, column=5).value,
            personnel_number=sheet.cell(row=current_row, column=2).value,
            position=sheet.cell(row=current_row, column=4).value,
        )
        imported_rows.append(imported_row)
        if matched_line is None:
            _register_missing_timesheet_employee(
                missing_by_name,
                employee_name=employee_name,
                hourly_rate=sheet.cell(row=current_row, column=5).value,
                source_line_number=source_line_number,
            )
            current_row += 1
            continue

        lines.append(matched_line)
        current_row += 1

    document_info["month_year"] = month_year
    missing_employees = list(missing_by_name.values())
    return {
        "document_info": document_info,
        "lines": lines,
        "imported_rows": imported_rows,
        "missing_employees": missing_employees,
        "requires_employee_creation": bool(missing_employees),
    }


def _parse_timesheet_excel_import(connection: sqlite3.Connection, content: bytes) -> dict[str, Any]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The import file must be a valid XLSX workbook") from exc
    sheet = workbook.active

    document_info: dict[str, Any] = {}
    for row_index in range(1, min(sheet.max_row, 20) + 1):
        label = sheet.cell(row=row_index, column=1).value
        value = sheet.cell(row=row_index, column=2).value
        if label == "Дата документа:":
            document_info["date"] = _parse_timesheet_date_import_value(value)
        elif label == "Дата:":
            document_info["date"] = _parse_timesheet_date_import_value(value)
        elif label == "Период:":
            document_info["month_year"] = _parse_timesheet_period_import_value(value)
        elif label == "Объект:":
            document_info["object_name"] = str(value or "")
        elif label == "Смета:":
            document_info["estimate_number"] = str(value or "")
        elif label == "Смета №:":
            document_info["estimate_number"] = str(value or "")
        elif label == "Бригадир:":
            document_info["foreman_name"] = str(value or "")
        elif not document_info.get("month_year"):
            detected_period = _try_parse_timesheet_period_from_range_header(label) or _try_parse_timesheet_period_from_range_header(value)
            if detected_period:
                document_info["month_year"] = detected_period

    month_year = str(document_info.get("month_year") or "")

    header_row = None
    header_layout = ""
    for row_index in range(1, min(sheet.max_row, 40) + 1):
        first_header = _normalize_timesheet_import_header(sheet.cell(row=row_index, column=1).value)
        second_header = _normalize_timesheet_import_header(sheet.cell(row=row_index, column=2).value)
        third_header = _normalize_timesheet_import_header(sheet.cell(row=row_index, column=3).value)
        if first_header.startswith("№") and second_header == "сотрудник":
            header_row = row_index
            header_layout = "standard"
            break
        if first_header.startswith("№") and second_header == "табельный номер" and third_header.replace(" ", "") == "фио":
            header_row = row_index
            header_layout = "alternative"
            break
    if header_row is None:
        raise HTTPException(status_code=400, detail="The import file does not contain a recognizable timesheet table")
    if header_layout == "alternative":
        return _parse_alternative_timesheet_excel_import(
            connection,
            sheet=sheet,
            document_info=document_info,
            header_row=header_row,
        )

    _timesheet_period_bounds(month_year)
    last_day = _timesheet_days_in_month(month_year)
    lines: list[dict[str, Any]] = []
    imported_rows: list[dict[str, Any]] = []
    missing_by_name: dict[str, dict[str, Any]] = {}
    current_row = header_row + 1
    while current_row <= sheet.max_row:
        first_cell = str(sheet.cell(row=current_row, column=1).value or "").strip()
        normalized_first = first_cell.lower()
        if normalized_first.startswith("итого") or normalized_first.startswith("бригадир"):
            break
        try:
            source_line_number = int(float(first_cell))
        except (TypeError, ValueError):
            source_line_number = len(lines) + sum(len(item["source_line_numbers"]) for item in missing_by_name.values()) + 1

        employee_name = str(sheet.cell(row=current_row, column=2).value or "").strip()
        if not employee_name:
            current_row += 1
            continue
        days = {}
        for day in range(1, last_day + 1):
            value = sheet.cell(row=current_row, column=3 + day).value
            if value not in (None, ""):
                days[day] = value
        imported_row, matched_line = _build_imported_timesheet_row(
            connection,
            source_line_number=source_line_number,
            employee_name=employee_name,
            month_year=month_year,
            days=days,
            hourly_rate=sheet.cell(row=current_row, column=3).value,
        )
        imported_rows.append(imported_row)
        if matched_line is None:
            _register_missing_timesheet_employee(
                missing_by_name,
                employee_name=employee_name,
                hourly_rate=sheet.cell(row=current_row, column=3).value,
                source_line_number=source_line_number,
            )
            current_row += 1
            continue
        lines.append(matched_line)
        current_row += 1
    missing_employees = list(missing_by_name.values())
    return {
        "document_info": document_info,
        "lines": lines,
        "imported_rows": imported_rows,
        "missing_employees": missing_employees,
        "requires_employee_creation": bool(missing_employees),
    }


def preview_timesheet_import(
    connection: sqlite3.Connection,
    *,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    lower_name = filename.lower()
    if lower_name.endswith(".json"):
        return _parse_timesheet_json_import(connection, content)
    return _parse_timesheet_excel_import(connection, content)


# ═══════════════════════════════════════════════════════════════════════════
# Cost Accounting Integration
# ═══════════════════════════════════════════════════════════════════════════


COST_ELEMENT_KINDS = [
    ("M", "Материалы", "materials", True),
    ("L", "Основная заработная плата", "labor", True),
    ("MM", "Эксплуатация машин и механизмов", "machinery", True),
    ("SC", "Субподрядные работы", "subcontract", True),
    ("PD", "Прочие прямые затраты", "other_direct", True),
    ("OH", "Накладные расходы", "overhead", False),
]

ALLOCATION_BASES = [
    ("Пропорционально ФОТ", "payroll"),
    ("Пропорционально прямым затратам", "direct_costs"),
    ("Пропорционально человеко-дням", "labor_days"),
]


def _ensure_cost_elements_exist(connection: sqlite3.Connection) -> None:
    """Create predefined cost elements and allocation bases if not present."""
    for code, name, kind, is_direct in COST_ELEMENT_KINDS:
        existing = connection.execute(
            "SELECT id FROM cost_elements WHERE kind = ?", (kind,)
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO cost_elements (code, name, kind, is_direct, is_predefined, created_at, modified_at) "
                "VALUES (?, ?, ?, ?, 1, ?, ?)",
                (code, name, kind, int(is_direct), _now_iso(), _now_iso()),
            )
    for name, kind in ALLOCATION_BASES:
        existing = connection.execute(
            "SELECT id FROM allocation_bases WHERE kind = ?", (kind,)
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO allocation_bases (name, kind, created_at, modified_at) "
                "VALUES (?, ?, ?, ?)",
                (name, kind, _now_iso(), _now_iso()),
            )


def _get_cost_element_id(connection: sqlite3.Connection, kind: str) -> int | None:
    """Resolve cost element ID by kind string (materials, labor, etc.)."""
    row = connection.execute(
        "SELECT id FROM cost_elements WHERE kind = ? AND marked_for_deletion = 0",
        (kind,),
    ).fetchone()
    return int(row["id"]) if row else None


def _period_from_date_str(date_str: str | None) -> str:
    """Extract YYYY-MM period from a date string."""
    if not date_str:
        return datetime.now().strftime("%Y-%m")
    return str(date_str)[:7]


# ── Estimate → PlannedCosts ───────────────────────────────────────────────

def _post_estimate_to_planned_costs(
    connection: sqlite3.Connection, estimate: dict[str, Any]
) -> None:
    """Write estimate lines to the planned_costs register."""
    _ensure_cost_elements_exist(connection)
    materials_ce = _get_cost_element_id(connection, "materials")
    labor_ce = _get_cost_element_id(connection, "labor")
    if not materials_ce and not labor_ce:
        return  # Cost elements not available — skip

    period = _period_from_date_str(estimate.get("date"))
    estimate_id = int(estimate["id"])
    object_id = estimate.get("object_id")

    # Clear old planned-cost movements for this estimate
    connection.execute(
        "DELETE FROM planned_costs WHERE estimate_id = ?", (estimate_id,)
    )

    for line in estimate.get("lines", []):
        if line.get("is_group") or not line.get("work_id"):
            continue

        work_id = int(line["work_id"])
        quantity = float(line.get("quantity") or 0)
        line_sum = float(line.get("sum") or 0)
        materials_amount = float(line.get("material_sum") or 0)
        if materials_amount == 0 and line_sum > 0:
            # No detail — assume entire sum is materials
            materials_amount = line_sum

        if materials_amount > 0 and materials_ce is not None:
            connection.execute(
                """INSERT INTO planned_costs
                   (period, estimate_id, object_id, work_id, cost_element_id,
                    planned_quantity, planned_amount, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    period, estimate_id, object_id, work_id, materials_ce,
                    quantity, round(materials_amount, 2), _now_iso(),
                ),
            )

        labor_rate = float(line.get("labor_rate") or 0)
        planned_labor = float(line.get("planned_labor") or 0)
        labor_amount = 0.0
        if labor_rate > 0 and planned_labor > 0:
            labor_amount = labor_rate * planned_labor
        elif labor_rate > 0:
            labor_amount = labor_rate * quantity

        if labor_amount > 0 and labor_ce is not None:
            connection.execute(
                """INSERT INTO planned_costs
                   (period, estimate_id, object_id, work_id, cost_element_id,
                    planned_quantity, planned_amount, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    period, estimate_id, object_id, work_id, labor_ce,
                    planned_labor or quantity, round(labor_amount, 2), _now_iso(),
                ),
            )


def _unpost_estimate_from_planned_costs(
    connection: sqlite3.Connection, estimate_id: int
) -> None:
    connection.execute(
        "DELETE FROM planned_costs WHERE estimate_id = ?", (estimate_id,)
    )


# ── DailyReport → ActualCosts (LABOR) ────────────────────────────────────

def _post_daily_report_to_actual_costs(
    connection: sqlite3.Connection, report: dict[str, Any]
) -> None:
    """Write daily-report labour movements to actual_costs register."""
    _ensure_cost_elements_exist(connection)
    labor_ce = _get_cost_element_id(connection, "labor")
    if labor_ce is None:
        return

    report_id = int(report["id"])
    period = _period_from_date_str(report.get("date"))
    doc_date = str(report.get("date", ""))[:10] or datetime.now().strftime("%Y-%m-%d")

    # Clear old movements
    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'DailyReport' AND registrar_id = ?",
        (report_id,),
    )

    object_id = report.get("object_id")
    estimate_id = report.get("estimate_id")

    for line in report.get("lines", []):
        if line.get("is_group") or not line.get("work_id"):
            continue
        work_id = int(line["work_id"])
        actual_labor = float(line.get("actual_labor") or 0)
        if actual_labor <= 0:
            continue

        # Resolve work price (labor_rate)
        price = float(line.get("price") or 0)
        if price == 0:
            work_row = connection.execute(
                "SELECT labor_rate FROM works WHERE id = ?", (work_id,)
            ).fetchone()
            price = float(work_row["labor_rate"]) if work_row else 0.0

        amount = round(actual_labor * price, 2)

        connection.execute(
            """INSERT INTO actual_costs
               (period, date, registrar_type, registrar_id, object_id, estimate_id,
                work_id, cost_element_id, quantity, amount, created_at)
               VALUES (?, ?, 'DailyReport', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                period, doc_date, report_id, object_id, estimate_id,
                work_id, labor_ce, actual_labor, amount, _now_iso(),
            ),
        )


def _unpost_daily_report_from_actual_costs(
    connection: sqlite3.Connection, report_id: int
) -> None:
    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'DailyReport' AND registrar_id = ?",
        (report_id,),
    )


# ── Timesheet → ActualCosts (LABOR) ──────────────────────────────────────

def _post_timesheet_to_actual_costs(
    connection: sqlite3.Connection, timesheet: dict[str, Any]
) -> None:
    """Write timesheet labour movements to actual_costs register."""
    _ensure_cost_elements_exist(connection)
    labor_ce = _get_cost_element_id(connection, "labor")
    if labor_ce is None:
        return

    timesheet_id = int(timesheet["id"])
    month_year = timesheet.get("month_year", "")
    try:
        year, month = map(int, month_year.split("-"))
    except (ValueError, AttributeError):
        return

    # Clear old movements
    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'Timesheet' AND registrar_id = ?",
        (timesheet_id,),
    )

    object_id = timesheet.get("object_id")
    estimate_id = timesheet.get("estimate_id")

    for line in timesheet.get("lines", []):
        total_hours = float(line.get("total_hours") or 0)
        if total_hours <= 0:
            continue
        hourly_rate = float(line.get("hourly_rate") or 0)
        amount = round(total_hours * hourly_rate, 2)
        if amount <= 0:
            continue

        # Use the middle of the month as the date
        doc_date = date(year, month, 15).isoformat()
        period = month_year

        # We don't have a specific work_id from timesheet lines,
        # so we use object-level aggregation (work_id=0)
        connection.execute(
            """INSERT INTO actual_costs
               (period, date, registrar_type, registrar_id, object_id, estimate_id,
                work_id, cost_element_id, quantity, amount, created_at)
               VALUES (?, ?, 'Timesheet', ?, ?, ?, 0, ?, ?, ?, ?)""",
            (
                period, doc_date, timesheet_id, object_id, estimate_id,
                labor_ce, total_hours, amount, _now_iso(),
            ),
        )


def _unpost_timesheet_from_actual_costs(
    connection: sqlite3.Connection, timesheet_id: int
) -> None:
    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'Timesheet' AND registrar_id = ?",
        (timesheet_id,),
    )
