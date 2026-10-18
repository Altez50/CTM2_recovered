"""STEP-01 price deltas, dependency boundaries and accounting invariants."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from api.database import get_connection, initialize_database
from api.models.auth import UserInfo
from api.price_adjustment_services import change_adjustment
from api.tests.test_trade_returns import trade  # shared real-API trade fixture


def create(call, source, *, kind='sale', price=140, date='2026-10-03', post=True, **extra):
    payload = {'kind': kind, 'source_id': source['id'], 'date': date,
               'lines': [{'source_line_id': source['lines'][0]['id'], 'new_price': price}], **extra}
    doc = call('POST', '/api/goods/price-adjustments', 201, json=payload)
    if post:
        call('POST', f'/api/goods/price-adjustments/{doc["id"]}/post')
    return call('GET', f'/api/goods/price-adjustments/{doc["id"]}')


@pytest.mark.parametrize('kind', ['sale', 'purchase'])
def test_original_invoice_unchanged_and_quantity_delta_zero(trade, kind):
    call, _, goods, _, _ = trade
    receipt = goods('receipts')
    source = goods('issues', 3, 150) if kind == 'sale' else receipt
    doc = create(call, source, kind=kind, price=140 if kind == 'sale' else 90)
    source_path = 'issues' if kind == 'sale' else 'receipts'
    assert call('GET', f'/api/goods/{source_path}/{source["id"]}') == source
    movements = call('GET', f'/api/goods/price-adjustments/{doc["id"]}/movements')
    assert sum(row['quantity_income']-row['quantity_expense'] for row in movements['inventory']) == 0
    assert movements['settlements'][0]['accrual_amount'] == (-30 if kind == 'sale' else -100)
    if kind == 'sale':
        assert movements['inventory'] == []
    else:
        assert movements['inventory'][0]['sum_expense'] == 100
        assert call('GET', '/api/goods/inventory/balances')[0]['average_price'] == 90
    initialize_database()
    initialize_database()
    assert call('GET', f'/api/goods/price-adjustments/{doc["id"]}')['is_posted']


@pytest.mark.parametrize('kind', ['sale', 'purchase'])
def test_paid_correction_creates_advance_and_cancellation_restores_it(trade, kind):
    call, _, goods, _, axes = trade
    receipt = goods('receipts')
    source = goods('issues', 3, 150) if kind == 'sale' else receipt
    payment = call('POST', '/api/payments/transactions', 201, json={'date': '2026-10-02', 'amount': source['sum_with_vat'],
        'direction': 'incoming' if kind == 'sale' else 'outgoing', 'counterparty_id': axes['counterparty_id'], 'contract_id': axes['contract_id']})
    call('POST', f'/api/payments/transactions/{payment["id"]}/post')
    doc = create(call, source, kind=kind, price=140 if kind == 'sale' else 90)
    advance = 'customer_advance' if kind == 'sale' else 'supplier_advance'
    assert call('GET', '/api/settlements/balance')[0][advance] == (30 if kind == 'sale' else 100)
    path = f'/api/goods/price-adjustments/{doc["id"]}'
    call('POST', path + '/unpost')
    assert call('GET', '/api/settlements/balance')[0][advance] == 0
    call('POST', path + '/post')
    assert len(call('GET', path + '/movements')['settlements']) == 1
    call('POST', path + '/post', 400)
    call('DELETE', path, 400)


def test_sale_price_increase_and_payment_after_adjustment(trade):
    call, _, goods, _, axes = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    doc = create(call, sale, price=180)
    assert doc['delta_without_vat'] == 90
    payment = call('POST', '/api/payments/transactions', 201, json={'date': '2026-10-04', 'direction': 'incoming', 'amount': 540,
        'counterparty_id': axes['counterparty_id'], 'contract_id': axes['contract_id']})
    call('POST', f'/api/payments/transactions/{payment["id"]}/post')
    assert call('GET', '/api/settlements/balance')[0]['receivable_balance'] == 0
    call('POST', f'/api/goods/price-adjustments/{doc["id"]}/unpost')
    assert call('GET', '/api/settlements/balance')[0]['customer_advance'] == 90


@pytest.mark.parametrize('kind', ['sale', 'purchase'])
def test_chain_stale_draft_dates_and_reverse_cancellation(trade, kind):
    call, _, goods, _, _ = trade
    receipt = goods('receipts')
    source = goods('issues', 3, 150) if kind == 'sale' else receipt
    first = create(call, source, kind=kind, price=80, post=False)
    stale = create(call, source, kind=kind, price=70, post=False)
    call('POST', f'/api/goods/price-adjustments/{first["id"]}/post')
    call('POST', f'/api/goods/price-adjustments/{stale["id"]}/post', 400)
    second = create(call, source, kind=kind, price=70, date='2026-10-04')
    assert second['lines'][0]['old_price'] == 80
    assert second['delta_without_vat'] == -10 * source['lines'][0]['quantity']
    path = f'/api/goods/price-adjustments/{first["id"]}'
    call('POST', path + '/unpost', 400)
    call('POST', '/api/goods/price-adjustments', 400, json={'kind': kind, 'source_id': source['id'], 'date': '2026-10-03',
        'lines': [{'source_line_id': source['lines'][0]['id'], 'new_price': 60}]})
    call('POST', f'/api/goods/price-adjustments/{second["id"]}/unpost')
    call('POST', path + '/unpost')
    call('POST', f'/api/goods/price-adjustments/{second["id"]}/post', 400)
    call('DELETE', f'/api/goods/price-adjustments/{second["id"]}')
    call('POST', path + '/post')
    assert len(call('GET', path + '/movements')['settlements']) == 1


def test_purchase_rejects_consumed_slice_and_later_unpost_requires_cost005(trade):
    call, _, goods, _, _ = trade
    receipt = goods('receipts')
    draft = create(call, receipt, kind='purchase', price=90, post=False)
    sale = goods('issues', 3, 150, date='2026-10-05')
    path = f'/api/goods/price-adjustments/{draft["id"]}'
    call('POST', path + '/post', 400)
    assert call('GET', path + '/movements')['inventory'] == []
    call('POST', '/api/goods/price-adjustments', 400, json={'kind': 'purchase', 'source_id': receipt['id'], 'date': '2026-10-03',
         'lines': [{'source_line_id': receipt['lines'][0]['id'], 'new_price': 110}]})
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('POST', path + '/post')
    call('POST', f'/api/goods/issues/{sale["id"]}/post?auto_schedule=false')
    assert call('GET', f'/api/goods/issues/{sale["id"]}')['lines'][0]['inventory_cost'] == 270
    call('POST', path + '/unpost', 400)
    assert call('GET', path)['is_posted']
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('POST', path + '/unpost')


@pytest.mark.parametrize('kind', ['sale', 'purchase'])
def test_returns_and_corrections_are_mutually_blocked_in_both_orders(trade, kind):
    call, _, goods, ret, _ = trade
    receipt = goods('receipts')
    source = goods('issues', 3, 150) if kind == 'sale' else receipt
    return_kind = 'customer' if kind == 'sale' else 'supplier'
    returned = ret(source, kind=return_kind, post=False)
    adjustment = create(call, source, kind=kind, price=90, post=False)
    path = f'/api/goods/price-adjustments/{adjustment["id"]}'
    return_path = f'/api/goods/returns/{returned["id"]}'
    call('POST', path + '/post')
    call('POST', return_path + '/post', 400)
    call('POST', path + '/unpost')
    call('POST', return_path + '/post')
    call('POST', path + '/post', 400)
    call('POST', return_path + '/unpost')
    call('POST', path + '/post')


@pytest.mark.parametrize('field', ['organization_id', 'counterparty_id', 'contract_id', 'warehouse_id', 'object_id', 'estimate_id'])
def test_foreign_analytics_rejected(trade, field):
    call, _, goods, _, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    call('POST', '/api/goods/price-adjustments', 400, json={'kind': 'sale', 'source_id': sale['id'], 'date': '2026-10-03',
        field: 99999, 'lines': [{'source_line_id': sale['lines'][0]['id'], 'new_price': 140}]})


def test_post_revalidates_changed_contract_owner(trade):
    call, ref, goods, _, axes = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    doc = create(call, sale, post=False)
    cp = ref('counterparties', name='Other owner')
    call('PUT', f'/api/references/contracts/{axes["contract_id"]}', json={'number': 'Other', 'counterparty_id': cp})
    call('POST', f'/api/goods/price-adjustments/{doc["id"]}/post', 400)
    assert call('GET', f'/api/goods/price-adjustments/{doc["id"]}/movements')['settlements'] == []


def test_invalid_foreign_duplicate_lines_and_price_validation(trade):
    call, _, goods, _, _ = trade
    receipt = goods('receipts')
    sale = goods('issues', 3, 150)
    base = {'kind': 'sale', 'source_id': sale['id'], 'date': '2026-10-03'}
    line = {'source_line_id': sale['lines'][0]['id'], 'new_price': 140}
    call('POST', '/api/goods/price-adjustments', 400, json={**base, 'lines': [line, line]})
    call('POST', '/api/goods/price-adjustments', 400, json={**base, 'lines': [{**line, 'source_line_id': receipt['lines'][0]['id'] + 9999}]})
    call('POST', '/api/goods/price-adjustments', 400, json={**base, 'date': '2026-09-30', 'lines': [line]})
    for bad in ({**line, 'new_price': -1}, {**line, 'quantity': 2}):
        call('POST', '/api/goods/price-adjustments', 422, json={**base, 'lines': [bad]})
    call('POST', '/api/goods/price-adjustments', 400, json={**base, 'lines': [{**line, 'new_price': 150}]})


def test_vat_rounding_and_zero_price(trade):
    call, _, goods, _, _ = trade
    goods('receipts')
    sale = goods('issues', 3, .17, vat=20)
    doc = create(call, sale, price=.13)
    assert doc['delta_without_vat'] == -.12
    assert doc['delta_vat'] == -.02
    assert doc['delta_with_vat'] == -.14
    zero = create(call, sale, price=0, date='2026-10-04')
    assert zero['lines'][0]['new_sum_without_vat'] == 0
    assert zero['lines'][0]['new_vat_amount'] == 0


def test_atomic_failure_after_inventory(trade, connection):
    call, _, goods, _, _ = trade
    receipt = goods('receipts')
    doc = create(call, receipt, kind='purchase', price=90, post=False)

    class FaultConnection:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, sql, params=()):
            if sql.startswith('INSERT INTO mutual_settlements_register'):
                raise RuntimeError('price-adjustment fault')
            return connection.execute(sql, params)

    with pytest.raises(RuntimeError, match='price-adjustment fault'):
        change_adjustment(FaultConnection(), adjustment_id=doc['id'], user=UserInfo(id=1, username='admin', role='admin', is_active=True), action='post')
    moves = call('GET', f'/api/goods/price-adjustments/{doc["id"]}/movements')
    assert moves['inventory'] == moves['settlements'] == []
    assert not moves['document']['is_posted']


def test_concurrent_revisions_reject_stale_baseline(trade):
    call, _, goods, _, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    docs = [create(call, sale, price=price, post=False) for price in (140, 130)]

    def post(doc):
        connection = get_connection()
        try:
            change_adjustment(connection, adjustment_id=doc['id'], user=UserInfo(id=1, username='admin', role='admin', is_active=True), action='post')
            return 200
        except HTTPException as exc:
            return exc.status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(post, docs)) == [200, 400]


def test_lifecycle_edit_source_delete_and_manager_permissions(trade, connection):
    call, _, goods, _, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    doc = create(call, sale)
    path = f'/api/goods/price-adjustments/{doc["id"]}'
    payload = {'kind': 'sale', 'source_id': sale['id'], 'date': '2026-10-03', 'lines': [{'source_line_id': sale['lines'][0]['id'], 'new_price': 130}]}
    call('PUT', path, 400, json=payload)
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost', 400)
    with pytest.raises(HTTPException) as err:
        change_adjustment(connection, adjustment_id=doc['id'], user=UserInfo(id=2, username='manager', role='manager', is_active=True), action='unpost')
    assert err.value.status_code == 403
    call('POST', path + '/unpost')
    call('PUT', path, json=payload)
    call('POST', path + '/post')
    call('POST', path + '/unpost')
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('DELETE', f'/api/goods/issues/{sale["id"]}', 400)
    call('DELETE', path)
    call('DELETE', f'/api/goods/issues/{sale["id"]}')


def test_backdated_sale_and_transfer_after_purchase_correction_are_rejected(trade):
    call, ref, goods, _, axes = trade
    receipt = goods('receipts')
    create(call, receipt, kind='purchase', price=90, date='2026-10-04')
    sale = goods('issues', 1, 150, date='2026-10-02', post=False)
    call('POST', f'/api/goods/issues/{sale["id"]}/post', 400)
    assert call('GET', f'/api/goods/issue/{sale["id"]}/movements')['inventory'] == []
    destination = ref('warehouses', name='Destination', organization_id=axes['organization_id'])
    transfer = call('POST', '/api/goods/transfers', 201, json={'date': '2026-10-02', 'organization_id': axes['organization_id'],
        'source_warehouse_id': axes['warehouse_id'], 'destination_warehouse_id': destination,
        'lines': [{'line_number': 1, 'material_id': receipt['lines'][0]['material_id'], 'unit_id': receipt['lines'][0]['unit_id'], 'quantity': 1}]})
    call('POST', f'/api/goods/transfers/{transfer["id"]}/post', 400)
    assert call('GET', f'/api/goods/transfers/{transfer["id"]}/movements')['inventory'] == []


def test_only_selected_line_and_its_object_are_revalued(trade):
    call, ref, goods, _, _ = trade
    base = goods('receipts', post=False)
    obj = ref('objects', name='Object of adjusted line')
    first = {key: base['lines'][0][key] for key in ('line_number', 'material_id', 'unit_id', 'name', 'quantity', 'price_without_vat', 'vat_rate')}
    receipt = call('PUT', f'/api/goods/receipts/{base["id"]}', json={
        'date': base['date'], 'organization_id': base['organization_id'], 'warehouse_id': base['warehouse_id'],
        'counterparty_id': base['counterparty_id'], 'contract_id': base['contract_id'], 'auto_schedule': False,
        'lines': [first, {**first, 'line_number': 2, 'object_id': obj, 'price_without_vat': 200}]})
    call('POST', f'/api/goods/receipts/{receipt["id"]}/post?auto_schedule=false')
    doc = create(call, receipt, kind='purchase', price=90)
    rows = call('GET', '/api/goods/inventory/balances')
    costs = {row['object_id']: row['sum_income']-row['sum_expense'] for row in rows}
    assert costs == {None: 900, obj: 2000}
    movements = call('GET', f'/api/goods/price-adjustments/{doc["id"]}/movements')
    assert len(movements['inventory']) == 1
    assert movements['inventory'][0]['object_id'] is None


def test_line_analytics_changed_after_draft_are_rejected(trade, connection):
    call, ref, goods, _, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    doc = create(call, sale, post=False)
    obj = ref('objects', name='Changed line object')
    connection.execute('UPDATE goods_issue_lines SET object_id = ? WHERE id = ?', (obj, sale['lines'][0]['id']))
    connection.commit()
    path = f'/api/goods/price-adjustments/{doc["id"]}'
    call('POST', path + '/post', 400)
    assert call('GET', path + '/movements')['settlements'] == []
