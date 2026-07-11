from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.work_services import _normalize_unit_name


DEFAULT_SOURCE_DB = PROJECT_ROOT.parent / "CTM" / "construction.db"
DEFAULT_TARGET_DB = PROJECT_ROOT / "construction.db"
DEFAULT_GROUP_NAME = "CTM Import / Specs Sample"
DEFAULT_GROUP_CODE = "CTM-SAMPLE-SPECS"
FALLBACK_UNITS_BY_COMPONENT = {
    "Material": "шт",
    "Labor": "ч",
    "Equipment": "ч",
    "Other": "шт",
}
LEGACY_UNIT_NAME_MAP = {
    "m": "м",
    "m2": "м²",
    "m3": "м³",
    "kg": "кг",
    "тн": "т",
    "час": "ч",
    "час.": "ч",
    "чел-час": "чел-час",
    "чел.час": "чел-час",
    "к-т": "к-т",
}
SAMPLE_WORK_IDS = (
    557955638,  # 7 строк, material + labor
    798634500,  # 4 строки, 2 material + 2 labor
    838772647,  # 4 строки, 3 material + 1 labor
    822837105,  # 3 строки, material + labor
    671231691,  # 2 строки, material + labor
)


@dataclass
class ImportStats:
    created_units: int = 0
    created_materials: int = 0
    updated_materials: int = 0
    created_works: int = 0
    updated_works: int = 0
    deleted_existing_specs: int = 0
    inserted_specs: int = 0


class ImportContext:
    def __init__(self, source: sqlite3.Connection, target: sqlite3.Connection) -> None:
        self.source = source
        self.target = target
        self.stats = ImportStats()
        self.source_units: dict[int, dict[str, object]] = {
            int(row["id"]): dict(row)
            for row in self.source.execute("SELECT id, name, description FROM units").fetchall()
        }
        self.source_materials: dict[int, dict[str, object]] = {
            int(row["id"]): dict(row)
            for row in self.source.execute(
                "SELECT id, code, description, price, unit_id, unit FROM materials"
            ).fetchall()
        }
        self.unit_ids_by_name: dict[str, int] = {}
        self.unit_ids_by_normalized_name: dict[str, int] = {}
        self.material_ids_by_code: dict[str, int] = {}
        self.material_ids_by_name: dict[str, int] = {}
        self.refresh_target_indexes()

    def refresh_target_indexes(self) -> None:
        self.unit_ids_by_name.clear()
        self.unit_ids_by_normalized_name.clear()
        self.material_ids_by_code.clear()
        self.material_ids_by_name.clear()

        for row in self.target.execute("SELECT id, name, short_name FROM units WHERE COALESCE(is_deleted, 0) = 0"):
            unit_id = int(row["id"])
            name = str(row["name"] or "").strip()
            short_name = str(row["short_name"] or "").strip()
            if name:
                self.unit_ids_by_name[name.lower()] = unit_id
                normalized = _normalize_unit_name(name)
                if normalized:
                    self.unit_ids_by_normalized_name[normalized] = unit_id
            if short_name:
                self.unit_ids_by_name[short_name.lower()] = unit_id
                normalized = _normalize_unit_name(short_name)
                if normalized:
                    self.unit_ids_by_normalized_name[normalized] = unit_id

        for row in self.target.execute("SELECT id, code, name FROM materials WHERE COALESCE(is_deleted, 0) = 0"):
            material_id = int(row["id"])
            code = str(row["code"] or "").strip()
            name = str(row["name"] or "").strip()
            if code:
                self.material_ids_by_code[code.lower()] = material_id
            if name:
                self.material_ids_by_name[name.lower()] = material_id


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def new_uuid() -> str:
    return str(uuid4())


def create_backup(target_db: Path) -> Path:
    backup_dir = PROJECT_ROOT / "db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{target_db.stem}.before_ctm_sample_specs_{timestamp}{target_db.suffix}"
    shutil.copy2(target_db, backup_path)
    return backup_path


