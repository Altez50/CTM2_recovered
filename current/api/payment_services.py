"""Service layer for the payment calendar subsystem.

Implements CRUD + posting for two documents (payment_schedules, payment_transactions)
and query helpers for the payment_schedule_register, following the same patterns as
api.services (document -> posting -> register).
"""

from __future__ import annotations
from api.trade_access import add_scope, add_schedule_scope, require_contract, require_payment_links, require_schedule, rollback_on_error, organizations, require_posted_payment, add_payment_scope, add_cash_history_scope

import sqlite3
from datetime import date, datetime, timedelta
from math import ceil
from typing import Any

from fastapi import HTTPException

from api.database import last_insert_id, new_uuid, register_sync_change, row_to_dict, rows_to_dicts, utcnow_iso
from api.goods_services import (
    apply_payment_to_settlements,
    remove_payment_from_settlements,
    suggest_incoming_from_goods_issues,
    suggest_outgoing_from_goods_receipts,
)
from api.models.auth import UserInfo
from api.models.common import Pagination
from api.list_query import apply_quick_filters, order_by_clause
from api.trade_settlement_rules import money, validate_contract, lock_settlement_contracts


def _now_iso() -> str:
    return utcnow_iso()


def _normalize_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 500)
    return page, page_size


def _build_pagination(page: int, page_size: int, total: int) -> Pagination:
    pages = ceil(total / page_size) if total else 1
    return Pagination(page=page, page_size=page_size, total=total, pages=pages)


