"""Lifecycle guards (delete/restore of posted and distributed cost documents)
and audit identity for RBAC=B cost operations (DEVELOPMENT_PLAN.md P1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.scripts.seed_cost_test_scenario import P1, seed_sources
from api.tests.conftest import login_headers

POSTED_DELETE_CASES = [
    ("/api/cost/material-consumptions", {"number": "LGD-MC", "date": "2026-09-02", "lines": []}),
    ("/api/cost/machinery-usage-reports", {"number": "LGD-MU", "date": "2026-09-02", "lines": []}),
    ("/api/cost/subcontract-acceptances", {"number": "LGD-SA", "date": "2026-09-02", "lines": []}),
]


def _audit_rows(connection, resource_type: str, resource_id: int) -> list[dict]:
    return [
        dict(row)
        for row in connection.execute(
            "SELECT user_id, username, action FROM audit_logs "
            "WHERE resource_type = ? AND resource_id = ? ORDER BY id",
            (resource_type, resource_id),
        ).fetchall()
    ]


@pytest.mark.parametrize(("collection", "payload"), POSTED_DELETE_CASES)
def test_posted_cost_documents_reject_delete(
    client: TestClient,
    admin_headers: dict[str, str],
    collection: str,
    payload: dict,
) -> None:
    created = client.post(collection, headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    doc_id = int(created.json()["data"]["id"])

    assert client.post(f"{collection}/{doc_id}/post", headers=admin_headers).status_code == 200
    assert client.delete(f"{collection}/{doc_id}", headers=admin_headers).status_code == 400

    assert client.post(f"{collection}/{doc_id}/unpost", headers=admin_headers).status_code == 200
    assert client.delete(f"{collection}/{doc_id}", headers=admin_headers).status_code == 200
    # Restore of the marked document succeeds; restore of a live document is a 404.
    restored = client.post(f"{collection}/{doc_id}/restore", headers=admin_headers)
    assert restored.status_code == 200, restored.text
    assert client.post(f"{collection}/{doc_id}/restore", headers=admin_headers).status_code == 404
    # The restored document is live again and can be marked once more.
    assert client.delete(f"{collection}/{doc_id}", headers=admin_headers).status_code == 200


def test_distributed_overhead_rejects_delete(
    client: TestClient,
    connection,
    admin_headers: dict[str, str],
) -> None:
    created = client.post(
        "/api/cost/overhead-expenses",
        headers=admin_headers,
        json={"number": "LGD-OH", "date": "2026-09-02", "period": "2026-09", "lines": []},
    )
    assert created.status_code == 201, created.text
    doc_id = int(created.json()["data"]["id"])

    connection.execute(
        "UPDATE overhead_expenses SET is_distributed = 1 WHERE id = ?", (doc_id,)
    )
    connection.commit()
    assert client.delete(f"/api/cost/overhead-expenses/{doc_id}", headers=admin_headers).status_code == 400

    connection.execute(
        "UPDATE overhead_expenses SET is_distributed = 0 WHERE id = ?", (doc_id,)
    )
    connection.commit()
    assert client.delete(f"/api/cost/overhead-expenses/{doc_id}", headers=admin_headers).status_code == 200
    restored = client.post(f"/api/cost/overhead-expenses/{doc_id}/restore", headers=admin_headers)
    assert restored.status_code == 200, restored.text
    assert client.post(f"/api/cost/overhead-expenses/{doc_id}/restore", headers=admin_headers).status_code == 404


def test_posted_cost_calculation_rejects_delete(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    created = client.post(
        "/api/cost/cost-calculations",
        headers=admin_headers,
        json={"number": "LGD-CC", "date": "2026-09-30", "period": "2026-09", "object_id": 0},
    )
    assert created.status_code == 201, created.text
    calc_id = int(created.json()["data"]["id"])

    calculated = client.post(f"/api/cost/cost-calculations/{calc_id}/calculate", headers=admin_headers)
    assert calculated.status_code == 200, calculated.text
    assert client.post(f"/api/cost/cost-calculations/{calc_id}/post", headers=admin_headers).status_code == 200
    assert client.delete(f"/api/cost/cost-calculations/{calc_id}", headers=admin_headers).status_code == 400

    assert client.post(f"/api/cost/cost-calculations/{calc_id}/unpost", headers=admin_headers).status_code == 200
    deleted = client.delete(f"/api/cost/cost-calculations/{calc_id}", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text
    restored = client.post(f"/api/cost/cost-calculations/{calc_id}/restore", headers=admin_headers)
    assert restored.status_code == 200, restored.text


def test_foreman_cannot_import_lines_into_cost_documents(
    client: TestClient,
) -> None:
    """Mass import is an office operation under RBAC=B; the foreman gets 403."""
    foreman_headers = login_headers(client, "foreman", "foreman")
    created = client.post(
        "/api/cost/material-consumptions",
        headers=foreman_headers,
        json={"number": "IMP-FM", "date": "2026-09-02", "lines": []},
    )
    assert created.status_code == 201, created.text
    doc_id = int(created.json()["data"]["id"])

    imported = client.post(
        f"/api/cost/material-consumptions/{doc_id}/import-text",
        headers=foreman_headers,
        params={"format": "tsv", "preview": True},
        content="",
    )
    assert imported.status_code == 403, imported.text


def test_calculation_warns_about_unattributed_timesheet_labor(
    client: TestClient,
    connection,
    admin_headers: dict[str, str],
) -> None:
    """Timesheet labor posts with work_id=0; the calculation must say so."""
    timesheet = client.post(
        "/api/documents/timesheets",
        headers=admin_headers,
        json={
            "number": "TS-WARN",
            "date": "2026-09-02",
            "month_year": "2026-09",
            "object_id": 1,
            "lines": [
                {"line_number": 1, "employee_id": 1, "hourly_rate": 100, "days": {"1": 8, "2": 8}},
            ],
        },
    )
    assert timesheet.status_code == 201, timesheet.text
    timesheet_id = int(timesheet.json()["data"]["id"])
    posted = client.post(f"/api/documents/timesheets/{timesheet_id}/post", headers=admin_headers)
    assert posted.status_code == 200, posted.text

    calc = client.post(
        "/api/cost/cost-calculations",
        headers=admin_headers,
        json={"number": "CC-WARN", "date": "2026-09-30", "period": "2026-09", "object_id": 0},
    )
    assert calc.status_code == 201, calc.text
    calc_id = int(calc.json()["data"]["id"])
    calculated = client.post(f"/api/cost/cost-calculations/{calc_id}/calculate", headers=admin_headers)
    assert calculated.status_code == 200, calculated.text
    warnings = calculated.json()["data"]["warnings"]
    assert any(
        "Timesheet labor is not attributed to works (work_id=0) for object=1, amount=1600" in warning
        for warning in warnings
    ), warnings

    # The labor itself is booked unchanged at object level — only diagnostics added.
    labor_row = connection.execute(
        "SELECT work_id, cost_element_id, quantity, amount FROM actual_costs "
        "WHERE registrar_type = 'Timesheet' AND registrar_id = ?",
        (timesheet_id,),
    ).fetchone()
    assert labor_row["work_id"] == 0
    assert labor_row["quantity"] == pytest.approx(16)
    assert labor_row["amount"] == pytest.approx(1600)


def test_lifecycle_audit_records_acting_user(
    client: TestClient,
    connection,
) -> None:
    manager_headers = login_headers(client, "manager", "manager")
    admin_headers = login_headers(client)
    foreman_headers = login_headers(client, "foreman", "foreman")

    # Manager creates and posts a material consumption — audit must carry the manager.
    created = client.post(
        "/api/cost/material-consumptions",
        headers=manager_headers,
        json={"number": "AUD-MC", "date": "2026-09-02", "lines": []},
    )
    assert created.status_code == 201, created.text
    doc_id = int(created.json()["data"]["id"])
    manager_me = client.get("/api/auth/me", headers=manager_headers).json()

    assert client.post(f"/api/cost/material-consumptions/{doc_id}/post", headers=manager_headers).status_code == 200
    rows = _audit_rows(connection, "material_consumption", doc_id)
    assert [row["action"] for row in rows] == ["post"]
    assert rows[0]["user_id"] == manager_me["id"]
    assert rows[0]["username"] == "manager"

    # Foreman deletes their own draft — audit must carry the foreman.
    foreman_created = client.post(
        "/api/cost/material-consumptions",
        headers=foreman_headers,
        json={"number": "AUD-FM", "date": "2026-09-02", "lines": []},
    )
    assert foreman_created.status_code == 201, foreman_created.text
    own_id = int(foreman_created.json()["data"]["id"])
    foreman_me = client.get("/api/auth/me", headers=foreman_headers).json()
    assert client.delete(f"/api/cost/material-consumptions/{own_id}", headers=foreman_headers).status_code == 200
    rows = _audit_rows(connection, "material_consumption", own_id)
    assert [row["action"] for row in rows] == ["delete"]
    assert rows[0]["user_id"] == foreman_me["id"]
    assert rows[0]["username"] == "foreman"

    # Admin restores the foreman's document — audit must carry the admin.
    assert client.post(f"/api/cost/material-consumptions/{own_id}/restore", headers=admin_headers).status_code == 200
    rows = _audit_rows(connection, "material_consumption", own_id)
    assert [row["action"] for row in rows] == ["delete", "restore"]
    assert rows[1]["username"] == "admin"

    # Overhead distribution and cancellation record the acting manager.
    refs = seed_sources(connection)
    distributed = client.post(
        "/api/cost/overhead/distribute",
        headers=manager_headers,
        json={"period": P1, "allocation_base_id": refs["base"]["payroll"], "object_id": 0},
    )
    assert distributed.status_code == 200, distributed.text
    overhead_rows = [
        dict(row)
        for row in connection.execute(
            "SELECT user_id, username, action FROM audit_logs WHERE resource_type = 'overhead' "
            "ORDER BY id"
        ).fetchall()
    ]
    assert overhead_rows[-1]["action"] == "distribute"
    assert overhead_rows[-1]["username"] == "manager"
    assert overhead_rows[-1]["user_id"] == manager_me["id"]

    cancelled = client.post(
        "/api/cost/overhead/cancel-distribution",
        headers=admin_headers,
        params={"period": P1},
    )
    assert cancelled.status_code == 200, cancelled.text
    overhead_rows = [
        dict(row)
        for row in connection.execute(
            "SELECT user_id, username, action FROM audit_logs WHERE resource_type = 'overhead' "
            "ORDER BY id"
        ).fetchall()
    ]
    assert overhead_rows[-1]["action"] == "cancel_distribution"
    assert overhead_rows[-1]["username"] == "admin"
