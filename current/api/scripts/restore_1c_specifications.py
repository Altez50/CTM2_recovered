from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.work_services import _normalize_unit_name


DEFAULT_SOURCE_DB = PROJECT_ROOT.parent / "CTM" / "backups" / "backup_20251230_144402" / "construction.db"
DEFAULT_TARGET_DB = PROJECT_ROOT / "construction.db"


LEGACY_UNIT_NAME_MAP = {
    "m2": "м²",
    "m3": "м³",
    "kg": "кг",
    "час": "ч",
    "м.п.": "м",
    "мп": "м",
    "пм": "м",
    "тн": "т",
}


def canonical_target_name_for_source(name: str | None) -> str | None:
    raw_name = (name or "").strip()
    if not raw_name:
        return None
    return LEGACY_UNIT_NAME_MAP.get(raw_name.lower(), raw_name)


def is_placeholder_unit_name(name: str | None) -> bool:
    value = (name or "").strip()
    return value.startswith("Ед. изм.") or value.startswith("Ед. ")


@dataclass
class RestoreStats:
    backup_path: Path | None = None
    inserted_works: int = 0
    inserted_units: int = 0
    updated_units: int = 0
    inserted_placeholder_units: int = 0
    inserted_materials: int = 0
    updated_materials: int = 0
    inserted_specs: int = 0
    updated_specs: int = 0
    skipped_specs_missing_work: int = 0
    skipped_orphan_work_ids: int = 0
    remapped_unit_ids: int = 0


class RestoreContext:
    def __init__(self, source_connection: sqlite3.Connection, target_connection: sqlite3.Connection) -> None:
        self.source = source_connection
        self.target = target_connection
        self.stats = RestoreStats()

        self.target_units_by_id: dict[int, dict[str, object]] = {}
        self.target_units_by_exact_name: dict[str, int] = {}
        self.target_units_by_normalized_name: dict[str, int] = {}
        self.source_units_by_id = {
            int(row["id"]): dict(row)
            for row in self.source.execute("SELECT id, name, description FROM units").fetchall()
        }
        self.refresh_target_unit_indexes()

    def refresh_target_unit_indexes(self) -> None:
        self.target_units_by_id.clear()
        self.target_units_by_exact_name.clear()
        self.target_units_by_normalized_name.clear()
        for row in self.target.execute(
            "SELECT id, name, short_name, marked_for_deletion, created_at FROM units ORDER BY id"
        ).fetchall():
            item = dict(row)
            unit_id = int(item["id"])
            name = str(item.get("name") or "")
            self.target_units_by_id[unit_id] = item
            if name and name not in self.target_units_by_exact_name:
                self.target_units_by_exact_name[name] = unit_id
            normalized_name = _normalize_unit_name(name) if name else ""
            if normalized_name and normalized_name not in self.target_units_by_normalized_name:
                self.target_units_by_normalized_name[normalized_name] = unit_id

    def lookup_existing_target_unit(self, candidate_name: str | None) -> int | None:
        if not candidate_name:
            return None
        if candidate_name in self.target_units_by_exact_name:
            return self.target_units_by_exact_name[candidate_name]
        normalized_name = _normalize_unit_name(candidate_name)
        if normalized_name and normalized_name in self.target_units_by_normalized_name:
            return self.target_units_by_normalized_name[normalized_name]
        return None

    def ensure_placeholder_unit(self, unit_id: int) -> int:
        existing = self.target_units_by_id.get(unit_id)
        if existing is not None:
            return unit_id

        placeholder_name = f"Ед. изм. {unit_id}"
        self.target.execute(
            """
            INSERT INTO units (id, name, short_name, marked_for_deletion, created_at)
            VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP)
            """,
            (unit_id, placeholder_name, f"Ед. {unit_id}"),
        )
        self.stats.inserted_placeholder_units += 1
        self.refresh_target_unit_indexes()
        return unit_id

    def resolve_unit_reference(self, source_unit_id: int | None) -> int | None:
        if source_unit_id in (None, 0):
            return None

        unit_id = int(source_unit_id)
        source_unit = self.source_units_by_id.get(unit_id)
        if source_unit is None:
            return self.ensure_placeholder_unit(unit_id)

        target_row = self.target_units_by_id.get(unit_id)
        source_name = str(source_unit.get("name") or "").strip()
        preferred_target_name = canonical_target_name_for_source(source_name)
        existing_target_id = self.lookup_existing_target_unit(preferred_target_name or source_name)

        if target_row is None:
            if existing_target_id is not None:
                if existing_target_id != unit_id:
                    self.stats.remapped_unit_ids += 1
                return existing_target_id

            self.target.execute(
                """
                INSERT INTO units (id, name, short_name, marked_for_deletion, created_at)
                VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                """,
                (
                    unit_id,
                    source_name or f"Ед. изм. {unit_id}",
                    source_name or f"Ед. {unit_id}",
                    int(source_unit.get("marked_for_deletion") or 0),
                    source_unit.get("created_at"),
                ),
            )
            self.stats.inserted_units += 1
            self.refresh_target_unit_indexes()
            return unit_id

        target_name = str(target_row.get("name") or "").strip()
        if is_placeholder_unit_name(target_name):
            if existing_target_id is not None and existing_target_id != unit_id:
                self.stats.remapped_unit_ids += 1
                return existing_target_id

            replacement_name = source_name or target_name
            replacement_short_name = replacement_name
            self.target.execute(
                "UPDATE units SET name = ?, short_name = ? WHERE id = ?",
                (replacement_name, replacement_short_name, unit_id),
            )
            self.stats.updated_units += 1
            self.refresh_target_unit_indexes()
            return unit_id

        if source_name == target_name:
            return unit_id

        if existing_target_id is not None:
            if existing_target_id != unit_id:
                self.stats.remapped_unit_ids += 1
            return existing_target_id

        # Fall back to the source ID if there is no better semantic match.
        self.target.execute(
            "UPDATE units SET name = ?, short_name = ? WHERE id = ?",
            (source_name or target_name, source_name or target_name, unit_id),
        )
        self.stats.updated_units += 1
        self.refresh_target_unit_indexes()
        return unit_id


