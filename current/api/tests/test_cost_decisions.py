from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.cost_accounting_services import (
    calculate_cost,
    get_cost_card,
    get_turnover_balance,
    post_cost_calculation,
    unpost_cost_calculation,
)
from api.database import new_uuid, utcnow_iso
from api.tests.conftest import login_headers


FIELD_CASES = [
    ("/api/cost/material-consumptions", {"warehouse": "P0"}),
    ("/api/cost/machinery-usage-reports", {}),
]

OFFICE_CASES = [
    ("/api/cost/subcontract-acceptances", {}),
    ("/api/cost/overhead-expenses", {"period": "2026-09"}),
    ("/api/cost/cost-calculations", {"period": "2026-09", "object_id": 0}),
]


def _headers_and_user(client: TestClient, username: str) -> tuple[dict[str, str], dict]:
    headers = login_headers(client, username, username)
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    return headers, response.json()


@pytest.mark.parametrize(("collection", "extra"), FIELD_CASES)
def test_foreman_can_manage_only_own_field_cost_drafts(
    client: TestClient,
    collection: str,
    extra: dict,
) -> None:
    foreman_headers, foreman = _headers_and_user(client, "foreman")
    manager_headers, _ = _headers_and_user(client, "manager")
    admin_headers, admin = _headers_and_user(client, "admin")

    payload = {
        "number": "RBAC-OWN",
        "date": "2026-09-02",
        "lines": [],
        **extra,
    }
    created = client.post(collection, headers=foreman_headers, json=payload)
    assert created.status_code == 201, created.text
    own_document = created.json()["data"]
    assert own_document["foreman_id"] == foreman["person_id"]

    updated = client.put(
        f"{collection}/{own_document['id']}",
        headers=foreman_headers,
        json={**payload, "number": "RBAC-OWN-U"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["foreman_id"] == foreman["person_id"]

    assert client.post(
        f"{collection}/{own_document['id']}/post", headers=foreman_headers
    ).status_code == 403

    other = client.post(
        collection,
        headers=manager_headers,
        json={**payload, "number": "RBAC-OTHER", "foreman_id": admin["person_id"]},
    )
    assert other.status_code == 201, other.text
    other_id = other.json()["data"]["id"]
    assert client.put(
        f"{collection}/{other_id}", headers=foreman_headers, json=payload
    ).status_code == 403
    assert client.delete(
        f"{collection}/{other_id}", headers=foreman_headers
    ).status_code == 403

    deleted = client.delete(
        f"{collection}/{own_document['id']}", headers=foreman_headers
    )
    assert deleted.status_code == 200, deleted.text
    assert client.post(
        f"{collection}/{own_document['id']}/restore", headers=foreman_headers
    ).status_code == 403
    restored = client.post(
        f"{collection}/{own_document['id']}/restore", headers=manager_headers
    )
    assert restored.status_code == 200, restored.text


@pytest.mark.parametrize(("collection", "extra"), OFFICE_CASES)
def test_foreman_cannot_write_office_cost_documents(
    client: TestClient,
    collection: str,
    extra: dict,
) -> None:
    foreman_headers, _ = _headers_and_user(client, "foreman")
    manager_headers, _ = _headers_and_user(client, "manager")
    payload = {
        "number": "RBAC-OFFICE",
        "date": "2026-09-02",
        "lines": [],
        **extra,
    }
    if collection.endswith("cost-calculations"):
        payload.pop("lines")

    assert client.post(collection, headers=foreman_headers, json=payload).status_code == 403
    created = client.post(collection, headers=manager_headers, json=payload)
    assert created.status_code == 201, created.text
    document_id = created.json()["data"]["id"]
    assert client.put(
        f"{collection}/{document_id}", headers=foreman_headers, json=payload
    ).status_code == 403
    assert client.delete(
        f"{collection}/{document_id}", headers=foreman_headers
    ).status_code == 403


def _insert_contract_estimate_scenario(connection) -> dict[str, int]:
    now = utcnow_iso()
    connection.execute(
        """INSERT INTO objects
           (name, marked_for_deletion, is_group, created_at, modified_at, uuid, updated_at, is_deleted)
           VALUES ('Contract value object', 0, 0, ?, ?, ?, ?, 0)""",
        (now, now, new_uuid(), now),
    )
    object_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        """INSERT INTO contracts
           (number, amount, kind, currency, vat_rate, payment_deferral_days,
            marked_for_deletion, is_group, created_at, modified_at, uuid, updated_at, is_deleted)
           VALUES ('CV-1', 1500, 'customer', 'RUB', 20, 0, 0, 0, ?, ?, ?, ?, 0)""",
        (now, now, new_uuid(), now),
    )
    contract_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        """INSERT INTO works
           (name, unit, price, labor_rate, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted)
           VALUES ('Contract value work', 'm2', 0, 0, 0, 0, ?, ?, ?, ?, 0)""",
        (now, now, new_uuid(), now),
    )
    work_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        """INSERT INTO estimates
           (number, date, object_id, contract_id, total_sum, total_labor, is_posted,
            marked_for_deletion, created_at, modified_at, uuid, updated_at, is_deleted)
           VALUES ('CV-EST', '2026-09-01', ?, ?, 1500, 0, 1, 0, ?, ?, ?, ?, 0)""",
        (object_id, contract_id, now, now, new_uuid(), now),
    )
    estimate_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        """INSERT INTO estimate_lines
           (estimate_id, line_number, work_id, quantity, unit, price, labor_rate, sum,
            planned_labor, is_group, is_collapsed, marked_for_deletion,
            created_at, modified_at, uuid, updated_at, is_deleted)
           VALUES (?, 1, ?, 10, 'm2', 150, 0, 1500, 0, 0, 0, 0, ?, ?, ?, ?, 0)""",
        (estimate_id, work_id, now, now, new_uuid(), now),
    )
    cost_element_id = int(connection.execute(
        "SELECT id FROM cost_elements WHERE kind = 'materials' ORDER BY id LIMIT 1"
    ).fetchone()[0])
    connection.execute(
        """INSERT INTO actual_costs
           (period, date, registrar_type, registrar_id, object_id, estimate_id,
            work_id, cost_element_id, quantity, amount, contract_id, created_at)
           VALUES ('2026-09', '2026-09-02', 'Test', 1, ?, ?, ?, ?, 999, 400, ?, ?)""",
        (object_id, estimate_id, work_id, cost_element_id, contract_id, now),
    )
    connection.execute(
        """INSERT INTO planned_costs
           (period, estimate_id, object_id, work_id, cost_element_id,
            planned_quantity, planned_amount, contract_id, created_at)
           VALUES ('2026-09', ?, ?, ?, ?, 4, 300, ?, ?)""",
        (estimate_id, object_id, work_id, cost_element_id, contract_id, now),
    )
    connection.execute(
        """INSERT INTO work_execution_register
           (recorder_type, recorder_id, line_number, period, object_id, estimate_id,
            work_id, quantity_income, quantity_expense, sum_income, sum_expense,
            created_at, modified_at, uuid, updated_at, is_deleted)
           VALUES ('daily_report', 1, 1, '2026-09-02', ?, ?, ?, 4, 0, 0, 0, ?, ?, ?, ?, 0)""",
        (object_id, estimate_id, work_id, now, now, new_uuid(), now),
    )
    connection.execute(
        """INSERT INTO cost_calculations
           (uuid, number, period, date, object_id, status, marked_for_deletion, created_at)
           VALUES (?, 'CV-CALC', '2026-09', '2026-09-30', ?, 'draft', 0, ?)""",
        (new_uuid(), object_id, now),
    )
    calculation_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.commit()
    return {
        "object_id": object_id,
        "work_id": work_id,
        "cost_element_id": cost_element_id,
        "calculation_id": calculation_id,
    }