def _cast_flags(item: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        if key in item and item[key] is not None:
            item[key] = bool(item[key])
    return item


def _coerce_bools(payload: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(payload.items()):
        if isinstance(value, bool):
            payload[key] = int(value)
    return payload


def _require_admin(user: UserInfo) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can post documents")


def _require_write(user: UserInfo) -> None:
    if user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions for this operation")


# ---------------------------------------------------------------------------
# Payment schedules: list / get / save / delete
# ---------------------------------------------------------------------------


def list_payment_schedules(
    connection: sqlite3.Connection,
    *,
    page: int,
    page_size: int,
    search: str | None = None,
    object_id: int | None = None,
    contract_id: int | None = None,
    is_posted: bool | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], Pagination]:
    page, page_size = _normalize_page(page, page_size)
    where_parts = ["ps.marked_for_deletion = 0"]
    params: list[Any] = []
    if search:
        where_parts.append("(ps.number LIKE ? OR o.name LIKE ? OR ct.number LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    if object_id:
        where_parts.append("ps.object_id = ?")
        params.append(object_id)
    if contract_id:
        where_parts.append("ps.contract_id = ?")
        params.append(contract_id)
    if is_posted is not None:
        where_parts.append("ps.is_posted = ?")
        params.append(int(bool(is_posted)))
    apply_quick_filters(
        where_parts,
        params,
        filters,
        {
            "number": ("ps.number", "like"),
            "date_from": ("ps.date_from", "eq"),
            "is_posted": ("ps.is_posted", "eq"),
            "object_name": ("o.name", "like"),
            "contract_number": ("ct.number", "like"),
        },
    )
    add_schedule_scope(connection, where_parts, params)
    where_sql = " AND ".join(where_parts)
    order = order_by_clause(
        sort_by, sort_order, {"id": "ps.id", "number": "ps.number", "date_from": "ps.date_from"}, "ps.date_from"
    )
    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM payment_schedules ps
        LEFT JOIN objects o ON o.id = ps.object_id
        LEFT JOIN contracts ct ON ct.id = ps.contract_id
        WHERE {where_sql}
        """,
        params,
    ).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT
            ps.*,
            o.name AS object_name,
            ct.number AS contract_number,
            p.full_name AS responsible_name
        FROM payment_schedules ps
        LEFT JOIN objects o ON o.id = ps.object_id
        LEFT JOIN contracts ct ON ct.id = ps.contract_id
        LEFT JOIN persons p ON p.id = ps.responsible_id
        WHERE {where_sql}
        {order}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    items = [_cast_flags(i, "is_posted", "marked_for_deletion") for i in rows_to_dicts(rows)]
    for item in items:
        totals = _schedule_totals(connection, int(item["id"]))
        item["total_incoming"] = totals["incoming"]
        item["total_outgoing"] = totals["outgoing"]
    return items, _build_pagination(page, page_size, total)


def _schedule_totals(connection: sqlite3.Connection, schedule_id: int) -> dict[str, float]:
    rows = connection.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN direction = 'incoming' THEN planned_amount ELSE 0 END), 0) AS incoming,
            COALESCE(SUM(CASE WHEN direction = 'outgoing' THEN planned_amount ELSE 0 END), 0) AS outgoing
        FROM payment_schedule_lines
        WHERE schedule_id = ?
          AND COALESCE(marked_for_deletion, 0) = 0
          AND COALESCE(is_deleted, 0) = 0
        """,
        (schedule_id,),
    ).fetchone()
    return {"incoming": round(float(rows["incoming"] or 0), 2), "outgoing": round(float(rows["outgoing"] or 0), 2)}


def get_payment_schedule(connection: sqlite3.Connection, schedule_id: int) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            ps.*,
            o.name AS object_name,
            ct.number AS contract_number,
            p.full_name AS responsible_name
        FROM payment_schedules ps
        LEFT JOIN objects o ON o.id = ps.object_id
        LEFT JOIN contracts ct ON ct.id = ps.contract_id
        LEFT JOIN persons p ON p.id = ps.responsible_id
        WHERE ps.id = ? AND ps.marked_for_deletion = 0
        """,
        (schedule_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Payment schedule not found")
    schedule = _cast_flags(row_to_dict(row) or {}, "is_posted", "marked_for_deletion")
    line_rows = connection.execute(
        """
        SELECT
            psl.*,
            cp.name AS counterparty_name,
            ct.number AS contract_number,
            e.number AS estimate_number,
            o.name AS object_name
        FROM payment_schedule_lines psl
        LEFT JOIN counterparties cp ON cp.id = psl.counterparty_id
        LEFT JOIN contracts ct ON ct.id = psl.contract_id
        LEFT JOIN estimates e ON e.id = psl.estimate_id
        LEFT JOIN objects o ON o.id = psl.object_id
        WHERE psl.schedule_id = ?
          AND COALESCE(psl.marked_for_deletion, 0) = 0
          AND COALESCE(psl.is_deleted, 0) = 0
        ORDER BY psl.line_number
        """,
        (schedule_id,),
    ).fetchall()
    line_items = [_cast_flags(i, "is_group", "is_collapsed") for i in rows_to_dicts(line_rows)]
    for item in line_items:
        fact = _line_fact_amount(connection, int(item["id"]))
        item["fact_amount"] = fact
        item["balance"] = round(float(item.get("planned_amount", 0)) - fact, 2)
    schedule["lines"] = line_items
    totals = _schedule_totals(connection, schedule_id)
    schedule["total_incoming"] = totals["incoming"]
    schedule["total_outgoing"] = totals["outgoing"]
    require_schedule(connection, schedule)
    return schedule


def _line_fact_amount(connection: sqlite3.Connection, line_id: int) -> float:
    scope, params = ['psr.linked_line_id = ?', "psr.recorder_type = 'payment_transaction'", 'psr.is_deleted = 0'], [line_id]
    add_cash_history_scope(connection, scope, params)
    row = connection.execute(
        f"""
        SELECT COALESCE(SUM(fact_amount), 0) AS fact
        FROM payment_schedule_register psr
        WHERE {' AND '.join(scope)}
        """,
        params,
    ).fetchone()
    return round(float(row["fact"] or 0), 2)


def _next_schedule_number(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT COUNT(*) AS cnt FROM payment_schedules WHERE marked_for_deletion = 0"
    ).fetchone()
    return f"ПК-{int(row['cnt'] or 0) + 1:04d}"


def _sync_schedule_lines(
    connection: sqlite3.Connection,
    *,
    schedule_id: int,
    lines: list[dict[str, Any]],
) -> None:
    existing_rows = connection.execute(
        """
        SELECT id, uuid
        FROM payment_schedule_lines
        WHERE schedule_id = ?
          AND COALESCE(marked_for_deletion, 0) = 0
          AND COALESCE(is_deleted, 0) = 0
        """,
        (schedule_id,),
    ).fetchall()
    existing_map = {int(r["id"]): str(r["uuid"]) for r in existing_rows}
    existing_uuid_map = {str(r["uuid"]): int(r["id"]) for r in existing_rows}
    incoming_ids: set[int] = set()
    line_uuid_map = dict(existing_uuid_map)
    parent_links: list[tuple[int, int | None, str | None]] = []

    for raw_line in lines:
        line = _coerce_bools(dict(raw_line))
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

        common_fields = {
            "line_number": int(line["line_number"]),
            "direction": line.get("direction") or "outgoing",
            "category": line.get("category") or "other",
            "planned_date": str(line["planned_date"]),
            "counterparty_id": line.get("counterparty_id"),
            "contract_id": line.get("contract_id"),
            "estimate_id": line.get("estimate_id"),
            "object_id": line.get("object_id"),
            "planned_amount": round(float(line.get("planned_amount") or 0), 2),
            "description": line.get("description"),
            "source_kind": line.get("source_kind") or "manual",
            "source_ref": line.get("source_ref"),
            "is_group": int(bool(line.get("is_group"))),
            "group_name": line.get("group_name"),
            "parent_group_id": explicit_parent_id if parent_group_uuid is None else None,
            "is_collapsed": int(bool(line.get("is_collapsed"))),
        }

        if line_id is not None and line_id in existing_map:
            incoming_ids.add(line_id)
            resolved_uuid = line_uuid or existing_map[line_id]
            update_payload = {
                **common_fields,
                "modified_at": modified_at,
                "updated_at": updated_at,
                "uuid": resolved_uuid,
                "marked_for_deletion": 0,
                "is_deleted": 0,
            }
            assignments = ", ".join(f"{c} = ?" for c in update_payload)
            connection.execute(
                f"UPDATE payment_schedule_lines SET {assignments} WHERE id = ? AND schedule_id = ?",
                [*update_payload.values(), line_id, schedule_id],
            )
            line_uuid_map[resolved_uuid] = line_id
            parent_links.append((line_id, explicit_parent_id, parent_group_uuid))
        else:
            insert_payload = {
                "schedule_id": schedule_id,
                **common_fields,
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
                f"INSERT INTO payment_schedule_lines ({columns}) VALUES ({placeholders})",
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
            "UPDATE payment_schedule_lines SET parent_group_id = ? WHERE id = ? AND schedule_id = ?",
            (resolved_parent_id, line_id, schedule_id),
        )

    for existing_id in existing_map:
        if existing_id in incoming_ids:
            continue
        now = _now_iso()
        connection.execute(
            """
            UPDATE payment_schedule_lines
            SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, existing_id),
        )


