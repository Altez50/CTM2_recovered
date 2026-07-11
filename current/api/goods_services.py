"""Service layer for the goods (ТМЦ) and mutual settlements subsystem.

Implements CRUD + posting for two documents (goods_receipts, goods_issues),
the inventory_register and mutual_settlements_register queries, auto-suggest
helpers for the payment calendar, and Excel import/export of document lines.

Follows the same document -> posting -> register pattern as
``api.payment_services``.
"""

from __future__ import annotations

import io
import sqlite3
import zipfile
from datetime import date, datetime, timedelta
from math import ceil
from typing import Any
from xml.etree import ElementTree as ET

from fastapi import HTTPException

from api.database import (
    last_insert_id,
    new_uuid,
    register_sync_change,
    row_to_dict,
    rows_to_dicts,
    utcnow_iso,
)
from api.models.auth import UserInfo
from api.models.common import Pagination


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def _round2(value: Any) -> float:
    return round(float(value or 0), 2)


def _compute_line_totals(quantity: float, price_without_vat: float, vat_rate: float) -> dict[str, float]:
    qty = max(0.0, float(quantity or 0))
    price = max(0.0, float(price_without_vat or 0))
    rate = max(0.0, float(vat_rate or 0))
    sum_without_vat = _round2(qty * price)
    vat_amount = _round2(sum_without_vat * rate / 100.0)
    sum_with_vat = _round2(sum_without_vat + vat_amount)
    return {
        "quantity": qty,
        "price_without_vat": price,
        "vat_rate": rate,
        "vat_amount": vat_amount,
        "sum_without_vat": sum_without_vat,
        "sum_with_vat": sum_with_vat,
    }


def _compute_document_totals(lines: list[dict[str, Any]]) -> dict[str, float]:
    sum_without_vat = _round2(sum(float(line.get("sum_without_vat") or 0) for line in lines))
    vat_amount = _round2(sum(float(line.get("vat_amount") or 0) for line in lines))
    sum_with_vat = _round2(sum(float(line.get("sum_with_vat") or 0) for line in lines))
    return {
        "sum_without_vat": sum_without_vat,
        "vat_amount": vat_amount,
        "sum_with_vat": sum_with_vat,
    }


_CONTRACT_FIELDS = (
    "organization_id",
    "counterparty_id",
    "contract_id",
    "object_id",
    "estimate_id",
)


def _contract_deferral_days(connection: sqlite3.Connection, contract_id: int | None) -> int:
    if not contract_id:
        return 0
    row = connection.execute(
        "SELECT payment_deferral_days FROM contracts WHERE id = ?",
        (contract_id,),
    ).fetchone()
    if row is None:
        return 0
    return int(row["payment_deferral_days"] or 0)


# ---------------------------------------------------------------------------
# Generic document CRUD (shared by receipts and issues)
# ---------------------------------------------------------------------------


_DOC_CONFIG: dict[str, dict[str, Any]] = {
    "receipt": {
        "table": "goods_receipts",
        "line_table": "goods_receipt_lines",
        "header_fk": "receipt_id",
        "prefix": "ПТ",
        "recorder_type": "goods_receipt",
        "line_entity_type": "goods_receipt_lines",
    },
    "issue": {
        "table": "goods_issues",
        "line_table": "goods_issue_lines",
        "header_fk": "issue_id",
        "prefix": "РТ",
        "recorder_type": "goods_issue",
        "line_entity_type": "goods_issue_lines",
    },
}


def _config(kind: str) -> dict[str, Any]:
    cfg = _DOC_CONFIG.get(kind)
    if cfg is None:
        raise ValueError(f"Unknown goods document kind: {kind}")
    return cfg


def _next_document_number(connection: sqlite3.Connection, cfg: dict[str, Any]) -> str:
    row = connection.execute(
        f"SELECT COUNT(*) AS cnt FROM {cfg['table']} WHERE marked_for_deletion = 0"
    ).fetchone()
    return f"{cfg['prefix']}-{int(row['cnt'] or 0) + 1:04d}"


def _list_documents(
    connection: sqlite3.Connection,
    *,
    kind: str,
    page: int,
    page_size: int,
    search: str | None = None,
    organization_id: int | None = None,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
    object_id: int | None = None,
    is_posted: bool | None = None,
) -> tuple[list[dict[str, Any]], Pagination]:
    cfg = _config(kind)
    page, page_size = _normalize_page(page, page_size)
    where_parts = [f"d.marked_for_deletion = 0"]
    params: list[Any] = []
    if search:
        where_parts.append("(d.number LIKE ? OR cp.name LIKE ? OR ct.number LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    if organization_id:
        where_parts.append("d.organization_id = ?")
        params.append(organization_id)
    if counterparty_id:
        where_parts.append("d.counterparty_id = ?")
        params.append(counterparty_id)
    if contract_id:
        where_parts.append("d.contract_id = ?")
        params.append(contract_id)
    if object_id:
        where_parts.append("d.object_id = ?")
        params.append(object_id)
    if is_posted is not None:
        where_parts.append("d.is_posted = ?")
        params.append(int(bool(is_posted)))
    where_sql = " AND ".join(where_parts)
    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM {cfg['table']} d
        LEFT JOIN counterparties cp ON cp.id = d.counterparty_id
        LEFT JOIN contracts ct ON ct.id = d.contract_id
        WHERE {where_sql}
        """,
        params,
    ).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT
            d.*,
            o.name AS organization_name,
            cp.name AS counterparty_name,
            ct.number AS contract_number,
            ob.name AS object_name,
            p.full_name AS responsible_name
        FROM {cfg['table']} d
        LEFT JOIN organizations o ON o.id = d.organization_id
        LEFT JOIN counterparties cp ON cp.id = d.counterparty_id
        LEFT JOIN contracts ct ON ct.id = d.contract_id
        LEFT JOIN objects ob ON ob.id = d.object_id
        LEFT JOIN persons p ON p.id = d.responsible_id
        WHERE {where_sql}
        ORDER BY d.date DESC, d.id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    items = [
        _cast_flags(i, "is_posted", "marked_for_deletion", "auto_schedule")
        for i in rows_to_dicts(rows)
    ]
    return items, _build_pagination(page, page_size, total)


def _get_document(connection: sqlite3.Connection, *, kind: str, document_id: int) -> dict[str, Any]:
    cfg = _config(kind)
    row = connection.execute(
        f"""
        SELECT
            d.*,
            o.name AS organization_name,
            cp.name AS counterparty_name,
            ct.number AS contract_number,
            ob.name AS object_name,
            p.full_name AS responsible_name
        FROM {cfg['table']} d
        LEFT JOIN organizations o ON o.id = d.organization_id
        LEFT JOIN counterparties cp ON cp.id = d.counterparty_id
        LEFT JOIN contracts ct ON ct.id = d.contract_id
        LEFT JOIN objects ob ON ob.id = d.object_id
        LEFT JOIN persons p ON p.id = d.responsible_id
        WHERE d.id = ? AND d.marked_for_deletion = 0
        """,
        (document_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{cfg['table']} not found")
    document = _cast_flags(row_to_dict(row) or {}, "is_posted", "marked_for_deletion")
    line_rows = connection.execute(
        f"""
        SELECT
            l.*,
            m.code AS material_code,
            m.name AS material_name,
            ob.name AS object_name,
            u.name AS unit_name
        FROM {cfg['line_table']} l
        LEFT JOIN materials m ON m.id = l.material_id
        LEFT JOIN objects ob ON ob.id = l.object_id
        LEFT JOIN units u ON u.id = l.unit_id
        WHERE l.{cfg['header_fk']} = ?
          AND COALESCE(l.marked_for_deletion, 0) = 0
          AND COALESCE(l.is_deleted, 0) = 0
        ORDER BY l.line_number
        """,
        (document_id,),
    ).fetchall()
    document["lines"] = [
        _cast_flags(i, "marked_for_deletion") for i in rows_to_dicts(line_rows)
    ]
    return document


def _sync_lines(
    connection: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    document_id: int,
    lines: list[dict[str, Any]],
) -> None:
    existing_rows = connection.execute(
        f"""
        SELECT id, uuid
        FROM {cfg['line_table']}
        WHERE {cfg['header_fk']} = ?
          AND COALESCE(marked_for_deletion, 0) = 0
          AND COALESCE(is_deleted, 0) = 0
        """,
        (document_id,),
    ).fetchall()
    existing_map = {int(r["id"]): str(r["uuid"]) for r in existing_rows}
    existing_uuid_map = {str(r["uuid"]): int(r["id"]) for r in existing_rows}
    incoming_ids: set[int] = set()

    for raw_line in lines:
        line = _coerce_bools(dict(raw_line))
        line_uuid = str(line.get("uuid") or "").strip() or None
        line_id = int(line["id"]) if line.get("id") is not None else None
        if line_uuid and line_uuid in existing_uuid_map:
            line_id = existing_uuid_map[line_uuid]

        totals = _compute_line_totals(
            line.get("quantity"),
            line.get("price_without_vat"),
            line.get("vat_rate"),
        )
        now = _now_iso()
        created_at = str(line.get("created_at") or now)
        modified_at = str(line.get("modified_at") or line.get("updated_at") or now)
        updated_at = str(line.get("updated_at") or modified_at or now)

        common_fields = {
            "line_number": int(line["line_number"]),
            "material_id": line.get("material_id"),
            "name": str(line.get("name") or "").strip() or "(без наименования)",
            "unit_id": line.get("unit_id"),
            "unit": line.get("unit"),
            "quantity": totals["quantity"],
            "price_without_vat": totals["price_without_vat"],
            "vat_rate": totals["vat_rate"],
            "vat_amount": totals["vat_amount"],
            "sum_without_vat": totals["sum_without_vat"],
            "sum_with_vat": totals["sum_with_vat"],
            "object_id": line.get("object_id"),
            "drawing_code": line.get("drawing_code"),
            "note": line.get("note"),
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
                f"UPDATE {cfg['line_table']} SET {assignments} WHERE id = ? AND {cfg['header_fk']} = ?",
                [*update_payload.values(), line_id, document_id],
            )
        else:
            insert_payload = {
                cfg["header_fk"]: document_id,
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
                f"INSERT INTO {cfg['line_table']} ({columns}) VALUES ({placeholders})",
                list(insert_payload.values()),
            )
            incoming_ids.add(last_insert_id(connection))

    for existing_id in existing_map:
        if existing_id in incoming_ids:
            continue
        now = _now_iso()
        connection.execute(
            f"""
            UPDATE {cfg['line_table']}
            SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, existing_id),
        )