def test_contract_value_comes_from_estimate_and_unpost_clears_result(connection) -> None:
    refs = _insert_contract_estimate_scenario(connection)
    result = calculate_cost(connection, refs["calculation_id"])
    assert result["warnings"] == []
    row = connection.execute(
        """SELECT completed_quantity, planned_cost, actual_cost, contract_value, profit
           FROM completed_works_cost WHERE calculation_id = ?""",
        (refs["calculation_id"],),
    ).fetchone()
    assert row["completed_quantity"] == pytest.approx(4)
    assert row["planned_cost"] == pytest.approx(300)
    assert row["actual_cost"] == pytest.approx(400)
    assert row["contract_value"] == pytest.approx(600)
    assert row["profit"] == pytest.approx(200)

    post_cost_calculation(connection, refs["calculation_id"])
    unpost_cost_calculation(connection, refs["calculation_id"])
    status = connection.execute(
        "SELECT status FROM cost_calculations WHERE id = ?", (refs["calculation_id"],)
    ).fetchone()["status"]
    assert status == "draft"
    assert connection.execute(
        "SELECT COUNT(*) FROM completed_works_cost WHERE calculation_id = ?",
        (refs["calculation_id"],),
    ).fetchone()[0] == 0


def test_reports_keep_marked_cost_elements_with_history(connection) -> None:
    refs = _insert_contract_estimate_scenario(connection)
    calculate_cost(connection, refs["calculation_id"])
    connection.execute(
        "UPDATE cost_elements SET marked_for_deletion = 1 WHERE id = ?",
        (refs["cost_element_id"],),
    )
    connection.commit()

    turnover = get_turnover_balance(connection, "2026-09", "2026-09", refs["object_id"])
    row = next(item for item in turnover["rows"] if item["cost_element_id"] == refs["cost_element_id"])
    assert row["inflow"] == pytest.approx(400)

    card = get_cost_card(connection, refs["object_id"], "2026-09", "2026-09")
    card_row = next(item for item in card["elements"] if item["cost_element_id"] == refs["cost_element_id"])
    assert card_row["actual_amount"] == pytest.approx(400)


