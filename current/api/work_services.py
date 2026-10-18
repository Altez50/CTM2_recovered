from __future__ import annotations

import io
import logging
import re
import sqlite3
import zipfile
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from fastapi import HTTPException

from api.database import last_insert_id, new_uuid, register_sync_change, row_to_dict, rows_to_dicts
from api.models.common import Pagination
from api.models.works import (
    ImportMaterialCreateRequest,
    ImportMaterialCreateResponse,
    ImportMaterialCreateResult,
    ImportPreviewResponse,
    ImportedSpecificationRow,
    MissingImportedMaterial,
    WorkCorrectionImportResponse,
    WorkCorrectionImportWorkResult,
    WorkDetailPayload,
)
from api.printing import build_excel_xml
from api.services import build_pagination


logger = logging.getLogger(__name__)

COMPONENT_TYPES = {"Material", "Labor", "Equipment", "Other"}
WORK_REVIEW_STATUSES = {"ok", "incorrect", "corrected"}
NEW_MATERIALS_FOLDER_NAME = "Новые материалы"

# Unit synonym mapping for normalization
# Maps various unit name variations to canonical forms
UNIT_SYNONYMS: dict[str, str] = {
    # Area units - canonical: м²
    "м2": "м²",
    "м.кв": "м²",
    "м.кв.": "м²",
    "кв.м": "м²",
    "кв. м": "м²",
    "кв м": "м²",
    "квм": "м²",
    "метр квадратный": "м²",
    "метр кв": "м²",
    "метр кв.": "м²",
    "м кв": "м²",
    "м кв.": "м²",
    
    # Volume units - canonical: м³
    "м3": "м³",
    "м.куб": "м³",
    "м.куб.": "м³",
    "куб.м": "м³",
    "куб. м": "м³",
    "куб м": "м³",
    "кубм": "м³",
    "метр кубический": "м³",
    "метр куб": "м³",
    "метр куб.": "м³",
    "м куб": "м³",
    "м куб.": "м³",
    
    # Weight units - canonical: кг, т
    "килограмм": "кг",
    "килограммов": "кг",
    "тонна": "т",
    "тонн": "т",
    
    # Length units - canonical: м
    "метр": "м",
    "метра": "м",
    "метров": "м",
    "м.п": "м",
    "м.п.": "м",
    "мп": "м",
    "м п": "м",
    "метр погонный": "м",
    "метр погонных": "м",
    "погонный метр": "м",
    
    # Quantity units - canonical: шт
    "штука": "шт",
    "штук": "шт",
    "штуки": "шт",
    "шт.": "шт",
    "ед": "шт",
    "ед.": "шт",
    "единица": "шт",
    "единиц": "шт",
    
    # Time units - canonical: ч, чел-час
    "час": "ч",
    "часа": "ч",
    "часов": "ч",
    "чел-час": "чел-час",
    "чел.час": "чел-час",
    "чел час": "чел-час",
    "человеко-час": "чел-час",
    "человеко час": "чел-час",
    "человекочас": "чел-час",
    
    # Other common units
    "л": "л",
    "литр": "л",
    "литра": "л",
    "литров": "л",
    "компл": "компл",
    "комплект": "компл",
    "комплекта": "компл",
    "комплектов": "компл",
    "смена": "смена",
    "смен": "смена",
    "смены": "смена",
}


def _normalize_unit_name(name: str) -> str:
    """
    Normalize unit name for duplicate prevention.
    
    Normalization rules:
    1. Strip leading/trailing whitespace
    2. Convert to lowercase
    3. Collapse multiple spaces to single space
    4. Apply synonym mapping to canonical form
    
    Args:
        name: Raw unit name from user input or Excel import
        
    Returns:
        Normalized canonical unit name
        
    Examples:
        >>> _normalize_unit_name("М2")
        "м²"
        >>> _normalize_unit_name("  кв.м  ")
        "м²"
        >>> _normalize_unit_name("метр")
        "м"
    """
    if not name:
        return ""
    
    # Strip and lowercase
    normalized = name.strip().lower()
    
    # Remove extra whitespace (collapse multiple spaces)
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Apply synonym mapping
    if normalized in UNIT_SYNONYMS:
        canonical = UNIT_SYNONYMS[normalized]
        logger.debug(f"Unit normalized: '{name}' → '{canonical}'")
        return canonical
    
    # Return normalized form even if not in synonym map
    return normalized


def _find_units_by_normalized_name(connection: sqlite3.Connection, normalized_name: str) -> list[dict[str, object]]:
    """Return active units that normalize to the same canonical name."""
    if not normalized_name:
        return []

    matches: list[dict[str, object]] = []
    for row in connection.execute(
        """
        SELECT id, name, short_name
        FROM units
        WHERE marked_for_deletion = 0
        ORDER BY id ASC
        """
    ).fetchall():
        raw_name = str(row["name"] or "")
        if _normalize_unit_name(raw_name) != normalized_name:
            continue
        matches.append(row_to_dict(row) or {})

    matches.sort(
        key=lambda item: (
            0 if str(item.get("name") or "") == normalized_name else 1,
            int(item.get("id") or 0),
        )
    )
    return matches


def _find_preferred_unit_by_normalized_name(
    connection: sqlite3.Connection,
    normalized_name: str,
) -> dict[str, object] | None:
    matches = _find_units_by_normalized_name(connection, normalized_name)
    return matches[0] if matches else None


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def ensure_new_materials_folder(connection: sqlite3.Connection) -> int:
    """Return the shared folder used by every automatic material creator."""
    rows = connection.execute(
        """
        SELECT id, name
        FROM materials
        WHERE COALESCE(is_group, 0) = 1
          AND marked_for_deletion = 0
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY id
        """
    ).fetchall()
    folder_key = " ".join(NEW_MATERIALS_FOLDER_NAME.split()).casefold()
    for row in rows:
        if " ".join(str(row["name"] or "").split()).casefold() == folder_key:
            return int(row["id"])

    timestamp = _utcnow()
    folder_uuid = new_uuid()
    connection.execute(
        """
        INSERT INTO materials (
            code, name, unit_id, price, parent_id, is_group,
            marked_for_deletion, created_at, modified_at, uuid, updated_at, is_deleted
        ) VALUES (NULL, ?, NULL, 0, NULL, 1, 0, ?, ?, ?, ?, 0)
        """,
        (NEW_MATERIALS_FOLDER_NAME, timestamp, timestamp, folder_uuid, timestamp),
    )
    folder_id = last_insert_id(connection)
    register_sync_change(connection, entity_type="materials", entity_uuid=folder_uuid, operation="INSERT")
    return folder_id


def _normalize_bool(value: object) -> bool:
    return bool(value) if value is not None else False


def _normalize_component_type(value: str | None) -> str:
    candidate = (value or "").strip()
    lookup = {
        "material": "Material",
        "materials": "Material",
        "материал": "Material",
        "материалы": "Material",
        "labor": "Labor",
        "labour": "Labor",
        "труд": "Labor",
        "трудозатраты": "Labor",
        "equipment": "Equipment",
        "оборудование": "Equipment",
        "other": "Other",
        "прочее": "Other",
    }
    normalized = lookup.get(candidate.lower(), candidate)
    if normalized not in COMPONENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported component type")
    return normalized