@rollback_on_error
def save_payment_schedule(
    connection: sqlite3.Connection,
    *,
    payload: dict[str, Any],
    schedule_id: int | None = None,
    user: UserInfo,
) -> dict[str, Any]:
    _require_write(user)
    lines = [dict(line) for line in payload.pop("lines", [])]
    if schedule_id is not None:
        connection.execute('UPDATE payment_schedules SET id = id WHERE id = ?', (schedule_id,))
    # Keep ownership stable from the access check through the completed write.
    lock_settlement_contracts(connection, payload.get('contract_id'),
                              *(line.get('contract_id') for line in lines))
    require_schedule(connection, {**payload, 'lines': lines})
    payload["date_from"] = str(payload["date_from"])
    payload["date_to"] = str(payload["date_to"])
    if not payload.get("number"):
        payload["number"] = _next_schedule_number(connection)

    if schedule_id is None:
        now = _now_iso()
        insert_payload = {
            **_coerce_bools(payload),
            "created_at": now,
            "modified_at": now,
            "uuid": payload.get("uuid") or new_uuid(),
            "updated_at": now,
            "is_posted": 0,
            "marked_for_deletion": 0,
            "is_deleted": 0,
        }
        columns = ", ".join(insert_payload.keys())
        placeholders = ", ".join(["?"] * len(insert_payload))
        connection.execute(
            f"INSERT INTO payment_schedules ({columns}) VALUES ({placeholders})",
            list(insert_payload.values()),
        )
        schedule_id = last_insert_id(connection)
        schedule_uuid = str(insert_payload["uuid"])
        sync_operation = "INSERT"
    else:
        existing = get_payment_schedule(connection, schedule_id)
        if existing["is_posted"]:
            raise HTTPException(status_code=400, detail="Posted schedule cannot be modified")
        schedule_uuid = str(existing["uuid"])
        now = _now_iso()
        update_payload = {
            **_coerce_bools(payload),
            "uuid": schedule_uuid,
            "modified_at": now,
            "updated_at": now,
            "is_deleted": 0,
        }
        assignments = ", ".join(f"{c} = ?" for c in update_payload)
        connection.execute(
            f"UPDATE payment_schedules SET {assignments} WHERE id = ?",
            [*update_payload.values(), schedule_id],
        )
        sync_operation = "UPDATE"

    _sync_schedule_lines(connection, schedule_id=schedule_id, lines=lines)
    register_sync_change(
        connection,
        entity_type="payment_schedules",
        entity_uuid=schedule_uuid,
        operation=sync_operation,
    )
    result = get_payment_schedule(connection, schedule_id)
    connection.commit()
    return result


@rollback_on_error
def delete_payment_schedule(connection: sqlite3.Connection, schedule_id: int, user: UserInfo) -> None:
    _require_write(user)
    connection.execute("UPDATE payment_schedules SET id = id WHERE id = ?", (schedule_id,))
    schedule = get_payment_schedule(connection, schedule_id)
    if schedule["is_posted"]:
        raise HTTPException(status_code=400, detail="Posted schedule cannot be deleted")
    now = _now_iso()
    connection.execute(
        "UPDATE payment_schedules SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ? WHERE id = ?",
        (now, now, schedule_id),
    )
    connection.execute(
        "UPDATE payment_schedule_lines SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ? WHERE schedule_id = ?",
        (now, now, schedule_id),
    )
    register_sync_change(
        connection,
        entity_type="payment_schedules",
        entity_uuid=str(schedule["uuid"]),
        operation="DELETE",
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Payment schedules: post / unpost
# ---------------------------------------------------------------------------


@rollback_on_error
def post_payment_schedule(connection: sqlite3.Connection, *, schedule_id: int, user: UserInfo) -> None:
    _require_admin(user)
    connection.execute("UPDATE payment_schedules SET id = id WHERE id = ?", (schedule_id,))
    schedule = get_payment_schedule(connection, schedule_id)
    if schedule["is_posted"]:
        raise HTTPException(status_code=400, detail="Payment schedule is already posted")
    if not schedule["lines"]:
        raise HTTPException(status_code=400, detail="Cannot post an empty schedule")
    connection.execute(
        "DELETE FROM payment_schedule_register WHERE recorder_type = 'payment_schedule' AND recorder_id = ?",
        (schedule_id,),
    )
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
                _now_iso(),
                _now_iso(),
                new_uuid(),
                _now_iso(),
            ),
        )
    connection.execute(
        "UPDATE payment_schedules SET is_posted = 1, posted_at = ?, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), _now_iso(), schedule_id),
    )
    register_sync_change(
        connection,
        entity_type="payment_schedules",
        entity_uuid=str(schedule["uuid"]),
        operation="UPDATE",
    )
    connection.commit()


