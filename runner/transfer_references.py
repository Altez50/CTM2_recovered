#!/usr/bin/env python3
"""Перенос справочников из прежней базы в локальную.

Стратегия: merge по uuid.
  - Если uuid из старой БД уже есть в локальной → пропускаем.
  - Если uuid новый, но id конфликтует → назначаем новый id, запоминаем mapping.
  - Соблюдаем порядок зависимостей (units → materials → work_specifications и т.д.).
  - После вставки обновляем FK по mapping'у.

Usage:
    python transfer_references.py [--dry-run] [--local-db <path>] [--old-db <path>]
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

LOCAL_DB_DEFAULT = r"f:\2026f\ctm3\CTM2_recovered\current\construction.db"
OLD_DB_DEFAULT = os.path.join(tempfile.gettempdir(), "ctm-old-prod.db")

# Порядок обработки: сначала таблицы без FK на другие справочники,
# затем зависимые.
TABLE_ORDER = [
    "units",
    "persons",
    "organizations",
    "counterparties",
    "objects",
    "works",
    "materials",
    "machines",
    "allocation_bases",
    "cost_elements",
    "work_specifications",
    "contracts",
]

# FK: (таблица, колонка) → (целевая таблица, целевая колонка)
# Только межтабличные FK (self-ref обрабатываем отдельно).
FK_MAP = {
    ("materials", "unit_id"):              ("units", "id"),
    ("organizations", "default_responsible_id"): ("persons", "id"),
    ("cost_elements", "allocation_base_id"): ("allocation_bases", "id"),
    ("work_specifications", "work_id"):     ("works", "id"),
    ("work_specifications", "material_id"): ("materials", "id"),
    ("work_specifications", "unit_id"):     ("units", "id"),
    ("contracts", "counterparty_id"):       ("counterparties", "id"),
    ("contracts", "organization_id"):       ("organizations", "id"),
}

# Колонки с self-reference (parent_id)
SELF_REF_TABLES = {
    "counterparties", "organizations", "objects", "works",
    "persons", "contracts",
}


def log(msg: str) -> None:
    print(msg, flush=True)


def get_columns(conn, table):
    """Get column names in order."""
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def merge_table(old_conn, local_conn, table, id_maps, dry_run=False):
    """Merge one table. Returns (inserted, skipped, remapped)."""
    cols = get_columns(local_conn, table)
    old_cols = get_columns(old_conn, table)

    # Use intersection of columns (handle schema differences)
    common_cols = [c for c in cols if c in old_cols]
    col_list = ", ".join(common_cols)
    placeholders = ", ".join(["?"] * len(common_cols))

    # Existing uuids in local
    existing_uuids = set()
    try:
        for row in local_conn.execute(f"SELECT uuid FROM {table}").fetchall():
            existing_uuids.add(row[0])
    except sqlite3.OperationalError:
        pass  # no uuid column

    # Existing ids in local
    existing_ids = set(
        r[0] for r in local_conn.execute(f"SELECT id FROM {table}").fetchall()
    )
    max_id = max(existing_ids) if existing_ids else 0

    # All rows from old DB
    old_rows = old_conn.execute(
        f"SELECT {col_list} FROM {table}"
    ).fetchall()
    col_idx = {c: i for i, c in enumerate(common_cols)}

    inserted = 0
    skipped = 0
    remapped = 0
    id_map = {}  # old_id → new_id

    for row in old_rows:
        row_dict = {c: row[col_idx[c]] for c in common_cols}
        old_uuid = row_dict.get("uuid")
        old_id = row_dict["id"]

        # Skip if uuid already exists
        if old_uuid and old_uuid in existing_uuids:
            skipped += 1
            continue

        # Handle ID conflict
        new_id = old_id
        if old_id in existing_ids:
            max_id += 1
            new_id = max_id
            id_map[old_id] = new_id
            existing_ids.add(new_id)
            remapped += 1
        else:
            existing_ids.add(old_id)

        # Update id in row
        row_dict["id"] = new_id

        # Update self-ref parent_id
        if table in SELF_REF_TABLES and "parent_id" in row_dict:
            pid = row_dict["parent_id"]
            if pid is not None and pid in id_map:
                row_dict["parent_id"] = id_map[pid]

        values = [row_dict[c] for c in common_cols]

        if not dry_run:
            try:
                local_conn.execute(
                    f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                    values,
                )
            except sqlite3.IntegrityError:
                # UNIQUE constraint (name, code, etc.) — data already present
                # under a different uuid/id. Skip, and remove the id from
                # existing_ids so we don't track a phantom remap.
                existing_ids.discard(new_id)
                if old_id in id_map:
                    del id_map[old_id]
                skipped += 1
                continue
        inserted += 1

    # Store the id_map for FK resolution
    id_maps[table] = id_map

    return inserted, skipped, remapped


def fix_foreign_keys(local_conn, id_maps, dry_run=False):
    """Update FK columns in dependent tables based on id maps."""
    fixed = 0
    for (table, col), (ref_table, ref_col) in FK_MAP.items():
        id_map = id_maps.get(ref_table, {})
        if not id_map:
            continue
        for old_id, new_id in id_map.items():
            if dry_run:
                count = local_conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {col} = ?",
                    (old_id,),
                ).fetchone()[0]
                fixed += count
            else:
                cur = local_conn.execute(
                    f"UPDATE {table} SET {col} = ? WHERE {col} = ?",
                    (new_id, old_id),
                )
                fixed += cur.rowcount
    return fixed


def main():
    dry_run = "--dry-run" in sys.argv
    local_db = LOCAL_DB_DEFAULT
    old_db = OLD_DB_DEFAULT

    for i, arg in enumerate(sys.argv):
        if arg == "--local-db" and i + 1 < len(sys.argv):
            local_db = sys.argv[i + 1]
        elif arg == "--old-db" and i + 1 < len(sys.argv):
            old_db = sys.argv[i + 1]

    if not os.path.exists(old_db):
        log(f"[!] Old DB not found: {old_db}")
        sys.exit(1)
    if not os.path.exists(local_db):
        log(f"[!] Local DB not found: {local_db}")
        sys.exit(1)

    mode = "DRY RUN" if dry_run else "LIVE"
    log(f"=== Transfer references ({mode}) ===")
    log(f"Source (old): {old_db}")
    log(f"Target (local): {local_db}")
    log("")

    # Backup local DB
    if not dry_run:
        backup = local_db + ".bak-before-ref-transfer"
        import shutil
        shutil.copy2(local_db, backup)
        log(f"Local DB backed up -> {backup}")
        log("")

    old_conn = sqlite3.connect(old_db)
    local_conn = sqlite3.connect(local_db)
    local_conn.execute("PRAGMA foreign_keys = OFF")

    id_maps = {}
    total_inserted = 0
    total_skipped = 0
    total_remapped = 0

    for table in TABLE_ORDER:
        try:
            ins, skip, remap = merge_table(
                old_conn, local_conn, table, id_maps, dry_run
            )
        except sqlite3.OperationalError as e:
            log(f"  {table:<25} ERROR: {e}")
            continue

        total_inserted += ins
        total_skipped += skip
        total_remapped += remap
        detail = f"  {table:<25} +{ins:<6} skip={skip:<6} remap={remap}"
        log(detail)

    # Fix FKs
    log("")
    log("Fixing foreign keys ...")
    fixed = fix_foreign_keys(local_conn, id_maps, dry_run)
    log(f"  FK updates: {fixed}")

    if not dry_run:
        local_conn.commit()

    # Summary
    log("")
    log(f"{'='*50}")
    log(f"Total: +{total_inserted} inserted, {total_skipped} skipped (uuid match), {total_remapped} id remapped")
    if not dry_run:
        log(f"Committed to {local_db}")
    log(f"{'='*50}")

    # Show final counts
    log("")
    log(f"{'TABLE':<25} {'COUNT':>8}")
    log("-" * 35)
    for table in TABLE_ORDER:
        try:
            cnt = local_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            log(f"  {table:<23} {cnt:>8}")
        except sqlite3.OperationalError:
            log(f"  {table:<23} {'N/A':>8}")

    old_conn.close()
    local_conn.close()


if __name__ == "__main__":
    main()