def sanitize_unit_name(raw_value: object | None) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    if any("\u0590" <= char <= "\u05FF" for char in value):
        return None
    mapped = LEGACY_UNIT_NAME_MAP.get(value.lower(), value)
    normalized = _normalize_unit_name(mapped)
    if not normalized:
        return mapped
    if any("\u0590" <= char <= "\u05FF" for char in normalized):
        return None
    return normalized


def source_unit_name(context: ImportContext, unit_id: object | None) -> str | None:
    if unit_id in (None, 0, "0"):
        return None
    row = context.source_units.get(int(unit_id))
    if row is None:
        return None
    return sanitize_unit_name(row.get("name"))


def ensure_unit(context: ImportContext, unit_name: str | None) -> tuple[int | None, str | None]:
    cleaned_name = sanitize_unit_name(unit_name)
    if not cleaned_name:
        return None, None

    by_name = context.unit_ids_by_name.get(cleaned_name.lower())
    if by_name is not None:
        return by_name, cleaned_name

    normalized = _normalize_unit_name(cleaned_name)
    by_normalized = context.unit_ids_by_normalized_name.get(normalized) if normalized else None
    if by_normalized is not None:
        return by_normalized, cleaned_name

    timestamp = now_iso()
    context.target.execute(
        """
        INSERT INTO units (
            name, short_name, marked_for_deletion, created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, 0, ?, ?, ?, ?, 0)
        """,
        (cleaned_name, cleaned_name, timestamp, timestamp, new_uuid(), timestamp),
    )
    context.stats.created_units += 1
    context.refresh_target_indexes()
    return context.unit_ids_by_name[cleaned_name.lower()], cleaned_name