@rollback_on_error
def unpost_payment_schedule(connection: sqlite3.Connection, *, schedule_id: int, user: UserInfo) -> None:
    _require_admin(user)
    connection.execute("UPDATE payment_schedules SET id = id WHERE id = ?", (schedule_id,))
    schedule = get_payment_schedule(connection, schedule_id)
    if not schedule["is_posted"]:
        raise HTTPException(status_code=400, detail="Payment schedule is not posted")

    linked_facts = connection.execute(
        """
        SELECT pt.id, pt.number, pt.uuid
        FROM payment_transactions pt
        WHERE pt.linked_schedule_id = ?
          AND pt.is_posted = 1
          AND COALESCE(pt.marked_for_deletion, 0) = 0
        """,
        (schedule_id,),
    ).fetchall()
    if linked_facts:
        details = ", ".join(
            f"{row['number'] or ('#' + str(row['id']))}" for row in linked_facts[:3]
        )
        suffix = f" and {len(linked_facts) - 3} more" if len(linked_facts) > 3 else ""
        raise HTTPException(
            status_code=400,
            detail=f"Cannot unpost: linked posted transactions exist ({details}{suffix}). Unpost them first.",
        )

    connection.execute(
        "DELETE FROM payment_schedule_register WHERE recorder_type = 'payment_schedule' AND recorder_id = ?",
        (schedule_id,),
    )
    connection.execute(
        "UPDATE payment_schedules SET is_posted = 0, posted_at = NULL, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), schedule_id),
    )
    register_sync_change(
        connection,
        entity_type="payment_schedules",
        entity_uuid=str(schedule["uuid"]),
        operation="UPDATE",
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Payment transactions: list / get / save / delete
# ---------------------------------------------------------------------------


def list_payment_transactions(
    connection: sqlite3.Connection,
    *,
    page: int,
    page_size: int,
    search: str | None = None,
    direction: str | None = None,
    counterparty_id: int | None = None,
    is_posted: bool | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], Pagination]:
    page, page_size = _normalize_page(page, page_size)
    where_parts = ["pt.marked_for_deletion = 0"]
    params: list[Any] = []
    if search:
        where_parts.append("(pt.number LIKE ? OR cp.name LIKE ?)")
        params.extend([f"%{search}%"] * 2)
    if direction:
        where_parts.append("pt.direction = ?")
        params.append(direction)
    if counterparty_id:
        where_parts.append("pt.counterparty_id = ?")
        params.append(counterparty_id)
    if is_posted is not None:
        where_parts.append("pt.is_posted = ?")
        params.append(int(bool(is_posted)))
    apply_quick_filters(
        where_parts,
        params,
        filters,
        {
            "number": ("pt.number", "like"),
            "date": ("pt.date", "eq"),
            "direction": ("pt.direction", "eq"),
            "is_posted": ("pt.is_posted", "eq"),
            "counterparty_name": ("cp.name", "like"),
        },
    )
    add_payment_scope(connection, where_parts, params)
    where_sql = " AND ".join(where_parts)
    order = order_by_clause(
        sort_by, sort_order, {"id": "pt.id", "number": "pt.number", "date": "pt.date"}, "pt.date"
    )
    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM payment_transactions pt
        LEFT JOIN counterparties cp ON cp.id = pt.counterparty_id
        WHERE {where_sql}
        """,
        params,
    ).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT
            pt.*,
            cp.name AS counterparty_name,
            ct.number AS contract_number
        FROM payment_transactions pt
        LEFT JOIN counterparties cp ON cp.id = pt.counterparty_id
        LEFT JOIN contracts ct ON ct.id = pt.contract_id
        WHERE {where_sql}
        {order}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    items = [_cast_flags(i, "is_posted", "marked_for_deletion") for i in rows_to_dicts(rows)]
    return items, _build_pagination(page, page_size, total)


def get_payment_transaction(connection: sqlite3.Connection, tx_id: int) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            pt.*,
            cp.name AS counterparty_name,
            ct.number AS contract_number,
            psl.uuid AS linked_line_uuid
        FROM payment_transactions pt
        LEFT JOIN counterparties cp ON cp.id = pt.counterparty_id
        LEFT JOIN contracts ct ON ct.id = pt.contract_id
        LEFT JOIN payment_schedule_lines psl ON psl.id = pt.linked_line_id
        WHERE pt.id = ? AND pt.marked_for_deletion = 0
        """,
        (tx_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Payment transaction not found")
    require_contract(connection, row["contract_id"])
    require_posted_payment(connection, tx_id)
    require_payment_links(connection, dict(row))
    return _cast_flags(row_to_dict(row) or {}, "is_posted", "marked_for_deletion", "allow_advance")


def _next_transaction_number(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT COUNT(*) AS cnt FROM payment_transactions WHERE marked_for_deletion = 0"
    ).fetchone()
    return f"ПЛ-{int(row['cnt'] or 0) + 1:04d}"


@rollback_on_error
def save_payment_transaction(
    connection: sqlite3.Connection,
    *,
    payload: dict[str, Any],
    tx_id: int | None = None,
    user: UserInfo,
) -> dict[str, Any]:
    _require_write(user)
    if tx_id is not None:
        connection.execute("UPDATE payment_transactions SET id = id WHERE id = ?", (tx_id,))
    lock_settlement_contracts(connection, payload.get('contract_id'))
    require_payment_links(connection, payload)
    validate_contract(connection, contract_id=payload.get("contract_id"),
                      counterparty_id=payload.get("counterparty_id"))
    if payload.get("allow_advance") and not payload.get("contract_id"):
        raise HTTPException(status_code=400, detail="Для аванса необходимо выбрать договор")
    payload["date"] = str(payload["date"])
    payload["amount"] = float(money(payload.get("amount")))
    if not payload.get("number"):
        payload["number"] = _next_transaction_number(connection)

    if tx_id is None:
        now = _now_iso()
        insert_payload = {
            **_coerce_bools(payload),
            "created_at": now,
            "modified_at": now,
            "uuid": payload.get("uuid") or new_uuid(),
            "updated_at": now,
            "is_posted": 0,
            "marked_for_deletion": 0,
            "is_deleted": 0,
        }
        columns = ", ".join(insert_payload.keys())
        placeholders = ", ".join(["?"] * len(insert_payload))
        connection.execute(
            f"INSERT INTO payment_transactions ({columns}) VALUES ({placeholders})",
            list(insert_payload.values()),
        )
        tx_id = last_insert_id(connection)
        tx_uuid = str(insert_payload["uuid"])
        sync_operation = "INSERT"
    else:
        existing = get_payment_transaction(connection, tx_id)
        if existing["is_posted"]:
            raise HTTPException(status_code=400, detail="Posted transaction cannot be modified")
        tx_uuid = str(existing["uuid"])
        now = _now_iso()
        update_payload = {
            **_coerce_bools(payload),
            "uuid": tx_uuid,
            "modified_at": now,
            "updated_at": now,
            "is_deleted": 0,
        }
        assignments = ", ".join(f"{c} = ?" for c in update_payload)
        connection.execute(
            f"UPDATE payment_transactions SET {assignments} WHERE id = ?",
            [*update_payload.values(), tx_id],
        )
        sync_operation = "UPDATE"

    register_sync_change(
        connection,
        entity_type="payment_transactions",
        entity_uuid=tx_uuid,
        operation=sync_operation,
    )
    result = get_payment_transaction(connection, tx_id)
    connection.commit()
    return result


@rollback_on_error
def delete_payment_transaction(connection: sqlite3.Connection, tx_id: int, user: UserInfo) -> None:
    _require_write(user)
    connection.execute("UPDATE payment_transactions SET id = id WHERE id = ?", (tx_id,))
    tx = get_payment_transaction(connection, tx_id)
    if tx["is_posted"]:
        raise HTTPException(status_code=400, detail="Posted transaction cannot be deleted")
    now = _now_iso()
    connection.execute(
        "UPDATE payment_transactions SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ? WHERE id = ?",
        (now, now, tx_id),
    )
    register_sync_change(
        connection,
        entity_type="payment_transactions",
        entity_uuid=str(tx["uuid"]),
        operation="DELETE",
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Payment transactions: post / unpost
# ---------------------------------------------------------------------------


@rollback_on_error
def post_payment_transaction(connection: sqlite3.Connection, *, tx_id: int, user: UserInfo) -> None:
    _require_admin(user)
    connection.execute('UPDATE payment_transactions SET id = id WHERE id = ?', (tx_id,))
    tx = get_payment_transaction(connection, tx_id)
    if tx["is_posted"]:
        raise HTTPException(status_code=400, detail="Payment transaction is already posted")

    lock_settlement_contracts(connection, tx.get('contract_id'))
    # Owners/links can change while a request waits for a lock.
    tx = get_payment_transaction(connection, tx_id)
    contract = validate_contract(connection, contract_id=tx.get("contract_id"),
                                 counterparty_id=tx.get("counterparty_id"))
    if tx.get("allow_advance") and (contract is None or contract["organization_id"] is None):
        raise HTTPException(status_code=400, detail="Для аванса необходим договор с организацией")
    _assert_payment_within_accruals(connection, tx)

    connection.execute(
        "DELETE FROM payment_schedule_register WHERE recorder_type = 'payment_transaction' AND recorder_id = ?",
        (tx_id,),
    )
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
            _now_iso(),
            _now_iso(),
            new_uuid(),
            _now_iso(),
        ),
    )
    # Mirror the payment into mutual_settlements_register (settles goods accruals).
    apply_payment_to_settlements(
        connection,
        tx_id=tx_id,
        tx_direction=tx["direction"],
        amount=float(tx.get("amount") or 0),
        organization_id=_resolve_tx_organization(connection, tx),
        counterparty_id=tx.get("counterparty_id"),
        contract_id=tx.get("contract_id"),
        object_id=tx.get("object_id"),
        estimate_id=tx.get("estimate_id"),
        period=str(tx["date"]),
        linked_line_id=tx.get("linked_line_id"),
    )
    connection.execute(
        "UPDATE payment_transactions SET is_posted = 1, posted_at = ?, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), _now_iso(), tx_id),
    )
    register_sync_change(
        connection,
        entity_type="payment_transactions",
        entity_uuid=str(tx["uuid"]),
        operation="UPDATE",
    )
    connection.commit()


