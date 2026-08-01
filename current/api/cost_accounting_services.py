"""Cost accounting API service functions — CRUD for documents, reports, operations."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException

from api.database import last_insert_id, new_uuid, register_sync_change, utcnow_iso
from api.list_query import apply_quick_filters, order_by_clause


# ── Audit ──────────────────────────────────────────────────────────────────


def _audit_log(
    connection: sqlite3.Connection,
    *,
    action: str,
    resource_type: str,
    resource_id: int,
    details: str = "",
    user_id: int | None = None,
    username: str = "",
) -> None:
    """Record an audit entry for a cost accounting operation."""
    try:
        connection.execute(
            """INSERT INTO audit_logs (user_id, username, action, resource_type, resource_id, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, action, resource_type, resource_id, details, utcnow_iso()),
        )
    except Exception:
        pass  # Audit should never break the main flow


def get_audit_logs(
    connection: sqlite3.Connection,
    *,
    resource_type: str | None = None,
    resource_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Retrieve audit log entries with optional filters."""
    where = "WHERE 1=1"
    params: list[Any] = []
    if resource_type:
        where += " AND resource_type = ?"
        params.append(resource_type)
    if resource_id is not None:
        where += " AND resource_id = ?"
        params.append(resource_id)
    total = connection.execute(
        f"SELECT COUNT(*) FROM audit_logs {where}", params
    ).fetchone()[0]
    rows = connection.execute(
        f"SELECT * FROM audit_logs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [dict(row) for row in rows], total


def _now_iso() -> str:
    return datetime.now().isoformat()


def _cost_element_id(connection: sqlite3.Connection, kind: str) -> int | None:
    row = connection.execute(
        "SELECT id FROM cost_elements WHERE kind = ? AND marked_for_deletion = 0", (kind,)
    ).fetchone()
    return int(row["id"]) if row else None


# ── Cost Elements ──────────────────────────────────────────────────────────


def list_cost_elements(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT ce.*, ab.name AS allocation_base_name
           FROM cost_elements ce
           LEFT JOIN allocation_bases ab ON ab.id = ce.allocation_base_id
           WHERE ce.marked_for_deletion = 0
           ORDER BY ce.id""",
    ).fetchall()
    return [dict(row) for row in rows]


def list_allocation_bases(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM allocation_bases WHERE marked_for_deletion = 0 ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]


# ── Machines ───────────────────────────────────────────────────────────────


def list_machines(
    connection: sqlite3.Connection,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    where = "WHERE marked_for_deletion = 0"
    params: list[Any] = []
    if search:
        where += " AND (name LIKE ? OR code LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    total = connection.execute(
        f"SELECT COUNT(*) FROM machines {where}", params
    ).fetchone()[0]
    offset = (page - 1) * page_size
    rows = connection.execute(
        f"SELECT * FROM machines {where} ORDER BY name LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()
    items = [dict(row) for row in rows]
    return items, {
        "page": page, "page_size": page_size, "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def save_machine(
    connection: sqlite3.Connection, payload: dict[str, Any], machine_id: int | None = None
) -> dict[str, Any]:
    if machine_id is None:
        payload.setdefault("created_at", _now_iso())
        payload.setdefault("modified_at", _now_iso())
        payload.setdefault("marked_for_deletion", False)
        cols = ", ".join(payload.keys())
        placeholders = ", ".join(["?"] * len(payload))
        connection.execute(
            f"INSERT INTO machines ({cols}) VALUES ({placeholders})", list(payload.values())
        )
        machine_id = last_insert_id(connection)
    else:
        sets = ", ".join(f"{k} = ?" for k in payload)
        connection.execute(
            f"UPDATE machines SET {sets}, modified_at = ? WHERE id = ?",
            list(payload.values()) + [_now_iso(), machine_id],
        )
    connection.commit()
    return get_machine(connection, machine_id)


def get_machine(connection: sqlite3.Connection, machine_id: int) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM machines WHERE id = ? AND marked_for_deletion = 0", (machine_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Machine not found")
    return dict(row)


def delete_machine(connection: sqlite3.Connection, machine_id: int) -> None:
    connection.execute(
        "UPDATE machines SET marked_for_deletion = 1, modified_at = ? WHERE id = ?",
        (_now_iso(), machine_id),
    )
    connection.commit()


# ── Material Consumption ──────────────────────────────────────────────────