def _save_document(
    connection: sqlite3.Connection,
    *,
    kind: str,
    payload: dict[str, Any],
    document_id: int | None = None,
    user: UserInfo,
) -> dict[str, Any]:
    _require_write(user)
    cfg = _config(kind)
    lines = [dict(line) for line in payload.pop("lines", [])]
    payload["date"] = str(payload["date"])
    payload.pop("auto_schedule", None)
    if not payload.get("number"):
        payload["number"] = _next_document_number(connection, cfg)

    # Pre-compute line totals so the header aggregates stay consistent.
    normalized_lines: list[dict[str, Any]] = []
    for line in lines:
        totals = _compute_line_totals(
            line.get("quantity"),
            line.get("price_without_vat"),
            line.get("vat_rate"),
        )
        normalized_lines.append({**line, **totals})
    totals = _compute_document_totals(normalized_lines)
    payload.update(totals)

    # due_date = date + contract deferral
    due_date = None
    if payload.get("date"):
        deferral = _contract_deferral_days(connection, payload.get("contract_id"))
        if deferral:
            try:
                due_date = (datetime.fromisoformat(payload["date"]).date() + timedelta(days=deferral)).isoformat()
            except ValueError:
                due_date = None
    payload["due_date"] = due_date

    if document_id is None:
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
            f"INSERT INTO {cfg['table']} ({columns}) VALUES ({placeholders})",
            list(insert_payload.values()),
        )
        document_id = last_insert_id(connection)
        document_uuid = str(insert_payload["uuid"])
        sync_operation = "INSERT"
    else:
        existing = _get_document(connection, kind=kind, document_id=document_id)
        if existing["is_posted"]:
            raise HTTPException(status_code=400, detail="Posted document cannot be modified")
        document_uuid = str(existing["uuid"])
        now = _now_iso()
        update_payload = {
            **_coerce_bools(payload),
            "uuid": document_uuid,
            "modified_at": now,
            "updated_at": now,
            "is_deleted": 0,
        }
        assignments = ", ".join(f"{c} = ?" for c in update_payload)
        connection.execute(
            f"UPDATE {cfg['table']} SET {assignments} WHERE id = ?",
            [*update_payload.values(), document_id],
        )
        sync_operation = "UPDATE"

    _sync_lines(connection, cfg=cfg, document_id=document_id, lines=normalized_lines)
    register_sync_change(
        connection,
        entity_type=cfg["table"],
        entity_uuid=document_uuid,
        operation=sync_operation,
    )
    connection.commit()
    return _get_document(connection, kind=kind, document_id=document_id)


