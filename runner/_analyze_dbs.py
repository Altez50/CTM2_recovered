#!/usr/bin/env python3
"""Download the old prod DB backup and compare reference tables with local DB."""
import os
import sys
import sqlite3
import paramiko
import tempfile

HOST = "192.168.0.39"
USER = "kassir"
PASS = "7535789"
PORT = 22

REMOTE_DB = "/srv/ctm/data/construction-ctm2.db"
LOCAL_DB = r"f:\2026f\ctm3\CTM2_recovered\current\construction.db"

REFERENCE_TABLES = [
    "counterparties", "objects", "works", "persons", "organizations",
    "contracts", "units", "materials", "work_specifications",
    "cost_elements", "allocation_bases", "machines",
]

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

    # Find the latest backup
    stdin, stdout, stderr = ssh.exec_command(
        f"ls -t '{REMOTE_DB}.bak-'* 2>/dev/null | head -1"
    )
    backup = stdout.read().decode().strip()
    if not backup:
        print("[!] No backup found on prod")
        ssh.close()
        sys.exit(1)
    print(f"Latest backup: {backup}")

    # Download it
    local_backup = os.path.join(tempfile.gettempdir(), "ctm-old-prod.db")
    print(f"Downloading -> {local_backup} ...")
    sftp = ssh.open_sftp()
    sftp.get(backup, local_backup)

    # Also get the current prod DB for comparison
    local_prod = os.path.join(tempfile.gettempdir(), "ctm-current-prod.db")
    print(f"Downloading current prod -> {local_prod} ...")
    sftp.get(REMOTE_DB, local_prod)
    sftp.close()
    ssh.close()

    sz_old = os.path.getsize(local_backup) / 1024
    sz_new = os.path.getsize(local_prod) / 1024
    sz_loc = os.path.getsize(LOCAL_DB) / 1024
    print(f"\nOld backup : {sz_old:.0f} KB")
    print(f"Prod now   : {sz_new:.0f} KB")
    print(f"Local      : {sz_loc:.0f} KB")

    print("\n" + "=" * 80)
    print(f"{'TABLE':<30} {'OLD BACKUP':>10} {'PROD NOW':>10} {'LOCAL':>10}")
    print("=" * 80)

    conns = {
        "old": sqlite3.connect(local_backup),
        "prod": sqlite3.connect(local_prod),
        "local": sqlite3.connect(LOCAL_DB),
    }

    for table in REFERENCE_TABLES:
        counts = {}
        for name, conn in conns.items():
            try:
                counts[name] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[name] = "N/A"
        print(f"{table:<30} {str(counts['old']):>10} {str(counts['prod']):>10} {str(counts['local']):>10}")

    # Also show transactional table counts for context
    print("\n--- Transactional tables (for context) ---")
    txn_tables = [
        "estimates", "estimate_lines", "daily_reports", "daily_report_lines",
        "timesheets", "payment_transactions", "goods_receipts", "goods_issues",
        "material_consumptions", "machinery_usage_reports",
        "subcontract_acceptances", "cost_calculations",
        "work_execution_register", "actual_costs",
    ]
    print(f"{'TABLE':<30} {'OLD BACKUP':>10} {'PROD NOW':>10} {'LOCAL':>10}")
    print("-" * 80)
    for table in txn_tables:
        counts = {}
        for name, conn in conns.items():
            try:
                counts[name] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[name] = "N/A"
        print(f"{table:<30} {str(counts['old']):>10} {str(counts['prod']):>10} {str(counts['local']):>10}")

    for conn in conns.values():
        conn.close()

    print(f"\nLocal backup path: {local_backup}")
    print(f"Local prod path:  {local_prod}")

if __name__ == "__main__":
    main()
