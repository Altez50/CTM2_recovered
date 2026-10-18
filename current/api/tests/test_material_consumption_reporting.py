from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_material_consumption_amount_reaches_cost_card_when_sum_is_stale(
    client: TestClient,
    connection,
    admin_headers: dict[str, str],
) -> None:
    """The server, not the client-provided derived sum, owns line valuation."""
    created = client.post(
        "/api/cost/material-consumptions",
        headers=admin_headers,
        json={
            "number": "MC-REPORT",
            "date": "2026-09-18",
            "object_id": 1,
            "lines": [
                {
                    "line_number": 1,
                    "actual_quantity": 3,
                    "price": 25,
                    "sum": 0,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    document = created.json()["data"]
    document_id = int(document["id"])
    assert document["lines"][0]["sum"] == pytest.approx(75)

    posted = client.post(
        f"/api/cost/material-consumptions/{document_id}/post",
        headers=admin_headers,
    )
    assert posted.status_code == 200, posted.text

    movement = connection.execute(
        "SELECT quantity, amount FROM actual_costs "
        "WHERE registrar_type = 'MaterialConsumption' AND registrar_id = ?",
        (document_id,),
    ).fetchone()
    assert movement["quantity"] == pytest.approx(3)
    assert movement["amount"] == pytest.approx(75)

    report = client.get(
        "/api/cost/reports/cost-card",
        headers=admin_headers,
        params={"object_id": 1, "period_from": "2026-09", "period_to": "2026-09"},
    )
    assert report.status_code == 200, report.text
    material_rows = [
        row for row in report.json()["data"]["elements"]
        if row["cost_element_kind"] == "materials"
    ]
    assert sum(row["actual_amount"] for row in material_rows) == pytest.approx(75)
    assert report.json()["data"]["total_actual"] == pytest.approx(75)
