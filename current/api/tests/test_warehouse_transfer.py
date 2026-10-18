from __future__ import annotations

from fastapi.testclient import TestClient

from api.database import ensure_runtime_schema
from api.sync_runtime import _upsert_goods_transfer_entity, serialize_entity


def test_transfer_balances_and_lifecycle(client: TestClient, admin_headers: dict[str, str], connection) -> None:
    material = connection.execute("SELECT id, unit_id, name FROM materials WHERE unit_id IS NOT NULL LIMIT 1").fetchone()
    assert material is not None
    source = client.post(
        "/api/references/warehouses", headers=admin_headers,
        json={"name": "Склад А", "code": "A", "organization_id": 1},
    )
    destination = client.post(
        "/api/references/warehouses", headers=admin_headers,
        json={"name": "Склад Б", "code": "B", "organization_id": 1},
    )
    assert source.status_code == destination.status_code == 200
    source_id = source.json()["data"]["id"]
    destination_id = destination.json()["data"]["id"]

    receipt = client.post(
        "/api/goods/receipts", headers=admin_headers,
        json={
            "date": "2026-09-21", "organization_id": 1, "warehouse_id": source_id,
            "auto_schedule": False,
            "lines": [{"line_number": 1, "material_id": material["id"],
                       "name": material["name"], "unit_id": material["unit_id"],
                       "quantity": 10, "price_without_vat": 20}],
        },
    )
    assert receipt.status_code == 201, receipt.text
    receipt_id = receipt.json()["data"]["id"]
    assert receipt.json()["data"]["warehouse_id"] == source_id
    assert client.post(f"/api/goods/receipts/{receipt_id}/post", headers=admin_headers,
                       params={"auto_schedule": "false"}).status_code == 200

    issue = client.post(
        "/api/goods/issues", headers=admin_headers,
        json={
            "date": "2026-09-21", "organization_id": 1, "warehouse_id": source_id,
            "auto_schedule": False,
            "lines": [{"line_number": 1, "material_id": material["id"],
                       "name": material["name"], "unit_id": material["unit_id"],
                       "quantity": 2, "price_without_vat": 30}],
        },
    )
    assert issue.status_code == 201, issue.text
    issue_id = issue.json()["data"]["id"]
    assert client.post(f"/api/goods/issues/{issue_id}/post", headers=admin_headers,
                       params={"auto_schedule": "false"}).status_code == 200
    issue_movement = client.get(f"/api/goods/issue/{issue_id}/movements", headers=admin_headers)
    assert issue_movement.json()["data"]["inventory"][0]["sum_expense"] == 40

    payload = {
        "date": "2026-09-21", "organization_id": 1,
        "source_warehouse_id": source_id, "destination_warehouse_id": destination_id,
        "lines": [{"line_number": 1, "material_id": material["id"],
                   "unit_id": material["unit_id"], "quantity": 4}],
    }
    created = client.post("/api/goods/transfers", headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    transfer_id = created.json()["data"]["id"]
    assert client.post(f"/api/goods/transfers/{transfer_id}/post", headers=admin_headers).status_code == 200

    snapshot = serialize_entity(connection, "goods_transfers", created.json()["data"]["uuid"])
    assert snapshot is not None and snapshot["is_posted"]
    _upsert_goods_transfer_entity(connection, snapshot)
    _upsert_goods_transfer_entity(connection, snapshot)
    connection.commit()

    movements = client.get(f"/api/goods/transfers/{transfer_id}/movements", headers=admin_headers)
    assert movements.status_code == 200
    rows = movements.json()["data"]["inventory"]
    assert len(rows) == 2
    assert sum(row["quantity_income"] for row in rows) == 4
    assert sum(row["quantity_expense"] for row in rows) == 4
    assert sum(row["sum_income"] for row in rows) == 80
    assert sum(row["sum_expense"] for row in rows) == 80
    assert movements.json()["data"]["settlements"] == []
    assert connection.execute(
        "SELECT COUNT(*) FROM inventory_register WHERE recorder_type = 'goods_transfer' AND recorder_id = ?",
        (transfer_id,),
    ).fetchone()[0] == 2

    source_balance = client.get("/api/goods/inventory/balances", headers=admin_headers,
                                params={"warehouse_id": source_id}).json()["data"]
    destination_balance = client.get("/api/goods/inventory/balances", headers=admin_headers,
                                     params={"warehouse_id": destination_id}).json()["data"]
    assert source_balance[0]["quantity_balance"] == 4
    assert destination_balance[0]["quantity_balance"] == 4
    assert source_balance[0]["average_price"] == 20
    assert destination_balance[0]["average_price"] == 20

    assert client.post(f"/api/goods/transfers/{transfer_id}/unpost", headers=admin_headers).status_code == 200
    assert client.get(f"/api/goods/transfers/{transfer_id}/movements", headers=admin_headers).json()["data"]["inventory"] == []


def test_transfer_rejects_shortage_and_same_warehouse(
    client: TestClient, admin_headers: dict[str, str], connection
) -> None:
    material = connection.execute("SELECT id, unit_id FROM materials WHERE unit_id IS NOT NULL LIMIT 1").fetchone()
    warehouse_ids = []
    for name in ("Источник", "Получатель"):
        result = client.post("/api/references/warehouses", headers=admin_headers,
                             json={"name": name, "organization_id": 1})
        assert result.status_code == 200, result.text
        warehouse_ids.append(result.json()["data"]["id"])
    payload = {
        "date": "2026-09-21", "organization_id": 1,
        "source_warehouse_id": warehouse_ids[0], "destination_warehouse_id": warehouse_ids[0],
        "lines": [{"line_number": 1, "material_id": material["id"],
                   "unit_id": material["unit_id"], "quantity": 2}],
    }
    same = client.post("/api/goods/transfers", headers=admin_headers, json=payload)
    assert same.status_code == 400
    payload["destination_warehouse_id"] = warehouse_ids[1]
    created = client.post("/api/goods/transfers", headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    transfer_id = created.json()["data"]["id"]
    shortage = client.post(f"/api/goods/transfers/{transfer_id}/post", headers=admin_headers)
    assert shortage.status_code == 400
    assert client.get(f"/api/goods/transfers/{transfer_id}/movements", headers=admin_headers).json()["data"]["inventory"] == []


def test_transfer_draft_copy_edit_delete_and_sync_rebuild(
    client: TestClient, admin_headers: dict[str, str], connection
) -> None:
    material = connection.execute("SELECT id, unit_id FROM materials WHERE unit_id IS NOT NULL LIMIT 1").fetchone()
    ids = []
    for name in ("Первый склад", "Второй склад"):
        response = client.post("/api/references/warehouses", headers=admin_headers,
                               json={"name": name, "organization_id": 1})
        assert response.status_code == 200, response.text
        ids.append(response.json()["data"]["id"])
    payload = {
        "date": "2026-09-21", "organization_id": 1,
        "source_warehouse_id": ids[0], "destination_warehouse_id": ids[1],
        "lines": [{"line_number": 1, "material_id": material["id"],
                   "unit_id": material["unit_id"], "quantity": 2}],
    }
    created = client.post("/api/goods/transfers", headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    document = created.json()["data"]
    assert document["number"].startswith("ПМ-")
    transfer_id = document["id"]
    payload["lines"][0]["uuid"] = document["lines"][0]["uuid"]
    updated = client.put(f"/api/goods/transfers/{transfer_id}", headers=admin_headers, json=payload)
    assert updated.status_code == 200, updated.text
    assert len(updated.json()["data"]["lines"]) == 1

    copied = client.post(f"/api/goods/transfers/{transfer_id}/copy", headers=admin_headers)
    assert copied.status_code == 201, copied.text
    assert copied.json()["data"]["id"] != transfer_id
    assert copied.json()["data"]["number"] != document["number"]
    assert not copied.json()["data"]["is_posted"]

    transfer_uuid = document["uuid"]
    snapshot = serialize_entity(connection, "goods_transfers", transfer_uuid)
    assert snapshot is not None
    assert snapshot["source_warehouse_uuid"] and snapshot["destination_warehouse_uuid"]
    _upsert_goods_transfer_entity(connection, snapshot)
    _upsert_goods_transfer_entity(connection, snapshot)
    assert connection.execute(
        "SELECT COUNT(*) FROM goods_transfer_lines WHERE transfer_id = ?", (transfer_id,)
    ).fetchone()[0] == 1
    connection.commit()

    deleted = client.delete(f"/api/goods/transfers/{transfer_id}", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"/api/goods/transfers/{transfer_id}", headers=admin_headers).status_code == 404


def test_legacy_warehouse_migration_preserves_label_and_movements(connection) -> None:
    organization = connection.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()
    assert organization is not None
    stamp = "2026-09-21"
    from api.database import new_uuid

    connection.execute(
        """INSERT INTO goods_receipts
           (number, date, organization_id, warehouse, uuid, created_at, modified_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("OLD-1", stamp, organization["id"], "Старый склад", new_uuid(), stamp, stamp, stamp),
    )
    receipt_id = connection.execute("SELECT MAX(id) FROM goods_receipts").fetchone()[0]
    connection.execute(
        """INSERT INTO inventory_register
           (recorder_type, recorder_id, line_number, period, quantity_income,
            uuid, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("goods_receipt", receipt_id, 1, stamp, 3, new_uuid(), stamp, stamp),
    )
    ensure_runtime_schema(connection)
    first = connection.execute(
        "SELECT warehouse_id, warehouse FROM goods_receipts WHERE id = ?", (receipt_id,)
    ).fetchone()
    assert first["warehouse"] == "Старый склад"
    assert first["warehouse_id"] is not None
    assert connection.execute(
        "SELECT warehouse_id FROM inventory_register WHERE recorder_type = 'goods_receipt' AND recorder_id = ?",
        (receipt_id,),
    ).fetchone()[0] == first["warehouse_id"]
    ensure_runtime_schema(connection)
    assert connection.execute(
        "SELECT COUNT(*) FROM warehouses WHERE organization_id = ? AND name = ?",
        (organization["id"], "Старый склад"),
    ).fetchone()[0] == 1
