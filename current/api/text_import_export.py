"""Unified text (TSV/JSON/XLSX) import & export for documents, with automatic
creation of missing reference entities (materials, units, works, counterparties,
machines).

This module generalises the proven patterns from `work_services`
(`_resolve_unit_id`, `_find_material_by_code_or_name`,
`create_materials_from_import_preview`) so every cost-accounting document can
import/export its tabular part with the same semantics:

* Reference columns are resolved by code first, then by name.
* Entities flagged `create=True` are inserted on the fly when missing.
* Entities flagged `create=False` produce a warning and the row is kept with a
  null reference (the caller decides whether to skip or keep).
* Documents are always created in `draft`/unposted state.

Supported document kinds live in `DOCUMENT_SCHEMAS`.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from typing import Any, Iterable

from fastapi import HTTPException

from api.database import last_insert_id, new_uuid, register_sync_change, row_to_dict
from api.work_services import (
    _find_material_by_code_or_name,
    _normalize_lookup_value,
    _normalize_unit_name,
    _resolve_unit_id,
    _utcnow,
)


# ── Reference resolvers (get_or_create) ────────────────────────────────────


def get_or_create_unit(connection: sqlite3.Connection, name: str | None) -> int | None:
    """Resolve a unit by name, creating it if missing. Wrapper over the
    canonical `_resolve_unit_id` from work_services."""
    if not name:
        return None
    return _resolve_unit_id(connection, None, name)


def get_or_create_material(
    connection: sqlite3.Connection,
    *,
    code: str | None = None,
    name: str | None = None,
    unit_name: str | None = None,
    price: float = 0.0,
) -> int | None:
    """Return material id, looking it up by code/name and creating if missing."""
    existing = _find_material_by_code_or_name(
        connection, material_code=code, material_name=name
    )
    if existing:
        return int(existing["id"])
    if not name and not code:
        return None
    unit_id = get_or_create_unit(connection, unit_name) if unit_name else None
    now = _utcnow()
    m_uuid = new_uuid()
    connection.execute(
        """INSERT INTO materials
               (code, name, unit_id, price, created_at, modified_at, uuid,
                updated_at, is_deleted, marked_for_deletion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)""",
        (
            (code or "").strip() or None,
            (name or "").strip(),
            unit_id,
            float(price or 0),
            now, now, m_uuid, now,
        ),
    )
    new_id = last_insert_id(connection)
    register_sync_change(connection, entity_type="materials", entity_uuid=m_uuid, operation="INSERT")
    return new_id


def get_or_create_work(
    connection: sqlite3.Connection,
    *,
    code: str | None = None,
    name: str | None = None,
    unit_name: str | None = None,
) -> int | None:
    """Return work id, looking it up by code then name; create if missing."""
    ncode = _normalize_lookup_value(code)
    nname = _normalize_lookup_value(name)
    if not ncode and not nname:
        return None

    rows = connection.execute(
        """SELECT id FROM works
           WHERE marked_for_deletion = 0 AND COALESCE(is_deleted,0) = 0
           ORDER BY id ASC"""
    ).fetchall()
    for r in rows:
        row = connection.execute(
            "SELECT code, name FROM works WHERE id = ?", (r["id"],)
        ).fetchone()
        if row and _normalize_lookup_value(row["code"]) == ncode and ncode:
            return int(r["id"])
    for r in rows:
        row = connection.execute(
            "SELECT code, name FROM works WHERE id = ?", (r["id"],)
        ).fetchone()
        if row and _normalize_lookup_value(row["name"]) == nname and nname:
            return int(r["id"])

    unit_id = get_or_create_unit(connection, unit_name) if unit_name else None
    now = _utcnow()
    w_uuid = new_uuid()
    connection.execute(
        """INSERT INTO works
               (code, name, unit, is_group, parent_id, price, labor_rate,
                created_at, modified_at, uuid, updated_at, is_deleted,
                marked_for_deletion)
           VALUES (?, ?, ?, 0, NULL, 0, 0, ?, ?, ?, ?, 0, 0)""",
        (
            ncode or None,
            nname,
            _normalize_unit_name(unit_name) if unit_name else None,
            now, now, w_uuid, now,
        ),
    )
    new_id = last_insert_id(connection)
    register_sync_change(connection, entity_type="works", entity_uuid=w_uuid, operation="INSERT")
    return new_id


def get_or_create_counterparty(
    connection: sqlite3.Connection,
    *,
    name: str | None = None,
    inn: str | None = None,
) -> int | None:
    if not name and not inn:
        return None
    # Try INN first, then name
    if inn:
        row = connection.execute(
            "SELECT id FROM counterparties WHERE inn = ? AND marked_for_deletion = 0",
            (inn.strip(),),
        ).fetchone()
        if row:
            return int(row["id"])
    if name:
        nname = _normalize_lookup_value(name)
        rows = connection.execute(
            "SELECT id, name FROM counterparties WHERE marked_for_deletion = 0"
        ).fetchall()
        for r in rows:
            if _normalize_lookup_value(r["name"]) == nname:
                return int(r["id"])
    now = _utcnow()
    c_uuid = new_uuid()
    connection.execute(
        """INSERT INTO counterparties
               (name, inn, created_at, modified_at, uuid, updated_at, is_deleted,
                marked_for_deletion)
           VALUES (?, ?, ?, ?, ?, ?, 0, 0)""",
        ((name or "").strip(), (inn or "").strip() or None, now, now, c_uuid, now),
    )
    new_id = last_insert_id(connection)
    register_sync_change(connection, entity_type="counterparties", entity_uuid=c_uuid, operation="INSERT")
    return new_id


def get_or_create_machine(
    connection: sqlite3.Connection,
    *,
    name: str | None = None,
    code: str | None = None,
    unit_name: str | None = None,
) -> int | None:
    nname = _normalize_lookup_value(name)
    ncode = _normalize_lookup_value(code)
    if not nname and not ncode:
        return None
    rows = connection.execute(
        "SELECT id, name, code FROM machines WHERE marked_for_deletion = 0"
    ).fetchall()
    for r in rows:
        if ncode and _normalize_lookup_value(r["code"]) == ncode:
            return int(r["id"])
    for r in rows:
        if nname and _normalize_lookup_value(r["name"]) == nname:
            return int(r["id"])
    now = _utcnow()
    connection.execute(
        """INSERT INTO machines
               (name, code, cost_per_hour, operator_rate_per_hour, unit,
                created_at, modified_at, marked_for_deletion)
           VALUES (?, ?, 0, 0, ?, ?, ?, 0)""",
        (
            (name or "").strip(),
            (code or "").strip(),
            unit_name or "",
            now, now,
        ),
    )
    return last_insert_id(connection)


def get_or_create_cost_element(
    connection: sqlite3.Connection, *, code: str | None = None, name: str | None = None
) -> int | None:
    ncode = _normalize_lookup_value(code)
    nname = _normalize_lookup_value(name)
    if not ncode and not nname:
        return None
    rows = connection.execute(
        "SELECT id, code, name FROM cost_elements WHERE marked_for_deletion = 0"
    ).fetchall()
    for r in rows:
        if ncode and _normalize_lookup_value(r["code"]) == ncode:
            return int(r["id"])
    for r in rows:
        if nname and _normalize_lookup_value(r["name"]) == nname:
            return int(r["id"])
    return None  # do not auto-create cost elements by policy


# ── Format helpers ─────────────────────────────────────────────────────────


def parse_tsv(text: str) -> list[dict[str, Any]]:
    """Parse TSV text with a header row into a list of dicts."""
    if not text or not text.strip():
        return []
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    return [dict(row) for row in reader]


def parse_json_text(text: str) -> Any:
    return json.loads(text)


def parse_xlsx_bytes(data: bytes) -> list[dict[str, Any]]:
    """Parse the first worksheet of an .xlsx file into dict rows using the
    first row as the header."""
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail="openpyxl is required for .xlsx import/export",
        ) from e
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration:
        return []
    header = [str(h).strip() if h is not None else "" for h in header]
    result: list[dict[str, Any]] = []
    for row in rows_iter:
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        record = {
            header[i]: ("" if i >= len(row) or row[i] is None else str(row[i]))
            for i in range(len(header))
        }
        result.append(record)
    return result


def to_tsv(rows: list[dict[str, Any]], headers: list[str]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter="\t", lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_format_cell(row.get(h)) for h in headers])
    return out.getvalue()


def to_xlsx_bytes(rows: list[dict[str, Any]], headers: list[str]) -> bytes:
    try:
        from openpyxl import Workbook
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail="openpyxl is required for .xlsx import/export",
        ) from e
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append([_coerce_cell(row.get(h)) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        # trim trailing zeros but keep ints readable
        if value == int(value):
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _coerce_cell(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    return value


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


# ── Document schema registry ───────────────────────────────────────────────
#
# Each schema describes:
#   line_table     – SQLite table for line items
#   doc_fk         – column on line_table referencing the document id
#   header_id_field– some reference snapshots (work_name etc.) we want to keep
#   columns        – ordered list of columns for import/export, each is a dict:
#       {field, label, type, ref, create}
#       type ∈ {"text","float","int"}
#       ref  ∈ {None, "material","work","unit","counterparty","machine",
#               "cost_element","object","estimate","foreman","person"}
#       create – whether missing references should be auto-created
#


DOCUMENT_SCHEMAS: dict[str, dict[str, Any]] = {
    "material_consumption": {
        "label": "Расход материалов",
        "line_table": "material_consumption_lines",
        "doc_fk": "document_id",
        "header_columns": ["number", "date", "object_id", "estimate_id", "foreman_id"],
        "columns": [
            {"field": "work_code", "label": "Код работы", "type": "text", "ref": "work", "create": False, "maps": "work_id"},
            {"field": "work_name", "label": "Работа", "type": "text", "ref": None, "create": False, "ref_helper": "work"},
            {"field": "material_code", "label": "Код материала", "type": "text", "ref": "material", "create": True, "maps": "material_id"},
            {"field": "material_name", "label": "Материал", "type": "text", "ref": None, "create": False, "ref_helper": "material"},
            {"field": "unit", "label": "Ед.", "type": "text", "ref": "unit", "create": True},
            {"field": "planned_quantity", "label": "Лимит", "type": "float"},
            {"field": "actual_quantity", "label": "Списано", "type": "float"},
            {"field": "price", "label": "Цена", "type": "float"},
            {"field": "sum", "label": "Сумма", "type": "float"},
        ],
    },
    "machinery_usage": {
        "label": "Использование машин",
        "line_table": "machinery_usage_lines",
        "doc_fk": "document_id",
        "header_columns": ["number", "date", "object_id", "estimate_id", "foreman_id"],
        "columns": [
            {"field": "machine_name", "label": "Машина", "type": "text", "ref": "machine", "create": True, "maps": "machine_id"},
            {"field": "work_code", "label": "Код работы", "type": "text", "ref": "work", "create": False, "maps": "work_id"},
            {"field": "work_name", "label": "Работа", "type": "text", "ref": None, "ref_helper": "work"},
            {"field": "unit", "label": "Ед.", "type": "text", "ref": "unit", "create": True},
            {"field": "hours", "label": "Часы", "type": "float"},
            {"field": "machine_cost", "label": "Стоимость маш.", "type": "float"},
            {"field": "operator_labor", "label": "ЗП машиниста", "type": "float"},
        ],
    },
    "subcontract_acceptance": {
        "label": "Субподряд",
        "line_table": "subcontract_acceptance_lines",
        "doc_fk": "document_id",
        "header_columns": ["number", "date", "object_id", "estimate_id"],
        "columns": [
            {"field": "work_code", "label": "Код работы", "type": "text", "ref": "work", "create": False, "maps": "work_id"},
            {"field": "work_name", "label": "Работа", "type": "text", "ref": None, "ref_helper": "work"},
            {"field": "counterparty_name", "label": "Субподрядчик", "type": "text", "ref": "counterparty", "create": True, "maps": "counterparty_id"},
            {"field": "unit", "label": "Ед.", "type": "text", "ref": "unit", "create": True},
            {"field": "sum", "label": "Сумма", "type": "float"},
            {"field": "description", "label": "Описание", "type": "text"},
        ],
    },
    "overhead_expense": {
        "label": "Накладные расходы",
        "line_table": "overhead_expense_lines",
        "doc_fk": "document_id",
        "header_columns": ["number", "date", "period"],
        "columns": [
            {"field": "cost_element_code", "label": "Код статьи", "type": "text", "ref": "cost_element", "create": False, "maps": "cost_element_id"},
            {"field": "cost_element_name", "label": "Статья затрат", "type": "text", "ref": None, "ref_helper": "cost_element"},
            {"field": "counterparty_name", "label": "Контрагент", "type": "text", "ref": "counterparty", "create": True, "maps": "counterparty_id"},
            {"field": "sum", "label": "Сумма", "type": "float"},
            {"field": "description", "label": "Описание", "type": "text"},
        ],
    },
    "daily_report": {
        "label": "Дневной отчёт",
        "line_table": "daily_report_lines",
        "doc_fk": "report_id",
        "header_columns": ["number", "date", "estimate_id", "foreman_id"],
        "columns": [
            {"field": "work_code", "label": "Код работы", "type": "text", "ref": "work", "create": False, "maps": "work_id"},
            {"field": "work_name", "label": "Работа", "type": "text", "ref": None, "ref_helper": "work"},
            {"field": "unit", "label": "Ед.", "type": "text", "ref": "unit", "create": True},
            {"field": "planned_labor", "label": "План. труд", "type": "float"},
            {"field": "quantity", "label": "Кол-во", "type": "float"},
            {"field": "price", "label": "Цена", "type": "float"},
            {"field": "actual_sum", "label": "Сумма", "type": "float"},
        ],
    },
    "estimate": {
        "label": "Смета",
        "line_table": "estimate_lines",
        "doc_fk": "estimate_id",
        "header_columns": ["number", "date", "customer_id", "object_id", "contractor_id", "responsible_id", "contract_id"],
        "columns": [
            {"field": "work_code", "label": "Код работы", "type": "text", "ref": "work", "create": True, "maps": "work_id"},
            {"field": "work_name", "label": "Работа", "type": "text", "ref": None, "ref_helper": "work"},
            {"field": "unit", "label": "Ед.", "type": "text", "ref": "unit", "create": True},
            {"field": "quantity", "label": "Кол-во", "type": "float"},
            {"field": "price", "label": "Цена", "type": "float"},
            {"field": "labor_rate", "label": "Трудоёмкость", "type": "float"},
            {"field": "sum", "label": "Сумма", "type": "float"},
            {"field": "planned_labor", "label": "План. труд", "type": "float"},
            {"field": "is_group", "label": "Группа", "type": "int"},
            {"field": "group_name", "label": "Название группы", "type": "text"},
        ],
    },
}


# ── Import (replace lines) ─────────────────────────────────────────────────


def _resolve_reference(
    connection: sqlite3.Connection,
    ref: str,
    row: dict[str, Any],
    create: bool,
) -> tuple[Any, list[str]]:
    """Resolve a reference value for the current row. Returns (value, warnings).

    For `material`/`work`/`counterparty`/`machine` references the resolver
    returns the integer id; for `unit` it returns the (possibly created) unit
    name string; for header FKs (object/estimate/foreman/person) it returns the
    integer id from the row directly.
    """
    warnings: list[str] = []
    if ref == "material":
        mid = get_or_create_material(
            connection,
            code=row.get("material_code") or None,
            name=row.get("material_name") or None,
            unit_name=row.get("unit") or None,
            price=_to_float(row.get("price")),
        )
        if mid is None:
            warnings.append(
                f"Не удалось сопоставить/создать материал: «{row.get('material_name') or row.get('material_code')}»"
            )
        return mid, warnings
    if ref == "work":
        wid = get_or_create_work(
            connection,
            code=row.get("work_code") or None,
            name=row.get("work_name") or None,
            unit_name=row.get("unit") or None,
        )
        if wid is None and create:
            # already attempted creation; if still None it means no name/code
            warnings.append(
                f"Работа не указана: «{row.get('work_name') or row.get('work_code')}»"
            )
        return wid, warnings
    if ref == "unit":
        # we keep unit as a text snapshot; creation happens through the
        # material/work resolver when needed.
        return (row.get("unit") or "").strip() or None, warnings
    if ref == "counterparty":
        cid = get_or_create_counterparty(
            connection,
            name=row.get("counterparty_name") or None,
            inn=row.get("counterparty_inn") or None,
        )
        if cid is None:
            warnings.append(
                f"Не удалось сопоставить контрагента: «{row.get('counterparty_name')}»"
            )
        return cid, warnings
    if ref == "machine":
        mid = get_or_create_machine(
            connection,
            name=row.get("machine_name") or None,
            code=row.get("machine_code") or None,
            unit_name=row.get("unit") or None,
        )
        if mid is None:
            warnings.append(f"Не удалось сопоставить машину: «{row.get('machine_name')}»")
        return mid, warnings
    if ref == "cost_element":
        ceid = get_or_create_cost_element(
            connection,
            code=row.get("cost_element_code") or None,
            name=row.get("cost_element_name") or None,
        )
        if ceid is None:
            warnings.append(
                f"Статья затрат не найдена: «{row.get('cost_element_name') or row.get('cost_element_code')}»"
            )
        return ceid, warnings
    return None, warnings


def _row_to_line(
    connection: sqlite3.Connection,
    schema: dict[str, Any],
    row: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Convert a parsed text row to a line dict ready for INSERT."""
    warnings: list[str] = []
    line: dict[str, Any] = {}

    for col in schema["columns"]:
        field = col["field"]
        ref = col.get("ref")
        maps = col.get("maps")
        ctype = col.get("type", "text")

        if ref:
            value, w = _resolve_reference(connection, ref, row, col.get("create", False))
            warnings.extend(w)
            if maps:
                line[maps] = value
            elif ctype == "text":
                # store resolved name/code as a snapshot
                line[field] = value if isinstance(value, str) else None
            continue

        # plain value column
        raw = row.get(field)
        if ctype == "float":
            line[field] = _to_float(raw)
        elif ctype == "int":
            line[field] = _to_int(raw)
        else:
            line[field] = (raw or "").strip() if isinstance(raw, str) else (raw or "")

    return line, warnings


