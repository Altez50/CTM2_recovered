from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.sync_runtime import (
    _serialize_goods_issues,
    _serialize_goods_receipts,
    _upsert_goods_issue_entity,
    _upsert_goods_receipt_entity,
)


@pytest.mark.parametrize(
    ("collection", "serializer", "upsert"),
    [
        ("receipts", _serialize_goods_receipts, _upsert_goods_receipt_entity),
        ("issues", _serialize_goods_issues, _upsert_goods_issue_entity),
    ],
)
def test_goods_warehouse_round_trip(
    client: TestClient,
    admin_headers: dict[str, str],
    connection,
    collection: str,
    serializer,
    upsert,
) -> None:
    base = f"/api/goods/{collection}"
    payload = {
        "number": f"WH-{collection}",
        "date": "2026-09-21",
        "organization_id": 1,
        "warehouse": "  Центральный склад  ",
        "auto_schedule": False,
        "lines": [],
    }

    created = client.post(base, headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    document = created.json()["data"]
    document_id = document["id"]
    assert document["warehouse"] == "Центральный склад"

    fetched = client.get(f"{base}/{document_id}", headers=admin_headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["data"]["warehouse"] == "Центральный склад"

    listed = client.get(base, headers=admin_headers, params={"search": "Центральный склад"})
    assert listed.status_code == 200, listed.text
    assert any(row["id"] == document_id for row in listed.json()["data"])

    filtered = client.get(base, headers=admin_headers, params={"f_warehouse": "Центральный"})
    assert filtered.status_code == 200, filtered.text
    assert any(row["id"] == document_id for row in filtered.json()["data"])

    serialized = serializer(connection, document["uuid"])
    assert serialized is not None
    assert serialized["warehouse"] == "Центральный склад"
    assert serialized["warehouse_uuid"]

    copied = client.post(f"{base}/{document_id}/copy", headers=admin_headers)
    assert copied.status_code == 201, copied.text
    assert copied.json()["data"]["warehouse"] == "Центральный склад"

    payload["warehouse"] = "Склад Б"
    updated = client.put(f"{base}/{document_id}", headers=admin_headers, json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["warehouse"] == "Склад Б"

    serialized["warehouse"] = "Склад из обмена"
    assert upsert(connection, serialized) == document_id
    connection.commit()
    synced = client.get(f"{base}/{document_id}", headers=admin_headers)
    assert synced.status_code == 200, synced.text
    assert synced.json()["data"]["warehouse"] == "Центральный склад"
    assert synced.json()["data"]["warehouse_id"] == document["warehouse_id"]


@pytest.mark.parametrize("collection", ["receipts", "issues"])
def test_goods_warehouse_remains_optional_for_older_clients(
    client: TestClient,
    admin_headers: dict[str, str],
    collection: str,
) -> None:
    created = client.post(
        f"/api/goods/{collection}",
        headers=admin_headers,
        json={"date": "2026-09-21", "organization_id": 1, "lines": []},
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["warehouse"] == "Основной склад"
    assert created.json()["data"]["warehouse_id"] is not None
