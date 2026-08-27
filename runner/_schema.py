#!/usr/bin/env python3
"""Check PK and column structure of reference tables in old and local DBs."""
import sqlite3
import tempfile, os

LOCAL_DB = r"f:\2026f\ctm3\CTM2_recovered\current\construction.db"
OLD_DB = os.path.join(tempfile.gettempdir(), "ctm-old-prod.db")

TABLES = ["counterparties", "objects", "works", "persons", "organizations",
          "contracts", "units", "materials", "work_specifications",
          "cost_elements", "allocation_bases", "machines"]

for label, path in [("LOCAL", LOCAL_DB), ("OLD", OLD_DB)]:
    print(f"\n{'='*60}\n{label}: {path}\n{'='*60}")
    conn = sqlite3.connect(path)
    for t in TABLES:
        try:
            cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
            if cols:
                pk_cols = [c[1] for c in cols if c[5]]  # c[5] = pk flag
                all_cols = [c[1] for c in cols]
                print(f"\n{t}  PK={pk_cols}")
                print(f"  cols: {', '.join(all_cols)}")
        except sqlite3.OperationalError as e:
            print(f"\n{t}  ERROR: {e}")
    conn.close()