def import_document_lines(
    connection: sqlite3.Connection,
    doc_type: str,
    doc_id: int,
    *,
    fmt: str,
    data: str | bytes,
    replace: bool = True,
) -> dict[str, Any]:
    """Import line items for a document from TSV/JSON/XLSX data.

    Replaces existing lines when `replace=True`. Auto-creates missing
    reference entities according to the schema. Returns a summary dict.
    """
    schema = DOCUMENT_SCHEMAS.get(doc_type)
    if not schema:
        raise HTTPException(status_code=400, detail=f"Unknown document type: {doc_type}")

    fmt = (fmt or "tsv").lower()
    if fmt == "tsv":
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        rows = parse_tsv(data)
    elif fmt == "json":
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        payload = parse_json_text(data)
        if isinstance(payload, dict) and "lines" in payload:
            rows = payload["lines"]
        elif isinstance(payload, list):
            rows = payload
        else:
            raise HTTPException(status_code=400, detail="JSON must be a list of lines or {lines:[...]}")
    elif fmt == "xlsx":
        if not isinstance(data, (bytes, bytearray)):
            raise HTTPException(status_code=400, detail="XLSX import requires raw bytes")
        rows = parse_xlsx_bytes(bytes(data))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

    if not rows:
        return {"imported": 0, "warnings": ["Нет строк для импорта"], "created_refs": {}}

    if replace:
        connection.execute(
            f"DELETE FROM {schema['line_table']} WHERE {schema['doc_fk']} = ?",
            (doc_id,),
        )

    imported = 0
    warnings: list[str] = []
    line_number = 0
    for row in rows:
        # skip fully empty rows
        if not any(str(v or "").strip() for v in row.values()):
            continue
        line_number += 1
        line, w = _row_to_line(connection, schema, row)
        warnings.extend(w)
        line["line_number"] = line_number
        line[schema["doc_fk"]] = doc_id
        cols = ", ".join(line.keys())
        placeholders = ", ".join(["?"] * len(line))
        connection.execute(
            f"INSERT INTO {schema['line_table']} ({cols}) VALUES ({placeholders})",
            list(line.values()),
        )
        imported += 1

    connection.commit()
    return {"imported": imported, "warnings": warnings, "format": fmt}