def _normalize_review_status(value: str | None) -> str:
    candidate = (value or "").strip().casefold()
    lookup = {
        "": "ok",
        "ok": "ok",
        "correct": "ok",
        "normal": "ok",
        "норма": "ok",
        "ок": "ok",
        "incorrect": "incorrect",
        "invalid": "incorrect",
        "needs_review": "incorrect",
        "review": "incorrect",
        "требует проверки": "incorrect",
        "ошибка": "incorrect",
        "некорректно": "incorrect",
        "incorrect imported specs": "incorrect",
        "corrected": "corrected",
        "fixed": "corrected",
        "исправлено": "corrected",
    }
    normalized = lookup.get(candidate, candidate)
    if normalized not in WORK_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported work review status")
    return normalized


def _build_issue_flags(
    *,
    component_type: object | None,
    material_id: object | None,
    unit_id: object | None,
    component_name: object | None,
) -> list[str]:
    flags: list[str] = []
    if str(component_type or "") == "Material" and material_id is None:
        flags.append("missing_material")
    if unit_id is None:
        flags.append("missing_unit")
    component_text = str(component_name or "")
    if component_text.startswith("Ресурс ") or component_text.startswith("Материал "):
        flags.append("placeholder_name")
    return flags


def _work_exists(connection: sqlite3.Connection, work_id: int) -> bool:
    row = connection.execute(
        "SELECT 1 FROM works WHERE id = ? AND marked_for_deletion = 0",
        (work_id,),
    ).fetchone()
    return row is not None


def _require_work(connection: sqlite3.Connection, work_id: int) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT
            w.id,
            w.uuid,
            w.name,
            w.code,
            w.unit,
            w.price,
            w.labor_rate,
            COALESCE(w.specification_review_status, 'ok') AS specification_review_status,
            w.specification_review_note,
            w.parent_id,
            parent.uuid AS parent_uuid,
            w.marked_for_deletion,
            w.is_group,
            w.updated_at,
            w.is_deleted
        FROM works w
        LEFT JOIN works parent ON parent.id = w.parent_id
        WHERE w.id = ? AND w.marked_for_deletion = 0
        """,
        (work_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Work not found")
    item = row_to_dict(row) or {}
    item["marked_for_deletion"] = _normalize_bool(item.get("marked_for_deletion"))
    item["is_group"] = _normalize_bool(item.get("is_group"))
    item["specification_review_status"] = _normalize_review_status(str(item.get("specification_review_status") or "ok"))
    item["specification_review_note"] = str(item.get("specification_review_note") or "").strip() or None
    return item


def _require_unit(connection: sqlite3.Connection, unit_id: int) -> dict[str, object]:
    row = connection.execute(
        "SELECT id, uuid, name, short_name FROM units WHERE id = ? AND marked_for_deletion = 0",
        (unit_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail="Unit not found")
    return row_to_dict(row) or {}


def _find_unit_by_uuid(connection: sqlite3.Connection, unit_uuid: str | None) -> dict[str, object] | None:
    if not unit_uuid:
        return None
    row = connection.execute(
        "SELECT id, uuid, name, short_name FROM units WHERE uuid = ? AND marked_for_deletion = 0",
        (unit_uuid,),
    ).fetchone()
    return row_to_dict(row) if row is not None else None


def _resolve_unit_id(connection: sqlite3.Connection, unit_id: int | None, unit_name: str | None) -> int | None:
    """
    Resolve unit_id from unit_id or unit_name, with enhanced duplicate prevention.
    
    Args:
        connection: Database connection
        unit_id: Explicit unit ID (takes precedence)
        unit_name: Unit name to resolve (will be normalized)
        
    Returns:
        Resolved unit_id or None if no unit specified
        
    Raises:
        HTTPException: If unit_id is invalid or database error occurs
    """
    if unit_id is not None:
        _require_unit(connection, unit_id)
        return unit_id

    if not unit_name:
        return None
    
    # Apply normalization
    normalized_name = _normalize_unit_name(unit_name)
    if not normalized_name:
        return None

    # Reuse any active unit that normalizes to the same canonical name.
    existing = _find_preferred_unit_by_normalized_name(connection, normalized_name)
    if existing is not None:
        logger.debug(f"Reusing existing unit: '{unit_name}' → ID {existing['id']} ('{existing['name']}')")
        return int(existing["id"])

    # Create new unit with canonical name
    try:
        now = _utcnow()
        unit_uuid = new_uuid()
        connection.execute(
            """
            INSERT INTO units (
                name, short_name, created_at, modified_at, uuid, updated_at, is_deleted
            ) VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (normalized_name, normalized_name, now, now, unit_uuid, now),
        )
        new_id = last_insert_id(connection)
        register_sync_change(connection, entity_type="units", entity_uuid=unit_uuid, operation="INSERT")
        logger.info(f"Created new unit: '{normalized_name}' (ID {new_id})")
        return new_id
    except sqlite3.IntegrityError as e:
        # Race condition: another thread/process created the unit
        logger.warning(f"Race condition detected for unit '{normalized_name}', retrying lookup")
        existing = _find_preferred_unit_by_normalized_name(connection, normalized_name)
        if existing:
            return int(existing["id"])
        # If still not found, re-raise the original error
        logger.error(f"Failed to resolve unit after race condition: {e}")
        raise HTTPException(status_code=500, detail="Failed to create unit") from e


