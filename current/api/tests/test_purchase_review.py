"""STEP-05 independent review: source value allocation and cross-path guards."""
from decimal import Decimal

import pytest

from api.tests.test_purchases import purchase
from api.tests.test_trade_returns import trade
from api.tests.test_trade_dimensions import line
from api.tests.test_trade_lifecycle import scoped_user
from api.models.auth import UserInfo
from api import purchase_services


@pytest.mark.parametrize('service', [False, True])
def test_partial_shortage_corrections_reverse_source_cents_and_vat(purchase, service):
    call, _, _, order, child, balance, _, template = purchase
    row = dict(line_number=1, name='Service', line_type='service', quantity=.3,
               price_without_vat=.17, vat_rate=20) if service else line(template, quantity=.3, price_without_vat=.17, vat_rate=20)
    source = order(service=service, lines=[row])
    invoice = child('acquisitions', source, .3)
    assert (invoice['sum_without_vat'], invoice['vat_amount']) == (.05, .01)
    act = child('discrepancies', invoice, .3)
    # Drafts coexist: each posting must allocate against the latest posted facts.
    docs = [child('quantity-adjustments', act, .1, post=False) for _ in range(3)]
    posted = [call('POST', f'/api/purchases/quantity-adjustments/{doc["id"]}/post') for doc in docs]
    for field in ('sum_without_vat', 'vat_amount', 'sum_with_vat'):
        assert sum(Decimal(str(doc[field])) for doc in posted) == Decimal(str(invoice[field]))
    assert balance() == (0, 0, 0)
    if service:
        assert sum(Decimal(str(row['expense_amount'])) for row in call('GET', '/api/purchases/expenses')) == 0
    # Reverse the middle allocation and post it again; all original cents return.
    middle = posted[1]
    call('POST', f'/api/purchases/quantity-adjustments/{middle["id"]}/unpost')
    call('POST', f'/api/purchases/quantity-adjustments/{middle["id"]}/post')
    assert balance() == (0, 0, 0)


def test_distinct_shortage_acts_share_the_original_invoice_value(purchase):
    call, _, _, order, child, balance, _, _ = purchase
    source = order(service=True, quantity=.3, price=.17)
    invoice = child('acquisitions', source, .3)
    for _ in range(3):
        act = child('discrepancies', invoice, .1)
        child('quantity-adjustments', act, .1)
    assert balance() == (0, 0, 0)
    assert sum(Decimal(str(row['expense_amount'])) for row in call('GET', '/api/purchases/expenses')) == 0


@pytest.mark.parametrize('fact', ['inventory_value', 'inventory_axis', 'settlement', 'expense'])
def test_quantity_correction_rejects_mismatching_original_inventory_value(purchase, connection, fact):
    call, _, _, order, child, balance, _, _ = purchase
    invoice = child('acquisitions', order(service=fact == 'expense'), 10)
    act = child('discrepancies', invoice, 2)
    correction = child('quantity-adjustments', act, 2, post=False)
    table, change = {'inventory_value': ('inventory_register', 'sum_income = 1100'),
                     'inventory_axis': ('inventory_register', 'unit_id = NULL'),
                     'settlement': ('mutual_settlements_register', 'accrual_amount = 1100'),
                     'expense': ('purchase_expense_register', 'vat_amount = 1')}[fact]
    connection.execute(f"UPDATE {table} SET {change} WHERE recorder_type = 'purchase_acquisition' AND recorder_id = ?", (invoice['id'],))
    connection.commit()
    before = balance()
    call('POST', f'/api/purchases/quantity-adjustments/{correction["id"]}/post', 400)
    assert balance() == before


def test_later_partial_shortage_keeps_external_consumption_guard(purchase):
    call, _, goods, order, child, balance, _, template = purchase
    source = order()
    invoice = child('acquisitions', source, 10)
    act = child('discrepancies', invoice, 2)
    first = child('quantity-adjustments', act, 1, date='2026-10-03')
    goods('issues', quantity=1, date='2026-10-04')
    second = child('quantity-adjustments', act, 1, date='2026-10-05', post=False)
    before = balance()
    call('POST', f'/api/purchases/quantity-adjustments/{second["id"]}/post', 400)
    call('POST', f'/api/purchases/quantity-adjustments/{first["id"]}/unpost', 400)
    assert balance() == before


