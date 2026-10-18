"""Executable business contract TRADE-ACCRUAL-001 (see scenarios/trade_accrual.json)."""
from __future__ import annotations

import itertools
import json
from pathlib import Path

SCENARIO = json.loads(
    (Path(__file__).parent / "scenarios" / "trade_accrual.json").read_text(encoding="utf-8")
)
DIMENSIONS = ("organization_id", "counterparty_id", "contract_id")


def test_trade_accrual_by_organization_counterparty_contract(client, admin_headers) -> None:
    def request(method, path, status=200, **kwargs):
        response = client.request(method, path, headers=admin_headers, **kwargs)
        assert response.status_code == status, f"{method} {path}: {response.text}"
        return response.json().get("data")

    def reference(kind, **payload):
        return request("POST", f"/api/references/{kind}", json=payload)["id"]

    organizations = {
        name: reference("organizations", name=f"Harness organization {name}")
        for name in ("A", "B")
    }
    counterparties = {
        name: reference("counterparties", name=f"Harness counterparty {name}")
        for name in ("X", "Y")
    }
    warehouses = {
        name: reference("warehouses", name=f"Harness warehouse {name}", organization_id=org_id)
        for name, org_id in organizations.items()
    }
    material_id = reference("materials", name="Harness goods", code="HARNESS-TRADE-001")
    slices = []
    for source in SCENARIO["slices"]:
        item = dict(source)
        item["organization_id"] = organizations[item["organization"]]
        item["counterparty_id"] = counterparties[item["counterparty"]]
        item["contract_id"] = reference(
            "contracts", number=item["contract"], date="2026-10-01",
            organization_id=item["organization_id"], counterparty_id=item["counterparty_id"],
            vat_rate=SCENARIO["vat_rate"], payment_deferral_days=10,
        )
        slices.append(item)

    expected = {}

    def key(row):
        return tuple(row[dimension] for dimension in DIMENSIONS)

    def assert_balances(**filters):
        rows = request("GET", "/api/settlements/balance", params=filters)
        actual = {}
        for row in rows:
            assert key(row) not in actual, "Duplicate settlement slice"
            assert row["object_id"] is None
            actual[key(row)] = (row["payable_balance"], row["receivable_balance"])
            assert row["payable_accrual"] == row["payable_balance"]
            assert row["receivable_accrual"] == row["receivable_balance"]
            assert row["payable_payment"] == row["receivable_payment"] == 0
        selected = {
            k: value for k, value in expected.items()
            if any(value) and all(k[DIMENSIONS.index(dim)] == ident for dim, ident in filters.items())
        }
        assert actual == selected, f"Settlement filters: {filters}"

    def movements(kind, document_id):
        return request("GET", f"/api/goods/{kind}/{document_id}/movements")

    def check_movement(item, kind):
        data = movements(kind, item[f"{kind}_id"])
        assert len(data["settlements"]) == len(data["inventory"]) == 1
        row = data["settlements"][0]
        assert key(row) == key(item)
        assert row["direction"] == ("payable" if kind == "receipt" else "receivable")
        assert row["accrual_amount"] == item["payable" if kind == "receipt" else "receivable"]
        assert row["payment_amount"] == row["planned_amount"] == 0
        inventory = data["inventory"][0]
        assert inventory["warehouse_id"] == warehouses[item["organization"]]
        if kind == "receipt":
            assert inventory["quantity_income"] == item["receipt_quantity"]
            assert inventory["quantity_expense"] == inventory["sum_expense"] == 0
            assert inventory["sum_income"] == item["receipt_quantity"] * 100
        else:
            assert inventory["quantity_expense"] == item["issue_quantity"]
            assert inventory["quantity_income"] == inventory["sum_income"] == 0
            assert inventory["sum_expense"] == item["issue_quantity"] * 100

    assert_balances()
    # Real documents created through API; no direct inserts into accounting registers.
    for kind, collection in (("receipt", "receipts"), ("issue", "issues")):
        for index, item in enumerate(slices):
            document = request("POST", f"/api/goods/{collection}", status=201, json={
                "number": f"HARNESS-{kind}-{index}", "date": SCENARIO[f"{kind}_date"],
                **{dim: item[dim] for dim in DIMENSIONS},
                "warehouse_id": warehouses[item["organization"]], "auto_schedule": False,
                "lines": [{"line_number": 1, "material_id": material_id, "name": "Harness goods",
                           "quantity": item[f"{kind}_quantity"],
                           "price_without_vat": SCENARIO[f"{kind}_price"],
                           "vat_rate": SCENARIO["vat_rate"]}],
            })
            item[f"{kind}_id"] = document["id"]
            assert not document["is_posted"]
            assert document["sum_with_vat"] == item["payable" if kind == "receipt" else "receivable"]
            data = movements(kind, document["id"])
            assert data["settlements"] == data["inventory"] == []
            assert_balances()  # Saving a draft must not accrue debt.
            url = f"/api/goods/{collection}/{document['id']}/post"
            request("POST", url, params={"auto_schedule": "false"})
            payable, receivable = expected.get(key(item), (0, 0))
            expected[key(item)] = (
                item["payable"] if kind == "receipt" else payable,
                item["receivable"] if kind == "issue" else receivable,
            )
            check_movement(item, kind)
            assert_balances()
            # Current API rejects posting an already posted document; no extra accrual.
            request("POST", url, status=400, params={"auto_schedule": "false"})
            check_movement(item, kind)
            assert_balances()

    # All 45 combinations: no filters, individual axes, pairs, full tuples,
    # and incompatible tuples which must return an empty result.
    domains = [[None, *sorted({row[dim] for row in slices})] for dim in DIMENSIONS]
    for values in itertools.product(*domains):
        assert_balances(**{dim: value for dim, value in zip(DIMENSIONS, values) if value is not None})

    assert request("GET", "/api/settlements/balance", params={"date": "2026-09-30"}) == []
    receipt_balances = request("GET", "/api/settlements/balance", params={"date": "2026-10-01"})
    assert {key(row): (row["payable_balance"], row["receivable_balance"]) for row in receipt_balances} == {
        key(item): (item["payable"], 0) for item in slices
    }

    for item in slices:
        filters = {dim: item[dim] for dim in DIMENSIONS}
        ledger = request("GET", "/api/settlements/ledger", params=filters)
        assert [(row["recorder_type"], row["recorder_id"], row["accrual_amount"]) for row in ledger] == [
            ("goods_receipt", item["receipt_id"], item["payable"]),
            ("goods_issue", item["issue_id"], item["receivable"]),
        ]
        assert ledger[-1]["payable_balance_running"] == item["payable"]
        assert ledger[-1]["receivable_balance_running"] == item["receivable"]
        # Receipt is an opening balance; sale is a turnover on the next day.
        turnover = request("GET", "/api/settlements/turnover", params={
            **filters, "date_from": "2026-10-02", "date_to": "2026-10-02",
        })
        assert len(turnover) == 1
        row = turnover[0]
        assert key(row) == key(item)
        for direction, opening, accrual, closing in (
            ("payable", item["payable"], 0, item["payable"]),
            ("receivable", 0, item["receivable"], item["receivable"]),
        ):
            assert row[f"{direction}_opening"] == opening
            assert row[f"{direction}_accrual_turnover"] == accrual
            assert row[f"{direction}_payment_turnover"] == 0
            assert row[f"{direction}_closing"] == closing

    for org_name, warehouse_id in warehouses.items():
        inventory = request("GET", "/api/goods/inventory/balances", params={"warehouse_id": warehouse_id})
        assert len(inventory) == 1
        relevant = [item for item in slices if item["organization"] == org_name]
        assert inventory[0]["quantity_balance"] == sum(item["stock_quantity"] for item in relevant)
        assert inventory[0]["sum_income"] - inventory[0]["sum_expense"] == sum(item["stock_cost"] for item in relevant)

    # Cancel sales first, then receipts. Every cancellation affects only its own slice.
    for kind, collection in (("issue", "issues"), ("receipt", "receipts")):
        for item in reversed(slices):
            request("POST", f"/api/goods/{collection}/{item[f'{kind}_id']}/unpost")
            payable, receivable = expected[key(item)]
            expected[key(item)] = (payable, 0) if kind == "issue" else (0, receivable)
            data = movements(kind, item[f"{kind}_id"])
            assert data["inventory"] == data["settlements"] == []
            assert_balances()

    # Restore the original documents, proving that a full post/unpost cycle leaves no duplicates.
    for kind, collection in (("receipt", "receipts"), ("issue", "issues")):
        for item in slices:
            request("POST", f"/api/goods/{collection}/{item[f'{kind}_id']}/post",
                    params={"auto_schedule": "false"})
            payable, receivable = expected[key(item)]
            expected[key(item)] = (item["payable"], receivable) if kind == "receipt" else (payable, item["receivable"])
            check_movement(item, kind)
            assert_balances()