def _require_material(connection: sqlite3.Connection, material_id: int) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT
            m.id,
            m.uuid,
            m.code,
            m.name,
            m.unit_id,
            u.uuid AS unit_uuid,
            m.price,
            u.name AS unit_name
        FROM materials m
        LEFT JOIN units u ON u.id = m.unit_id
        WHERE m.id = ? AND m.marked_for_deletion = 0
        """,
        (material_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail="Material not found")
    return row_to_dict(row) or {}


def _find_material_by_uuid(connection: sqlite3.Connection, material_uuid: str | None) -> dict[str, object] | None:
    if not material_uuid:
        return None
    row = connection.execute(
        """
        SELECT
            m.id,
            m.uuid,
            m.code,
            m.name,
            m.unit_id,
            u.uuid AS unit_uuid,
            m.price,
            u.name AS unit_name
        FROM materials m
        LEFT JOIN units u ON u.id = m.unit_id
        WHERE m.uuid = ? AND m.marked_for_deletion = 0
        """,
        (material_uuid,),
    ).fetchone()
    return row_to_dict(row) if row is not None else None


def _normalize_lookup_value(value: object | None) -> str:
    return " ".join(str(value or "").split()).strip().casefold()


def _find_material_by_code_or_name(
    connection: sqlite3.Connection,
    *,
    material_code: str | None = None,
    material_name: str | None = None,
) -> dict[str, object] | None:
    normalized_code = _normalize_lookup_value(material_code)
    normalized_name = _normalize_lookup_value(material_name)
    if not normalized_code and not normalized_name:
        return None

    rows = connection.execute(
        """
        SELECT
            m.id,
            m.uuid,
            m.code,
            m.name,
            m.unit_id,
            u.uuid AS unit_uuid,
            m.price,
            u.name AS unit_name
        FROM materials m
        LEFT JOIN units u ON u.id = m.unit_id
        WHERE m.marked_for_deletion = 0
          AND COALESCE(m.is_deleted, 0) = 0
          AND COALESCE(m.is_group, 0) = 0
        ORDER BY m.id ASC
        """
    ).fetchall()

    for row in rows:
        item = row_to_dict(row) or {}
        if normalized_code and _normalize_lookup_value(item.get("code")) == normalized_code:
            return item

    for row in rows:
        item = row_to_dict(row) or {}
        if normalized_name and _normalize_lookup_value(item.get("name")) == normalized_name:
            return item
    return None


def _register_missing_material(
    missing_by_key: dict[str, MissingImportedMaterial],
    *,
    source_row: int,
    material_name: str,
    material_code: str | None,
    unit_name: str | None,
    unit_id: int | None,
    unit_status: str | None,
    unit_price: float,
) -> None:
    normalized_name = " ".join(material_name.split()).strip()
    normalized_code = " ".join((material_code or "").split()).strip() or None
    if not normalized_name:
        return

    key = f"code:{normalized_code.casefold()}" if normalized_code else f"name:{normalized_name.casefold()}"
    existing = missing_by_key.get(key)
    if existing is None:
        missing_by_key[key] = MissingImportedMaterial(
            material_name=normalized_name,
            material_code=normalized_code,
            unit_name=unit_name,
            unit_id=unit_id,
            unit_status=unit_status,
            unit_price=max(0.0, round(float(unit_price or 0), 2)),
            source_row_numbers=[source_row],
        )
        return

    if source_row not in existing.source_row_numbers:
        existing.source_row_numbers.append(source_row)
    if not existing.unit_name and unit_name:
        existing.unit_name = unit_name
    if existing.unit_id is None and unit_id is not None:
        existing.unit_id = unit_id
    if not existing.unit_status and unit_status:
        existing.unit_status = unit_status
    if float(existing.unit_price or 0) == 0 and unit_price > 0:
        existing.unit_price = max(0.0, round(float(unit_price or 0), 2))


def _validate_parent(connection: sqlite3.Connection, parent_id: int | None, work_id: int | None = None) -> None:
    if parent_id is None:
        return

    parent = connection.execute(
        "SELECT id, parent_id, is_group FROM works WHERE id = ? AND marked_for_deletion = 0",
        (parent_id,),
    ).fetchone()
    if parent is None:
        raise HTTPException(status_code=400, detail="Parent work not found")
    if not bool(parent["is_group"]):
        raise HTTPException(status_code=400, detail="Parent must be a group work")
    if work_id is None:
        return

    pointer = parent["parent_id"]
    while pointer is not None:
        if pointer == work_id:
            raise HTTPException(status_code=400, detail="Circular parent relationship is not allowed")
        pointer_row = connection.execute("SELECT parent_id FROM works WHERE id = ?", (pointer,)).fetchone()
        if pointer_row is None:
            break
        pointer = pointer_row["parent_id"]


def _normalize_specification_payload(
    connection: sqlite3.Connection,
    raw_payload: dict[str, object],
) -> dict[str, object]:
    component_type = _normalize_component_type(str(raw_payload.get("component_type") or ""))
    material_id = raw_payload.get("material_id")
    material_uuid = str(raw_payload.get("material_uuid") or "").strip() or None
    material: dict[str, object] | None = None
    if material_id is None and material_uuid:
        material = _find_material_by_uuid(connection, material_uuid)
        material_id = material["id"] if material is not None else None
    if material_id is not None:
        material = _require_material(connection, int(material_id))
        component_type = "Material"

    component_name = str(raw_payload.get("component_name") or "").strip()
    if not component_name and material:
        component_name = str(material["name"])
    if not component_name:
        raise HTTPException(status_code=400, detail="Specification component name is required")

    consumption_rate = raw_payload.get("consumption_rate")
    unit_price = raw_payload.get("unit_price")
    try:
        consumption_rate_value = float(consumption_rate)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Consumption rate must be a number") from None
    try:
        unit_price_value = float(unit_price)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Unit price must be a number") from None

    if consumption_rate_value <= 0:
        raise HTTPException(status_code=400, detail="Consumption rate must be greater than zero")
    if unit_price_value < 0:
        raise HTTPException(status_code=400, detail="Unit price must be greater than or equal to zero")

    unit_id = raw_payload.get("unit_id")
    unit_uuid = str(raw_payload.get("unit_uuid") or "").strip() or None
    unit_name = raw_payload.get("unit_name")
    if material and unit_id is None and not unit_name:
        unit_id = material.get("unit_id")
        unit_name = material.get("unit_name")
        unit_uuid = str(material.get("unit_uuid") or "").strip() or None
    if unit_id is None and unit_uuid:
        unit = _find_unit_by_uuid(connection, unit_uuid)
        unit_id = unit["id"] if unit is not None else None
        if unit_name is None and unit is not None:
            unit_name = unit.get("name")
    resolved_unit_id = _resolve_unit_id(
        connection,
        int(unit_id) if unit_id is not None else None,
        str(unit_name) if unit_name is not None else None,
    )
    resolved_unit = _require_unit(connection, resolved_unit_id) if resolved_unit_id is not None else None

    return {
        "id": int(raw_payload["id"]) if raw_payload.get("id") is not None else None,
        "uuid": str(raw_payload.get("uuid") or "").strip() or None,
        "component_type": component_type,
        "component_name": component_name,
        "unit_id": resolved_unit_id,
        "unit_uuid": str(resolved_unit.get("uuid")) if resolved_unit is not None and resolved_unit.get("uuid") else None,
        "consumption_rate": consumption_rate_value,
        "unit_price": unit_price_value,
        "material_id": int(material_id) if material_id is not None else None,
        "material_uuid": str(material.get("uuid")) if material is not None and material.get("uuid") else material_uuid,
        "created_at": raw_payload.get("created_at"),
        "modified_at": raw_payload.get("modified_at"),
        "updated_at": raw_payload.get("updated_at"),
        "is_deleted": int(bool(raw_payload.get("is_deleted", 0))),
    }


def _row_to_specification_record(row: dict[str, object]) -> dict[str, object]:
    consumption_rate = float(row.get("consumption_rate") or 0)
    unit_price = float(row.get("unit_price") or 0)
    return {
        "id": int(row["id"]),
        "uuid": row.get("uuid"),
        "work_id": int(row["work_id"]),
        "work_uuid": row.get("work_uuid"),
        "component_type": str(row["component_type"]),
        "component_name": str(row["component_name"]),
        "unit_id": int(row["unit_id"]) if row.get("unit_id") is not None else None,
        "unit_uuid": row.get("unit_uuid"),
        "unit_name": row.get("unit_name"),
        "consumption_rate": consumption_rate,
        "unit_price": unit_price,
        "total_cost": round(consumption_rate * unit_price, 2),
        "material_id": int(row["material_id"]) if row.get("material_id") is not None else None,
        "material_uuid": row.get("material_uuid"),
        "modified_at": row.get("modified_at") or row.get("updated_at"),
    }


def list_units(
    connection: sqlite3.Connection,
    *,
    search: str | None = None,
) -> list[dict[str, object]]:
    where_parts = ["marked_for_deletion = 0"]
    params: list[object] = []
    if search:
        where_parts.append("name LIKE ?")
        params.append(f"%{search.strip()}%")
    rows = connection.execute(
        f"""
        SELECT id, uuid, name, short_name
        FROM units
        WHERE {' AND '.join(where_parts)}
        ORDER BY name COLLATE NOCASE ASC
        LIMIT 100
        """,
        params,
    ).fetchall()
    return rows_to_dicts(rows)


def list_materials(
    connection: sqlite3.Connection,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> tuple[list[dict[str, object]], Pagination]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    where_parts = [
        "m.marked_for_deletion = 0",
        "COALESCE(m.is_deleted, 0) = 0",
        "COALESCE(m.is_group, 0) = 0",
    ]
    params: list[object] = []
    if search:
        where_parts.append("(m.name LIKE ? OR COALESCE(m.code, '') LIKE ?)")
        params.extend([f"%{search.strip()}%", f"%{search.strip()}%"])

    total = connection.execute(
        f"SELECT COUNT(*) FROM materials m WHERE {' AND '.join(where_parts)}",
        params,
    ).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT m.id, m.uuid, m.code, m.name, m.unit_id, u.uuid AS unit_uuid, m.price, u.name AS unit_name
        FROM materials m
        LEFT JOIN units u ON u.id = m.unit_id
        WHERE {' AND '.join(where_parts)}
        ORDER BY m.name COLLATE NOCASE ASC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return rows_to_dicts(rows), build_pagination(page, page_size, int(total))


def update_material(
    connection: sqlite3.Connection,
    material_id: int,
    *,
    name: str | None = None,
    code: str | None = None,
    unit_id: int | None = None,
    price: float | None = None,
) -> dict[str, object]:
    row = connection.execute(
        "SELECT id, uuid FROM materials WHERE id = ? AND marked_for_deletion = 0",
        (material_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Material not found")
    now = _utcnow()
    assignments: list[str] = ["modified_at = ?", "updated_at = ?"]
    params: list[object] = [now, now]
    if name is not None:
        assignments.append("name = ?")
        params.append(name.strip())
    if code is not None:
        assignments.append("code = ?")
        params.append(code.strip() if code.strip() else None)
    if unit_id is not None:
        assignments.append("unit_id = ?")
        params.append(unit_id if unit_id > 0 else None)
    if price is not None:
        assignments.append("price = ?")
        params.append(float(price))
    connection.execute(
        f"UPDATE materials SET {', '.join(assignments)} WHERE id = ?",
        [*params, material_id],
    )
    register_sync_change(connection, entity_type="materials", entity_uuid=str(row["uuid"]), operation="UPDATE")
    connection.commit()
    updated = connection.execute(
        """
        SELECT m.id, m.uuid, m.code, m.name, m.unit_id, u.uuid AS unit_uuid, m.price, u.name AS unit_name
        FROM materials m
        LEFT JOIN units u ON u.id = m.unit_id
        WHERE m.id = ?
        """,
        (material_id,),
    ).fetchone()
    return row_to_dict(updated) or {}


def delete_material(connection: sqlite3.Connection, material_id: int) -> None:
    row = connection.execute(
        "SELECT uuid FROM materials WHERE id = ? AND marked_for_deletion = 0",
        (material_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Material not found")
    now = _utcnow()
    connection.execute(
        "UPDATE materials SET marked_for_deletion = 1, is_deleted = 1, modified_at = ?, updated_at = ? WHERE id = ?",
        (now, now, material_id),
    )
    register_sync_change(connection, entity_type="materials", entity_uuid=str(row["uuid"]), operation="UPDATE")
    connection.commit()


def get_work_specifications(connection: sqlite3.Connection, work_id: int) -> list[dict[str, object]]:
    _require_work(connection, work_id)
    rows = connection.execute(
        """
        SELECT
            ws.id,
            ws.uuid,
            ws.work_id,
            w.uuid AS work_uuid,
            ws.component_type,
            ws.component_name,
            ws.unit_id,
            u.uuid AS unit_uuid,
            ws.consumption_rate,
            ws.unit_price,
            ws.material_id,
            m.uuid AS material_uuid,
            ws.modified_at,
            ws.updated_at,
            u.name AS unit_name
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
    return [_row_to_specification_record(row_to_dict(row) or {}) for row in rows]