def preferred_spec_unit_name(
    context: ImportContext,
    *,
    source_spec: dict[str, object],
    source_material: dict[str, object] | None,
) -> str | None:
    candidates = [
        source_unit_name(context, source_spec.get("unit_id")),
        source_unit_name(context, source_material.get("unit_id") if source_material else None),
        sanitize_unit_name(source_material.get("unit")) if source_material else None,
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return FALLBACK_UNITS_BY_COMPONENT.get(str(source_spec.get("component_type") or ""), "шт")


def ensure_material(
    context: ImportContext,
    *,
    source_material: dict[str, object],
    fallback_unit_name: str | None,
) -> int:
    name = str(source_material.get("description") or "").strip() or "Материал без названия"
    code = str(source_material.get("code") or "").strip() or None
    unit_name = source_unit_name(context, source_material.get("unit_id")) or fallback_unit_name
    unit_id, _ = ensure_unit(context, unit_name)
    price = round(float(source_material.get("price") or 0), 2)
    timestamp = now_iso()

    material_id = context.material_ids_by_code.get(code.lower()) if code else None
    if material_id is None:
        material_id = context.material_ids_by_name.get(name.lower())

    if material_id is None:
        context.target.execute(
            """
            INSERT INTO materials (
                code, name, unit_id, price, marked_for_deletion, created_at, modified_at, uuid, updated_at, is_deleted
            )
            VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, 0)
            """,
            (code, name, unit_id, price, timestamp, timestamp, new_uuid(), timestamp),
        )
        context.stats.created_materials += 1
        context.refresh_target_indexes()
        created_id = context.material_ids_by_code.get(code.lower()) if code else context.material_ids_by_name[name.lower()]
        return created_id

    context.target.execute(
        """
        UPDATE materials
        SET code = ?,
            name = ?,
            unit_id = ?,
            price = ?,
            marked_for_deletion = 0,
            modified_at = ?,
            updated_at = ?,
            is_deleted = 0
        WHERE id = ?
        """,
        (code, name, unit_id, price, timestamp, timestamp, material_id),
    )
    context.stats.updated_materials += 1
    context.refresh_target_indexes()
    return material_id


def ensure_group_work(target: sqlite3.Connection, *, name: str, code: str) -> int:
    row = target.execute(
        """
        SELECT id
        FROM works
        WHERE code = ? AND is_group = 1
        ORDER BY id
        LIMIT 1
        """,
        (code,),
    ).fetchone()
    timestamp = now_iso()
    if row is not None:
        target.execute(
            """
            UPDATE works
            SET name = ?,
                code = ?,
                unit = NULL,
                price = 0,
                labor_rate = 0,
                parent_id = NULL,
                marked_for_deletion = 0,
                is_group = 1,
                modified_at = ?,
                updated_at = ?,
                is_deleted = 0
            WHERE id = ?
            """,
            (name, code, timestamp, timestamp, int(row["id"])),
        )
        return int(row["id"])

    target.execute(
        """
        INSERT INTO works (
            name, code, unit, price, labor_rate, parent_id, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, NULL, 0, 0, NULL, 0, 1, ?, ?, ?, ?, 0)
        """,
        (name, code, timestamp, timestamp, new_uuid(), timestamp),
    )
    return int(target.execute("SELECT last_insert_rowid()").fetchone()[0])


def upsert_sample_work(
    target: sqlite3.Connection,
    *,
    parent_id: int,
    source_work: dict[str, object],
    unit_name: str | None,
) -> tuple[int, bool]:
    existing = target.execute(
        """
        SELECT id
        FROM works
        WHERE code = ? AND parent_id = ?
        ORDER BY id
        LIMIT 1
        """,
        (source_work.get("code"), parent_id),
    ).fetchone()
    timestamp = now_iso()
    payload = (
        source_work.get("name"),
        source_work.get("code"),
        unit_name,
        round(float(source_work.get("price") or 0), 2),
        round(float(source_work.get("labor_rate") or 0), 2),
        parent_id,
        timestamp,
        timestamp,
    )
    if existing is not None:
        target.execute(
            """
            UPDATE works
            SET name = ?,
                code = ?,
                unit = ?,
                price = ?,
                labor_rate = ?,
                parent_id = ?,
                marked_for_deletion = 0,
                is_group = 0,
                modified_at = ?,
                updated_at = ?,
                is_deleted = 0
            WHERE id = ?
            """,
            (*payload, int(existing["id"])),
        )
        return int(existing["id"]), False

    target.execute(
        """
        INSERT INTO works (
            name, code, unit, price, labor_rate, parent_id, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, 0)
        """,
        (*payload, new_uuid(), timestamp),
    )
    return int(target.execute("SELECT last_insert_rowid()").fetchone()[0]), True


def replace_work_specifications(
    context: ImportContext,
    *,
    target_work_id: int,
    source_specs: list[dict[str, object]],
) -> None:
    deleted = int(
        context.target.execute("SELECT COUNT(*) FROM work_specifications WHERE work_id = ?", (target_work_id,)).fetchone()[0]
    )
    if deleted:
        context.target.execute("DELETE FROM work_specifications WHERE work_id = ?", (target_work_id,))
        context.stats.deleted_existing_specs += deleted

    timestamp = now_iso()
    for source_spec in source_specs:
        source_material = None
        raw_material_id = source_spec.get("material_id")
        if raw_material_id not in (None, 0, "0"):
            source_material = context.source_materials.get(int(raw_material_id))

        unit_name = preferred_spec_unit_name(context, source_spec=source_spec, source_material=source_material)
        unit_id, resolved_unit_name = ensure_unit(context, unit_name)

        material_id = None
        if source_material is not None:
            material_id = ensure_material(context, source_material=source_material, fallback_unit_name=resolved_unit_name)

        component_name = str(source_spec.get("component_name") or "").strip()
        if not component_name and source_material is not None:
            component_name = str(source_material.get("description") or "").strip()
        if not component_name:
            component_name = "Компонент без названия"

        context.target.execute(
            """
            INSERT INTO work_specifications (
                work_id, component_type, component_name, unit_id, consumption_rate, unit_price,
                marked_for_deletion, material_id, created_at, modified_at, uuid, updated_at, is_deleted
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, 0)
            """,
            (
                target_work_id,
                source_spec.get("component_type"),
                component_name,
                unit_id,
                round(float(source_spec.get("consumption_rate") or 0), 4),
                round(float(source_spec.get("unit_price") or 0), 2),
                material_id,
                timestamp,
                timestamp,
                new_uuid(),
                timestamp,
            ),
        )
        context.stats.inserted_specs += 1


def source_work_specs(source: sqlite3.Connection, work_id: int) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in source.execute(
            """
            SELECT *
            FROM work_specifications
            WHERE work_id = ?
              AND COALESCE(marked_for_deletion, 0) = 0
              AND COALESCE(is_deleted, 0) = 0
            ORDER BY id
            """,
            (work_id,),
        ).fetchall()
    ]