def _completed_row(connection, calculation_id: int) -> dict:
    return dict(connection.execute(
        "SELECT completed_quantity, contract_value, profit FROM completed_works_cost "
        "WHERE calculation_id = ?",
        (calculation_id,),
    ).fetchone())


def test_contract_rate_is_quantity_weighted_across_estimate_lines(connection) -> None:
    """Принятое правило: расценка = Σ стоимости строк / Σ сметного объёма."""
    refs = _insert_contract_estimate_scenario(connection)
    now = utcnow_iso()
    estimate_id = int(connection.execute(
        "SELECT id FROM estimates WHERE number = 'CV-EST'"
    ).fetchone()[0])
    # Вторая строка той же работы: объём 10 по расценке 50.
    connection.execute(
        """INSERT INTO estimate_lines
           (estimate_id, line_number, work_id, quantity, unit, price, labor_rate, sum,
            planned_labor, is_group, is_collapsed, marked_for_deletion,
            created_at, modified_at, uuid, updated_at, is_deleted)
           VALUES (?, 2, ?, 10, 'm2', 50, 0, 500, 0, 0, 0, 0, ?, ?, ?, ?, 0)""",
        (estimate_id, refs["work_id"], now, now, new_uuid(), now),
    )
    connection.commit()

    result = calculate_cost(connection, refs["calculation_id"])
    # Средневзвешенная расценка: (1500 + 500) / (10 + 10) = 100 → 4 × 100 = 400.
    row = _completed_row(connection, refs["calculation_id"])
    assert row["completed_quantity"] == pytest.approx(4)
    assert row["contract_value"] == pytest.approx(400)
    assert any("Multiple estimate rates were weighted" in warning for warning in result["warnings"])


def test_zero_estimate_quantity_warns_and_blocks_rate(connection) -> None:
    refs = _insert_contract_estimate_scenario(connection)
    connection.execute(
        "UPDATE estimate_lines SET quantity = 0 WHERE estimate_id = "
        "(SELECT id FROM estimates WHERE number = 'CV-EST')"
    )
    connection.commit()

    result = calculate_cost(connection, refs["calculation_id"])
    assert any("Estimate quantity is zero" in warning for warning in result["warnings"])
    assert any("No posted estimate rate" in warning for warning in result["warnings"])
    row = _completed_row(connection, refs["calculation_id"])
    assert row["completed_quantity"] == pytest.approx(4)
    assert row["contract_value"] == pytest.approx(0)


def test_unposted_estimate_warns_and_blocks_rate(connection) -> None:
    refs = _insert_contract_estimate_scenario(connection)
    connection.execute(
        "UPDATE estimates SET is_posted = 0 WHERE number = 'CV-EST'"
    )
    connection.commit()

    result = calculate_cost(connection, refs["calculation_id"])
    assert len(result["warnings"]) == 1
    assert result["warnings"][0].startswith("No posted estimate rate for object=")
    assert f"work={refs['work_id']}" in result["warnings"][0]
    row = _completed_row(connection, refs["calculation_id"])
    assert row["contract_value"] == pytest.approx(0)
