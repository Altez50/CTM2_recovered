from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


CRUD_CASES = [
    ("/api/documents/daily-reports", {"number": "P0-DR", "date": "2026-09-02", "lines": []}),
    ("/api/documents/timesheets", {"number": "P0-TS", "date": "2026-09-02", "month_year": "2026-09", "object_id": 1, "lines": [{"line_number": 1, "employee_id": 1, "days": {"1": 8}}]}),
    ("/api/cost/material-consumptions", {"number": "P0-MC", "date": "2026-09-02", "lines": []}),
    ("/api/cost/machinery-usage-reports", {"number": "P0-MU", "date": "2026-09-02", "lines": []}),
    ("/api/cost/subcontract-acceptances", {"number": "P0-SA", "date": "2026-09-02", "lines": []}),
    ("/api/cost/overhead-expenses", {"number": "P0-OH", "date": "2026-09-02", "period": "2026-09", "lines": []}),
    ("/api/cost/cost-calculations", {"number": "P0-CC", "date": "2026-09-02", "period": "2026-09", "object_id": 0}),
    ("/api/goods/receipts", {"number": "P0-GR", "date": "2026-09-02", "organization_id": 1, "auto_schedule": False, "lines": [{"line_number": 1, "name": "P0 material", "quantity": 1, "price_without_vat": 10}]}),
    ("/api/goods/issues", {"number": "P0-GI", "date": "2026-09-02", "organization_id": 1, "auto_schedule": False, "lines": [{"line_number": 1, "name": "P0 material", "quantity": 0, "price_without_vat": 10}]}),
    ("/api/payments/schedules", {"number": "P0-PS", "date_from": "2026-09-01", "date_to": "2026-09-30", "lines": [{"line_number": 1, "planned_date": "2026-09-10", "planned_amount": 10, "direction": "outgoing", "category": "other"}]}),
    ("/api/payments/transactions", {"number": "P0-PT", "date": "2026-09-02", "amount": 10, "direction": "outgoing", "category": "other"}),
]


@pytest.mark.parametrize(("collection", "payload"), CRUD_CASES)
def test_document_create_get_update_matrix(
    client: TestClient,
    admin_headers: dict[str, str],
    collection: str,
    payload: dict,
) -> None:
    created = client.post(collection, headers=admin_headers, json=payload)
    assert created.status_code == 201, f"{collection}: {created.text}"
    document_id = int(created.json()["data"]["id"])
    fetched = client.get(f"{collection}/{document_id}", headers=admin_headers)
    assert fetched.status_code == 200, f"{collection}: {fetched.text}"
    updated_payload = {**payload, "number": payload["number"] + "-U"}
    updated = client.put(f"{collection}/{document_id}", headers=admin_headers, json=updated_payload)
    assert updated.status_code == 200, f"{collection}: {updated.text}"
    assert updated.json()["data"]["number"] == updated_payload["number"]


POSTABLE_CASES = [
    CRUD_CASES[index]
    for index in (0, 1, 2, 3, 4, 7, 8, 9, 10)
]


@pytest.mark.parametrize(("collection", "payload"), POSTABLE_CASES)
def test_document_post_unpost_matrix(
    client: TestClient,
    admin_headers: dict[str, str],
    collection: str,
    payload: dict,
) -> None:
    created = client.post(collection, headers=admin_headers, json=payload)
    assert created.status_code == 201, f"{collection}: {created.text}"
    document_id = int(created.json()["data"]["id"])
    posted = client.post(f"{collection}/{document_id}/post", headers=admin_headers)
    assert posted.status_code == 200, f"{collection}: {posted.text}"
    locked_edit = client.put(f"{collection}/{document_id}", headers=admin_headers, json=payload)
    assert locked_edit.status_code == 400, f"{collection} accepted an edit after posting"
    unposted = client.post(f"{collection}/{document_id}/unpost", headers=admin_headers)
    assert unposted.status_code == 200, f"{collection}: {unposted.text}"