def ensure_missing_works(context: RestoreContext) -> set[int]:
    target_work_ids = {int(row["id"]) for row in context.target.execute("SELECT id FROM works").fetchall()}
    required_work_ids = {
        int(row["work_id"])
        for row in context.source.execute("SELECT DISTINCT work_id FROM work_specifications").fetchall()
    }
    missing_work_ids = sorted(required_work_ids - target_work_ids)
    source_work_rows = {
        int(row["id"]): dict(row)
        for row in context.source.execute("SELECT * FROM works").fetchall()
    }

    for work_id in missing_work_ids:
        source_row = source_work_rows.get(work_id)
        if source_row is None:
            context.stats.skipped_orphan_work_ids += 1
            continue

        unit_name = None
        source_unit_id = source_row.get("unit_id")
        if source_unit_id not in (None, 0):
            source_unit = context.source_units_by_id.get(int(source_unit_id))
            if source_unit is not None:
                unit_name = str(source_unit.get("name") or "").strip() or None
            else:
                unit_name = f"Ед. изм. {source_unit_id}"

        context.target.execute(
            """
            INSERT INTO works (
                id,
                name,
                code,
                unit,
                price,
                labor_rate,
                parent_id,
                marked_for_deletion,
                is_group
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_id,
                source_row.get("name"),
                source_row.get("code"),
                canonical_target_name_for_source(unit_name) or unit_name,
                float(source_row.get("price") or 0),
                float(source_row.get("labor_rate") or 0),
                source_row.get("parent_id"),
                int(source_row.get("marked_for_deletion") or 0),
                int(source_row.get("is_group") or 0),
            ),
        )
        context.stats.inserted_works += 1

    return {int(row["id"]) for row in context.target.execute("SELECT id FROM works").fetchall()}


def import_materials(context: RestoreContext) -> None:
    for source_row in context.source.execute("SELECT * FROM materials ORDER BY id").fetchall():
        item = dict(source_row)
        material_id = int(item["id"])
        mapped_unit_id = context.resolve_unit_reference(item.get("unit_id"))
        material_name = str(item.get("description") or "").strip() or f"Материал {material_id}"

        existing = context.target.execute(
            "SELECT 1 FROM materials WHERE id = ?",
            (material_id,),
        ).fetchone()
        if existing is None:
            context.target.execute(
                """
                INSERT INTO materials (
                    id,
                    code,
                    name,
                    unit_id,
                    price,
                    marked_for_deletion,
                    created_at,
                    modified_at
                )
                VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), COALESCE(?, CURRENT_TIMESTAMP))
                """,
                (
                    material_id,
                    item.get("code"),
                    material_name,
                    mapped_unit_id,
                    float(item.get("price") or 0),
                    int(item.get("marked_for_deletion") or 0),
                    item.get("created_at"),
                    item.get("modified_at"),
                ),
            )
            context.stats.inserted_materials += 1
            continue

        context.target.execute(
            """
            UPDATE materials
            SET code = ?,
                name = ?,
                unit_id = ?,
                price = ?,
                marked_for_deletion = ?,
                modified_at = COALESCE(?, modified_at)
            WHERE id = ?
            """,
            (
                item.get("code"),
                material_name,
                mapped_unit_id,
                float(item.get("price") or 0),
                int(item.get("marked_for_deletion") or 0),
                item.get("modified_at"),
                material_id,
            ),
        )
        context.stats.updated_materials += 1


def import_specifications(context: RestoreContext, available_work_ids: set[int]) -> None:
    for source_row in context.source.execute("SELECT * FROM work_specifications ORDER BY id").fetchall():
        item = dict(source_row)
        work_id = int(item["work_id"])
        if work_id not in available_work_ids:
            context.stats.skipped_specs_missing_work += 1
            continue

        mapped_unit_id = context.resolve_unit_reference(item.get("unit_id"))
        material_id = item.get("material_id")
        if material_id in (0, "0"):
            material_id = None

        existing = context.target.execute(
            "SELECT 1 FROM work_specifications WHERE id = ?",
            (int(item["id"]),),
        ).fetchone()
        if existing is None:
            context.target.execute(
                """
                INSERT INTO work_specifications (
                    id,
                    work_id,
                    component_type,
                    component_name,
                    unit_id,
                    consumption_rate,
                    unit_price,
                    created_at,
                    modified_at,
                    marked_for_deletion,
                    material_id,
                    uuid,
                    updated_at,
                    is_deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?)
                """,
                (
                    int(item["id"]),
                    work_id,
                    item.get("component_type"),
                    item.get("component_name"),
                    mapped_unit_id,
                    float(item.get("consumption_rate") or 0),
                    float(item.get("unit_price") or 0),
                    item.get("created_at"),
                    item.get("modified_at"),
                    int(item.get("marked_for_deletion") or 0),
                    material_id,
                    item.get("uuid"),
                    item.get("updated_at"),
                    int(item.get("is_deleted") or 0),
                ),
            )
            context.stats.inserted_specs += 1
            continue

        context.target.execute(
            """
            UPDATE work_specifications
            SET work_id = ?,
                component_type = ?,
                component_name = ?,
                unit_id = ?,
                consumption_rate = ?,
                unit_price = ?,
                modified_at = COALESCE(?, modified_at),
                marked_for_deletion = ?,
                material_id = ?,
                uuid = ?,
                updated_at = COALESCE(?, updated_at),
                is_deleted = ?
            WHERE id = ?
            """,
            (
                work_id,
                item.get("component_type"),
                item.get("component_name"),
                mapped_unit_id,
                float(item.get("consumption_rate") or 0),
                float(item.get("unit_price") or 0),
                item.get("modified_at"),
                int(item.get("marked_for_deletion") or 0),
                material_id,
                item.get("uuid"),
                item.get("updated_at"),
                int(item.get("is_deleted") or 0),
                int(item["id"]),
            ),
        )
        context.stats.updated_specs += 1


def create_backup(target_db: Path) -> Path:
    backup_dir = PROJECT_ROOT / "db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{target_db.stem}.before_1c_specs_restore_{timestamp}{target_db.suffix}"
    shutil.copy2(target_db, backup_path)
    return backup_path


def summarize(target_connection: sqlite3.Connection) -> list[str]:
    spec_count = int(target_connection.execute("SELECT COUNT(*) FROM work_specifications").fetchone()[0])
    works_with_specs = int(
        target_connection.execute("SELECT COUNT(DISTINCT work_id) FROM work_specifications").fetchone()[0]
    )
    material_count = int(target_connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0])
    unit_count = int(target_connection.execute("SELECT COUNT(*) FROM units").fetchone()[0])
    return [
        f"work_specifications={spec_count}",
        f"works_with_specs={works_with_specs}",
        f"materials={material_count}",
        f"units={unit_count}",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore 1C specifications into the current CTM2 database.")
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB)
    parser.add_argument("--apply", action="store_true", help="Apply changes to the target DB.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    source_db = args.source_db.resolve()
    target_db = args.target_db.resolve()
    if not source_db.exists():
        raise SystemExit(f"Source DB not found: {source_db}")
    if not target_db.exists():
        raise SystemExit(f"Target DB not found: {target_db}")

    if not args.apply:
        src = sqlite3.connect(source_db)
        dst = sqlite3.connect(target_db)
        src.row_factory = sqlite3.Row
        dst.row_factory = sqlite3.Row
        try:
            context = RestoreContext(src, dst)
            available_work_ids = ensure_missing_works(context)
            import_materials(context)
            import_specifications(context, available_work_ids)
            print("DRY RUN")
            print(f"source={source_db}")
            print(f"target={target_db}")
            print(
                f"would insert works={context.stats.inserted_works}, units={context.stats.inserted_units}, "
                f"placeholder_units={context.stats.inserted_placeholder_units}, materials={context.stats.inserted_materials}, "
                f"specs={context.stats.inserted_specs}"
            )
            print(
                f"would update units={context.stats.updated_units}, materials={context.stats.updated_materials}, "
                f"specs={context.stats.updated_specs}, remapped_unit_ids={context.stats.remapped_unit_ids}"
            )
            print(
                f"would skip specs_missing_work={context.stats.skipped_specs_missing_work}, "
                f"orphan_work_ids={context.stats.skipped_orphan_work_ids}"
            )
            dst.rollback()
        finally:
            dst.close()
            src.close()
        return 0

    backup_path = create_backup(target_db)
    src = sqlite3.connect(source_db)
    dst = sqlite3.connect(target_db)
    src.row_factory = sqlite3.Row
    dst.row_factory = sqlite3.Row
    dst.execute("PRAGMA foreign_keys = ON")
    try:
        context = RestoreContext(src, dst)
        context.stats.backup_path = backup_path
        with dst:
            available_work_ids = ensure_missing_works(context)
            import_materials(context)
            import_specifications(context, available_work_ids)

        print("APPLIED")
        print(f"backup={backup_path}")
        print(
            f"inserted works={context.stats.inserted_works}, units={context.stats.inserted_units}, "
            f"placeholder_units={context.stats.inserted_placeholder_units}, materials={context.stats.inserted_materials}, "
            f"specs={context.stats.inserted_specs}"
        )
        print(
            f"updated units={context.stats.updated_units}, materials={context.stats.updated_materials}, "
            f"specs={context.stats.updated_specs}, remapped_unit_ids={context.stats.remapped_unit_ids}"
        )
        print(
            f"skipped specs_missing_work={context.stats.skipped_specs_missing_work}, "
            f"orphan_work_ids={context.stats.skipped_orphan_work_ids}"
        )
        print("summary:", ", ".join(summarize(dst)))
    finally:
        dst.close()
        src.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