def get_work_detail(connection: sqlite3.Connection, work_id: int) -> dict[str, object]:
    work = _require_work(connection, work_id)
    work["specifications"] = get_work_specifications(connection, work_id)
    return work


def get_work_by_uuid(connection: sqlite3.Connection, work_uuid: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT id FROM works WHERE uuid = ? AND COALESCE(is_deleted, 0) = 0",
        (work_uuid,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Work not found")
    return get_work_detail(connection, int(row["id"]))


def _validate_work_payload(connection: sqlite3.Connection, payload: dict[str, object], work_id: int | None = None) -> dict[str, object]:
    normalized = WorkDetailPayload(**payload).model_dump()
    normalized["name"] = normalized["name"].strip()
    normalized["code"] = normalized["code"].strip() if normalized.get("code") else None
    normalized["unit"] = normalized["unit"].strip() if normalized.get("unit") else None
    normalized["specification_review_status"] = _normalize_review_status(
        str(normalized.get("specification_review_status") or "ok")
    )
    normalized["specification_review_note"] = (
        str(normalized.get("specification_review_note") or "").strip() or None
    )
    if normalized.get("parent_id") is None and normalized.get("parent_uuid"):
        parent_row = connection.execute(
            "SELECT id FROM works WHERE uuid = ? AND marked_for_deletion = 0",
            (normalized["parent_uuid"],),
        ).fetchone()
        normalized["parent_id"] = int(parent_row["id"]) if parent_row is not None else None
    _validate_parent(connection, normalized.get("parent_id"), work_id)
    return normalized


def _sync_specifications(
    connection: sqlite3.Connection,
    *,
    work_id: int,
    specifications: list[dict[str, object]],
) -> list[dict[str, object]]:
    existing_rows = connection.execute(
        """
        SELECT id, uuid
        FROM work_specifications
        WHERE work_id = ?
          AND COALESCE(marked_for_deletion, 0) = 0
          AND COALESCE(is_deleted, 0) = 0
        """,
        (work_id,),
    ).fetchall()
    existing_ids = {int(row["id"]) for row in existing_rows}
    existing_uuid_map = {str(row["uuid"]): int(row["id"]) for row in existing_rows if row["uuid"]}
    incoming_ids: set[int] = set()

    for raw_spec in specifications:
        normalized = _normalize_specification_payload(connection, raw_spec)
        now = _utcnow()
        spec_id = int(normalized["id"]) if normalized["id"] is not None else None
        spec_uuid = str(normalized.get("uuid") or "").strip() or None
        if spec_id is None and spec_uuid and spec_uuid in existing_uuid_map:
            spec_id = existing_uuid_map[spec_uuid]
        if spec_id is not None and spec_id in existing_ids:
            incoming_ids.add(spec_id)
            modified_at = str(normalized.get("modified_at") or normalized.get("updated_at") or now)
            updated_at = str(normalized.get("updated_at") or modified_at or now)
            connection.execute(
                """
                UPDATE work_specifications
                SET component_type = ?,
                    component_name = ?,
                    unit_id = ?,
                    consumption_rate = ?,
                    unit_price = ?,
                    material_id = ?,
                    modified_at = ?,
                    updated_at = ?,
                    uuid = ?,
                    marked_for_deletion = 0,
                    is_deleted = ?
                WHERE id = ? AND work_id = ?
                """,
                (
                    normalized["component_type"],
                    normalized["component_name"],
                    normalized["unit_id"],
                    normalized["consumption_rate"],
                    normalized["unit_price"],
                    normalized["material_id"],
                    modified_at,
                    updated_at,
                    spec_uuid or next(
                        key for key, value in existing_uuid_map.items() if value == spec_id
                    ),
                    int(normalized.get("is_deleted", 0)),
                    spec_id,
                    work_id,
                ),
            )
            continue

        created_at = str(normalized.get("created_at") or now)
        modified_at = str(normalized.get("modified_at") or normalized.get("updated_at") or now)
        updated_at = str(normalized.get("updated_at") or modified_at or now)
        connection.execute(
            """
            INSERT INTO work_specifications (
                work_id,
                component_type,
                component_name,
                unit_id,
                consumption_rate,
                unit_price,
                material_id,
                uuid,
                created_at,
                modified_at,
                updated_at,
                marked_for_deletion,
                is_deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                work_id,
                normalized["component_type"],
                normalized["component_name"],
                normalized["unit_id"],
                normalized["consumption_rate"],
                normalized["unit_price"],
                normalized["material_id"],
                spec_uuid or new_uuid(),
                created_at,
                modified_at,
                updated_at,
            ),
        )
        incoming_ids.add(last_insert_id(connection))

    ids_to_delete = existing_ids - incoming_ids
    if ids_to_delete:
        connection.executemany(
            """
            UPDATE work_specifications
            SET marked_for_deletion = 1,
                is_deleted = 1,
                modified_at = ?,
                updated_at = ?
            WHERE id = ? AND work_id = ?
            """,
            [(_utcnow(), _utcnow(), spec_id, work_id) for spec_id in ids_to_delete],
        )

    return get_work_specifications(connection, work_id)


def create_work(connection: sqlite3.Connection, payload: dict[str, object]) -> dict[str, object]:
    normalized = _validate_work_payload(connection, payload)
    specifications = normalized.pop("specifications", [])
    now = _utcnow()
    work_uuid = str(normalized.get("uuid") or new_uuid())
    connection.execute(
        """
        INSERT INTO works (
            name, code, unit, price, labor_rate, specification_review_status, specification_review_note,
            parent_id, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            normalized["name"],
            normalized["code"],
            normalized["unit"],
            normalized["price"],
            normalized["labor_rate"],
            normalized["specification_review_status"],
            normalized["specification_review_note"],
            normalized["parent_id"],
            int(normalized["marked_for_deletion"]),
            int(normalized["is_group"]),
            now,
            now,
            work_uuid,
            now,
        ),
    )
    work_id = last_insert_id(connection)
    _sync_specifications(connection, work_id=work_id, specifications=specifications)
    register_sync_change(connection, entity_type="works", entity_uuid=work_uuid, operation="INSERT")
    connection.commit()
    return get_work_detail(connection, work_id)


def update_work(connection: sqlite3.Connection, work_id: int, payload: dict[str, object]) -> dict[str, object]:
    existing = _require_work(connection, work_id)
    normalized = _validate_work_payload(connection, payload, work_id)
    specifications = normalized.pop("specifications", [])
    now = _utcnow()
    connection.execute(
        """
        UPDATE works
        SET name = ?,
            code = ?,
            unit = ?,
            price = ?,
            labor_rate = ?,
            specification_review_status = ?,
            specification_review_note = ?,
            parent_id = ?,
            marked_for_deletion = ?,
            is_group = ?,
            modified_at = ?,
            uuid = ?,
            updated_at = ?,
            is_deleted = 0
        WHERE id = ?
        """,
        (
            normalized["name"],
            normalized["code"],
            normalized["unit"],
            normalized["price"],
            normalized["labor_rate"],
            normalized["specification_review_status"],
            normalized["specification_review_note"],
            normalized["parent_id"],
            int(normalized["marked_for_deletion"]),
            int(normalized["is_group"]),
            now,
            str(existing["uuid"]),
            now,
            work_id,
        ),
    )
    _sync_specifications(connection, work_id=work_id, specifications=specifications)
    register_sync_change(connection, entity_type="works", entity_uuid=str(existing["uuid"]), operation="UPDATE")
    connection.commit()
    return get_work_detail(connection, work_id)


def delete_work(connection: sqlite3.Connection, work_id: int) -> None:
    work = _require_work(connection, work_id)
    now = _utcnow()
    connection.execute(
        """
        UPDATE works
        SET marked_for_deletion = 1,
            modified_at = ?,
            updated_at = ?,
            is_deleted = 1
        WHERE id = ?
        """,
        (now, now, work_id),
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
        (now, now, work_id),
    )
    register_sync_change(connection, entity_type="works", entity_uuid=str(work["uuid"]), operation="DELETE")
    connection.commit()


def preview_copy_specifications(connection: sqlite3.Connection, source_work_id: int) -> list[dict[str, object]]:
    return get_work_specifications(connection, source_work_id)


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


def _header_mapping(header: list[str]) -> dict[str, int]:
    normalized = {
        index: "".join(ch.lower() for ch in value if ch.isalnum() or ch.isspace()).strip().replace(" ", "")
        for index, value in enumerate(header)
    }
    aliases = {
        "component_type": {"тип", "componenttype", "type"},
        "component_name": {"наименование", "name", "componentname"},
        "material_code": {"код", "артикул", "materialcode", "code"},
        "unit_name": {"едизм", "едизм.", "едизмения", "едизмерения", "unit"},
        "consumption_rate": {"норма", "consumptionrate", "rate"},
        "unit_price": {"цена", "unitprice", "price"},
        "total_cost": {"сумма", "total", "totalcost"},
    }
    result: dict[str, int] = {}
    for index, value in normalized.items():
        for target, candidates in aliases.items():
            if value in candidates:
                result[target] = index
                break
    return result


def _parse_import_rows(connection: sqlite3.Connection, rows: list[list[str]]) -> ImportPreviewResponse:
    """
    Parse import rows with unit status detection and normalization warnings.
    
    Args:
        connection: Database connection for unit lookup
        rows: Excel rows (first row is header)
        
    Returns:
        ImportPreviewResponse with unit status and warnings
    """
    if not rows:
        raise HTTPException(status_code=400, detail="The import file is empty")

    header_map = _header_mapping(rows[0])
    required_fields = {"component_type", "component_name", "unit_name", "consumption_rate", "unit_price"}
    missing = sorted(required_fields - set(header_map))
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(missing)}")

    preview_rows: list[ImportedSpecificationRow] = []
    missing_materials_by_key: dict[str, MissingImportedMaterial] = {}
    valid_count = 0
    for source_index, row in enumerate(rows[1:], start=2):
        item = ImportedSpecificationRow(source_row=source_index)
        item.component_type = row[header_map["component_type"]].strip() if len(row) > header_map["component_type"] else None
        item.component_name = row[header_map["component_name"]].strip() if len(row) > header_map["component_name"] else None
        item.material_code = (
            row[header_map["material_code"]].strip() if "material_code" in header_map and len(row) > header_map["material_code"] else None
        ) or None
        
        # Extract and normalize unit name
        raw_unit_name = row[header_map["unit_name"]].strip() if len(row) > header_map["unit_name"] else None
        
        # NEW: Detect unit status and add normalization warnings
        if raw_unit_name:
            normalized_unit = _normalize_unit_name(raw_unit_name)
            
            # Check if unit exists in database
            existing_unit = _find_preferred_unit_by_normalized_name(connection, normalized_unit)
            
            if existing_unit:
                # Will reuse existing unit
                item.unit_name = normalized_unit
                item.unit_id = existing_unit["id"]
                item.unit_status = "existing"
            else:
                # Will create new unit
                item.unit_name = normalized_unit
                item.unit_id = None
                item.unit_status = "new"
            
            # Show normalization warning if changed
            if raw_unit_name != normalized_unit:
                item.warnings.append(
                    f"Единица измерения нормализована: '{raw_unit_name}' → '{normalized_unit}'"
                )
        else:
            item.unit_name = None

        raw_rate = row[header_map["consumption_rate"]].strip() if len(row) > header_map["consumption_rate"] else ""
        raw_price = row[header_map["unit_price"]].strip() if len(row) > header_map["unit_price"] else ""
        try:
            item.consumption_rate = float(raw_rate.replace(",", "."))
        except ValueError:
            item.errors.append("Некорректная норма расхода")
        try:
            item.unit_price = float(raw_price.replace(",", "."))
        except ValueError:
            item.errors.append("Некорректная цена")

        if not item.component_type:
            item.errors.append("Не указан тип компонента")
        elif item.component_type:
            try:
                item.component_type = _normalize_component_type(item.component_type)
            except HTTPException:
                item.errors.append("Неизвестный тип компонента")
        if not item.component_name:
            item.errors.append("Не указано наименование")
        if not item.unit_name:
            item.errors.append("Не указана единица измерения")
        if item.consumption_rate is not None and item.consumption_rate <= 0:
            item.errors.append("Норма расхода должна быть больше нуля")
        if item.unit_price is not None and item.unit_price < 0:
            item.errors.append("Цена должна быть не меньше нуля")

        if item.consumption_rate is not None and item.unit_price is not None:
            item.total_cost = round(item.consumption_rate * item.unit_price, 2)

        if item.component_type == "Material" and item.component_name:
            material = _find_material_by_code_or_name(
                connection,
                material_code=item.material_code,
                material_name=item.component_name,
            )
            if material is not None:
                item.material_id = int(material["id"])
                item.material_status = "existing"
                item.matched_material_name = str(material.get("name") or "")
                item.matched_material_code = str(material.get("code") or "") or None
                material_unit_name = str(material.get("unit_name") or "").strip() or None
                material_unit_id = int(material["unit_id"]) if material.get("unit_id") is not None else None
                if not item.unit_name and material_unit_name:
                    item.unit_name = material_unit_name
                    item.unit_id = material_unit_id
                    item.unit_status = "existing" if material_unit_id is not None else item.unit_status
                elif item.unit_name and material_unit_name and _normalize_unit_name(item.unit_name) != _normalize_unit_name(material_unit_name):
                    item.warnings.append(
                        f"Единица в файле ('{item.unit_name}') не совпадает с единицей материала в справочнике ('{material_unit_name}')"
                    )
            else:
                item.material_status = "new"
                if item.unit_name and item.unit_price is not None:
                    _register_missing_material(
                        missing_materials_by_key,
                        source_row=source_index,
                        material_name=item.component_name,
                        material_code=item.material_code,
                        unit_name=item.unit_name,
                        unit_id=item.unit_id,
                        unit_status=item.unit_status,
                        unit_price=float(item.unit_price or 0),
                    )

        if not item.errors:
            valid_count += 1
        preview_rows.append(item)

    return ImportPreviewResponse(
        rows=preview_rows,
        valid_count=valid_count,
        error_count=sum(1 for row in preview_rows if row.errors),
        missing_materials=list(missing_materials_by_key.values()),
    )


def preview_work_specification_import(connection: sqlite3.Connection, filename: str, content: bytes) -> dict[str, object]:
    """
    Preview work specification import with unit status detection.
    
    Args:
        connection: Database connection for unit lookup
        filename: Name of uploaded file
        content: File content bytes
        
    Returns:
        Import preview with unit status and warnings
    """
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        rows = _extract_rows_from_xlsx(content)
    elif lower.endswith(".xls"):
        rows = _extract_rows_from_spreadsheet_xml(content)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .xlsx or .xls")
    return _parse_import_rows(connection, rows).model_dump()


def create_materials_from_import_preview(
    connection: sqlite3.Connection,
    payload: ImportMaterialCreateRequest,
) -> dict[str, object]:
    created_count = 0
    reused_count = 0
    results: list[ImportMaterialCreateResult] = []
    new_materials_folder_id: int | None = None

    for item in payload.materials:
        existing = _find_material_by_code_or_name(
            connection,
            material_code=item.material_code,
            material_name=item.material_name,
        )
        if existing is not None:
            reused_count += 1
            results.append(
                ImportMaterialCreateResult(
                    material_id=int(existing["id"]),
                    material_name=str(existing.get("name") or item.material_name),
                    material_code=str(existing.get("code") or "") or None,
                    unit_id=int(existing["unit_id"]) if existing.get("unit_id") is not None else None,
                    unit_name=str(existing.get("unit_name") or "") or None,
                    price=round(float(existing.get("price") or 0), 2),
                    status="reused",
                    source_row_numbers=item.source_row_numbers,
                )
            )
            continue

        resolved_unit_id = _resolve_unit_id(connection, item.unit_id, item.unit_name)
        resolved_unit = _require_unit(connection, resolved_unit_id) if resolved_unit_id is not None else None
        if new_materials_folder_id is None:
            new_materials_folder_id = ensure_new_materials_folder(connection)
        timestamp = _utcnow()
        material_uuid = new_uuid()
        connection.execute(
            """
            INSERT INTO materials (
                code, name, unit_id, price, parent_id, is_group,
                marked_for_deletion, created_at, modified_at, uuid, updated_at, is_deleted
            ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, 0)
            """,
            (
                (item.material_code or "").strip() or None,
                item.material_name.strip(),
                resolved_unit_id,
                round(float(item.unit_price or 0), 2),
                new_materials_folder_id,
                timestamp,
                timestamp,
                material_uuid,
                timestamp,
            ),
        )
        material_id = last_insert_id(connection)
        register_sync_change(connection, entity_type="materials", entity_uuid=material_uuid, operation="INSERT")
        created_count += 1
        results.append(
            ImportMaterialCreateResult(
                material_id=material_id,
                material_name=item.material_name.strip(),
                material_code=(item.material_code or "").strip() or None,
                unit_id=resolved_unit_id,
                unit_name=str(resolved_unit.get("name") or "") if resolved_unit is not None else None,
                price=round(float(item.unit_price or 0), 2),
                status="created",
                source_row_numbers=item.source_row_numbers,
            )
        )

    connection.commit()
    return ImportMaterialCreateResponse(
        created_count=created_count,
        reused_count=reused_count,
        materials=results,
    ).model_dump()


def export_work_specifications(connection: sqlite3.Connection, work_id: int) -> bytes:
    work = _require_work(connection, work_id)
    specifications = get_work_specifications(connection, work_id)
    totals_by_type = {
        component_type: round(sum(row["total_cost"] for row in specifications if row["component_type"] == component_type), 2)
        for component_type in sorted(COMPONENT_TYPES)
    }
    total_cost = round(sum(row["total_cost"] for row in specifications), 2)

    rows = [
        ["Карточка работы", str(work["name"]), "", "", "", ""],
        ["Код работы", str(work.get("code") or ""), "", "", "", ""],
        ["Единица работы", str(work.get("unit") or ""), "", "", "", ""],
        ["Итоговая стоимость", "", "", "", "", str(total_cost)],
        ["", "", "", "", "", ""],
    ]
    for row in specifications:
        rows.append(
            [
                str(row["component_type"]),
                str(row["component_name"]),
                str(row.get("unit_name") or ""),
                str(row["consumption_rate"]),
                str(row["unit_price"]),
                str(row["total_cost"]),
            ]
        )
    rows.append(["", "", "", "", "", ""])
    rows.append(["Подитоги по типам", "", "", "", "", ""])
    for component_type, total in totals_by_type.items():
        rows.append([component_type, "", "", "", "", str(total)])
    rows.append(["Итого", "", "", "", "", str(total_cost)])
    return build_excel_xml(
        "WorkSpecification",
        ["Раздел", "Наименование", "Ед. изм.", "Норма", "Цена", "Сумма"],
        rows,
    )


def export_flagged_work_specifications(
    connection: sqlite3.Connection,
    review_status: str = "incorrect",
) -> bytes:
    normalized_status = _normalize_review_status(review_status)
    rows = connection.execute(
        """
        SELECT
            w.id AS work_id,
            w.uuid AS work_uuid,
            w.code AS work_code,
            w.name AS work_name,
            w.unit AS work_unit,
            w.updated_at AS work_updated_at,
            COALESCE(w.specification_review_status, 'ok') AS specification_review_status,
            COALESCE(w.specification_review_note, '') AS specification_review_note,
            ws.id AS spec_id,
            ws.uuid AS spec_uuid,
            ws.component_type,
            ws.component_name,
            ws.unit_id,
            u.name AS unit_name,
            ws.material_id,
            m.code AS material_code,
            ws.consumption_rate,
            ws.unit_price
        FROM works w
        LEFT JOIN work_specifications ws
            ON ws.work_id = w.id
           AND COALESCE(ws.marked_for_deletion, 0) = 0
           AND COALESCE(ws.is_deleted, 0) = 0
        LEFT JOIN units u ON u.id = ws.unit_id
        LEFT JOIN materials m ON m.id = ws.material_id
        WHERE w.marked_for_deletion = 0
          AND COALESCE(w.is_deleted, 0) = 0
          AND COALESCE(w.specification_review_status, 'ok') = ?
        ORDER BY w.code COLLATE NOCASE ASC, w.name COLLATE NOCASE ASC, ws.id ASC
        """,
        (normalized_status,),
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="No works found for the selected review status")

    export_rows: list[list[str]] = []
    for row in rows:
        issue_flags = []
        if row["spec_id"] is None:
            issue_flags = ["no_specifications"]
        else:
            issue_flags = _build_issue_flags(
                component_type=row["component_type"],
                material_id=row["material_id"],
                unit_id=row["unit_id"],
                component_name=row["component_name"],
            )

        total_cost = ""
        if row["spec_id"] is not None:
            total_cost = str(
                round(float(row["consumption_rate"] or 0) * float(row["unit_price"] or 0), 2)
            )

        export_rows.append(
            [
                str(row["specification_review_status"] or "ok"),
                str(row["specification_review_note"] or ""),
                str(row["work_code"] or ""),
                str(row["work_name"] or ""),
                str(row["work_unit"] or ""),
                str(row["work_id"] or ""),
                str(row["work_uuid"] or ""),
                str(row["work_updated_at"] or ""),
                str(row["spec_id"] or ""),
                str(row["spec_uuid"] or ""),
                str(row["component_type"] or ""),
                str(row["material_code"] or ""),
                str(row["component_name"] or ""),
                str(row["unit_name"] or ""),
                str(row["consumption_rate"] or ""),
                str(row["unit_price"] or ""),
                total_cost,
                ",".join(issue_flags),
            ]
        )

    return build_excel_xml(
        "FlaggedWorkSpecifications",
        [
            "Статус проверки",
            "Комментарий",
            "Код работы",
            "Наименование работы",
            "Ед. работы",
            "Work ID",
            "Work UUID",
            "Обновлено",
            "Spec ID",
            "Spec UUID",
            "Тип",
            "Код материала",
            "Наименование",
            "Ед. изм.",
            "Норма",
            "Цена",
            "Сумма",
            "Флаги",
        ],
        export_rows,
    )


def mark_works_with_import_issues(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT
            w.id,
            w.uuid,
            SUM(CASE WHEN ws.material_id IS NULL THEN 1 ELSE 0 END) AS missing_materials,
            SUM(CASE WHEN ws.component_type = 'Material' AND ws.material_id IS NULL THEN 1 ELSE 0 END) AS missing_material_rows,
            SUM(CASE WHEN ws.unit_id IS NULL THEN 1 ELSE 0 END) AS missing_units
        FROM works w
        JOIN work_specifications ws
            ON ws.work_id = w.id
           AND COALESCE(ws.marked_for_deletion, 0) = 0
           AND COALESCE(ws.is_deleted, 0) = 0
        WHERE w.marked_for_deletion = 0
          AND COALESCE(w.is_deleted, 0) = 0
        GROUP BY w.id, w.uuid
        HAVING missing_material_rows > 0 OR missing_units > 0
        """
    ).fetchall()

    now = _utcnow()
    marked_count = 0
    for row in rows:
        note_parts: list[str] = []
        if int(row["missing_material_rows"] or 0) > 0:
            note_parts.append(f"строк-материалов без материала: {int(row['missing_material_rows'])}")
        if int(row["missing_units"] or 0) > 0:
            note_parts.append(f"строк без единицы: {int(row['missing_units'])}")
        connection.execute(
            """
            UPDATE works
            SET specification_review_status = 'incorrect',
                specification_review_note = ?,
                modified_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            ("; ".join(note_parts) or "Импортированная спецификация требует проверки", now, now, int(row["id"])),
        )
        register_sync_change(connection, entity_type="works", entity_uuid=str(row["uuid"]), operation="UPDATE")
        marked_count += 1

    connection.commit()
    return {"marked_count": marked_count}


def _correction_header_mapping(header: list[str]) -> dict[str, int]:
    normalized = {
        index: "".join(ch.lower() for ch in value if ch.isalnum() or ch.isspace()).strip().replace(" ", "")
        for index, value in enumerate(header)
    }
    aliases = {
        "review_status": {"статуспроверки", "reviewstatus", "status"},
        "review_note": {"комментарий", "примечание", "reviewnote", "note"},
        "work_code": {"кодработы", "workcode"},
        "work_name": {"наименованиеработы", "workname"},
        "work_unit": {"едработы", "workunit"},
        "work_id": {"workid", "идработы", "работаid"},
        "work_uuid": {"workuuid", "uuidработы"},
        "work_updated_at": {"обновлено", "workupdatedat", "updatedat"},
        "spec_id": {"specid", "идстроки", "строкаid"},
        "spec_uuid": {"specuuid", "uuidстроки"},
        "component_type": {"тип", "componenttype", "type"},
        "material_code": {"кодматериала", "materialcode", "материалкод"},
        "component_name": {"наименование", "name", "componentname"},
        "unit_name": {"едизм", "едизм.", "едизмерения", "единицаизмерения", "unit"},
        "consumption_rate": {"норма", "consumptionrate", "rate"},
        "unit_price": {"цена", "unitprice", "price"},
        "total_cost": {"сумма", "total", "totalcost"},
        "issue_flags": {"флаги", "issueflags"},
    }
    result: dict[str, int] = {}
    for index, value in normalized.items():
        for target, candidates in aliases.items():
            if value in candidates:
                result[target] = index
                break
    return result


def _cell_value(row: list[str], mapping: dict[str, int], key: str) -> str:
    if key not in mapping:
        return ""
    index = mapping[key]
    if index >= len(row):
        return ""
    return row[index].strip()


def import_work_specification_corrections(
    connection: sqlite3.Connection,
    filename: str,
    content: bytes,
) -> dict[str, object]:
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        rows = _extract_rows_from_xlsx(content)
    elif lower.endswith(".xls"):
        rows = _extract_rows_from_spreadsheet_xml(content)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .xlsx or .xls")

    if not rows:
        raise HTTPException(status_code=400, detail="The correction file is empty")

    header_map = _correction_header_mapping(rows[0])
    required_fields = {"work_id", "work_uuid", "component_type", "component_name", "unit_name", "consumption_rate", "unit_price"}
    if not ({"work_id", "work_uuid"} & set(header_map)):
        raise HTTPException(status_code=400, detail="Missing required columns: work_id or work_uuid")
    missing = sorted((required_fields - {"work_id", "work_uuid"}) - set(header_map))
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(missing)}")

    grouped_specs: dict[int, list[dict[str, object]]] = {}
    work_rows: dict[int, int] = {}
    work_meta: dict[int, dict[str, object]] = {}
    errors: list[str] = []

    for source_index, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue

        work_uuid = _cell_value(row, header_map, "work_uuid")
        work_id_raw = _cell_value(row, header_map, "work_id")
        work: dict[str, object] | None = None
        try:
            if work_uuid:
                work = get_work_by_uuid(connection, work_uuid)
            elif work_id_raw:
                work = get_work_detail(connection, int(work_id_raw))
        except (HTTPException, ValueError):
            work = None

        if work is None:
            errors.append(f"Строка {source_index}: работа не найдена по work_id/work_uuid")
            continue

        component_type_value = _cell_value(row, header_map, "component_type")
        component_name_value = _cell_value(row, header_map, "component_name")
        unit_name_value = _cell_value(row, header_map, "unit_name")
        rate_raw = _cell_value(row, header_map, "consumption_rate")
        price_raw = _cell_value(row, header_map, "unit_price")

        if not any((component_type_value, component_name_value, unit_name_value, rate_raw, price_raw)):
            continue

        try:
            component_type = _normalize_component_type(component_type_value)
        except HTTPException:
            errors.append(f"Строка {source_index}: неизвестный тип компонента")
            continue

        try:
            consumption_rate = float(rate_raw.replace(",", "."))
        except ValueError:
            errors.append(f"Строка {source_index}: некорректная норма расхода")
            continue
        try:
            unit_price = float(price_raw.replace(",", "."))
        except ValueError:
            errors.append(f"Строка {source_index}: некорректная цена")
            continue

        if consumption_rate <= 0:
            errors.append(f"Строка {source_index}: норма расхода должна быть больше нуля")
            continue
        if unit_price < 0:
            errors.append(f"Строка {source_index}: цена должна быть не меньше нуля")
            continue

        material_id: int | None = None
        material_code_value = _cell_value(row, header_map, "material_code") or None
        if component_type == "Material":
            material = _find_material_by_code_or_name(
                connection,
                material_code=material_code_value,
                material_name=component_name_value,
            )
            if material is None:
                errors.append(
                    f"Строка {source_index}: материал '{component_name_value}' не найден в справочнике"
                )
                continue
            material_id = int(material["id"])
            component_name_value = str(material.get("name") or component_name_value).strip()
            unit_name_value = str(material.get("unit_name") or unit_name_value).strip()

        spec_payload = {
            "id": int(_cell_value(row, header_map, "spec_id")) if _cell_value(row, header_map, "spec_id") else None,
            "uuid": _cell_value(row, header_map, "spec_uuid") or None,
            "component_type": component_type,
            "component_name": component_name_value.strip(),
            "unit_name": unit_name_value.strip(),
            "consumption_rate": consumption_rate,
            "unit_price": unit_price,
            "material_id": material_id,
        }

        if not spec_payload["component_name"]:
            errors.append(f"Строка {source_index}: не указано наименование компонента")
            continue
        if not spec_payload["unit_name"]:
            errors.append(f"Строка {source_index}: не указана единица измерения")
            continue

        grouped_specs.setdefault(int(work["id"]), []).append(spec_payload)
        work_rows[int(work["id"])] = work_rows.get(int(work["id"]), 0) + 1
        work_meta[int(work["id"])] = work

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors[:20]))
    if not grouped_specs:
        raise HTTPException(status_code=400, detail="The correction file does not contain importable specification rows")

    now = _utcnow()
    updated_works: list[WorkCorrectionImportWorkResult] = []
    updated_specification_count = 0

    for work_id, specs in grouped_specs.items():
        saved_specs = _sync_specifications(connection, work_id=work_id, specifications=specs)
        work = work_meta[work_id]
        connection.execute(
            """
            UPDATE works
            SET specification_review_status = 'corrected',
                specification_review_note = ?,
                modified_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (f"Исправлено импортом спецификации {now}", now, now, work_id),
        )
        register_sync_change(connection, entity_type="works", entity_uuid=str(work["uuid"]), operation="UPDATE")
        updated_specification_count += len(saved_specs)
        updated_works.append(
            WorkCorrectionImportWorkResult(
                work_id=work_id,
                work_uuid=str(work.get("uuid") or "") or None,
                work_code=str(work.get("code") or "") or None,
                work_name=str(work.get("name") or ""),
                row_count=work_rows.get(work_id, 0),
                specification_count=len(saved_specs),
                specification_review_status="corrected",
            )
        )

    connection.commit()
    return WorkCorrectionImportResponse(
        updated_work_count=len(updated_works),
        updated_specification_count=updated_specification_count,
        works=updated_works,
    ).model_dump()