@pytest.mark.parametrize('service', [False, True])
def test_failed_post_rolls_back_reallocated_cents_and_audit_before_retry(purchase, connection, monkeypatch, service):
    call, _, _, order, child, _, _, _ = purchase
    invoice = child('acquisitions', order(service=service, quantity=.3, price=.17), .3)
    act = child('discrepancies', invoice, .3)
    first, second = [child('quantity-adjustments', act, .1, post=False) for _ in range(2)]
    call('POST', f'/api/purchases/quantity-adjustments/{first["id"]}/post')
    tables = ('purchase_documents', 'purchase_lines', 'inventory_register', 'mutual_settlements_register', 'purchase_expense_register', 'purchase_events', 'sync_changes')
    def snapshot():
        return {table: [dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY id')] for table in tables}
    before = snapshot()
    real_event = purchase_services.record_event
    def fail(*args):
        real_event(*args)
        raise RuntimeError('review fault after cent reallocation')
    with monkeypatch.context() as patch:
        patch.setattr(purchase_services, 'record_event', fail)
        with pytest.raises(RuntimeError, match='cent reallocation'):
            purchase_services.change_document(connection, second['id'], 'quantity-adjustments', 'post',
                UserInfo(id=1, username='admin', role='admin', is_active=True))
    assert not connection.in_transaction and snapshot() == before
    result = call('POST', f'/api/purchases/quantity-adjustments/{second["id"]}/post')
    assert result['sum_without_vat'] == .01


@pytest.mark.parametrize('mode', ['direct', 'order'])
def test_purchase_recorders_reach_scoped_stock_and_settlement_reports(purchase, client, mode):
    call, ref, _, order, child, _, axes, template = purchase
    service = dict(line_number=2, name='Service', line_type='service', quantity=2, price_without_vat=500, vat_rate=0)
    source = order(mode=mode, lines=[line(template, quantity=10, price_without_vat=100, vat_rate=0), service])
    receipt = child('receipt-orders', source, 8) if mode == 'order' else None
    def linked(kind, basis, quantities):
        rows = [dict(source_line_id=row['id'], quantity=q) for row, q in zip(basis['lines'], quantities, strict=True)]
        if kind == 'discrepancies' and receipt:
            rows[0]['receipt_line_id'] = receipt['lines'][0]['id']
        doc = call('POST', f'/api/purchases/{kind}', 201, json=dict(source_id=basis['id'], date='2026-10-03', lines=rows))
        return call('POST', f'/api/purchases/{kind}/{doc["id"]}/post')
    invoice = linked('acquisitions', source, [10, 2])
    act = linked('discrepancies', invoice, [2, 1])
    linked('quantity-adjustments', act, [2, 1])
    foreign = ref('organizations', name='Foreign purchase owner')
    contract = ref('contracts', number='Foreign', organization_id=foreign, counterparty_id=axes['counterparty_id'])
    warehouse = ref('warehouses', name='Foreign', organization_id=foreign)
    other = call('POST', '/api/purchases/orders', 201, json=dict(date='2026-10-01', organization_id=foreign,
        counterparty_id=axes['counterparty_id'], contract_id=contract, warehouse_id=warehouse,
        lines=[line(template, quantity=10, price_without_vat=999), service]))
    other = call('POST', f'/api/purchases/orders/{other["id"]}/post')
    linked('acquisitions', other, [10, 2])
    _, headers = scoped_user(call, client, [axes['organization_id']], role='viewer')
    def report(path, **params):
        response = client.get(path, params=params, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()['data']
    stock = report('/api/goods/inventory/balances')
    assert len(stock) == 1 and stock[0]['quantity_balance'] == 8 and stock[0]['sum_income'] - stock[0]['sum_expense'] == 800
    moves = report('/api/goods/inventory/movements', date_from='2026-10-01', date_to='2026-10-31')
    assert {row['organization_id'] for row in moves} == {axes['organization_id']}
    assert {row['recorder_type'] for row in moves} == ({'purchase_receipt_order'} if receipt else {'purchase_acquisition', 'purchase_quantity_adjustment'})
    ledger = report('/api/settlements/ledger', organization_id=axes['organization_id'])
    assert sum(row['accrual_amount'] for row in ledger) == 1300
    assert report('/api/settlements/ledger', organization_id=foreign) == []
    assert sum(row['expense_amount'] for row in report('/api/purchases/expenses')) == 500
    balances = report('/api/settlements/balance')
    assert len(balances) == 1 and balances[0]['payable_balance'] == 1300
    turnover = report('/api/settlements/turnover', date_from='2026-10-01', date_to='2026-10-31')
    assert len(turnover) == 1 and turnover[0]['organization_id'] == axes['organization_id'] and turnover[0]['payable_closing'] == 1300


@pytest.mark.parametrize('kind', ['acquisitions', 'quantity-adjustments'])
def test_contract_payment_blocks_purchase_unpost_until_payment_is_reversed(purchase, kind):
    call, _, _, order, child, balance, axes, _ = purchase
    invoice = child('acquisitions', order(), 10)
    doc = invoice if kind == 'acquisitions' else child('quantity-adjustments', child('discrepancies', invoice, 2), 2)
    payment = call('POST', '/api/payments/transactions', 201, json=dict(date='2026-10-04', direction='outgoing',
        amount=100, category='supplier', counterparty_id=axes['counterparty_id'], contract_id=axes['contract_id']))
    call('POST', f'/api/payments/transactions/{payment["id"]}/post')
    before = balance()
    call('POST', f'/api/purchases/{kind}/{doc["id"]}/unpost', 400)
    assert balance() == before
    call('POST', f'/api/payments/transactions/{payment["id"]}/unpost')
    call('POST', f'/api/purchases/{kind}/{doc["id"]}/unpost')
    call('POST', f'/api/purchases/{kind}/{doc["id"]}/post')
    assert balance()[2] == (1000 if kind == 'acquisitions' else 800)


def test_partial_corrections_leave_exact_order_capacity_and_cancellation_limit(purchase):
    call, _, _, order, child, balance, _, _ = purchase
    source = order()
    invoice = child('acquisitions', source, 4)
    act = child('discrepancies', invoice, 2)
    for _ in range(2):
        child('quantity-adjustments', act, 1)
    assert balance() == (2, 200, 200)
    status = call('GET', f'/api/purchases/orders/{source["id"]}')['lines'][0]
    assert (status['open_quantity'], status['shortage_quantity'], status['financial_quantity']) == (6, 2, 2)
    cancel = child('cancellations', source, 6)
    call('POST', '/api/purchases/acquisitions', 400, json=dict(date='2026-10-04', source_id=source['id'],
        lines=[dict(source_line_id=source['lines'][0]['id'], quantity=1)]))
    call('POST', f'/api/purchases/cancellations/{cancel["id"]}/unpost')
    child('acquisitions', source, 6, date='2026-10-04')
    assert balance() == (8, 800, 800)
