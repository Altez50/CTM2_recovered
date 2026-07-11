from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import SCHEMA_INDEXES_SQL, SCHEMA_TABLES_SQL, ensure_runtime_schema
from dbf_importer import CTM2DBFImporter, DEFAULT_DBF_DIRECTORY


DEFAULT_TARGET_DB = PROJECT_ROOT / "construction.db"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "dbf_import_reports"


def create_backup(target_db: Path) -> Path:
    backup_dir = PROJECT_ROOT / "db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{target_db.stem}.before_dbf_import_{timestamp}{target_db.suffix}"
    shutil.copy2(target_db, backup_path)
    return backup_path


def create_report_path(report_dir: Path, target_db: Path, *, mode: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return report_dir / f"{target_db.stem}.dbf_import_{mode}_{timestamp}.json"


def build_connection(target_db: Path) -> sqlite3.Connection:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target_db)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_TABLES_SQL)
    ensure_runtime_schema(connection)
    connection.executescript(SCHEMA_INDEXES_SQL)
    connection.commit()
    return connection


def build_validation_snapshot(connection: sqlite3.Connection) -> dict[str, Any]:
    return {
        "units_active": int(
            connection.execute("SELECT COUNT(*) FROM units WHERE COALESCE(is_deleted, 0) = 0").fetchone()[0]
        ),
        "materials_active": int(
            connection.execute("SELECT COUNT(*) FROM materials WHERE COALESCE(is_deleted, 0) = 0").fetchone()[0]
        ),
        "works_active": int(
            connection.execute("SELECT COUNT(*) FROM works WHERE COALESCE(is_deleted, 0) = 0").fetchone()[0]
        ),
        "work_specifications_total": int(connection.execute("SELECT COUNT(*) FROM work_specifications").fetchone()[0]),
        "works_with_specifications": int(
            connection.execute("SELECT COUNT(DISTINCT work_id) FROM work_specifications").fetchone()[0]
        ),
        "material_bound_specifications": int(
            connection.execute(
                "SELECT COUNT(*) FROM work_specifications WHERE material_id IS NOT NULL"
            ).fetchone()[0]
        ),
        "unit_bound_specifications": int(
            connection.execute(
                "SELECT COUNT(*) FROM work_specifications WHERE unit_id IS NOT NULL"
            ).fetchone()[0]
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import 1C v7 DBF catalogs/specifications into CTM2 SQLite database."
    )
    parser.add_argument("--dbf-dir", type=Path, default=DEFAULT_DBF_DIRECTORY, help="Directory with SC12/20/25/46 DBF files")
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB, help="Target CTM2 SQLite database")
    parser.add_argument("--limit", type=int, default=None, help="Limit records per DBF file for smoke tests")
    parser.add_argument(
        "--replace-specifications",
        action="store_true",
        help="Delete existing work_specifications before importing DBF specifications",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. Without this flag the script runs in dry-run mode and rolls back.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip automatic backup when --apply is used",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory for JSON import reports",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dbf_dir = args.dbf_dir.resolve()
    target_db = args.target_db.resolve()
    report_dir = args.report_dir.resolve()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")

    backup_path: Path | None = None
    if args.apply and not args.no_backup and target_db.exists():
        backup_path = create_backup(target_db)

    connection = build_connection(target_db)
    try:
        connection.execute("BEGIN")
        importer = CTM2DBFImporter(connection)
        stats = importer.import_directory(
            dbf_dir,
            limit=args.limit,
            replace_specifications=args.replace_specifications,
        )
        mode = "apply" if args.apply else "dry-run"
        report_path = create_report_path(report_dir, target_db, mode=mode)
        summary = {
            "mode": mode,
            "started_at": started_at,
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "dbf_dir": str(dbf_dir),
            "target_db": str(target_db),
            "backup": str(backup_path) if backup_path else None,
            "report_path": str(report_path),
            "replace_specifications": bool(args.replace_specifications),
            "limit": args.limit,
            "stats": stats.to_dict(),
            "validation": build_validation_snapshot(connection),
        }
        report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.apply:
            connection.commit()
        else:
            connection.rollback()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
