"""Stage-one edge cases beyond the five executable acceptance contracts."""
import pytest


@pytest.fixture
def trade_api(client, admin_headers):
    def call(method, url, status=200, **kwargs):
        response = client.request(method, url, headers=admin_headers, **kwargs)
        assert response.status_code == status, response.text
        return response.json().get("data")

    def ref(kind, **payload):
        return call("POST", f"/api/references/{kind}", json=payload)["id"]

    org = ref("organizations", name="Stage1 A")
    cp = ref("counterparties", name="Stage1 X")
    other_cp = ref("counterparties", name="Stage1 Y")
    contract = ref("contracts", number="Stage1 AX", organization_id=org, counterparty_id=cp)
    other_contract = ref("contracts", number="Stage1 AY", organization_id=org, counterparty_id=other_cp)
    obj = ref("objects", name="Stage1 object")
    payment = {"date": "2026-10-01", "direction": "incoming", "amount": 100,
               "counterparty_id": cp, "contract_id": contract}
    return call, payment, org, obj, other_cp, other_contract


@pytest.mark.parametrize("direction", ["incoming", "outgoing"])
def test_advance_requires_explicit_permission_and_rejects_repost(trade_api, direction):
    call, payload, org, _, _, _ = trade_api
    base = "/api/payments/transactions"
    payload["direction"] = direction
    tx = call("POST", base, 201, json=payload)
    call("POST", f"{base}/{tx['id']}/post", 400)
    assert call("GET", f"{base}/{tx['id']}/movements")["settlements"] == []
    tx = call("PUT", f"{base}/{tx['id']}", json={**payload, "allow_advance": True})
    call("POST", f"{base}/{tx['id']}/post")
    call("POST", f"{base}/{tx['id']}/post", 400)
    row = call("GET", "/api/settlements/balance")[0]
    advance = "customer_advance" if direction == "incoming" else "supplier_advance"
    assert row[advance] == 100
    assert row["organization_id"] == org
    assert row["receivable_balance"] == row["payable_balance"] == 0
    call("POST", f"{base}/{tx['id']}/unpost")
    assert call("GET", "/api/settlements/balance") == []
    call("POST", f"{base}/{tx['id']}/post")
    assert len(call("GET", f"{base}/{tx['id']}/movements")["settlements"]) == 1


def test_payment_contract_ownership_is_revalidated_at_post(trade_api):
    call, payload, _, _, other_cp, _ = trade_api
    base = "/api/payments/transactions"
    call("POST", base, 400, json={**payload, "counterparty_id": other_cp})
    call("POST", base, 400, json={**payload, "contract_id": None, "allow_advance": True})
    tx = call("POST", base, 201, json={**payload, "allow_advance": True})
    call("PUT", f"/api/references/contracts/{payload['contract_id']}",
         json={"number": "Changed owner", "counterparty_id": other_cp})
    call("POST", f"{base}/{tx['id']}/post", 400)
    assert call("GET", "/api/settlements/balance") == []
    assert call("GET", f"{base}/{tx['id']}/movements")["settlements"] == []


