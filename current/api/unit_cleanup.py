from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from api.database import row_to_dict
from api.work_services import _normalize_unit_name


def get_unit_reference_counts(connection: sqlite3.Connection, unit_id: int) -> dict[str, int]:
    material_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM materials WHERE unit_id = ?",
            (unit_id,),
        ).fetchone()[0]
    )
    specification_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM work_specifications WHERE unit_id = ?",
            (unit_id,),
        ).fetchone()[0]
    )
    return {
        "materials_count": material_count,
        "work_specifications_count": specification_count,
        "reference_count": material_count + specification_count,
    }


def _choose_recommended_target(
    units: list[dict[str, object]],
    normalized_name: str,
) -> dict[str, object]:
    return sorted(
        units,
        key=lambda item: (
            0 if str(item.get("name") or "") == normalized_name else 1,
            -int(item.get("reference_count") or 0),
            int(item.get("id") or 0),
        ),
    )[0]


def _legacy_work_usage_by_normalized_name(connection: sqlite3.Connection) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in connection.execute(
        """
        SELECT unit, COUNT(*) AS reference_count
        FROM works
        WHERE unit IS NOT NULL AND TRIM(unit) != ''
        GROUP BY unit
        ORDER BY COUNT(*) DESC, unit ASC
        """
    ).fetchall():
        normalized_name = _normalize_unit_name(str(row["unit"] or ""))
        if not normalized_name:
            continue
        groups[normalized_name].append(
            {
                "name": str(row["unit"]),
                "reference_count": int(row["reference_count"]),
            }
        )
    return groups


def find_duplicate_unit_groups(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in connection.execute(
        """
        SELECT id, name, short_name
        FROM units
        WHERE marked_for_deletion = 0
        ORDER BY id ASC
        """
    ).fetchall():
        item = row_to_dict(row) or {}
        normalized_name = _normalize_unit_name(str(item.get("name") or ""))
        if not normalized_name:
            continue
        item["normalized_name"] = normalized_name
        item.update(get_unit_reference_counts(connection, int(item["id"])))
        groups[normalized_name].append(item)

    legacy_work_usage = _legacy_work_usage_by_normalized_name(connection)
    results: list[dict[str, Any]] = []
    for normalized_name, units in groups.items():
        if len(units) < 2:
            continue
        recommended_target = _choose_recommended_target(units, normalized_name)
        legacy_units = legacy_work_usage.get(normalized_name, [])
        results.append(
            {
                "normalized_name": normalized_name,
                "unit_count": len(units),
                "units": units,
                "recommended_target": recommended_target,
                "source_unit_ids": [
                    int(unit["id"])
                    for unit in units
                    if int(unit["id"]) != int(recommended_target["id"])
                ],
                "reference_count": sum(int(unit["reference_count"]) for unit in units),
                "legacy_work_reference_count": sum(int(item["reference_count"]) for item in legacy_units),
                "legacy_work_units": legacy_units,
            }
        )

    results.sort(
        key=lambda item: (
            -(int(item["reference_count"]) + int(item["legacy_work_reference_count"])),
            str(item["normalized_name"]),
        )
    )
    return results


def find_duplicate_unit_group(
    connection: sqlite3.Connection,
    normalized_name: str,
) -> dict[str, Any] | None:
    target_name = _normalize_unit_name(normalized_name)
    for group in find_duplicate_unit_groups(connection):
        if str(group["normalized_name"]) == target_name:
            return group
    return None


def merge_unit_ids(
    connection: sqlite3.Connection,
    target_unit_id: int,
    source_unit_ids: list[int],
    *,
    dry_run: bool = True,
    canonical_name: str | None = None,
) -> dict[str, Any]:
    target_row = connection.execute(
        """
        SELECT id, name, short_name
        FROM units
        WHERE id = ? AND marked_for_deletion = 0
        """,
        (target_unit_id,),
    ).fetchone()
    if target_row is None:
        raise ValueError(f"Target unit {target_unit_id} not found")

    target = row_to_dict(target_row) or {}
    normalized_names = {_normalize_unit_name(str(target["name"] or ""))}

    source_ids = sorted({int(unit_id) for unit_id in source_unit_ids if int(unit_id) != target_unit_id})
    source_rows = connection.execute(
        f"""
        SELECT id, name, short_name
        FROM units
        WHERE id IN ({",".join("?" for _ in source_ids)}) AND marked_for_deletion = 0
        ORDER BY id ASC
        """,
        tuple(source_ids),
    ).fetchall() if source_ids else []

    if len(source_rows) != len(source_ids):
        found_ids = {int(row["id"]) for row in source_rows}
        missing = [unit_id for unit_id in source_ids if unit_id not in found_ids]
        raise ValueError(f"Source units not found: {missing}")

    sources = [row_to_dict(row) or {} for row in source_rows]
    for source in sources:
        normalized_names.add(_normalize_unit_name(str(source.get("name") or "")))
    if len(normalized_names) != 1:
        raise ValueError("Target and source units do not normalize to the same value")

    normalized_name = normalized_names.pop()
    canonical_name = _normalize_unit_name(canonical_name) if canonical_name else normalized_name

    changes: list[dict[str, Any]] = []
    totals = {"materials_updated": 0, "work_specifications_updated": 0}
    for source in sources:
        counts = get_unit_reference_counts(connection, int(source["id"]))
        changes.append(
            {
                "source_unit": source,
                **counts,
            }
        )
        if dry_run:
            totals["materials_updated"] += counts["materials_count"]
            totals["work_specifications_updated"] += counts["work_specifications_count"]
            continue

        material_updates = connection.execute(
            "UPDATE materials SET unit_id = ? WHERE unit_id = ?",
            (target_unit_id, int(source["id"])),
        ).rowcount
        specification_updates = connection.execute(
            "UPDATE work_specifications SET unit_id = ? WHERE unit_id = ?",
            (target_unit_id, int(source["id"])),
        ).rowcount
        connection.execute(
            "UPDATE units SET marked_for_deletion = 1 WHERE id = ?",
            (int(source["id"]),),
        )
        totals["materials_updated"] += max(material_updates, 0)
        totals["work_specifications_updated"] += max(specification_updates, 0)

    rename_conflict = connection.execute(
        "SELECT id FROM units WHERE name = ? AND id != ? LIMIT 1",
        (canonical_name, target_unit_id),
    ).fetchone()
    can_rename_target = canonical_name != str(target["name"] or "") and rename_conflict is None
    if can_rename_target and not dry_run:
        connection.execute(
            "UPDATE units SET name = ?, short_name = ? WHERE id = ?",
            (canonical_name, canonical_name, target_unit_id),
        )

    return {
        "dry_run": dry_run,
        "normalized_name": normalized_name,
        "canonical_name": canonical_name,
        "target_unit": target,
        "source_unit_ids": source_ids,
        "changes": changes,
        **totals,
        "target_rename": {
            "from": str(target["name"] or ""),
            "to": canonical_name,
            "will_rename": can_rename_target,
            "blocked_by_existing_name": bool(rename_conflict),
        },
    }