def _delete_document(
    connection: sqlite3.Connection,
    *,
    kind: str,
    document_id: int,
    user: UserInfo,
) -> None:
    _require_write(user)
    cfg = _config(kind)
    document = _get_document(connection, kind=kind, document_id=document_id)
    if document["is_posted"]:
        raise HTTPException(status_code=400, detail="Posted document cannot be deleted")
    now = _now_iso()
    connection.execute(
        f"UPDATE {cfg['table']} SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ? WHERE id = ?",
        (now, now, document_id),
    )
    connection.execute(
        f"UPDATE {cfg['line_table']} SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ? WHERE {cfg['header_fk']} = ?",
        (now, now, document_id),
    )
    register_sync_change(
        connection,
        entity_type=cfg["table"],
        entity_uuid=str(document["uuid"]),
        operation="DELETE",
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------


def _inventory_balance(
    connection: sqlite3.Connection,
    *,
    material_id: int | None,
    object_id: int | None,
    on_date: str,
) -> tuple[float, float, float]:
    """Return (quantity_balance, sum_income, quantity_income) up to ``on_date``."""
    if material_id is None:
        return 0.0, 0.0, 0.0
    params: list[Any] = [material_id, on_date]
    object_clause = ""
    if object_id is not None:
        object_clause = "AND object_id = ?"
        params.append(object_id)
    row = connection.execute(
        f"""
        SELECT
            COALESCE(SUM(quantity_income), 0) AS qty_in,
            COALESCE(SUM(quantity_expense), 0) AS qty_out,
            COALESCE(SUM(sum_income), 0) AS sum_in
        FROM inventory_register
        WHERE material_id = ?
          AND period <= ?
          AND COALESCE(is_deleted, 0) = 0
          {object_clause}
        """,
        params,
    ).fetchone()
    qty_in = float(row["qty_in"] or 0)
    qty_out = float(row["qty_out"] or 0)
    sum_in = float(row["sum_in"] or 0)
    return round(qty_in - qty_out, 6), round(sum_in, 2), round(qty_in, 6)


def _post_document(
    connection: sqlite3.Connection,
    *,
    kind: str,
    document_id: int,
    user: UserInfo,
    auto_schedule: bool = True,
) -> None:
    _require_admin(user)
    cfg = _config(kind)
    document = _get_document(connection, kind=kind, document_id=document_id)
    if document["is_posted"]:
        raise HTTPException(status_code=400, detail="Document is already posted")
    if not document["lines"]:
        raise HTTPException(status_code=400, detail="Cannot post an empty document")

    # Re-aggregate header totals from the (possibly edited) lines.
    totals = _compute_document_totals(document["lines"])

    direction = "payable" if kind == "receipt" else "receivable"

    # For issues (realization) check inventory availability per (material, object).
    if kind == "issue":
        doc_date = str(document["date"])
        shortages: list[str] = []
        for line in document["lines"]:
            if not line.get("material_id"):
                continue
            line_object_id = line.get("object_id")
            if line_object_id is None:
                line_object_id = document.get("object_id")
            balance, _, _ = _inventory_balance(
                connection,
                material_id=int(line["material_id"]),
                object_id=line_object_id,
                on_date=doc_date,
            )
            needed = float(line.get("quantity") or 0)
            if needed > balance + 1e-9:
                shortages.append(
                    f"строка {line['line_number']}: '{line.get('name')}' "
                    f"нужно {needed:g}, остаток {balance:g}"
                )
        if shortages:
            raise HTTPException(
                status_code=400,
                detail="Недостаточно остатка на складе: " + "; ".join(shortages[:5]),
            )

    # 1. Clean previous register rows for this registrar (idempotent repost).
    connection.execute(
        "DELETE FROM inventory_register WHERE recorder_type = ? AND recorder_id = ?",
        (cfg["recorder_type"], document_id),
    )
    connection.execute(
        "DELETE FROM mutual_settlements_register WHERE recorder_type = ? AND recorder_id = ?",
        (cfg["recorder_type"], document_id),
    )

    # 2. Write inventory_register per line.
    for line in document["lines"]:
        line_object_id = line.get("object_id")
        if line_object_id is None:
            line_object_id = document.get("object_id")
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
                cfg["recorder_type"],
                document_id,
                int(line["line_number"]),
                str(document["date"]),
                line.get("material_id"),
                line_object_id,
                line.get("unit_id"),
                round(float(line.get("quantity") or 0), 6) if kind == "receipt" else 0.0,
                round(float(line.get("quantity") or 0), 6) if kind == "issue" else 0.0,
                round(float(line.get("sum_without_vat") or 0), 2) if kind == "receipt" else 0.0,
                round(float(line.get("sum_without_vat") or 0), 2) if kind == "issue" else 0.0,
                _now_iso(),
                new_uuid(),
                _now_iso(),
            ),
        )

    # 3. Write one mutual_settlements_register accrual line.
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
            cfg["recorder_type"],
            document_id,
            str(document["date"]),
            int(document["organization_id"]),
            document.get("counterparty_id"),
            document.get("contract_id"),
            document.get("object_id"),
            document.get("estimate_id"),
            direction,
            round(totals["sum_with_vat"], 2),
            _now_iso(),
            new_uuid(),
            _now_iso(),
        ),
    )

    # 4. Update header totals + posted flag.
    now = _now_iso()
    connection.execute(
        f"""
        UPDATE {cfg['table']}
        SET sum_without_vat = ?, vat_amount = ?, sum_with_vat = ?,
            is_posted = 1, posted_at = ?, modified_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            totals["sum_without_vat"],
            totals["vat_amount"],
            totals["sum_with_vat"],
            now,
            now,
            now,
            document_id,
        ),
    )
    register_sync_change(
        connection,
        entity_type=cfg["table"],
        entity_uuid=str(document["uuid"]),
        operation="UPDATE",
    )

    # 5. Optional auto-schedule into the payment calendar (current open schedule).
    if auto_schedule:
        _try_auto_schedule(connection, kind=kind, document=document, totals=totals)

    connection.commit()


def _try_auto_schedule(
    connection: sqlite3.Connection,
    *,
    kind: str,
    document: dict[str, Any],
    totals: dict[str, float],
) -> None:
    doc_date = str(document["date"])
    deferral = _contract_deferral_days(connection, document.get("contract_id"))
    try:
        planned_date = (
            datetime.fromisoformat(doc_date).date() + timedelta(days=deferral)
        ).isoformat()
    except ValueError:
        planned_date = doc_date

    # Find a payment_schedule whose date_from..date_to covers the planned_date.
    schedule = connection.execute(
        """
        SELECT id, uuid FROM payment_schedules
        WHERE marked_for_deletion = 0 AND COALESCE(is_deleted, 0) = 0
          AND is_posted = 0
          AND date_from <= ? AND date_to >= ?
        ORDER BY date_from DESC, id DESC
        LIMIT 1
        """,
        (planned_date, planned_date),
    ).fetchone()
    if schedule is None:
        return

    schedule_id = int(schedule["id"])
    next_line_row = connection.execute(
        """
        SELECT COALESCE(MAX(line_number), 0) + 1 AS next_no
        FROM payment_schedule_lines
        WHERE schedule_id = ?
        """,
        (schedule_id,),
    ).fetchone()
    next_no = int(next_line_row["next_no"])

    direction = "outgoing" if kind == "receipt" else "incoming"
    category = "supplier_invoice" if kind == "receipt" else "customer_invoice"
    source_kind = "goods_receipt" if kind == "receipt" else "goods_issue"

    connection.execute(
        """
        INSERT INTO payment_schedule_lines (
            schedule_id, line_number, direction, category, planned_date,
            counterparty_id, contract_id, estimate_id, object_id,
            planned_amount, description, source_kind, source_ref,
            is_group, group_name, parent_group_id, is_collapsed,
            marked_for_deletion, created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, 0, 0, ?, ?, ?, ?, 0)
        """,
        (
            schedule_id,
            next_no,
            direction,
            category,
            planned_date,
            document.get("counterparty_id"),
            document.get("contract_id"),
            document.get("estimate_id"),
            document.get("object_id"),
            round(totals["sum_with_vat"], 2),
            f"Авто: {document.get('number')} от {doc_date}",
            source_kind,
            f"{source_kind}:{document['id']}",
            _now_iso(),
            _now_iso(),
            new_uuid(),
            _now_iso(),
        ),
    )
    register_sync_change(
        connection,
        entity_type="payment_schedule_lines",
        entity_uuid=str(schedule["uuid"]),
        operation="UPDATE",
    )


def _unpost_document(
    connection: sqlite3.Connection,
    *,
    kind: str,
    document_id: int,
    user: UserInfo,
) -> None:
    _require_admin(user)
    cfg = _config(kind)
    document = _get_document(connection, kind=kind, document_id=document_id)
    if not document["is_posted"]:
        raise HTTPException(status_code=400, detail="Document is not posted")

    # Block unpost if a posted payment transaction already settled this document.
    linked_payments = connection.execute(
        """
        SELECT pt.id, pt.number
        FROM mutual_settlements_register msr
        JOIN payment_transactions pt
          ON pt.id = msr.recorder_id AND msr.recorder_type = 'payment_transaction'
        WHERE msr.payment_amount > 0
          AND pt.contract_id = ?
          AND pt.is_posted = 1
          AND COALESCE(pt.marked_for_deletion, 0) = 0
        LIMIT 1
        """,
        (document.get("contract_id"),),
    ).fetchall()
    if linked_payments:
        raise HTTPException(
            status_code=400,
            detail="Cannot unpost: posted payment transactions already settled this contract. Unpost them first.",
        )

    connection.execute(
        "DELETE FROM inventory_register WHERE recorder_type = ? AND recorder_id = ?",
        (cfg["recorder_type"], document_id),
    )
    connection.execute(
        "DELETE FROM mutual_settlements_register WHERE recorder_type = ? AND recorder_id = ?",
        (cfg["recorder_type"], document_id),
    )
    # Remove auto-scheduled payment lines that originated from this document.
    connection.execute(
        """
        UPDATE payment_schedule_lines
        SET marked_for_deletion = 1, is_deleted = 1
        WHERE source_ref = ?
        """,
        (f"{cfg['recorder_type']}:{document_id}",),
    )
    now = _now_iso()
    connection.execute(
        f"UPDATE {cfg['table']} SET is_posted = 0, posted_at = NULL, modified_at = ?, updated_at = ? WHERE id = ?",
        (now, now, document_id),
    )
    register_sync_change(
        connection,
        entity_type=cfg["table"],
        entity_uuid=str(document["uuid"]),
        operation="UPDATE",
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Public receipt / issue wrappers
# ---------------------------------------------------------------------------


def list_goods_receipts(connection: sqlite3.Connection, **kwargs: Any) -> tuple[list[dict[str, Any]], Pagination]:
    return _list_documents(connection, kind="receipt", **kwargs)


def get_goods_receipt(connection: sqlite3.Connection, document_id: int) -> dict[str, Any]:
    return _get_document(connection, kind="receipt", document_id=document_id)


def save_goods_receipt(
    connection: sqlite3.Connection,
    *,
    payload: dict[str, Any],
    document_id: int | None = None,
    user: UserInfo,
) -> dict[str, Any]:
    return _save_document(connection, kind="receipt", payload=payload, document_id=document_id, user=user)


def delete_goods_receipt(connection: sqlite3.Connection, document_id: int, user: UserInfo) -> None:
    _delete_document(connection, kind="receipt", document_id=document_id, user=user)


def post_goods_receipt(
    connection: sqlite3.Connection,
    *,
    document_id: int,
    user: UserInfo,
    auto_schedule: bool = True,
) -> None:
    _post_document(connection, kind="receipt", document_id=document_id, user=user, auto_schedule=auto_schedule)


def unpost_goods_receipt(connection: sqlite3.Connection, *, document_id: int, user: UserInfo) -> None:
    _unpost_document(connection, kind="receipt", document_id=document_id, user=user)


def list_goods_issues(connection: sqlite3.Connection, **kwargs: Any) -> tuple[list[dict[str, Any]], Pagination]:
    return _list_documents(connection, kind="issue", **kwargs)


def get_goods_issue(connection: sqlite3.Connection, document_id: int) -> dict[str, Any]:
    return _get_document(connection, kind="issue", document_id=document_id)


def save_goods_issue(
    connection: sqlite3.Connection,
    *,
    payload: dict[str, Any],
    document_id: int | None = None,
    user: UserInfo,
) -> dict[str, Any]:
    return _save_document(connection, kind="issue", payload=payload, document_id=document_id, user=user)


def delete_goods_issue(connection: sqlite3.Connection, document_id: int, user: UserInfo) -> None:
    _delete_document(connection, kind="issue", document_id=document_id, user=user)


def post_goods_issue(
    connection: sqlite3.Connection,
    *,
    document_id: int,
    user: UserInfo,
    auto_schedule: bool = True,
) -> None:
    _post_document(connection, kind="issue", document_id=document_id, user=user, auto_schedule=auto_schedule)


def unpost_goods_issue(connection: sqlite3.Connection, *, document_id: int, user: UserInfo) -> None:
    _unpost_document(connection, kind="issue", document_id=document_id, user=user)


def copy_goods_receipt(connection: sqlite3.Connection, *, document_id: int, user: UserInfo) -> dict[str, Any]:
    source = _get_document(connection, kind="receipt", document_id=document_id)
    return _copy_document(connection, kind="receipt", source=source, user=user)


def copy_goods_issue(connection: sqlite3.Connection, *, document_id: int, user: UserInfo) -> dict[str, Any]:
    source = _get_document(connection, kind="issue", document_id=document_id)
    return _copy_document(connection, kind="issue", source=source, user=user)


def _copy_document(
    connection: sqlite3.Connection,
    *,
    kind: str,
    source: dict[str, Any],
    user: UserInfo,
) -> dict[str, Any]:
    from datetime import date as _date

    payload = {
        "number": "",
        "date": _date.today().isoformat(),
        "organization_id": source.get("organization_id"),
        "counterparty_id": source.get("counterparty_id"),
        "contract_id": source.get("contract_id"),
        "object_id": source.get("object_id"),
        "responsible_id": source.get("responsible_id"),
        "notes": source.get("notes"),
        "lines": [
            {
                "material_id": line.get("material_id"),
                "object_id": line.get("object_id"),
                "quantity": line.get("quantity", 0),
                "price_without_vat": line.get("price_without_vat", 0),
                "vat_rate": line.get("vat_rate", 0),
                "unit_id": line.get("unit_id"),
            }
            for line in source.get("lines", [])
        ],
    }
    return _save_document(connection, kind=kind, payload=payload, user=user)


# ---------------------------------------------------------------------------
# Inventory register queries
# ---------------------------------------------------------------------------


def inventory_balances(
    connection: sqlite3.Connection,
    *,
    on_date: str | None = None,
    object_id: int | None = None,
    material_id: int | None = None,
) -> list[dict[str, Any]]:
    target_date = on_date or date.today().isoformat()
    where_parts = ["COALESCE(ir.is_deleted, 0) = 0", "ir.period <= ?"]
    params: list[Any] = [target_date]
    if object_id is not None:
        where_parts.append("ir.object_id = ?")
        params.append(object_id)
    if material_id is not None:
        where_parts.append("ir.material_id = ?")
        params.append(material_id)
    where_sql = " AND ".join(where_parts)
    rows = connection.execute(
        f"""
        SELECT
            ir.material_id,
            m.code AS material_code,
            m.name AS material_name,
            ir.object_id,
            ob.name AS object_name,
            ir.unit_id,
            u.name AS unit_name,
            COALESCE(SUM(ir.quantity_income), 0) AS qty_in,
            COALESCE(SUM(ir.quantity_expense), 0) AS qty_out,
            COALESCE(SUM(ir.sum_income), 0) AS sum_in,
            COALESCE(SUM(ir.sum_expense), 0) AS sum_out
        FROM inventory_register ir
        LEFT JOIN materials m ON m.id = ir.material_id
        LEFT JOIN objects ob ON ob.id = ir.object_id
        LEFT JOIN units u ON u.id = ir.unit_id
        WHERE {where_sql}
        GROUP BY ir.material_id, m.code, m.name, ir.object_id, ob.name, ir.unit_id, u.name
        HAVING (qty_in - qty_out) <> 0
        ORDER BY m.name, ob.name
        """,
        params,
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        qty_in = float(row["qty_in"] or 0)
        qty_out = float(row["qty_out"] or 0)
        sum_in = float(row["sum_in"] or 0)
        sum_out = float(row["sum_out"] or 0)
        balance = round(qty_in - qty_out, 6)
        avg_price = round(sum_in / qty_in, 2) if qty_in else 0.0
        items.append(
            {
                "material_id": row["material_id"],
                "material_code": row["material_code"],
                "material_name": row["material_name"],
                "object_id": row["object_id"],
                "object_name": row["object_name"],
                "unit_id": row["unit_id"],
                "unit_name": row["unit_name"],
                "quantity_income": round(qty_in, 6),
                "quantity_expense": round(qty_out, 6),
                "quantity_balance": balance,
                "sum_income": round(sum_in, 2),
                "sum_expense": round(sum_out, 2),
                "average_price": avg_price,
            }
        )
    return items


def inventory_movements(
    connection: sqlite3.Connection,
    *,
    date_from: str,
    date_to: str,
    object_id: int | None = None,
    material_id: int | None = None,
) -> list[dict[str, Any]]:
    where_parts = ["COALESCE(ir.is_deleted, 0) = 0", "ir.period >= ?", "ir.period <= ?"]
    params: list[Any] = [date_from, date_to]
    if object_id is not None:
        where_parts.append("ir.object_id = ?")
        params.append(object_id)
    if material_id is not None:
        where_parts.append("ir.material_id = ?")
        params.append(material_id)
    where_sql = " AND ".join(where_parts)
    rows = connection.execute(
        f"""
        SELECT
            ir.period, ir.recorder_type, ir.recorder_id, ir.line_number,
            ir.material_id, m.code AS material_code, m.name AS material_name,
            ir.object_id, ob.name AS object_name,
            ir.unit_id, u.name AS unit_name,
            ir.quantity_income, ir.quantity_expense, ir.sum_income, ir.sum_expense
        FROM inventory_register ir
        LEFT JOIN materials m ON m.id = ir.material_id
        LEFT JOIN objects ob ON ob.id = ir.object_id
        LEFT JOIN units u ON u.id = ir.unit_id
        WHERE {where_sql}
        ORDER BY ir.period, ir.recorder_type, ir.recorder_id, ir.line_number
        """,
        params,
    ).fetchall()
    return rows_to_dicts(rows)


def get_document_movements(
    connection: sqlite3.Connection,
    *,
    kind: str,
    document_id: int,
) -> dict[str, Any]:
    """All register rows produced by a single goods document.

    Returns ``{document, inventory, settlements, totals}``. A non-posted
    document has no movements → empty ``inventory`` / ``settlements`` lists.
    """
    cfg = _config(kind)
    document = _get_document(connection, kind=kind, document_id=document_id)
    recorder_type = cfg["recorder_type"]

    inv_rows = connection.execute(
        """
        SELECT
            ir.line_number, ir.period,
            ir.material_id, m.code AS material_code, m.name AS material_name,
            ir.object_id, ob.name AS object_name,
            ir.unit_id, u.name AS unit_name,
            ir.quantity_income, ir.quantity_expense, ir.sum_income, ir.sum_expense
        FROM inventory_register ir
        LEFT JOIN materials m ON m.id = ir.material_id
        LEFT JOIN objects ob ON ob.id = ir.object_id
        LEFT JOIN units u ON u.id = ir.unit_id
        WHERE ir.recorder_type = ? AND ir.recorder_id = ?
          AND COALESCE(ir.is_deleted, 0) = 0
        ORDER BY ir.line_number
        """,
        (recorder_type, document_id),
    ).fetchall()
    inventory = rows_to_dicts(inv_rows)

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
        WHERE msr.recorder_type = ? AND msr.recorder_id = ?
          AND COALESCE(msr.is_deleted, 0) = 0
        ORDER BY msr.line_number
        """,
        (recorder_type, document_id),
    ).fetchall()
    settlements = rows_to_dicts(set_rows)

    totals = {
        "quantity_income": _round2(sum(float(r.get("quantity_income") or 0) for r in inventory)),
        "quantity_expense": _round2(sum(float(r.get("quantity_expense") or 0) for r in inventory)),
        "sum_income": _round2(sum(float(r.get("sum_income") or 0) for r in inventory)),
        "sum_expense": _round2(sum(float(r.get("sum_expense") or 0) for r in inventory)),
        "accrual_amount": _round2(sum(float(r.get("accrual_amount") or 0) for r in settlements)),
        "payment_amount": _round2(sum(float(r.get("payment_amount") or 0) for r in settlements)),
        "planned_amount": _round2(sum(float(r.get("planned_amount") or 0) for r in settlements)),
    }
    return {
        "document": {
            "id": document["id"],
            "number": document.get("number"),
            "date": document.get("date"),
            "kind": kind,
            "is_posted": bool(document.get("is_posted")),
            "sum_with_vat": _round2(document.get("sum_with_vat")),
        },
        "inventory": inventory,
        "settlements": settlements,
        "totals": totals,
    }