def list_material_consumptions(
    connection: sqlite3.Connection,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    object_id: int | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    where_parts = ["mc.marked_for_deletion = 0"]
    params: list[Any] = []
    if search:
        where_parts.append("mc.number LIKE ?")
        params.append(f"%{search}%")
    if object_id:
        where_parts.append("mc.object_id = ?")
        params.append(object_id)
    apply_quick_filters(
        where_parts,
        params,
        filters,
        {
            "number": ("mc.number", "like"),
            "date": ("mc.date", "eq"),
            "is_posted": ("mc.is_posted", "eq"),
            "object_name": ("o.name", "like"),
        },
    )
    where = "WHERE " + " AND ".join(where_parts)
    total = connection.execute(
        f"SELECT COUNT(*) FROM material_consumptions mc LEFT JOIN objects o ON o.id = mc.object_id {where}", params
    ).fetchone()[0]
    offset = (page - 1) * page_size
    order = order_by_clause(
        sort_by, sort_order, {"id": "mc.id", "number": "mc.number", "date": "mc.date"}, "mc.date"
    )
    rows = connection.execute(
        f"""SELECT mc.*, o.name AS object_name, e.number AS estimate_number,
                   p.full_name AS foreman_name
            FROM material_consumptions mc
            LEFT JOIN objects o ON o.id = mc.object_id
            LEFT JOIN estimates e ON e.id = mc.estimate_id
            LEFT JOIN persons p ON p.id = mc.foreman_id
            {where}
            {order}
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ).fetchall()
    items = [dict(row) for row in rows]
    for item in items:
        item["lines"] = _get_material_consumption_lines(connection, item["id"])
    return items, {
        "page": page, "page_size": page_size, "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def _get_material_consumption_lines(
    connection: sqlite3.Connection, doc_id: int
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT mcl.*, w.name AS work_name, m.name AS material_name
           FROM material_consumption_lines mcl
           LEFT JOIN works w ON w.id = mcl.work_id
           LEFT JOIN materials m ON m.id = mcl.material_id
           WHERE mcl.document_id = ?
           ORDER BY mcl.line_number""",
        (doc_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_material_consumption(
    connection: sqlite3.Connection, doc_id: int
) -> dict[str, Any]:
    row = connection.execute(
        """SELECT mc.*, o.name AS object_name, e.number AS estimate_number,
                  p.full_name AS foreman_name
           FROM material_consumptions mc
           LEFT JOIN objects o ON o.id = mc.object_id
           LEFT JOIN estimates e ON e.id = mc.estimate_id
           LEFT JOIN persons p ON p.id = mc.foreman_id
           WHERE mc.id = ? AND mc.marked_for_deletion = 0""",
        (doc_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Material consumption not found")
    result = dict(row)
    result["lines"] = _get_material_consumption_lines(connection, doc_id)
    return result


def save_material_consumption(
    connection: sqlite3.Connection, payload: dict[str, Any], doc_id: int | None = None
) -> dict[str, Any]:
    lines = payload.pop("lines", [])
    payload["date"] = str(payload["date"])
    if doc_id is None:
        payload.setdefault("created_at", _now_iso())
        payload.setdefault("is_posted", False)
        payload.setdefault("marked_for_deletion", False)
        cols = ", ".join(k for k in payload if k != "lines")
        vals = [payload[k] for k in payload if k != "lines"]
        placeholders = ", ".join(["?"] * len(vals))
        connection.execute(
            f"INSERT INTO material_consumptions ({cols}) VALUES ({placeholders})", vals
        )
        doc_id = last_insert_id(connection)
    else:
        existing = connection.execute(
            "SELECT id, is_posted FROM material_consumptions WHERE id = ? AND marked_for_deletion = 0",
            (doc_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Material consumption not found")
        if existing["is_posted"]:
            raise HTTPException(status_code=400, detail="Cannot edit a posted document. Unpost it first.")
        sets = ", ".join(f"{k} = ?" for k in payload if k not in ("lines", "id"))
        vals = [payload[k] for k in payload if k not in ("lines", "id")]
        connection.execute(
            f"UPDATE material_consumptions SET {sets}, modified_at = ? WHERE id = ?",
            vals + [_now_iso(), doc_id],
        )
    # Replace lines
    connection.execute(
        "DELETE FROM material_consumption_lines WHERE document_id = ?", (doc_id,)
    )
    for idx, line in enumerate(lines):
        line["line_number"] = idx + 1
        line["document_id"] = doc_id
        cols = ", ".join(line.keys())
        placeholders = ", ".join(["?"] * len(line))
        connection.execute(
            f"INSERT INTO material_consumption_lines ({cols}) VALUES ({placeholders})",
            list(line.values()),
        )
    connection.commit()
    return get_material_consumption(connection, doc_id)


def delete_material_consumption(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    connection.execute(
        "UPDATE material_consumptions SET marked_for_deletion = 1 WHERE id = ?",
        (doc_id,),
    )
    connection.commit()


def restore_material_consumption(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    connection.execute(
        "UPDATE material_consumptions SET marked_for_deletion = 0 WHERE id = ?",
        (doc_id,),
    )
    connection.commit()


def post_material_consumption(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    from api.services import _ensure_cost_elements_exist, _get_cost_element_id

    doc = get_material_consumption(connection, doc_id)
    if doc["is_posted"]:
        raise HTTPException(status_code=400, detail="Document is already posted")

    _ensure_cost_elements_exist(connection)
    materials_ce = _get_cost_element_id(connection, "materials")
    period = str(doc["date"])[:7]
    doc_date = str(doc["date"])[:10]

    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'MaterialConsumption' AND registrar_id = ?",
        (doc_id,),
    )
    for line in doc.get("lines", []):
        ce_id = line.get("cost_element_id") or materials_ce
        connection.execute(
            """INSERT INTO actual_costs
               (period, date, registrar_type, registrar_id, object_id, estimate_id,
                work_id, cost_element_id, quantity, amount, created_at)
               VALUES (?, ?, 'MaterialConsumption', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                period, doc_date, doc_id,
                doc.get("object_id"), doc.get("estimate_id"),
                line.get("work_id"), ce_id,
                line.get("actual_quantity", 0), line.get("sum", 0),
                _now_iso(),
            ),
        )
    connection.execute(
        "UPDATE material_consumptions SET is_posted = 1, posted_at = ? WHERE id = ?",
        (_now_iso(), doc_id),
    )
    _audit_log(connection, action="post", resource_type="material_consumption", resource_id=doc_id,
               details=f"Material consumption posted: {doc['number']} ({doc['date']})")
    connection.commit()


def unpost_material_consumption(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    doc = get_material_consumption(connection, doc_id)
    if not doc["is_posted"]:
        raise HTTPException(status_code=400, detail="Document is not posted")
    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'MaterialConsumption' AND registrar_id = ?",
        (doc_id,),
    )
    connection.execute(
        "UPDATE material_consumptions SET is_posted = 0, posted_at = NULL WHERE id = ?",
        (doc_id,),
    )
    _audit_log(connection, action="unpost", resource_type="material_consumption", resource_id=doc_id,
               details=f"Material consumption unposted: #{doc_id}")
    connection.commit()


# ── Machinery Usage Report ────────────────────────────────────────────────


def list_machinery_usage_reports(
    connection: sqlite3.Connection,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    object_id: int | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    where_parts = ["mur.marked_for_deletion = 0"]
    params: list[Any] = []
    if search:
        where_parts.append("mur.number LIKE ?")
        params.append(f"%{search}%")
    if object_id:
        where_parts.append("mur.object_id = ?")
        params.append(object_id)
    apply_quick_filters(
        where_parts,
        params,
        filters,
        {
            "number": ("mur.number", "like"),
            "date": ("mur.date", "eq"),
            "is_posted": ("mur.is_posted", "eq"),
            "object_name": ("o.name", "like"),
        },
    )
    where = "WHERE " + " AND ".join(where_parts)
    total = connection.execute(
        f"SELECT COUNT(*) FROM machinery_usage_reports mur LEFT JOIN objects o ON o.id = mur.object_id {where}", params
    ).fetchone()[0]
    offset = (page - 1) * page_size
    order = order_by_clause(
        sort_by, sort_order, {"id": "mur.id", "number": "mur.number", "date": "mur.date"}, "mur.date"
    )
    rows = connection.execute(
        f"""SELECT mur.*, o.name AS object_name, e.number AS estimate_number
            FROM machinery_usage_reports mur
            LEFT JOIN objects o ON o.id = mur.object_id
            LEFT JOIN estimates e ON e.id = mur.estimate_id
            {where}
            {order}
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ).fetchall()
    items = [dict(row) for row in rows]
    for item in items:
        item["lines"] = _get_machinery_lines(connection, item["id"])
    return items, {
        "page": page, "page_size": page_size, "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def _get_machinery_lines(
    connection: sqlite3.Connection, doc_id: int
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT mrl.*, m.name AS machine_name
           FROM machinery_usage_lines mrl
           LEFT JOIN machines m ON m.id = mrl.machine_id
           WHERE mrl.document_id = ?
           ORDER BY mrl.line_number""",
        (doc_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_machinery_usage_report(
    connection: sqlite3.Connection, doc_id: int
) -> dict[str, Any]:
    row = connection.execute(
        """SELECT mur.*, o.name AS object_name, e.number AS estimate_number
           FROM machinery_usage_reports mur
           LEFT JOIN objects o ON o.id = mur.object_id
           LEFT JOIN estimates e ON e.id = mur.estimate_id
           WHERE mur.id = ? AND mur.marked_for_deletion = 0""",
        (doc_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Machinery usage report not found")
    result = dict(row)
    result["lines"] = _get_machinery_lines(connection, doc_id)
    return result


def save_machinery_usage_report(
    connection: sqlite3.Connection, payload: dict[str, Any], doc_id: int | None = None
) -> dict[str, Any]:
    lines = payload.pop("lines", [])
    payload["date"] = str(payload["date"])
    if doc_id is None:
        payload.setdefault("created_at", _now_iso())
        payload.setdefault("is_posted", False)
        payload.setdefault("marked_for_deletion", False)
        cols = ", ".join(k for k in payload if k != "lines")
        vals = [payload[k] for k in payload if k != "lines"]
        placeholders = ", ".join(["?"] * len(vals))
        connection.execute(
            f"INSERT INTO machinery_usage_reports ({cols}) VALUES ({placeholders})", vals
        )
        doc_id = last_insert_id(connection)
    else:
        existing = connection.execute(
            "SELECT id, is_posted FROM machinery_usage_reports WHERE id = ? AND marked_for_deletion = 0",
            (doc_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Machinery usage report not found")
        if existing["is_posted"]:
            raise HTTPException(status_code=400, detail="Cannot edit a posted document. Unpost it first.")
        sets = ", ".join(f"{k} = ?" for k in payload if k not in ("lines", "id"))
        vals = [payload[k] for k in payload if k not in ("lines", "id")]
        connection.execute(
            f"UPDATE machinery_usage_reports SET {sets}, modified_at = ? WHERE id = ?",
            vals + [_now_iso(), doc_id],
        )
    connection.execute(
        "DELETE FROM machinery_usage_lines WHERE document_id = ?", (doc_id,)
    )
    for idx, line in enumerate(lines):
        line["line_number"] = idx + 1
        line["document_id"] = doc_id
        cols = ", ".join(line.keys())
        placeholders = ", ".join(["?"] * len(line))
        connection.execute(
            f"INSERT INTO machinery_usage_lines ({cols}) VALUES ({placeholders})",
            list(line.values()),
        )
    connection.commit()
    return get_machinery_usage_report(connection, doc_id)


def delete_machinery_usage_report(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    connection.execute(
        "UPDATE machinery_usage_reports SET marked_for_deletion = 1 WHERE id = ?",
        (doc_id,),
    )
    connection.commit()


def restore_machinery_usage_report(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    connection.execute(
        "UPDATE machinery_usage_reports SET marked_for_deletion = 0 WHERE id = ?",
        (doc_id,),
    )
    connection.commit()


def post_machinery_usage_report(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    from api.services import _ensure_cost_elements_exist, _get_cost_element_id

    doc = get_machinery_usage_report(connection, doc_id)
    if doc["is_posted"]:
        raise HTTPException(status_code=400, detail="Document is already posted")

    _ensure_cost_elements_exist(connection)
    machinery_ce = _get_cost_element_id(connection, "machinery")
    labor_ce = _get_cost_element_id(connection, "labor")
    period = str(doc["date"])[:7]
    doc_date = str(doc["date"])[:10]

    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'MachineryUsageReport' AND registrar_id = ?",
        (doc_id,),
    )
    for line in doc.get("lines", []):
        # MACHINERY movement
        connection.execute(
            """INSERT INTO actual_costs
               (period, date, registrar_type, registrar_id, object_id, estimate_id,
                work_id, cost_element_id, quantity, amount, created_at)
               VALUES (?, ?, 'MachineryUsageReport', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                period, doc_date, doc_id,
                doc.get("object_id"), doc.get("estimate_id"),
                line.get("work_id"), machinery_ce,
                line.get("hours", 0), line.get("machine_cost", 0),
                _now_iso(),
            ),
        )
        # LABOR (operator) movement
        operator_labor = float(line.get("operator_labor") or 0)
        if operator_labor > 0 and labor_ce:
            connection.execute(
                """INSERT INTO actual_costs
                   (period, date, registrar_type, registrar_id, object_id, estimate_id,
                    work_id, cost_element_id, quantity, amount, created_at)
                   VALUES (?, ?, 'MachineryUsageReport', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    period, doc_date, doc_id,
                    doc.get("object_id"), doc.get("estimate_id"),
                    line.get("work_id"), labor_ce,
                    line.get("hours", 0), operator_labor,
                    _now_iso(),
                ),
            )
    connection.execute(
        "UPDATE machinery_usage_reports SET is_posted = 1, posted_at = ? WHERE id = ?",
        (_now_iso(), doc_id),
    )
    _audit_log(connection, action="post", resource_type="machinery_usage_report", resource_id=doc_id)
    connection.commit()


def unpost_machinery_usage_report(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    doc = get_machinery_usage_report(connection, doc_id)
    if not doc["is_posted"]:
        raise HTTPException(status_code=400, detail="Document is not posted")
    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'MachineryUsageReport' AND registrar_id = ?",
        (doc_id,),
    )
    connection.execute(
        "UPDATE machinery_usage_reports SET is_posted = 0, posted_at = NULL WHERE id = ?",
        (doc_id,),
    )
    _audit_log(connection, action="unpost", resource_type="machinery_usage_report", resource_id=doc_id)
    connection.commit()


# ── Subcontract Acceptance ────────────────────────────────────────────────


def list_subcontract_acceptances(
    connection: sqlite3.Connection,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    object_id: int | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    where_parts = ["sa.marked_for_deletion = 0"]
    params: list[Any] = []
    if search:
        where_parts.append("sa.number LIKE ?")
        params.append(f"%{search}%")
    if object_id:
        where_parts.append("sa.object_id = ?")
        params.append(object_id)
    apply_quick_filters(
        where_parts,
        params,
        filters,
        {
            "number": ("sa.number", "like"),
            "date": ("sa.date", "eq"),
            "is_posted": ("sa.is_posted", "eq"),
            "object_name": ("o.name", "like"),
        },
    )
    where = "WHERE " + " AND ".join(where_parts)
    total = connection.execute(
        f"SELECT COUNT(*) FROM subcontract_acceptances sa LEFT JOIN objects o ON o.id = sa.object_id {where}", params
    ).fetchone()[0]
    offset = (page - 1) * page_size
    order = order_by_clause(
        sort_by, sort_order, {"id": "sa.id", "number": "sa.number", "date": "sa.date"}, "sa.date"
    )
    rows = connection.execute(
        f"""SELECT sa.*, o.name AS object_name, e.number AS estimate_number
            FROM subcontract_acceptances sa
            LEFT JOIN objects o ON o.id = sa.object_id
            LEFT JOIN estimates e ON e.id = sa.estimate_id
            {where}
            {order}
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ).fetchall()
    items = [dict(row) for row in rows]
    for item in items:
        item["lines"] = _get_subcontract_lines(connection, item["id"])
    return items, {
        "page": page, "page_size": page_size, "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def _get_subcontract_lines(
    connection: sqlite3.Connection, doc_id: int
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT sal.*, c.name AS counterparty_name
           FROM subcontract_acceptance_lines sal
           LEFT JOIN counterparties c ON c.id = sal.counterparty_id
           WHERE sal.document_id = ?
           ORDER BY sal.line_number""",
        (doc_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_subcontract_acceptance(
    connection: sqlite3.Connection, doc_id: int
) -> dict[str, Any]:
    row = connection.execute(
        """SELECT sa.*, o.name AS object_name, e.number AS estimate_number
           FROM subcontract_acceptances sa
           LEFT JOIN objects o ON o.id = sa.object_id
           LEFT JOIN estimates e ON e.id = sa.estimate_id
           WHERE sa.id = ? AND sa.marked_for_deletion = 0""",
        (doc_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Subcontract acceptance not found")
    result = dict(row)
    result["lines"] = _get_subcontract_lines(connection, doc_id)
    return result


def save_subcontract_acceptance(
    connection: sqlite3.Connection, payload: dict[str, Any], doc_id: int | None = None
) -> dict[str, Any]:
    lines = payload.pop("lines", [])
    payload["date"] = str(payload["date"])
    if doc_id is None:
        payload.setdefault("created_at", _now_iso())
        payload.setdefault("is_posted", False)
        payload.setdefault("marked_for_deletion", False)
        cols = ", ".join(k for k in payload if k != "lines")
        vals = [payload[k] for k in payload if k != "lines"]
        placeholders = ", ".join(["?"] * len(vals))
        connection.execute(
            f"INSERT INTO subcontract_acceptances ({cols}) VALUES ({placeholders})", vals
        )
        doc_id = last_insert_id(connection)
    else:
        existing = connection.execute(
            "SELECT id, is_posted FROM subcontract_acceptances WHERE id = ? AND marked_for_deletion = 0",
            (doc_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Subcontract acceptance not found")
        if existing["is_posted"]:
            raise HTTPException(status_code=400, detail="Cannot edit a posted document. Unpost it first.")
        sets = ", ".join(f"{k} = ?" for k in payload if k not in ("lines", "id"))
        vals = [payload[k] for k in payload if k not in ("lines", "id")]
        connection.execute(
            f"UPDATE subcontract_acceptances SET {sets}, modified_at = ? WHERE id = ?",
            vals + [_now_iso(), doc_id],
        )
    connection.execute(
        "DELETE FROM subcontract_acceptance_lines WHERE document_id = ?", (doc_id,)
    )
    for idx, line in enumerate(lines):
        line["line_number"] = idx + 1
        line["document_id"] = doc_id
        cols = ", ".join(line.keys())
        placeholders = ", ".join(["?"] * len(line))
        connection.execute(
            f"INSERT INTO subcontract_acceptance_lines ({cols}) VALUES ({placeholders})",
            list(line.values()),
        )
    connection.commit()
    return get_subcontract_acceptance(connection, doc_id)


def delete_subcontract_acceptance(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    connection.execute(
        "UPDATE subcontract_acceptances SET marked_for_deletion = 1 WHERE id = ?",
        (doc_id,),
    )
    connection.commit()


def restore_subcontract_acceptance(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    connection.execute(
        "UPDATE subcontract_acceptances SET marked_for_deletion = 0 WHERE id = ?",
        (doc_id,),
    )
    connection.commit()


def post_subcontract_acceptance(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    from api.services import _ensure_cost_elements_exist, _get_cost_element_id

    doc = get_subcontract_acceptance(connection, doc_id)
    if doc["is_posted"]:
        raise HTTPException(status_code=400, detail="Document is already posted")

    _ensure_cost_elements_exist(connection)
    sub_ce = _get_cost_element_id(connection, "subcontract")
    period = str(doc["date"])[:7]
    doc_date = str(doc["date"])[:10]

    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'SubcontractAcceptance' AND registrar_id = ?",
        (doc_id,),
    )
    for line in doc.get("lines", []):
        connection.execute(
            """INSERT INTO actual_costs
               (period, date, registrar_type, registrar_id, object_id, estimate_id,
                work_id, cost_element_id, quantity, amount, created_at)
               VALUES (?, ?, 'SubcontractAcceptance', ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                period, doc_date, doc_id,
                doc.get("object_id"), doc.get("estimate_id"),
                line.get("work_id"), sub_ce,
                line.get("sum", 0),
                _now_iso(),
            ),
        )
    connection.execute(
        "UPDATE subcontract_acceptances SET is_posted = 1, posted_at = ? WHERE id = ?",
        (_now_iso(), doc_id),
    )
    _audit_log(connection, action="post", resource_type="subcontract_acceptance", resource_id=doc_id)
    connection.commit()


def unpost_subcontract_acceptance(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    doc = get_subcontract_acceptance(connection, doc_id)
    if not doc["is_posted"]:
        raise HTTPException(status_code=400, detail="Document is not posted")
    connection.execute(
        "DELETE FROM actual_costs WHERE registrar_type = 'SubcontractAcceptance' AND registrar_id = ?",
        (doc_id,),
    )
    connection.execute(
        "UPDATE subcontract_acceptances SET is_posted = 0, posted_at = NULL WHERE id = ?",
        (doc_id,),
    )
    _audit_log(connection, action="unpost", resource_type="subcontract_acceptance", resource_id=doc_id)
    connection.commit()


# ── Overhead Expense ──────────────────────────────────────────────────────


def list_overhead_expenses(
    connection: sqlite3.Connection,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    period: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    where_parts = ["oe.marked_for_deletion = 0"]
    params: list[Any] = []
    if search:
        where_parts.append("oe.number LIKE ?")
        params.append(f"%{search}%")
    if period:
        where_parts.append("oe.period = ?")
        params.append(period)
    apply_quick_filters(
        where_parts,
        params,
        filters,
        {
            "number": ("oe.number", "like"),
            "period": ("oe.period", "eq"),
            "is_posted": ("oe.is_posted", "eq"),
        },
    )
    where = "WHERE " + " AND ".join(where_parts)
    total = connection.execute(
        f"SELECT COUNT(*) FROM overhead_expenses oe {where}", params
    ).fetchone()[0]
    offset = (page - 1) * page_size
    order = order_by_clause(
        sort_by, sort_order, {"id": "oe.id", "number": "oe.number", "period": "oe.period"}, "oe.period"
    )
    rows = connection.execute(
        f"SELECT * FROM overhead_expenses oe {where} {order} LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()
    items = [dict(row) for row in rows]
    for item in items:
        item["lines"] = _get_overhead_lines(connection, item["id"])
    return items, {
        "page": page, "page_size": page_size, "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def _get_overhead_lines(
    connection: sqlite3.Connection, doc_id: int
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT oel.*, ce.name AS cost_element_name, c.name AS counterparty_name
           FROM overhead_expense_lines oel
           LEFT JOIN cost_elements ce ON ce.id = oel.cost_element_id
           LEFT JOIN counterparties c ON c.id = oel.counterparty_id
           WHERE oel.document_id = ?
           ORDER BY oel.line_number""",
        (doc_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_overhead_expense(
    connection: sqlite3.Connection, doc_id: int
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM overhead_expenses WHERE id = ? AND marked_for_deletion = 0",
        (doc_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Overhead expense not found")
    result = dict(row)
    result["lines"] = _get_overhead_lines(connection, doc_id)
    return result


def save_overhead_expense(
    connection: sqlite3.Connection, payload: dict[str, Any], doc_id: int | None = None
) -> dict[str, Any]:
    lines = payload.pop("lines", [])
    payload["date"] = str(payload["date"])
    if doc_id is None:
        payload.setdefault("created_at", _now_iso())
        payload.setdefault("is_distributed", False)
        payload.setdefault("marked_for_deletion", False)
        cols = ", ".join(k for k in payload if k != "lines")
        vals = [payload[k] for k in payload if k != "lines"]
        placeholders = ", ".join(["?"] * len(vals))
        connection.execute(
            f"INSERT INTO overhead_expenses ({cols}) VALUES ({placeholders})", vals
        )
        doc_id = last_insert_id(connection)
    else:
        existing = connection.execute(
            "SELECT id, is_distributed FROM overhead_expenses WHERE id = ? AND marked_for_deletion = 0",
            (doc_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Overhead expense not found")
        if existing["is_distributed"]:
            raise HTTPException(status_code=400, detail="Cannot edit a distributed overhead document")
        sets = ", ".join(f"{k} = ?" for k in payload if k not in ("lines", "id"))
        vals = [payload[k] for k in payload if k not in ("lines", "id")]
        connection.execute(
            f"UPDATE overhead_expenses SET {sets}, modified_at = ? WHERE id = ?",
            vals + [_now_iso(), doc_id],
        )
    connection.execute(
        "DELETE FROM overhead_expense_lines WHERE document_id = ?", (doc_id,)
    )
    for idx, line in enumerate(lines):
        line["line_number"] = idx + 1
        line["document_id"] = doc_id
        cols = ", ".join(line.keys())
        placeholders = ", ".join(["?"] * len(line))
        connection.execute(
            f"INSERT INTO overhead_expense_lines ({cols}) VALUES ({placeholders})",
            list(line.values()),
        )
    connection.commit()
    return get_overhead_expense(connection, doc_id)


def delete_overhead_expense(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    connection.execute(
        "UPDATE overhead_expenses SET marked_for_deletion = 1 WHERE id = ?",
        (doc_id,),
    )
    connection.commit()


def restore_overhead_expense(
    connection: sqlite3.Connection, doc_id: int
) -> None:
    connection.execute(
        "UPDATE overhead_expenses SET marked_for_deletion = 0 WHERE id = ?",
        (doc_id,),
    )
    connection.commit()


# ── Overhead Distribution ─────────────────────────────────────────────────


def distribute_overhead(
    connection: sqlite3.Connection,
    period: str,
    allocation_base_id: int,
    object_id: int = 0,
) -> dict[str, Any]:
    from api.services import _ensure_cost_elements_exist, _get_cost_element_id

    _ensure_cost_elements_exist(connection)

    # Check if already distributed for this scope
    if object_id == 0:
        existing = connection.execute(
            "SELECT COUNT(*) FROM overhead_distribution WHERE period = ?", (period,)
        ).fetchone()[0]
    else:
        existing = connection.execute(
            "SELECT COUNT(*) FROM overhead_distribution WHERE period = ? AND object_id = ?",
            (period, object_id),
        ).fetchone()[0]
    if existing > 0:
        raise HTTPException(
            status_code=400,
            detail="Overhead for this period/scope is already distributed. Cancel distribution first.",
        )

    # Get total overhead for period
    total = connection.execute(
        """SELECT COALESCE(SUM(oel.sum), 0)
           FROM overhead_expense_lines oel
           JOIN overhead_expenses oe ON oe.id = oel.document_id
           WHERE oe.period = ? AND oe.marked_for_deletion = 0""",
        (period,),
    ).fetchone()[0]
    if total <= 0:
        raise HTTPException(status_code=400, detail="No undistributed overhead for this period")

    # Get allocation base info
    base_row = connection.execute(
        "SELECT kind, name FROM allocation_bases WHERE id = ?", (allocation_base_id,)
    ).fetchone()
    if not base_row:
        raise HTTPException(status_code=400, detail="Allocation base not found")

    base_kind = base_row["kind"]

    # Calculate base values per (object, estimate, work)
    if base_kind == "payroll":
        labor_ce = _get_cost_element_id(connection, "labor")
        if not labor_ce:
            raise HTTPException(status_code=400, detail="LABOR cost element not found")
        base_rows = connection.execute(
            """SELECT object_id, estimate_id, work_id, COALESCE(SUM(amount), 0) AS base_val
               FROM actual_costs
               WHERE period = ? AND cost_element_id = ?
               GROUP BY object_id, estimate_id, work_id""",
            (period, labor_ce),
        ).fetchall()
    elif base_kind == "direct_costs":
        base_rows = connection.execute(
            """SELECT object_id, estimate_id, work_id, COALESCE(SUM(amount), 0) AS base_val
               FROM actual_costs
               WHERE period = ?
               GROUP BY object_id, estimate_id, work_id""",
            (period,),
        ).fetchall()
    elif base_kind == "labor_days":
        labor_ce = _get_cost_element_id(connection, "labor")
        if not labor_ce:
            raise HTTPException(status_code=400, detail="LABOR cost element not found")
        base_rows = connection.execute(
            """SELECT object_id, estimate_id, work_id, COALESCE(SUM(quantity), 0) AS base_val
               FROM actual_costs
               WHERE period = ? AND cost_element_id = ?
               GROUP BY object_id, estimate_id, work_id""",
            (period, labor_ce),
        ).fetchall()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown allocation base kind: {base_kind}")

    total_base = sum(float(row["base_val"]) for row in base_rows)
    if total_base <= 0:
        raise HTTPException(status_code=400, detail="Allocation base value is zero — cannot distribute")

    # Distribute proportionally (scope delete + insert to the requested object, if any)
    if object_id == 0:
        connection.execute("DELETE FROM overhead_distribution WHERE period = ?", (period,))
    else:
        connection.execute(
            "DELETE FROM overhead_distribution WHERE period = ? AND object_id = ?",
            (period, object_id),
        )

    # Resolve the rows that will actually receive a share (global base, filtered recipients)
    target_rows = [
        row for row in base_rows
        if float(row["base_val"]) > 0 and (object_id == 0 or row["object_id"] == object_id)
    ]

    record_count = 0
    allocated = 0.0
    for idx, row in enumerate(target_rows):
        obj_id = row["object_id"]
        est_id = row["estimate_id"]
        work_id = row["work_id"]
        base_val = float(row["base_val"])
        raw_share = (base_val / total_base) * total
        # Last written row absorbs the rounding residual so Σ shares == pool exactly
        if idx == len(target_rows) - 1:
            share = round(total - allocated, 2)
        else:
            share = round(raw_share, 2)
        allocated += share
        connection.execute(
            """INSERT INTO overhead_distribution
               (period, object_id, estimate_id, work_id, amount, allocation_base_id, base_value, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (period, obj_id, est_id, work_id, share, allocation_base_id, base_val, _now_iso()),
        )
        record_count += 1

    # Mark overhead documents as distributed only on a full (all-objects) distribution.
    # Per-object distribution is a partial operation and must not lock the whole period.
    if object_id == 0:
        connection.execute(
            "UPDATE overhead_expenses SET is_distributed = 1 WHERE period = ? AND marked_for_deletion = 0",
            (period,),
        )
    _audit_log(connection, action="distribute", resource_type="overhead", resource_id=0,
               details=f"Overhead distributed for {period}: base={base_row['name']}, total={round(total, 2)}, records={record_count}")
    connection.commit()

    return {
        "period": period,
        "allocation_base_name": base_row["name"],
        "total_distributed": round(total, 2),
        "record_count": record_count,
    }


def cancel_overhead_distribution(
    connection: sqlite3.Connection, period: str
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT COUNT(*) FROM overhead_distribution WHERE period = ?", (period,)
    ).fetchone()
    if row[0] == 0:
        raise HTTPException(status_code=400, detail="No distribution found for this period")

    connection.execute(
        "DELETE FROM overhead_distribution WHERE period = ?", (period,)
    )
    connection.execute(
        "UPDATE overhead_expenses SET is_distributed = 0 WHERE period = ?",
        (period,),
    )
    _audit_log(connection, action="cancel_distribution", resource_type="overhead", resource_id=0,
               details=f"Overhead distribution cancelled for {period}")
    connection.commit()
    return {"period": period, "cancelled": True}


# ── Cost Calculation ─────────────────────────────────────────────────────


def list_cost_calculations(
    connection: sqlite3.Connection,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    where_parts = ["cc.marked_for_deletion = 0"]
    params: list[Any] = []
    if search:
        where_parts.append("(cc.number LIKE ? OR cc.period LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    apply_quick_filters(
        where_parts,
        params,
        filters,
        {
            "number": ("cc.number", "like"),
            "period": ("cc.period", "eq"),
            "is_posted": ("cc.is_posted", "eq"),
            "object_name": ("o.name", "like"),
        },
    )
    where = "WHERE " + " AND ".join(where_parts)
    total = connection.execute(
        f"SELECT COUNT(*) FROM cost_calculations cc LEFT JOIN objects o ON o.id = cc.object_id {where}", params
    ).fetchone()[0]
    offset = (page - 1) * page_size
    order = order_by_clause(
        sort_by, sort_order, {"id": "cc.id", "number": "cc.number", "period": "cc.period"}, "cc.period"
    )
    rows = connection.execute(
        f"""SELECT cc.*, o.name AS object_name
            FROM cost_calculations cc
            LEFT JOIN objects o ON o.id = cc.object_id
            {where}
            {order}
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ).fetchall()
    items = [dict(row) for row in rows]
    return items, {
        "page": page, "page_size": page_size, "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def get_cost_calculation(
    connection: sqlite3.Connection, calc_id: int
) -> dict[str, Any]:
    row = connection.execute(
        """SELECT cc.*, o.name AS object_name
           FROM cost_calculations cc
           LEFT JOIN objects o ON o.id = cc.object_id
           WHERE cc.id = ? AND cc.marked_for_deletion = 0""",
        (calc_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Cost calculation not found")
    return dict(row)


def save_cost_calculation(
    connection: sqlite3.Connection, payload: dict[str, Any], calc_id: int | None = None
) -> dict[str, Any]:
    payload["date"] = str(payload["date"])
    if calc_id is None:
        payload.setdefault("created_at", _now_iso())
        payload.setdefault("status", "draft")
        payload.setdefault("marked_for_deletion", False)
        cols = ", ".join(payload.keys())
        vals = list(payload.values())
        placeholders = ", ".join(["?"] * len(vals))
        connection.execute(
            f"INSERT INTO cost_calculations ({cols}) VALUES ({placeholders})", vals
        )
        calc_id = last_insert_id(connection)
    else:
        existing = connection.execute(
            "SELECT status FROM cost_calculations WHERE id = ? AND marked_for_deletion = 0",
            (calc_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Cost calculation not found")
        if existing["status"] == "posted":
            raise HTTPException(status_code=400, detail="Cannot edit a posted calculation")
        sets = ", ".join(f"{k} = ?" for k in payload if k != "id")
        vals = [payload[k] for k in payload if k != "id"]
        connection.execute(
            f"UPDATE cost_calculations SET {sets} WHERE id = ?",
            vals + [calc_id],
        )
    connection.commit()
    return get_cost_calculation(connection, calc_id)


def delete_cost_calculation(
    connection: sqlite3.Connection, calc_id: int
) -> None:
    connection.execute(
        "UPDATE cost_calculations SET marked_for_deletion = 1 WHERE id = ?",
        (calc_id,),
    )
    connection.commit()


def calculate_cost(
    connection: sqlite3.Connection, calc_id: int
) -> dict[str, Any]:
    calc = get_cost_calculation(connection, calc_id)
    if calc["status"] == "posted":
        raise HTTPException(status_code=400, detail="Calculation is already posted")

    period = calc["period"]
    object_id = calc["object_id"]
    obj_filter = "AND object_id = ?" if object_id != 0 else ""
    obj_params = (object_id,) if object_id != 0 else ()

    # Clear previous results
    connection.execute(
        "DELETE FROM completed_works_cost WHERE calculation_id = ?", (calc_id,)
    )

    # Aggregate: actual costs + overhead per (object, work).
    # Grouping by object_id preserves object identity for all-objects calculations
    # (object_id == 0) so per-object reports stay correct.
    results = connection.execute(
        f"""SELECT
               COALESCE(object_id, 0) AS object_id,
               work_id,
               COALESCE(SUM(amount), 0) AS actual_direct,
               COALESCE(SUM(quantity), 0) AS completed_qty
            FROM actual_costs
            WHERE period = ? {obj_filter}
            GROUP BY COALESCE(object_id, 0), work_id""",
        (period,) + obj_params,
    ).fetchall()

    # Get overhead distribution totals per (object, work)
    overhead_rows = connection.execute(
        f"""SELECT COALESCE(object_id, 0) AS object_id, work_id,
                   COALESCE(SUM(amount), 0) AS overhead_amount
            FROM overhead_distribution
            WHERE period = ? {obj_filter}
            GROUP BY COALESCE(object_id, 0), work_id""",
        (period,) + obj_params,
    ).fetchall()
    overhead_map = {
        (row["object_id"], row["work_id"]): float(row["overhead_amount"]) for row in overhead_rows
    }

    # Get planned costs per (object, work)
    planned_rows = connection.execute(
        f"""SELECT COALESCE(object_id, 0) AS object_id, work_id,
                   COALESCE(SUM(planned_amount), 0) AS planned_total
            FROM planned_costs
            WHERE period = ? {obj_filter}
            GROUP BY COALESCE(object_id, 0), work_id""",
        (period,) + obj_params,
    ).fetchall()
    planned_map = {
        (row["object_id"], row["work_id"]): float(row["planned_total"]) for row in planned_rows
    }

    record_count = 0
    for row in results:
        work_id = row["work_id"]
        row_obj_id = row["object_id"]
        actual_direct = float(row["actual_direct"])
        overhead = overhead_map.get((row_obj_id, work_id), 0.0)
        actual_cost = actual_direct + overhead
        planned_cost = planned_map.get((row_obj_id, work_id), 0.0)
        completed_qty = float(row["completed_qty"])
        deviation = round(actual_cost - planned_cost, 2)
        # Contract value = planned_cost (default; can be overridden)
        contract_value = planned_cost
        profit = round(contract_value - actual_cost, 2)

        connection.execute(
            """INSERT INTO completed_works_cost
               (period, calculation_id, object_id, work_id, completed_quantity,
                planned_cost, actual_cost, deviation, contract_value, profit, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                period, calc_id, row_obj_id, work_id, completed_qty,
                round(planned_cost, 2), round(actual_cost, 2),
                deviation, round(contract_value, 2), profit, _now_iso(),
            ),
        )
        record_count += 1

    connection.execute(
        "UPDATE cost_calculations SET status = 'calculated' WHERE id = ?", (calc_id,)
    )
    _audit_log(connection, action="calculate", resource_type="cost_calculation", resource_id=calc_id,
               details=f"Cost calculation executed: period={period}, object_id={object_id}, records={record_count}")
    connection.commit()
    return {"calculation_id": calc_id, "status": "calculated", "record_count": record_count}


def post_cost_calculation(
    connection: sqlite3.Connection, calc_id: int
) -> None:
    calc = get_cost_calculation(connection, calc_id)
    if calc["status"] != "calculated":
        raise HTTPException(status_code=400, detail="Calculation must be in 'calculated' status")
    connection.execute(
        "UPDATE cost_calculations SET status = 'posted' WHERE id = ?", (calc_id,)
    )
    _audit_log(connection, action="post", resource_type="cost_calculation", resource_id=calc_id,
               details=f"Cost calculation posted: period={calc['period']}")
    connection.commit()


def unpost_cost_calculation(
    connection: sqlite3.Connection, calc_id: int
) -> None:
    calc = get_cost_calculation(connection, calc_id)
    if calc["status"] != "posted":
        raise HTTPException(status_code=400, detail="Calculation is not posted")
    connection.execute(
        "UPDATE cost_calculations SET status = 'draft' WHERE id = ?", (calc_id,)
    )
    connection.execute(
        "DELETE FROM completed_works_cost WHERE calculation_id = ?", (calc_id,)
    )
    _audit_log(connection, action="unpost", resource_type="cost_calculation", resource_id=calc_id,
               details=f"Cost calculation unposted: period={calc['period']}")
    connection.commit()


# ── Reports ────────────────────────────────────────────────────────────────


def _cost_report_tables_ready(connection: sqlite3.Connection) -> bool:
    """True if the cost-accounting tables needed by reports exist."""
    try:
        connection.execute("SELECT 1 FROM cost_elements LIMIT 1").fetchone()
        return True
    except sqlite3.OperationalError:
        return False


def get_cost_card(
    connection: sqlite3.Connection, object_id: int,
    period_from: str | None = None, period_to: str | None = None,
) -> dict[str, Any]:
    if not _cost_report_tables_ready(connection):
        return {
            "object_id": object_id, "object_name": None,
            "period_from": period_from, "period_to": period_to,
            "elements": [], "total_planned": 0.0, "total_actual": 0.0,
            "total_deviation": 0.0, "total_contract_value": 0.0,
            "total_profit": 0.0, "profitability_pct": 0.0, "works": [],
        }
    obj_name = None
    if object_id:
        obj_row = connection.execute(
            "SELECT name FROM objects WHERE id = ?", (object_id,)
        ).fetchone()
        obj_name = obj_row["name"] if obj_row else None

    extra_filter = ""
    params: list[Any] = []
    if period_from:
        extra_filter += " AND x.period >= ?"
        params.append(period_from)
    if period_to:
        extra_filter += " AND x.period <= ?"
        params.append(period_to)
    if object_id:
        extra_filter += " AND x.object_id = ?"
        params.append(object_id)

    # Actual costs by element (filtered by period and object_id)
    elements = connection.execute(
        f"""SELECT
               ce.id, ce.name, ce.kind,
               COALESCE((
                   SELECT SUM(ac.amount) FROM actual_costs ac
                   WHERE ac.cost_element_id = ce.id{extra_filter.replace('x.', 'ac.')}
               ), 0) AS actual_amount
            FROM cost_elements ce
            ORDER BY ce.id""",
        params,
    ).fetchall()

    # Planned costs by element (filtered by period and object_id)
    planned_by_element = connection.execute(
        f"""SELECT ce.id,
               COALESCE((
                   SELECT SUM(pc.planned_amount) FROM planned_costs pc
                   WHERE pc.cost_element_id = ce.id{extra_filter.replace('x.', 'pc.')}
               ), 0) AS planned_amount
            FROM cost_elements ce
            ORDER BY ce.id""",
        params,
    ).fetchall()
    planned_map = {row["id"]: float(row["planned_amount"]) for row in planned_by_element}

    element_summaries = []
    total_planned = 0.0
    total_actual = 0.0
    for el in elements:
        planned = planned_map.get(el["id"], 0.0)
        actual = float(el["actual_amount"])
        total_planned += planned
        total_actual += actual
        element_summaries.append({
            "cost_element_id": el["id"],
            "cost_element_name": el["name"],
            "cost_element_kind": el["kind"],
            "planned_amount": round(planned, 2),
            "actual_amount": round(actual, 2),
            "deviation": round(actual - planned, 2),
        })

    # Work-level detail from completed_works_cost
    cw_filter = "WHERE 1=1"
    cw_params: list[Any] = []
    if period_from:
        cw_filter += " AND cwc.period >= ?"
        cw_params.append(period_from)
    if period_to:
        cw_filter += " AND cwc.period <= ?"
        cw_params.append(period_to)
    if object_id:
        cw_filter += " AND cwc.object_id = ?"
        cw_params.append(object_id)

    work_rows = connection.execute(
        f"""SELECT cwc.*, w.name AS work_name
            FROM completed_works_cost cwc
            LEFT JOIN works w ON w.id = cwc.work_id
            {cw_filter}
            ORDER BY cwc.deviation DESC""",
        cw_params,
    ).fetchall()

    works = []
    total_contract = 0.0
    total_profit = 0.0
    for row in work_rows:
        works.append({
            "work_id": row["work_id"],
            "work_name": row["work_name"],
            "completed_quantity": float(row["completed_quantity"]),
            "planned_cost": float(row["planned_cost"]),
            "actual_cost": float(row["actual_cost"]),
            "deviation": float(row["deviation"]),
            "contract_value": float(row["contract_value"]),
            "profit": float(row["profit"]),
            "profitability_pct": round(
                (float(row["profit"]) / float(row["actual_cost"]) * 100)
                if float(row["actual_cost"]) else 0.0, 1
            ),
        })
        total_contract += float(row["contract_value"])
        total_profit += float(row["profit"])

    total_deviation = round(total_actual - total_planned, 2)
    return {
        "object_id": object_id,
        "object_name": obj_name,
        "period_from": period_from,
        "period_to": period_to,
        "elements": element_summaries,
        "total_planned": round(total_planned, 2),
        "total_actual": round(total_actual, 2),
        "total_deviation": total_deviation,
        "total_contract_value": round(total_contract, 2),
        "total_profit": round(total_profit, 2),
        "profitability_pct": round(
            (total_profit / total_actual * 100) if total_actual else 0.0, 1
        ),
        "works": works,
    }


def get_turnover_balance(
    connection: sqlite3.Connection, period_from: str, period_to: str, object_id: int = 0
) -> dict[str, Any]:
    if not _cost_report_tables_ready(connection):
        return {"rows": []}
    obj_filter = "AND object_id = ?" if object_id else ""
    obj_params = (object_id,) if object_id else ()

    elements = connection.execute(
        "SELECT id, name, kind FROM cost_elements WHERE marked_for_deletion = 0 ORDER BY id"
    ).fetchall()

    rows = []
    for el in elements:
        # Opening: all periods before period_from
        opening = connection.execute(
            f"""SELECT COALESCE(SUM(amount), 0)
                FROM actual_costs
                WHERE cost_element_id = ? AND period < ? {obj_filter}""",
            (el["id"], period_from) + obj_params,
        ).fetchone()[0]

        # Inflow: positive amounts within [period_from, period_to]
        inflow = connection.execute(
            f"""SELECT COALESCE(SUM(amount), 0)
                FROM actual_costs
                WHERE cost_element_id = ? AND period >= ? AND period <= ? AND amount > 0 {obj_filter}""",
            (el["id"], period_from, period_to) + obj_params,
        ).fetchone()[0]

        # Outflow: negative amounts (reversals) within [period_from, period_to]
        outflow = connection.execute(
            f"""SELECT COALESCE(SUM(ABS(amount)), 0)
                FROM actual_costs
                WHERE cost_element_id = ? AND period >= ? AND period <= ? AND amount < 0 {obj_filter}""",
            (el["id"], period_from, period_to) + obj_params,
        ).fetchone()[0]

        closing = float(opening) + float(inflow) - float(outflow)
        rows.append({
            "cost_element_id": el["id"],
            "cost_element_name": el["name"],
            "cost_element_kind": el["kind"],
            "opening_balance": round(float(opening), 2),
            "inflow": round(float(inflow), 2),
            "outflow": round(float(outflow), 2),
            "closing_balance": round(closing, 2),
        })

    obj_name = None
    if object_id:
        obj_row = connection.execute(
            "SELECT name FROM objects WHERE id = ?", (object_id,)
        ).fetchone()
        obj_name = obj_row["name"] if obj_row else None

    return {
        "period_from": period_from,
        "period_to": period_to,
        "object_id": object_id,
        "object_name": obj_name,
        "rows": rows,
    }


def get_deviations(
    connection: sqlite3.Connection, period: str, threshold_pct: float = 0.0, object_id: int = 0
) -> dict[str, Any]:
    if not _cost_report_tables_ready(connection):
        return {"rows": []}
    obj_filter = "AND cwc.object_id = ?" if object_id else ""
    obj_params = (period, object_id) if object_id else (period,)

    rows = connection.execute(
        f"""SELECT cwc.*, w.name AS work_name, ce.name AS cost_element_name
            FROM completed_works_cost cwc
            LEFT JOIN works w ON w.id = cwc.work_id
            LEFT JOIN cost_elements ce ON ce.id = (
                SELECT cost_element_id FROM actual_costs
                WHERE work_id = cwc.work_id AND period = cwc.period
                LIMIT 1
            )
            WHERE cwc.period = ? {obj_filter}
            ORDER BY ABS(cwc.deviation) DESC""",
        obj_params,
    ).fetchall()

    result_rows = []
    for row in rows:
        actual = float(row["actual_cost"])
        deviation = float(row["deviation"])
        pct = round(abs(deviation) / float(row["planned_cost"]) * 100, 1) if float(row["planned_cost"]) else 0.0
        if threshold_pct == 0 or pct >= threshold_pct:
            result_rows.append({
                "work_id": row["work_id"],
                "work_name": row["work_name"],
                "cost_element_name": row["cost_element_name"] or "-",
                "planned_amount": float(row["planned_cost"]),
                "actual_amount": actual,
                "deviation": deviation,
                "deviation_pct": pct,
            })

    return {
        "period": period,
        "object_id": object_id,
        "threshold_pct": threshold_pct,
        "rows": result_rows,
    }


def get_profitability(
    connection: sqlite3.Connection, period: str | None = None
) -> dict[str, Any]:
    if not _cost_report_tables_ready(connection):
        return {"rows": []}
    period_filter = "WHERE cwc.period = ?" if period else ""
    params = (period,) if period else ()

    rows = connection.execute(
        f"""SELECT
               cwc.object_id,
               o.name AS object_name,
               COALESCE(SUM(cwc.planned_cost), 0) AS planned_cost,
               COALESCE(SUM(cwc.actual_cost), 0) AS actual_cost,
               COALESCE(SUM(cwc.contract_value), 0) AS contract_value,
               COALESCE(SUM(cwc.profit), 0) AS profit
            FROM completed_works_cost cwc
            LEFT JOIN objects o ON o.id = cwc.object_id
            {period_filter}
            GROUP BY cwc.object_id
            ORDER BY profit DESC""",
        params,
    ).fetchall()

    result_rows = []
    for row in rows:
        actual = float(row["actual_cost"])
        profit = float(row["profit"])
        result_rows.append({
            "object_id": row["object_id"],
            "object_name": row["object_name"],
            "planned_cost": round(float(row["planned_cost"]), 2),
            "actual_cost": round(actual, 2),
            "contract_value": round(float(row["contract_value"]), 2),
            "profit": round(profit, 2),
            "profitability_pct": round((profit / actual * 100) if actual else 0.0, 1),
        })

    return {"period": period, "rows": result_rows}