def source_work_row(source: sqlite3.Connection, work_id: int) -> dict[str, object] | None:
    row = source.execute(
        """
        SELECT id, code, name, unit, unit_id, price, labor_rate
        FROM works
        WHERE id = ?
          AND COALESCE(marked_for_deletion, 0) = 0
          AND COALESCE(is_deleted, 0) = 0
        """,
        (work_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a small sample of legacy CTM work specifications into CTM2.")
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB)
    parser.add_argument("--group-name", default=DEFAULT_GROUP_NAME)
    parser.add_argument("--group-code", default=DEFAULT_GROUP_CODE)
    parser.add_argument("--apply", action="store_true", help="Apply the import instead of only printing the plan.")
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
        print("DRY RUN")
        print(f"source={source_db}")
        print(f"target={target_db}")
        print(f"group={args.group_name} ({args.group_code})")
        print(f"sample_work_ids={', '.join(str(item) for item in SAMPLE_WORK_IDS)}")
        return 0

    backup_path = create_backup(target_db)
    source = sqlite3.connect(source_db)
    target = sqlite3.connect(target_db)
    source.row_factory = sqlite3.Row
    target.row_factory = sqlite3.Row
    target.execute("PRAGMA foreign_keys = ON")

    try:
        context = ImportContext(source, target)
        group_id = ensure_group_work(target, name=args.group_name, code=args.group_code)

        imported_items: list[tuple[int, str, int]] = []
        for source_work_id in SAMPLE_WORK_IDS:
            source_work = source_work_row(source, source_work_id)
            if source_work is None:
                print(f"skip missing source work_id={source_work_id}")
                continue

            work_unit_name = sanitize_unit_name(source_work.get("unit")) or source_unit_name(context, source_work.get("unit_id"))
            target_work_id, created = upsert_sample_work(
                target,
                parent_id=group_id,
                source_work=source_work,
                unit_name=work_unit_name,
            )
            if created:
                context.stats.created_works += 1
            else:
                context.stats.updated_works += 1

            specs = source_work_specs(source, source_work_id)
            replace_work_specifications(context, target_work_id=target_work_id, source_specs=specs)
            imported_items.append((target_work_id, str(source_work.get("code") or ""), len(specs)))

        target.commit()

        print("APPLIED")
        print(f"backup={backup_path}")
        print(f"group_id={group_id}")
        print(
            "stats:",
            f"created_units={context.stats.created_units},",
            f"created_materials={context.stats.created_materials},",
            f"updated_materials={context.stats.updated_materials},",
            f"created_works={context.stats.created_works},",
            f"updated_works={context.stats.updated_works},",
            f"deleted_existing_specs={context.stats.deleted_existing_specs},",
            f"inserted_specs={context.stats.inserted_specs}",
        )
        print("imported_works:")
        for target_work_id, code, spec_count in imported_items:
            print(f"  - target_work_id={target_work_id}, code={code}, specs={spec_count}")
    finally:
        target.close()
        source.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