def _resolve_tx_organization(connection: sqlite3.Connection, tx: dict[str, Any]) -> int | None:
    """Best-effort organization resolution for a payment transaction.

    Payment transactions don't carry ``organization_id`` directly, so we infer it
    from the linked contract or the first organization available. Returns ``None``
    when nothing can be resolved.
    """
    contract_id = tx.get("contract_id")
    if contract_id:
        row = connection.execute(
            "SELECT organization_id FROM contracts WHERE id = ?",
            (contract_id,),
        ).fetchone()
        if row is not None and row["organization_id"] is not None:
            return int(row["organization_id"])
    row = connection.execute(
        "SELECT id FROM organizations WHERE marked_for_deletion = 0 ORDER BY id LIMIT 1"
    ).fetchone()
    return None if row is None else int(row["id"])


def _assert_payment_within_accruals(connection: sqlite3.Connection, tx: dict[str, Any]) -> None:
    """Enforce invariant: payment_amount <= accrual_amount per (direction, contract).

    Soft check — only blocks when a contract is set and the payment would drive
    the settlement balance below zero (i.e. overpay beyond open accruals). When
    no contract is present the check is skipped (cannot be evaluated).
    """
    contract_id = tx.get("contract_id")
    if not contract_id or tx.get("allow_advance"):
        return
    direction = "payable" if tx["direction"] == "outgoing" else "receivable"
    row = connection.execute(
        """
        SELECT
            COALESCE(SUM(accrual_amount), 0) AS accrual,
            COALESCE(SUM(payment_amount), 0) AS payment
        FROM mutual_settlements_register
        WHERE contract_id = ? AND direction = ?
          AND organization_id = ? AND counterparty_id = ?
          AND (object_id = ? OR (object_id IS NULL AND ? IS NULL))
          AND period <= ?
          AND COALESCE(is_deleted, 0) = 0
        """,
        (contract_id, direction, _resolve_tx_organization(connection, tx), tx.get("counterparty_id"),
         tx.get("object_id"), tx.get("object_id"), str(tx["date"])),
    ).fetchone()
    open_balance = money(row["accrual"]) - money(row["payment"])
    amount = money(tx.get("amount"))
    if amount > open_balance:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Платёж ({amount:g}) превышает открытую задолженность по договору "
                f"({open_balance:g}). Разрешите аванс или сначала начислите задолженность проведением документа ТМЦ."
            ),
        )