# ── Export ─────────────────────────────────────────────────────────────────


def _line_to_export_row(
    connection: sqlite3.Connection,
    schema: dict[str, Any],
    line: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for col in schema["columns"]:
        field = col["field"]
        ref = col.get("ref")
        maps = col.get("maps")

        if ref in ("material",):
            mid = line.get("material_id") if maps == "material_id" else line.get(maps) if maps else None
            name = code = unit = None
            if mid:
                m = connection.execute(
                    "SELECT name, code, unit_name FROM materials WHERE id = ?", (mid,)
                ).fetchone()
                if m:
                    name, code = m["name"], m["code"]
            row["material_name"] = name or line.get("material_name") or ""
            row["material_code"] = code or ""
            row["unit"] = unit or line.get("unit") or ""
            continue
        if ref == "work":
            wid = line.get(maps) if maps else line.get("work_id")
            name = code = None
            if wid:
                w = connection.execute(
                    "SELECT name, code, unit FROM works WHERE id = ?", (wid,)
                ).fetchone()
                if w:
                    name, code = w["name"], w["code"]
                    if not row.get("unit") and w["unit"]:
                        row["unit"] = w["unit"]
            row["work_name"] = name or line.get("work_name") or ""
            row["work_code"] = code or ""
            if not row.get("unit"):
                row["unit"] = line.get("unit") or ""
            continue
        if ref == "counterparty":
            cid = line.get(maps) if maps else line.get("counterparty_id")
            name = None
            if cid:
                c = connection.execute(
                    "SELECT name FROM counterparties WHERE id = ?", (cid,)
                ).fetchone()
                if c:
                    name = c["name"]
            row["counterparty_name"] = name or line.get("counterparty_name") or ""
            continue
        if ref == "machine":
            mid = line.get(maps) if maps else line.get("machine_id")
            name = code = None
            if mid:
                m = connection.execute(
                    "SELECT name, code FROM machines WHERE id = ?", (mid,)
                ).fetchone()
                if m:
                    name, code = m["name"], m["code"]
            row["machine_name"] = name or line.get("machine_name") or ""
            continue
        if ref == "cost_element":
            ceid = line.get(maps) if maps else line.get("cost_element_id")
            name = code = None
            if ceid:
                ce = connection.execute(
                    "SELECT name, code FROM cost_elements WHERE id = ?", (ceid,)
                ).fetchone()
                if ce:
                    name, code = ce["name"], ce["code"]
            row["cost_element_name"] = name or line.get("cost_element_name") or ""
            row["cost_element_code"] = code or ""
            continue
        if ref == "unit":
            row[field] = line.get(field) or ""
            continue
        # plain
        row[field] = line.get(field, "")
    return row


def export_document(
    connection: sqlite3.Connection,
    doc_type: str,
    doc_id: int,
    *,
    fmt: str = "tsv",
) -> dict[str, Any]:
    """Export a document (header + lines) to the requested format.

    Returns a dict with keys:
        body  – str for tsv/json, bytes for xlsx
        media_type
        filename
    """
    schema = DOCUMENT_SCHEMAS.get(doc_type)
    if not schema:
        raise HTTPException(status_code=400, detail=f"Unknown document type: {doc_type}")

    fmt = (fmt or "tsv").lower()
    headers = [col["label"] for col in schema["columns"]]

    line_rows_raw = connection.execute(
        f"SELECT * FROM {schema['line_table']} WHERE {schema['doc_fk']} = ? ORDER BY line_number",
        (doc_id,),
    ).fetchall()
    export_rows: list[dict[str, Any]] = []
    for raw in line_rows_raw:
        line = row_to_dict(raw) or {}
        export_rows.append(_line_to_export_row(connection, schema, line))

    if fmt == "tsv":
        body = to_tsv(export_rows, headers)
        return {
            "body": body,
            "media_type": "text/tab-separated-values; charset=utf-8",
            "filename": f"{doc_type}_{doc_id}.tsv",
        }
    if fmt == "json":
        body = json.dumps(
            {"doc_type": doc_type, "doc_id": doc_id, "lines": export_rows},
            ensure_ascii=False,
            indent=2,
        )
        return {
            "body": body,
            "media_type": "application/json; charset=utf-8",
            "filename": f"{doc_type}_{doc_id}.json",
        }
    if fmt == "xlsx":
        body = to_xlsx_bytes(export_rows, headers)
        return {
            "body": body,
            "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "filename": f"{doc_type}_{doc_id}.xlsx",
        }
    raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")


def supported_doc_types() -> list[str]:
    return list(DOCUMENT_SCHEMAS.keys())