def test_advances_do_not_cross_objects_contracts_or_directions(trade_api):
    call, payload, org, obj, other_cp, other_contract = trade_api
    base = "/api/payments/transactions"
    for tx_payload in (
        {**payload, "amount": 60.01, "object_id": obj},
        {**payload, "amount": 20.02, "direction": "outgoing"},
        {**payload, "amount": 30.03, "contract_id": other_contract, "counterparty_id": other_cp},
    ):
        tx = call("POST", base, 201, json={**tx_payload, "allow_advance": True})
        call("POST", f"{base}/{tx['id']}/post")
    # Service lines accrue debt without requiring inventory fixture data.
    document = call("POST", "/api/goods/issues", 201, json={
        "date": "2026-10-02", "organization_id": org, "counterparty_id": payload["counterparty_id"],
        "contract_id": payload["contract_id"], "auto_schedule": False,
        "lines": [{"line_number": 1, "name": "Service", "quantity": 1, "price_without_vat": 100, "vat_rate": 0}],
    })
    call("POST", f"/api/goods/issues/{document['id']}/post", params={"auto_schedule": "false"})
    rows = call("GET", "/api/settlements/balance", params={"contract_id": payload["contract_id"]})
    assert {(r["object_id"], r["receivable_balance"], r["customer_advance"], r["supplier_advance"]) for r in rows} == {
        (None, 100, 0, 20.02), (obj, 0, 60.01, 0),
    }
    assert call("GET", "/api/settlements/balance", params={"date": "2026-09-30"}) == []
    ledger = call("GET", "/api/settlements/ledger", params={"organization_id": org,
                  "contract_id": payload["contract_id"], "date_from": "2026-10-02"})
    assert len(ledger) == 1
    assert ledger[0]["receivable_balance_running"] == 100
    assert ledger[0]["customer_advance_running"] == 60.01
    assert ledger[0]["supplier_advance_running"] == 20.02
    turnover = call("GET", "/api/settlements/turnover", params={"contract_id": payload["contract_id"],
                    "date_from": "2026-10-02", "date_to": "2026-10-02"})
    assert sum(r["receivable_closing"] for r in turnover) == 100
    assert sum(r["customer_advance_closing"] for r in turnover) == 60.01
    assert sum(r["supplier_advance_closing"] for r in turnover) == 20.02
    overdue = call("GET", "/api/settlements/overdue", params={"date": "2026-10-03"})
    assert sum(r["overdue_amount"] for r in overdue if r["direction"] == "receivable") == 100
    tx = call("POST", base, 201, json={**payload, "date": "2026-10-02", "amount": 100.01})
    call("POST", f"{base}/{tx['id']}/post", 400)  # even one kopeck needs permission


def test_contract_picker_filters_both_owners(trade_api):
    call, payload, org, _, other_cp, other_contract = trade_api
    rows = call("GET", "/api/references/contracts", params={"organization_id": org,
                "counterparty_id": payload["counterparty_id"]})
    assert [r["id"] for r in rows] == [payload["contract_id"]]
    rows = call("GET", "/api/references/contracts", params={"organization_id": org,
                "counterparty_id": other_cp})
    assert [r["id"] for r in rows] == [other_contract]


def test_turnover_keeps_equal_opposite_opening_resources(trade_api):
    call, payload, org, _, _, _ = trade_api
    tx = call("POST", "/api/payments/transactions", 201, json={**payload, "allow_advance": True})
    call("POST", f"/api/payments/transactions/{tx['id']}/post")
    receipt = call("POST", "/api/goods/receipts", 201, json={
        "date": "2026-10-01", "organization_id": org, "counterparty_id": payload["counterparty_id"],
        "contract_id": payload["contract_id"], "auto_schedule": False,
        "lines": [{"line_number": 1, "name": "Service", "quantity": 1, "price_without_vat": 100, "vat_rate": 0}],
    })
    call("POST", f"/api/goods/receipts/{receipt['id']}/post", params={"auto_schedule": "false"})
    rows = call("GET", "/api/settlements/turnover", params={"contract_id": payload["contract_id"],
                "date_from": "2026-10-02", "date_to": "2026-10-02"})
    assert len(rows) == 1
    assert rows[0]["customer_advance_opening"] == rows[0]["customer_advance_closing"] == 100
    assert rows[0]["payable_opening"] == rows[0]["payable_closing"] == 100


def test_advance_permission_survives_sync_roundtrip(trade_api, connection):
    from api.sync_runtime import _serialize_payment_transactions, _upsert_payment_transaction_entity

    call, payload, _, _, _, _ = trade_api
    tx = call("POST", "/api/payments/transactions", 201, json={**payload, "allow_advance": True})
    snapshot = _serialize_payment_transactions(connection, tx["uuid"])
    assert snapshot["allow_advance"]
    ident = _upsert_payment_transaction_entity(connection, snapshot)
    connection.commit()
    assert ident == tx["id"]
    assert call("GET", f"/api/payments/transactions/{ident}")["allow_advance"]


def test_advance_schema_migration_is_idempotent(connection):
    from api.database import ensure_runtime_schema

    connection.execute("ALTER TABLE payment_transactions DROP COLUMN allow_advance")
    ensure_runtime_schema(connection)
    ensure_runtime_schema(connection)
    columns = [r["name"] for r in connection.execute("PRAGMA table_info(payment_transactions)").fetchall()]
    assert columns.count("allow_advance") == 1