@rollback_on_error
def unpost_payment_transaction(connection: sqlite3.Connection, *, tx_id: int, user: UserInfo) -> None:
    _require_admin(user)
    connection.execute("UPDATE payment_transactions SET id = id WHERE id = ?", (tx_id,))
    tx = get_payment_transaction(connection, tx_id)
    if not tx["is_posted"]:
        raise HTTPException(status_code=400, detail="Payment transaction is not posted")
    lock_settlement_contracts(connection, tx.get('contract_id'))
    tx = get_payment_transaction(connection, tx_id)
    # A cash refund consumes the payment's settlement credit. Removing that
    # payment first would manufacture debt after money has already left.
    if connection.execute('''SELECT id FROM mutual_settlements_register
        WHERE recorder_type = 'goods_return_refund' AND is_deleted = 0 AND payment_amount < 0
        AND organization_id = ? AND direction = ?
        AND (counterparty_id = ? OR (counterparty_id IS NULL AND ? IS NULL))
        AND (contract_id = ? OR (contract_id IS NULL AND ? IS NULL))
        AND (object_id = ? OR (object_id IS NULL AND ? IS NULL)) AND period >= ? LIMIT 1''',
        (_resolve_tx_organization(connection, tx), 'payable' if tx['direction'] == 'outgoing' else 'receivable',
         tx.get('counterparty_id'), tx.get('counterparty_id'), tx.get('contract_id'), tx.get('contract_id'),
         tx.get('object_id'), tx.get('object_id'), str(tx['date']))).fetchone():
        raise HTTPException(status_code=400, detail='Сначала отмените зависимые возвраты денег')
    connection.execute(
        "DELETE FROM payment_schedule_register WHERE recorder_type = 'payment_transaction' AND recorder_id = ?",
        (tx_id,),
    )
    remove_payment_from_settlements(connection, tx_id=tx_id)
    connection.execute(
        "UPDATE payment_transactions SET is_posted = 0, posted_at = NULL, modified_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), tx_id),
    )
    register_sync_change(
        connection,
        entity_type="payment_transactions",
        entity_uuid=str(tx["uuid"]),
        operation="UPDATE",
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Auto-suggest helpers
# ---------------------------------------------------------------------------


def suggest_incoming_from_work_execution(
    connection: sqlite3.Connection,
    *,
    date_from: str,
    date_to: str,
    object_id: int | None = None,
    contract_id: int | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [date_from, date_to]
    object_clause = ""
    if object_id is not None:
        object_clause = "AND e.object_id = ?"
        params.append(object_id)
    contract_clause = ""
    if contract_id is not None:
        contract_clause = "AND e.contract_id = ?"
        params.append(contract_id)

    scope = ["1 = 1"]
    add_scope(connection, scope, params, "ct.organization_id")
    scope_sql = " AND ".join(scope)
    rows = connection.execute(
        f"""
        SELECT
            e.contract_id,
            e.object_id,
            wer.estimate_id,
            ct.counterparty_id,
            SUM(wer.sum_expense) AS executed_sum,
            MAX(wer.period) AS last_date
        FROM work_execution_register wer
        LEFT JOIN estimates e ON e.id = wer.estimate_id
        LEFT JOIN contracts ct ON ct.id = e.contract_id
        WHERE wer.sum_expense > 0
          AND wer.period >= ?
          AND wer.period <= ?
          {object_clause}
          {contract_clause}
          AND COALESCE(wer.is_deleted, 0) = 0
          AND {scope_sql}
        GROUP BY e.contract_id, e.object_id, wer.estimate_id, ct.counterparty_id
        ORDER BY last_date DESC
        """,
        params,
    ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "direction": "incoming",
                "category": "customer_stage",
                "planned_date": str(row["last_date"]),
                "counterparty_id": row["counterparty_id"],
                "contract_id": row["contract_id"],
                "estimate_id": row["estimate_id"],
                "object_id": row["object_id"],
                "planned_amount": round(float(row["executed_sum"] or 0), 2),
                "description": None,
                "source_kind": "work_execution",
                "source_ref": f"estimate:{row['estimate_id']}" if row["estimate_id"] else None,
            }
        )
    return results


def suggest_outgoing_from_payroll(
    connection: sqlite3.Connection,
    *,
    date_from: str,
    date_to: str,
    object_id: int | None = None,
    estimate_id: int | None = None,
) -> list[dict[str, Any]]:
    if organizations(connection) is not None:
        raise HTTPException(status_code=403, detail="Общий расчет зарплаты не имеет организации; требуется неограниченный доступ")
    params: list[Any] = [date_from, date_to]
    object_clause = ""
    if object_id is not None:
        object_clause = "AND pr.object_id = ?"
        params.append(object_id)
    estimate_clause = ""
    if estimate_id is not None:
        estimate_clause = "AND pr.estimate_id = ?"
        params.append(estimate_id)

    rows = connection.execute(
        f"""
        SELECT
            pr.employee_id,
            p.full_name AS employee_name,
            SUM(pr.amount) AS payroll_sum,
            MAX(pr.work_date) AS last_date,
            pr.object_id,
            pr.estimate_id
        FROM payroll_register pr
        LEFT JOIN persons p ON p.id = pr.employee_id
        WHERE pr.amount > 0
          AND pr.work_date >= ?
          AND pr.work_date <= ?
          {object_clause}
          {estimate_clause}
          AND COALESCE(pr.is_deleted, 0) = 0
        GROUP BY pr.employee_id, p.full_name, pr.object_id, pr.estimate_id
        ORDER BY last_date DESC
        """,
        params,
    ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "direction": "outgoing",
                "category": "payroll",
                "planned_date": str(row["last_date"]),
                "counterparty_id": None,
                "contract_id": None,
                "estimate_id": row["estimate_id"],
                "object_id": row["object_id"],
                "planned_amount": round(float(row["payroll_sum"] or 0), 2),
                "description": f"Зарплата: {row['employee_name']}" if row["employee_name"] else None,
                "source_kind": "payroll",
                "source_ref": f"employee:{row['employee_id']}" if row["employee_id"] else None,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Register query
# ---------------------------------------------------------------------------


def query_payment_register(
    connection: sqlite3.Connection,
    *,
    page: int,
    page_size: int,
    period_from: str | None = None,
    period_to: str | None = None,
    object_id: int | None = None,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
    direction: str | None = None,
    category: str | None = None,
    group_by: list[str] | None = None,
) -> tuple[list[dict[str, Any]], Pagination, dict[str, float]]:
    page, page_size = _normalize_page(page, page_size)
    where_parts = ["COALESCE(psr.is_deleted, 0) = 0"]
    params: list[Any] = []
    if period_from:
        where_parts.append("psr.period >= ?")
        params.append(period_from)
    if period_to:
        where_parts.append("psr.period <= ?")
        params.append(period_to)
    if object_id:
        where_parts.append("psr.object_id = ?")
        params.append(object_id)
    if counterparty_id:
        where_parts.append("psr.counterparty_id = ?")
        params.append(counterparty_id)
    if contract_id:
        where_parts.append("psr.contract_id = ?")
        params.append(contract_id)
    if direction:
        where_parts.append("psr.direction = ?")
        params.append(direction)
    if category:
        where_parts.append("psr.category = ?")
        params.append(category)

    add_scope(connection, where_parts, params, "(SELECT organization_id FROM contracts WHERE id = psr.contract_id)")
    add_cash_history_scope(connection, where_parts, params)
    where_sql = " AND ".join(where_parts)
    rows = connection.execute(
        f"""
        SELECT
            psr.*,
            cp.name AS counterparty_name,
            ct.number AS contract_number,
            o.name AS object_name,
            e.number AS estimate_number
        FROM payment_schedule_register psr
        LEFT JOIN counterparties cp ON cp.id = psr.counterparty_id
        LEFT JOIN contracts ct ON ct.id = psr.contract_id
        LEFT JOIN objects o ON o.id = psr.object_id
        LEFT JOIN estimates e ON e.id = psr.estimate_id
        WHERE {where_sql}
        ORDER BY psr.period DESC, psr.id DESC
        """,
        params,
    ).fetchall()
    items = rows_to_dicts(rows)

    for item in items:
        item["planned_date"] = item.get("period")
        item["balance"] = round(float(item.get("planned_amount", 0)) - float(item.get("fact_amount", 0)), 2)
        item["is_paid"] = float(item.get("fact_amount", 0)) >= float(item.get("planned_amount", 0)) and float(item.get("planned_amount", 0)) > 0
        today = date.today().isoformat()
        item["is_overdue"] = (
            not item["is_paid"]
            and str(item.get("period", "")) < today
            and float(item.get("planned_amount", 0)) > 0
        )

    if group_by:
        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in items:
            key = tuple(
                item.get(f"{field}_name")
                or item.get(f"{field}_number")
                or item.get(f"{field}_id")
                or item.get(field)
                for field in group_by
            )
            if key not in grouped:
                grouped[key] = {
                    "planned_date": None,
                    "direction": item["direction"],
                    "category": item["category"],
                    "counterparty_id": item.get("counterparty_id"),
                    "counterparty_name": item.get("counterparty_name"),
                    "contract_id": item.get("contract_id"),
                    "contract_number": item.get("contract_number"),
                    "object_id": item.get("object_id"),
                    "object_name": item.get("object_name"),
                    "estimate_id": item.get("estimate_id"),
                    "estimate_number": item.get("estimate_number"),
                    "planned_amount": 0.0,
                    "fact_amount": 0.0,
                    "balance": 0.0,
                    "is_paid": False,
                    "is_overdue": False,
                }
            group = grouped[key]
            group["planned_amount"] += float(item.get("planned_amount", 0))
            group["fact_amount"] += float(item.get("fact_amount", 0))
        items = list(grouped.values())
        for item in items:
            item["planned_amount"] = round(item["planned_amount"], 2)
            item["fact_amount"] = round(item["fact_amount"], 2)
            item["balance"] = round(item["planned_amount"] - item["fact_amount"], 2)
            item["is_paid"] = item["fact_amount"] >= item["planned_amount"] and item["planned_amount"] > 0

    total = len(items)
    totals = {
        "incoming_planned": round(sum(float(i.get("planned_amount", 0)) for i in items if i.get("direction") == "incoming"), 2),
        "outgoing_planned": round(sum(float(i.get("planned_amount", 0)) for i in items if i.get("direction") == "outgoing"), 2),
        "incoming_fact": round(sum(float(i.get("fact_amount", 0)) for i in items if i.get("direction") == "incoming"), 2),
        "outgoing_fact": round(sum(float(i.get("fact_amount", 0)) for i in items if i.get("direction") == "outgoing"), 2),
    }
    totals["net_flow"] = round(totals["incoming_planned"] - totals["outgoing_planned"], 2)
    return (
        items[(page - 1) * page_size : (page - 1) * page_size + page_size],
        _build_pagination(page, page_size, total),
        totals,
    )


def query_cashflow_by_day(
    connection: sqlite3.Connection,
    *,
    date_from: str,
    date_to: str,
    object_id: int | None = None,
    counterparty_id: int | None = None,
) -> list[dict[str, Any]]:
    where_parts = ["COALESCE(psr.is_deleted, 0) = 0", "psr.period >= ?", "psr.period <= ?"]
    params: list[Any] = [date_from, date_to]
    if object_id:
        where_parts.append("psr.object_id = ?")
        params.append(object_id)
    if counterparty_id:
        where_parts.append("psr.counterparty_id = ?")
        params.append(counterparty_id)
    add_scope(connection, where_parts, params, "(SELECT organization_id FROM contracts WHERE id = psr.contract_id)")
    add_cash_history_scope(connection, where_parts, params)
    where_sql = " AND ".join(where_parts)

    rows = connection.execute(
        f"""
        SELECT
            psr.period,
            psr.direction,
            psr.recorder_type,
            SUM(psr.planned_amount) AS planned,
            SUM(psr.fact_amount) AS fact
        FROM payment_schedule_register psr
        WHERE {where_sql}
        GROUP BY psr.period, psr.direction, psr.recorder_type
        ORDER BY psr.period
        """,
        params,
    ).fetchall()

    by_day: dict[str, dict[str, float]] = {}
    for row in rows:
        day = str(row["period"])
        if day not in by_day:
            by_day[day] = {
                "incoming_planned": 0.0,
                "outgoing_planned": 0.0,
                "incoming_fact": 0.0,
                "outgoing_fact": 0.0,
            }
        entry = by_day[day]
        if row["direction"] == "incoming":
            entry["incoming_planned"] += float(row["planned"] or 0)
            entry["incoming_fact"] += float(row["fact"] or 0)
        else:
            entry["outgoing_planned"] += float(row["planned"] or 0)
            entry["outgoing_fact"] += float(row["fact"] or 0)

    start = datetime.fromisoformat(date_from).date()
    end = datetime.fromisoformat(date_to).date()
    result: list[dict[str, Any]] = []
    cumulative = 0.0
    current = start
    while current <= end:
        day_str = current.isoformat()
        entry = by_day.get(day_str, {})
        incoming_planned = round(float(entry.get("incoming_planned", 0)), 2)
        outgoing_planned = round(float(entry.get("outgoing_planned", 0)), 2)
        incoming_fact = round(float(entry.get("incoming_fact", 0)), 2)
        outgoing_fact = round(float(entry.get("outgoing_fact", 0)), 2)
        cumulative += incoming_planned - outgoing_planned
        result.append(
            {
                "date": day_str,
                "incoming_planned": incoming_planned,
                "outgoing_planned": outgoing_planned,
                "incoming_fact": incoming_fact,
                "outgoing_fact": outgoing_fact,
                "cumulative_balance": round(cumulative, 2),
                "is_deficit": cumulative < 0,
            }
        )
        current += timedelta(days=1)
    return result


def get_payment_transaction_movements(
    connection: sqlite3.Connection,
    *,
    tx_id: int,
) -> dict[str, Any]:
    """Mutual-settlement rows produced by a single payment transaction."""
    tx = get_payment_transaction(connection, tx_id)
    set_rows = connection.execute(
        """
        SELECT
            msr.line_number, msr.period, msr.direction,
            msr.organization_id, o.name AS organization_name,
            msr.counterparty_id, cp.name AS counterparty_name,
            msr.contract_id, ct.number AS contract_number,
            msr.object_id, ob.name AS object_name,
            msr.accrual_amount, msr.payment_amount, msr.planned_amount
        FROM mutual_settlements_register msr
        LEFT JOIN organizations o ON o.id = msr.organization_id
        LEFT JOIN counterparties cp ON cp.id = msr.counterparty_id
        LEFT JOIN contracts ct ON ct.id = msr.contract_id
        LEFT JOIN objects ob ON ob.id = msr.object_id
        WHERE msr.recorder_type = 'payment_transaction' AND msr.recorder_id = ?
          AND COALESCE(msr.is_deleted, 0) = 0
        ORDER BY msr.line_number
        """,
        (tx_id,),
    ).fetchall()
    settlements = rows_to_dicts(set_rows)
    totals = {
        "payment_amount": sum(float(r.get("payment_amount") or 0) for r in settlements),
    }
    return {
        "document": {
            "id": tx["id"],
            "number": tx.get("number"),
            "date": tx.get("date"),
            "direction": tx.get("direction"),
            "category": tx.get("category"),
            "is_posted": bool(tx.get("is_posted")),
            "amount": tx.get("amount"),
        },
        "settlements": settlements,
        "totals": totals,
    }