# ---------------------------------------------------------------------------
# Mutual settlements queries
# ---------------------------------------------------------------------------


def settlements_balance(
    connection: sqlite3.Connection,
    *,
    organization_id: int | None = None,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
    object_id: int | None = None,
    on_date: str | None = None,
) -> list[dict[str, Any]]:
    where_parts = ["COALESCE(msr.is_deleted, 0) = 0"]
    params: list[Any] = []
    if on_date:
        where_parts.append("msr.period <= ?")
        params.append(on_date)
    if organization_id is not None:
        where_parts.append("msr.organization_id = ?")
        params.append(organization_id)
    if counterparty_id is not None:
        where_parts.append("msr.counterparty_id = ?")
        params.append(counterparty_id)
    if contract_id is not None:
        where_parts.append("msr.contract_id = ?")
        params.append(contract_id)
    if object_id is not None:
        where_parts.append("msr.object_id = ?")
        params.append(object_id)
    where_sql = " AND ".join(where_parts)
    rows = connection.execute(
        f"""
        SELECT
            msr.organization_id,
            o.name AS organization_name,
            msr.counterparty_id,
            cp.name AS counterparty_name,
            msr.contract_id,
            ct.number AS contract_number,
            msr.object_id,
            ob.name AS object_name,
            COALESCE(SUM(CASE WHEN msr.direction = 'receivable' THEN msr.accrual_amount ELSE 0 END), 0) AS rec_accrual,
            COALESCE(SUM(CASE WHEN msr.direction = 'receivable' THEN msr.payment_amount ELSE 0 END), 0) AS rec_payment,
            COALESCE(SUM(CASE WHEN msr.direction = 'payable' THEN msr.accrual_amount ELSE 0 END), 0) AS pay_accrual,
            COALESCE(SUM(CASE WHEN msr.direction = 'payable' THEN msr.payment_amount ELSE 0 END), 0) AS pay_payment
        FROM mutual_settlements_register msr
        LEFT JOIN organizations o ON o.id = msr.organization_id
        LEFT JOIN counterparties cp ON cp.id = msr.counterparty_id
        LEFT JOIN contracts ct ON ct.id = msr.contract_id
        LEFT JOIN objects ob ON ob.id = msr.object_id
        WHERE {where_sql}
        GROUP BY msr.organization_id, o.name, msr.counterparty_id, cp.name,
                 msr.contract_id, ct.number, msr.object_id, ob.name
        HAVING (rec_accrual + rec_payment + pay_accrual + pay_payment) <> 0
        ORDER BY o.name, cp.name, ct.number
        """,
        params,
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        rec_accrual = float(row["rec_accrual"] or 0)
        rec_payment = float(row["rec_payment"] or 0)
        pay_accrual = float(row["pay_accrual"] or 0)
        pay_payment = float(row["pay_payment"] or 0)
        items.append(
            {
                "organization_id": row["organization_id"],
                "organization_name": row["organization_name"],
                "counterparty_id": row["counterparty_id"],
                "counterparty_name": row["counterparty_name"],
                "contract_id": row["contract_id"],
                "contract_number": row["contract_number"],
                "object_id": row["object_id"],
                "object_name": row["object_name"],
                "receivable_accrual": round(rec_accrual, 2),
                "receivable_payment": round(rec_payment, 2),
                "receivable_balance": round(rec_accrual - rec_payment, 2),
                "payable_accrual": round(pay_accrual, 2),
                "payable_payment": round(pay_payment, 2),
                "payable_balance": round(pay_accrual - pay_payment, 2),
            }
        )
    return items


def settlements_ledger(
    connection: sqlite3.Connection,
    *,
    organization_id: int,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    where_parts = ["COALESCE(msr.is_deleted, 0) = 0", "msr.organization_id = ?"]
    params: list[Any] = [organization_id]
    if counterparty_id is not None:
        where_parts.append("msr.counterparty_id = ?")
        params.append(counterparty_id)
    if contract_id is not None:
        where_parts.append("msr.contract_id = ?")
        params.append(contract_id)
    if date_from:
        where_parts.append("msr.period >= ?")
        params.append(date_from)
    if date_to:
        where_parts.append("msr.period <= ?")
        params.append(date_to)
    where_sql = " AND ".join(where_parts)
    rows = connection.execute(
        f"""
        SELECT
            msr.period, msr.recorder_type, msr.recorder_id, msr.line_number,
            msr.direction, msr.accrual_amount, msr.payment_amount, msr.planned_amount,
            msr.contract_id, ct.number AS contract_number,
            msr.object_id, ob.name AS object_name
        FROM mutual_settlements_register msr
        LEFT JOIN contracts ct ON ct.id = msr.contract_id
        LEFT JOIN objects ob ON ob.id = msr.object_id
        WHERE {where_sql}
        ORDER BY msr.period, msr.id
        """,
        params,
    ).fetchall()
    items: list[dict[str, Any]] = []
    rec_running = 0.0
    pay_running = 0.0
    for row in rows:
        accrual = float(row["accrual_amount"] or 0)
        payment = float(row["payment_amount"] or 0)
        if row["direction"] == "receivable":
            rec_running += accrual - payment
        else:
            pay_running += accrual - payment
        items.append(
            {
                "period": row["period"],
                "recorder_type": row["recorder_type"],
                "recorder_id": row["recorder_id"],
                "line_number": row["line_number"],
                "direction": row["direction"],
                "accrual_amount": round(accrual, 2),
                "payment_amount": round(payment, 2),
                "planned_amount": round(float(row["planned_amount"] or 0), 2),
                "contract_id": row["contract_id"],
                "contract_number": row["contract_number"],
                "object_id": row["object_id"],
                "object_name": row["object_name"],
                "receivable_balance_running": round(rec_running, 2),
                "payable_balance_running": round(pay_running, 2),
            }
        )
    return items


def settlements_overdue(connection: sqlite3.Connection, *, on_date: str | None = None) -> list[dict[str, Any]]:
    today = on_date or date.today().isoformat()
    rows = connection.execute(
        """
        SELECT
            msr.organization_id,
            o.name AS organization_name,
            msr.counterparty_id,
            cp.name AS counterparty_name,
            msr.contract_id,
            ct.number AS contract_number,
            msr.direction,
            msr.period,
            SUM(msr.accrual_amount - msr.payment_amount) AS overdue_amount
        FROM mutual_settlements_register msr
        LEFT JOIN organizations o ON o.id = msr.organization_id
        LEFT JOIN counterparties cp ON cp.id = msr.counterparty_id
        LEFT JOIN contracts ct ON ct.id = msr.contract_id
        WHERE COALESCE(msr.is_deleted, 0) = 0
          AND msr.period < ?
        GROUP BY msr.organization_id, o.name, msr.counterparty_id, cp.name,
                 msr.contract_id, ct.number, msr.direction, msr.period
        HAVING overdue_amount > 0.001
        ORDER BY o.name, cp.name, msr.period
        """,
        (today,),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        period = str(row["period"])
        try:
            days = (datetime.fromisoformat(today).date() - datetime.fromisoformat(period).date()).days
        except ValueError:
            days = 0
        items.append(
            {
                "organization_id": row["organization_id"],
                "organization_name": row["organization_name"],
                "counterparty_id": row["counterparty_id"],
                "counterparty_name": row["counterparty_name"],
                "contract_id": row["contract_id"],
                "contract_number": row["contract_number"],
                "direction": row["direction"],
                "overdue_amount": round(float(row["overdue_amount"] or 0), 2),
                "period": period,
                "days_overdue": max(0, days),
            }
        )
    return items


def settlements_turnover(
    connection: sqlite3.Connection,
    *,
    date_from: str,
    date_to: str,
    organization_id: int | None = None,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
) -> list[dict[str, Any]]:
    """Оборотно-сальдовая ведомость по взаиморасчетам.

    Для каждого (орг, контрагент, договор): сальдо начальное (на ``date_from``),
    обороты (начисления и оплаты в [date_from, date_to]) и сальдо конечное,
    раздельно по ``receivable`` (Дт — нам должны) и ``payable`` (Кт — мы должны).
    Использует ``CASE WHEN`` (переносимо между SQLite и PostgreSQL).
    """
    where_parts = ["COALESCE(msr.is_deleted, 0) = 0"]
    params: list[Any] = []
    if organization_id is not None:
        where_parts.append("msr.organization_id = ?")
        params.append(organization_id)
    if counterparty_id is not None:
        where_parts.append("msr.counterparty_id = ?")
        params.append(counterparty_id)
    if contract_id is not None:
        where_parts.append("msr.contract_id = ?")
        params.append(contract_id)
    where_sql = " AND ".join(where_parts)

    def _sum(direction: str, field: str, window: str) -> str:
        if window == "opening":
            period_cond = "msr.period < ?"
            window_params = [date_from]
        else:  # turnover
            period_cond = "msr.period >= ? AND msr.period <= ?"
            window_params = [date_from, date_to]
        # Embed the direction/period as a CASE-insensitive aggregate via SUM(CASE WHEN ...).
        return (
            f"COALESCE(SUM(CASE WHEN msr.direction = '{direction}' AND {period_cond} "
            f"THEN msr.{field} ELSE 0 END), 0)"
        ), window_params

    # Build SELECT with 8 sums; collect their period params in the right order.
    clauses: list[str] = []
    clause_params: list[Any] = []
    for direction in ("receivable", "payable"):
        for field in ("accrual_amount", "payment_amount"):
            for window in ("opening", "turnover"):
                sql, wp = _sum(direction, field, window)
                prefix = "rec" if direction == "receivable" else "pay"
                wnd = "open" if window == "opening" else "turn"
                fld = "acc" if field == "accrual_amount" else "pay"
                clauses.append(f"{sql} AS {prefix}_{wnd}_{fld}")
                clause_params.extend(wp)

    rows = connection.execute(
        f"""
        SELECT
            msr.organization_id,
            o.name AS organization_name,
            msr.counterparty_id,
            cp.name AS counterparty_name,
            msr.contract_id,
            ct.number AS contract_number,
            {', '.join(clauses)}
        FROM mutual_settlements_register msr
        LEFT JOIN organizations o ON o.id = msr.organization_id
        LEFT JOIN counterparties cp ON cp.id = msr.counterparty_id
        LEFT JOIN contracts ct ON ct.id = msr.contract_id
        WHERE {where_sql}
        GROUP BY msr.organization_id, o.name, msr.counterparty_id, cp.name, msr.contract_id, ct.number
        ORDER BY o.name, cp.name, ct.number
        """,
        [*clause_params, *params],
    ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        rec_open = float(row["rec_open_acc"] or 0) - float(row["rec_open_pay"] or 0)
        rec_acc = float(row["rec_turn_acc"] or 0)
        rec_pay = float(row["rec_turn_pay"] or 0)
        pay_open = float(row["pay_open_acc"] or 0) - float(row["pay_open_pay"] or 0)
        pay_acc = float(row["pay_turn_acc"] or 0)
        pay_pay = float(row["pay_turn_pay"] or 0)
        if abs(rec_open + rec_acc + rec_pay + pay_open + pay_acc + pay_pay) < 0.001:
            continue
        items.append(
            {
                "organization_id": row["organization_id"],
                "organization_name": row["organization_name"],
                "counterparty_id": row["counterparty_id"],
                "counterparty_name": row["counterparty_name"],
                "contract_id": row["contract_id"],
                "contract_number": row["contract_number"],
                "receivable_opening": round(rec_open, 2),
                "receivable_accrual_turnover": round(rec_acc, 2),
                "receivable_payment_turnover": round(rec_pay, 2),
                "receivable_closing": round(rec_open + rec_acc - rec_pay, 2),
                "payable_opening": round(pay_open, 2),
                "payable_accrual_turnover": round(pay_acc, 2),
                "payable_payment_turnover": round(pay_pay, 2),
                "payable_closing": round(pay_open + pay_acc - pay_pay, 2),
                "period_from": date_from,
                "period_to": date_to,
            }
        )
    return items


# ---------------------------------------------------------------------------
# Payment application (called from payment_services)
# ---------------------------------------------------------------------------


def apply_payment_to_settlements(
    connection: sqlite3.Connection,
    *,
    tx_id: int,
    tx_direction: str,
    amount: float,
    organization_id: int | None,
    counterparty_id: int | None,
    contract_id: int | None,
    object_id: int | None,
    estimate_id: int | None,
    period: str,
    linked_line_id: int | None = None,
) -> None:
    """Write a payment line into mutual_settlements_register.

    FIFO application: the ``payment_amount`` is recorded against the matching
    direction (``payable`` for outgoing, ``receivable`` for incoming). When the
    payment exceeds open accruals, it is still recorded (an overpayment /
    advance), but the invariant ``payment <= accrual`` is enforced elsewhere by
    the UI. Here we only store the movement.
    """
    direction = "payable" if tx_direction == "outgoing" else "receivable"
    connection.execute(
        "DELETE FROM mutual_settlements_register "
        "WHERE recorder_type = 'payment_transaction' AND recorder_id = ?",
        (tx_id,),
    )
    # mutual_settlements_register.organization_id is NOT NULL; payments without
    # an organization context (no contract and no organization in DB) do not
    # participate in mutual settlements — they are still recorded in
    # payment_schedule_register by the caller.
    if organization_id is None:
        return
    connection.execute(
        """
        INSERT INTO mutual_settlements_register (
            recorder_type, recorder_id, line_number, period,
            organization_id, counterparty_id, contract_id, object_id, estimate_id,
            direction, accrual_amount, payment_amount, planned_amount,
            linked_line_id, created_at, uuid, updated_at, is_deleted
        )
        VALUES ('payment_transaction', ?, 1, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, ?, 0)
        """,
        (
            tx_id,
            period,
            organization_id,
            counterparty_id,
            contract_id,
            object_id,
            estimate_id,
            direction,
            round(float(amount or 0), 2),
            linked_line_id,
            _now_iso(),
            new_uuid(),
            _now_iso(),
        ),
    )


def remove_payment_from_settlements(connection: sqlite3.Connection, *, tx_id: int) -> None:
    connection.execute(
        "DELETE FROM mutual_settlements_register "
        "WHERE recorder_type = 'payment_transaction' AND recorder_id = ?",
        (tx_id,),
    )


# ---------------------------------------------------------------------------
# Auto-suggest for payment calendar
# ---------------------------------------------------------------------------


def suggest_outgoing_from_goods_receipts(
    connection: sqlite3.Connection,
    *,
    date_from: str,
    date_to: str,
    organization_id: int | None = None,
    object_id: int | None = None,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            gr.id, gr.number, gr.date, gr.sum_with_vat,
            gr.organization_id, gr.counterparty_id, gr.contract_id, gr.object_id,
            COALESCE(SUM(msr.payment_amount), 0) AS paid
        FROM goods_receipts gr
        LEFT JOIN mutual_settlements_register msr
          ON msr.recorder_id = gr.id AND msr.recorder_type = 'goods_receipt'
         AND msr.direction = 'payable'
        WHERE gr.is_posted = 1
          AND COALESCE(gr.marked_for_deletion, 0) = 0
          AND gr.date >= ? AND gr.date <= ?
          AND (? IS NULL OR gr.organization_id = ?)
          AND (? IS NULL OR gr.object_id = ?)
        GROUP BY gr.id
        HAVING (gr.sum_with_vat - paid) > 0.001
        ORDER BY gr.date
        """,
        (date_from, date_to, organization_id, organization_id, object_id, object_id),
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        rest = round(float(row["sum_with_vat"] or 0) - float(row["paid"] or 0), 2)
        if rest <= 0:
            continue
        deferral = _contract_deferral_days(connection, row["contract_id"])
        try:
            planned_date = (
                datetime.fromisoformat(str(row["date"])).date() + timedelta(days=deferral)
            ).isoformat()
        except ValueError:
            planned_date = str(row["date"])
        results.append(
            {
                "direction": "outgoing",
                "category": "supplier_invoice",
                "planned_date": planned_date,
                "counterparty_id": row["counterparty_id"],
                "contract_id": row["contract_id"],
                "estimate_id": None,
                "object_id": row["object_id"],
                "planned_amount": rest,
                "description": f"Поступление ТМЦ {row['number']} от {row['date']}",
                "source_kind": "goods_receipt",
                "source_ref": f"goods_receipt:{row['id']}",
            }
        )
    return results


def suggest_incoming_from_goods_issues(
    connection: sqlite3.Connection,
    *,
    date_from: str,
    date_to: str,
    organization_id: int | None = None,
    object_id: int | None = None,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            gi.id, gi.number, gi.date, gi.sum_with_vat,
            gi.organization_id, gi.counterparty_id, gi.contract_id, gi.object_id,
            COALESCE(SUM(msr.payment_amount), 0) AS paid
        FROM goods_issues gi
        LEFT JOIN mutual_settlements_register msr
          ON msr.recorder_id = gi.id AND msr.recorder_type = 'goods_issue'
         AND msr.direction = 'receivable'
        WHERE gi.is_posted = 1
          AND COALESCE(gi.marked_for_deletion, 0) = 0
          AND gi.date >= ? AND gi.date <= ?
          AND (? IS NULL OR gi.organization_id = ?)
          AND (? IS NULL OR gi.object_id = ?)
        GROUP BY gi.id
        HAVING (gi.sum_with_vat - paid) > 0.001
        ORDER BY gi.date
        """,
        (date_from, date_to, organization_id, organization_id, object_id, object_id),
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        rest = round(float(row["sum_with_vat"] or 0) - float(row["paid"] or 0), 2)
        if rest <= 0:
            continue
        deferral = _contract_deferral_days(connection, row["contract_id"])
        try:
            planned_date = (
                datetime.fromisoformat(str(row["date"])).date() + timedelta(days=deferral)
            ).isoformat()
        except ValueError:
            planned_date = str(row["date"])
        results.append(
            {
                "direction": "incoming",
                "category": "customer_invoice",
                "planned_date": planned_date,
                "counterparty_id": row["counterparty_id"],
                "contract_id": row["contract_id"],
                "estimate_id": None,
                "object_id": row["object_id"],
                "planned_amount": rest,
                "description": f"Реализация ТМЦ {row['number']} от {row['date']}",
                "source_kind": "goods_issue",
                "source_ref": f"goods_issue:{row['id']}",
            }
        )
    return results


# ---------------------------------------------------------------------------
# Excel export / import of document lines
# ---------------------------------------------------------------------------


_GOODS_LINE_HEADERS = [
    "№",
    "Материал",
    "Код материала",
    "Наименование",
    "Ед.изм.",
    "Количество",
    "Цена без НДС",
    "Ставка НДС %",
    "Сумма без НДС",
    "Сумма НДС",
    "Сумма с НДС",
    "Объект",
    "Чертёж/СП",
    "Примечание",
]


def _line_to_excel_row(line: dict[str, Any]) -> list[str]:
    return [
        str(line.get("line_number") or ""),
        str(line.get("material_id") or ""),
        str(line.get("material_code") or ""),
        str(line.get("name") or ""),
        str(line.get("unit_name") or line.get("unit") or ""),
        str(line.get("quantity") or ""),
        str(line.get("price_without_vat") or ""),
        str(line.get("vat_rate") or ""),
        str(line.get("sum_without_vat") or ""),
        str(line.get("vat_amount") or ""),
        str(line.get("sum_with_vat") or ""),
        str(line.get("object_id") or ""),
        str(line.get("drawing_code") or ""),
        str(line.get("note") or ""),
    ]


def _build_excel_xml(title: str, headers: list[str], rows: list[list[str]]) -> bytes:
    from xml.sax.saxutils import escape

    worksheet_rows = [
        "<Row>"
        + "".join(f'<Cell><Data ss:Type="String">{escape(str(cell))}</Data></Cell>' for cell in headers)
        + "</Row>"
    ]
    for row in rows:
        worksheet_rows.append(
            "<Row>"
            + "".join(f'<Cell><Data ss:Type="String">{escape(str(cell))}</Data></Cell>' for cell in row)
            + "</Row>"
        )
    xml = f"""<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="{escape(title)}">
  <Table>
   {''.join(worksheet_rows)}
  </Table>
 </Worksheet>
</Workbook>
"""
    return xml.encode("utf-8-sig")


def export_goods_document_lines(
    connection: sqlite3.Connection,
    *,
    kind: str,
    document_id: int,
) -> bytes:
    document = _get_document(connection, kind=kind, document_id=document_id)
    cfg = _config(kind)
    rows = [_line_to_excel_row(line) for line in document["lines"]]
    title = f"{cfg['prefix']}-{document.get('number') or document_id}"
    return _build_excel_xml(title, _GOODS_LINE_HEADERS, rows)


def _extract_rows_from_spreadsheet_xml(content: bytes) -> list[list[str]]:
    namespace = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
    root = ET.fromstring(content.decode("utf-8-sig"))
    rows: list[list[str]] = []
    for row in root.findall(".//ss:Worksheet/ss:Table/ss:Row", namespace):
        values: list[str] = []
        for cell in row.findall("ss:Cell", namespace):
            data = cell.find("ss:Data", namespace)
            values.append("" if data is None or data.text is None else data.text.strip())
        if any(value != "" for value in values):
            rows.append(values)
    return rows


def _extract_rows_from_xlsx(content: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for text_node in shared_root.findall(".//{*}t"):
                shared_strings.append(text_node.text or "")
        worksheet_name = next(
            (name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")),
            None,
        )
        if worksheet_name is None:
            raise HTTPException(status_code=400, detail="Workbook does not contain worksheets")
        root = ET.fromstring(archive.read(worksheet_name))
        rows: list[list[str]] = []
        for row in root.findall(".//{*}sheetData/{*}row"):
            values: list[str] = []
            for cell in row.findall("{*}c"):
                cell_type = cell.attrib.get("t")
                raw_value = cell.find("{*}v")
                if cell_type == "s" and raw_value is not None and raw_value.text is not None:
                    index = int(raw_value.text)
                    values.append(shared_strings[index] if index < len(shared_strings) else "")
                elif cell_type == "inlineStr":
                    text_node = cell.find(".//{*}t")
                    values.append("" if text_node is None or text_node.text is None else text_node.text)
                else:
                    values.append("" if raw_value is None or raw_value.text is None else raw_value.text)
            if any(value != "" for value in values):
                rows.append(values)
        return rows


def _parse_float(value: str | None) -> float:
    if value is None:
        return 0.0
    cleaned = str(value).strip().replace(",", ".").replace(" ", "")
    if cleaned == "":
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if cleaned == "":
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _goods_header_mapping(header: list[str]) -> dict[str, int]:
    normalized = {
        index: "".join(ch.lower() for ch in value if ch.isalnum()).strip()
        for index, value in enumerate(header)
    }
    aliases = {
        "line_number": {"№", "n", "номер", "nn", "line", "нпп"},
        "material_id": {"материал", "materialid", "material", "идмат"},
        "material_code": {"кодматериала", "код", "артикул", "materialcode", "code"},
        "name": {"наименование", "name", "наим", "номенклатура"},
        "unit": {"едизм", "ед", "unit", "единица"},
        "quantity": {"количество", "колво", "quantity", "qty", "кол"},
        "price_without_vat": {"ценабезндс", "цена", "price", "pricevat", "ценабез"},
        "vat_rate": {"ставкандс", "ндс", "vatrate", "vat"},
        "sum_without_vat": {"суммабезндс", "суммабез", "sumvat"},
        "vat_amount": {"суммандс", "ндссумма", "vatamount"},
        "sum_with_vat": {"суммасндс", "сумма", "total", "sumwithvat"},
        "object_id": {"объект", "objectid", "object"},
        "drawing_code": {"чертеж", "чертёж", "сп", "drawing", "drawingcode"},
        "note": {"примечание", "note", "comment"},
    }
    result: dict[str, int] = {}
    for index, value in normalized.items():
        for target, candidates in aliases.items():
            if value in candidates:
                result[target] = index
                break
    return result


def preview_goods_lines_import(
    connection: sqlite3.Connection,
    *,
    kind: str,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        rows = _extract_rows_from_xlsx(content)
    elif lower.endswith(".xls"):
        rows = _extract_rows_from_spreadsheet_xml(content)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .xlsx or .xls")
    if not rows:
        raise HTTPException(status_code=400, detail="The import file is empty")

    header_map = _goods_header_mapping(rows[0])
    if "name" not in header_map and "material_id" not in header_map:
        raise HTTPException(
            status_code=400,
            detail="Не найден столбец 'Наименование' или 'Материал'. Проверьте заголовки.",
        )

    warnings: list[str] = []
    lines: list[dict[str, Any]] = []
    line_no = 0
    for raw in rows[1:]:
        def cell(key: str) -> str | None:
            idx = header_map.get(key)
            return None if idx is None or idx >= len(raw) else raw[idx]

        name_val = (cell("name") or "").strip()
        material_id = _parse_int(cell("material_id"))
        if not name_val and material_id is None:
            continue

        # Resolve name from material if empty.
        if not name_val and material_id is not None:
            m_row = connection.execute(
                "SELECT name FROM materials WHERE id = ?",
                (material_id,),
            ).fetchone()
            if m_row is not None:
                name_val = str(m_row["name"] or "")
            else:
                warnings.append(f"Строка {line_no + 1}: материал id={material_id} не найден")

        # Material code → resolve material_id if missing.
        code_val = (cell("material_code") or "").strip()
        if material_id is None and code_val:
            m_row = connection.execute(
                "SELECT id FROM materials WHERE code = ? AND code IS NOT NULL AND code != ''",
                (code_val,),
            ).fetchone()
            if m_row is not None:
                material_id = int(m_row["id"])

        quantity = _parse_float(cell("quantity"))
        price = _parse_float(cell("price_without_vat"))
        vat_rate = _parse_float(cell("vat_rate")) or 20.0
        totals = _compute_line_totals(quantity, price, vat_rate)

        line_no += 1
        lines.append(
            {
                "line_number": line_no,
                "material_id": material_id,
                "name": name_val or "(без наименования)",
                "unit_id": None,
                "unit": (cell("unit") or "").strip() or None,
                "quantity": totals["quantity"],
                "price_without_vat": totals["price_without_vat"],
                "vat_rate": totals["vat_rate"],
                "vat_amount": totals["vat_amount"],
                "sum_without_vat": totals["sum_without_vat"],
                "sum_with_vat": totals["sum_with_vat"],
                "object_id": _parse_int(cell("object_id")),
                "drawing_code": (cell("drawing_code") or "").strip() or None,
                "note": (cell("note") or "").strip() or None,
            }
        )

    return {
        "filename": filename,
        "detected_columns": header_map,
        "rows": lines,
        "warnings": warnings,
    }
