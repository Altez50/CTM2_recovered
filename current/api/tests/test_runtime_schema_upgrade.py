import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.config import settings
from api.database import SCHEMA_TABLES_SQL, initialize_database
from api.main import app
from api.security import hash_password


@pytest.mark.parametrize("has_warehouse_label", [False, True])
def test_startup_upgrades_legacy_inventory_and_allows_login(tmp_path, monkeypatch, has_warehouse_label):
    path = tmp_path / "legacy.db"
    monkeypatch.setattr(settings, "db_type", "sqlite")
    monkeypatch.setattr(settings, "database_path", path)
    monkeypatch.setattr(settings, "allow_seed_data", False)
    monkeypatch.setattr(settings, "reset_database_on_schema_mismatch", False)

    # Pre-warehouse databases have these tables already, so CREATE TABLE IF
    # NOT EXISTS cannot supply the columns needed by the new inventory index.
    legacy_schema = SCHEMA_TABLES_SQL
    for table in ("goods_receipts", "goods_issues", "inventory_register"):
        pattern = rf"CREATE TABLE IF NOT EXISTS {table} \(.*?\n\);"
        block = re.search(pattern, legacy_schema, re.S).group()
        legacy_block = re.sub(
            r"^    (?:warehouse_id INTEGER,|movement_side TEXT,|FOREIGN KEY \(warehouse_id\).*)\n",
            "", block, flags=re.M,
        )
        if not has_warehouse_label:
            legacy_block = legacy_block.replace("    warehouse TEXT NOT NULL DEFAULT '',\n", "")
        legacy_schema = legacy_schema.replace(block, legacy_block)

    with sqlite3.connect(path) as connection:
        connection.executescript(legacy_schema)
        connection.execute("INSERT INTO users (username, password_hash, role, uuid) VALUES (?, ?, ?, ?)",
                           ("admin", hash_password("admin"), "admin", "legacy-admin"))
        connection.execute("INSERT INTO organizations (name, uuid) VALUES ('Legacy org', 'legacy-org')")
        for table, recorder in (("goods_receipts", "goods_receipt"), ("goods_issues", "goods_issue")):
            columns = ", warehouse" if has_warehouse_label else ""
            values = ", 'Legacy warehouse'" if has_warehouse_label else ""
            connection.execute(f"INSERT INTO {table} (number, date, organization_id, uuid{columns}) "
                               f"VALUES ('OLD-1', '2026-01-01', 1, ?{values})", (recorder,))
            connection.execute("""INSERT INTO inventory_register
                (recorder_type, recorder_id, line_number, period, quantity_income, sum_income, uuid)
                VALUES (?, 1, 1, '2026-01-01', 3, 150, ?)""", (recorder, recorder + "-movement"))

    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    initialize_database()  # The upgrade must also be safe on the next restart.
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0] == 1
        for table, recorder in (("goods_receipts", "goods_receipt"), ("goods_issues", "goods_issue")):
            document = connection.execute(f"SELECT warehouse_id, warehouse, number, uuid FROM {table}").fetchone()
            assert document[0] is not None
            assert document[1:] == ("Legacy warehouse" if has_warehouse_label else "", "OLD-1", recorder)
            movement = connection.execute("""SELECT warehouse_id, quantity_income, sum_income, uuid
                FROM inventory_register WHERE recorder_type = ?""", (recorder,)).fetchone()
            assert movement == (document[0], 3, 150, recorder + "-movement")
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'idx_inventory_dimensions'").fetchone()
