"""Stage-two invariant checks beyond the executable RET acceptance catalog."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from api.database import get_connection, initialize_database
from api.models.auth import UserInfo
from api.return_services import change_return


@pytest.fixture
def trade(client, admin_headers, connection):
    def call(method, path, status=200, **kwargs):
        response = client.request(method, path, headers=admin_headers, **kwargs)
        assert response.status_code == status, response.text
        return response.json().get('data')

    def ref(kind, **data):
        return call('POST', f'/api/references/{kind}', json=data)['id']

    org = ref('organizations', name='Returns A')
    cp = ref('counterparties', name='Returns X')
    contract = ref('contracts', number='Returns AX', organization_id=org, counterparty_id=cp)
    warehouse = ref('warehouses', name='Returns W', organization_id=org)
    unit = connection.execute('SELECT id FROM units ORDER BY id LIMIT 1').fetchone()[0]
    material = ref('materials', name='Returned product', unit_id=unit)
    axes = dict(organization_id=org, counterparty_id=cp, contract_id=contract, warehouse_id=warehouse)

    def goods(kind, quantity=10, price=100, date='2026-10-01', vat=0, post=True, **extra):
        payload = dict(date=date, auto_schedule=False, **axes,
                       lines=[dict(line_number=1, name='Product', material_id=material, unit_id=unit,
                                   quantity=quantity, price_without_vat=price, vat_rate=vat)])
        payload.update(extra)
        doc = call('POST', f'/api/goods/{kind}', 201, json=payload)
        if post:
            call('POST', f'/api/goods/{kind}/{doc["id"]}/post?auto_schedule=false')
        return call('GET', f'/api/goods/{kind}/{doc["id"]}')

    def ret(source, quantity=1, kind='customer', date='2026-10-03', post=True, **extra):
        payload = dict(kind=kind, source_id=source['id'], date=date,
                       lines=[dict(source_line_id=source['lines'][0]['id'], quantity=quantity)])
        payload.update(extra)
        doc = call('POST', '/api/goods/returns', 201, json=payload)
        if post:
            call('POST', f'/api/goods/returns/{doc["id"]}/post')
        return call('GET', f'/api/goods/returns/{doc["id"]}')

    return call, ref, goods, ret, axes


def test_original_sale_cost_survives_later_purchase_and_repost(trade):
    call, _, goods, ret, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150, date='2026-10-02')
    goods('receipts', 10, 300, date='2026-10-03')
    returned = ret(sale, date='2026-10-04')
    assert returned['inventory_cost'] == 100
    movements = call('GET', f'/api/goods/returns/{returned["id"]}/movements')
    assert movements['inventory'][0]['sum_income'] == 100
    assert movements['settlements'][0]['accrual_amount'] == -150
    call('POST', f'/api/goods/returns/{returned["id"]}/unpost')
    call('POST', f'/api/goods/returns/{returned["id"]}/post')
    assert call('GET', f'/api/goods/returns/{returned["id"]}')['inventory_cost'] == 100
    rows = call('GET', '/api/goods/inventory/balances')
    assert rows[0]['quantity_balance'] == 18
    assert rows[0]['sum_income'] - rows[0]['sum_expense'] == 3800


@pytest.mark.parametrize('kind', ['customer', 'supplier'])
def test_fractional_returns_reverse_exact_original_cost_and_vat(trade, kind):
    call, _, goods, ret, _ = trade
    receipt = goods('receipts', .3, .17, vat=20)
    source = goods('issues', .3, .23, date='2026-10-02', vat=20) if kind == 'customer' else receipt
    docs = [ret(source, .1, kind=kind) for _ in range(3)]
    for field in ('sum_without_vat', 'vat_amount', 'sum_with_vat'):
        assert sum((Decimal(str(doc[field])) for doc in docs), Decimal(0)) == Decimal(str(source[field]))
    original_cost = source['lines'][0]['inventory_cost'] if kind == 'customer' else source['sum_without_vat']
    assert sum((Decimal(str(doc['inventory_cost'])) for doc in docs), Decimal(0)) == Decimal(str(original_cost))
    call('POST', '/api/goods/returns', 400, json={'kind': kind, 'source_id': source['id'], 'date': '2026-10-03',
         'lines': [{'source_line_id': source['lines'][0]['id'], 'quantity': .000001}]})


@pytest.mark.parametrize('field', ['organization_id', 'counterparty_id', 'contract_id', 'warehouse_id', 'object_id'])
def test_return_rejects_changed_header_analytics(trade, field):
    call, _, goods, _, axes = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    call('POST', '/api/goods/returns', 400, json={'kind': 'customer', 'source_id': sale['id'], 'date': '2026-10-03',
         field: axes.get(field, 0) + 99999, 'lines': [{'source_line_id': sale['lines'][0]['id'], 'quantity': 1}]})


def test_contract_owner_revalidated_at_post(trade):
    call, ref, goods, ret, axes = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    doc = ret(sale, post=False)
    cp = ref('counterparties', name='Other owner')
    call('PUT', f'/api/references/contracts/{axes["contract_id"]}', json={'number': 'Changed', 'counterparty_id': cp})
    call('POST', f'/api/goods/returns/{doc["id"]}/post', 400)
    assert call('GET', f'/api/goods/returns/{doc["id"]}/movements')['inventory'] == []


def test_foreign_duplicate_and_unposted_source_lines_rejected(trade):
    call, _, goods, _, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    other = goods('issues', 1, 160, post=False)
    base = {'kind': 'customer', 'source_id': sale['id'], 'date': '2026-10-03'}
    own = {'source_line_id': sale['lines'][0]['id'], 'quantity': 1}
    call('POST', '/api/goods/returns', 400, json={**base, 'lines': [{'source_line_id': other['lines'][0]['id'], 'quantity': 1}]})
    call('POST', '/api/goods/returns', 400, json={**base, 'lines': [own, own]})
    call('POST', '/api/goods/returns', 400, json={**base, 'source_id': other['id'], 'lines': [{'source_line_id': other['lines'][0]['id'], 'quantity': 1}]})
    call('POST', '/api/goods/returns', 400, json={**base, 'date': '2026-09-30', 'lines': [own]})


def test_supplier_return_checks_stock_and_rolls_back(trade):
    call, _, goods, ret, _ = trade
    receipt = goods('receipts')
    goods('issues', 9, 150)
    doc = ret(receipt, 2, kind='supplier', post=False)
    call('POST', f'/api/goods/returns/{doc["id"]}/post', 400)
    movements = call('GET', f'/api/goods/returns/{doc["id"]}/movements')
    assert movements['inventory'] == movements['settlements'] == []
    assert not movements['document']['is_posted']


def test_customer_unpost_cannot_remove_consumed_return(trade):
    call, _, goods, ret, _ = trade
    goods('receipts', 3)
    sale = goods('issues', 3, 150)
    doc = ret(sale)
    goods('issues', 1, 150, date='2026-10-04')
    call('POST', f'/api/goods/returns/{doc["id"]}/unpost', 400)
    assert len(call('GET', f'/api/goods/returns/{doc["id"]}/movements')['inventory']) == 1


def test_backdated_supplier_return_cannot_break_later_stock(trade):
    call, _, goods, ret, _ = trade
    receipt = goods('receipts')
    goods('issues', 10, 150, date='2026-10-05')
    doc = ret(receipt, 1, kind='supplier', post=False)
    call('POST', f'/api/goods/returns/{doc["id"]}/post', 400)
    assert call('GET', f'/api/goods/returns/{doc["id"]}/movements')['inventory'] == []


@pytest.mark.parametrize('kind', ['customer', 'supplier'])
def test_refund_caps_dates_cash_direction_and_repost(trade, kind):
    call, _, goods, ret, axes = trade
    receipt = goods('receipts')
    source = goods('issues', 3, 150) if kind == 'customer' else receipt
    direction = 'incoming' if kind == 'customer' else 'outgoing'
    payment = call('POST', '/api/payments/transactions', 201, json={'date': '2026-10-02', 'direction': direction,
        'amount': source['sum_with_vat'], 'counterparty_id': axes['counterparty_id'], 'contract_id': axes['contract_id']})
    call('POST', f'/api/payments/transactions/{payment["id"]}/post')
    doc = ret(source, kind=kind)
    base = {'return_id': doc['id'], 'date': '2026-10-03', 'amount': doc['sum_with_vat']}
    call('POST', '/api/goods/return-refunds', 400, json={**base, 'date': '2026-10-02'})
    excess = call('POST', '/api/goods/return-refunds', 201, json={**base, 'amount': doc['sum_with_vat'] + .01})
    call('POST', f'/api/goods/return-refunds/{excess["id"]}/post', 400)
    refund = call('POST', '/api/goods/return-refunds', 201, json=base)
    path = f'/api/goods/return-refunds/{refund["id"]}'
    call('POST', path + '/post')
    moves = call('GET', path + '/movements')
    assert moves['cash'][0]['direction'] == ('outgoing' if kind == 'customer' else 'incoming')
    assert moves['cash'][0]['fact_amount'] == doc['sum_with_vat']
    assert moves['settlements'][0]['direction'] == ('receivable' if kind == 'customer' else 'payable')
    assert moves['settlements'][0]['payment_amount'] == -doc['sum_with_vat']
    call('POST', path + '/post', 400)
    call('PUT', path, 400, json=base)
    call('DELETE', path, 400)
    call('POST', f'/api/goods/returns/{doc["id"]}/unpost', 400)
    call('POST', path + '/unpost')
    call('POST', path + '/post')
    assert len(call('GET', path + '/movements')['cash']) == 1
    call('POST', path + '/unpost')
    call('DELETE', path)


def test_unpaid_return_cannot_refund_unrelated_contract_advance(trade):
    call, ref, goods, ret, axes = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    doc = ret(sale)
    other = ref('contracts', number='Other contract', organization_id=axes['organization_id'], counterparty_id=axes['counterparty_id'])
    payment = call('POST', '/api/payments/transactions', 201, json={'date': '2026-10-03', 'direction': 'incoming', 'allow_advance': True,
        'amount': 1000, 'counterparty_id': axes['counterparty_id'], 'contract_id': other})
    call('POST', f'/api/payments/transactions/{payment["id"]}/post')
    refund = call('POST', '/api/goods/return-refunds', 201, json={'return_id': doc['id'], 'date': '2026-10-03', 'amount': 150})
    call('POST', f'/api/goods/return-refunds/{refund["id"]}/post', 400)
    assert call('GET', f'/api/goods/return-refunds/{refund["id"]}/movements')['cash'] == []


def test_fault_after_inventory_insert_is_atomic(trade, connection):
    call, _, goods, ret, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    doc = ret(sale, post=False)

    class FailingConnection:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, sql, params=()):
            if sql.startswith('INSERT INTO mutual_settlements_register'):
                raise RuntimeError('injected failure after inventory')
            return connection.execute(sql, params)

    with pytest.raises(RuntimeError, match='injected failure'):
        change_return(FailingConnection(), document_id=doc['id'], user=UserInfo(id=1, username='admin', role='admin', is_active=True), action='post')
    moves = call('GET', f'/api/goods/returns/{doc["id"]}/movements')
    assert moves['inventory'] == moves['settlements'] == []
    assert not moves['document']['is_posted']


def test_concurrent_returns_cannot_exceed_source(trade):
    call, _, goods, ret, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    drafts = [ret(sale, 2, post=False) for _ in range(2)]

    def post(doc):
        from fastapi import HTTPException
        connection = get_connection()
        try:
            change_return(connection, document_id=doc['id'], user=UserInfo(id=1, username='admin', role='admin', is_active=True), action='post')
            return 200
        except HTTPException as exc:
            return exc.status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(post, drafts)) == [200, 400]
    rows = call('GET', '/api/goods/returns')
    assert sum(line['quantity'] for doc in rows if doc['is_posted'] for line in doc['lines']) == 2


def test_return_schema_initialization_is_repeatable(trade, connection):
    call, _, goods, ret, _ = trade
    receipt = goods('receipts')
    doc = ret(receipt, kind='supplier')
    initialize_database()
    initialize_database()
    assert call('GET', f'/api/goods/returns/{doc["id"]}')['is_posted']
    assert len(call('GET', f'/api/goods/returns/{doc["id"]}/movements')['inventory']) == 1


def test_original_cost_must_match_source_register(trade, connection):
    call, _, goods, _, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    connection.execute('UPDATE goods_issue_lines SET inventory_cost = 900 WHERE id = ?', (sale['lines'][0]['id'],))
    connection.commit()
    call('POST', '/api/goods/returns', 400, json={'kind': 'customer', 'source_id': sale['id'], 'date': '2026-10-03',
         'lines': [{'source_line_id': sale['lines'][0]['id'], 'quantity': 1}]})


def test_returnable_quantities_edit_delete_and_source_lifecycle(trade):
    call, _, goods, ret, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    doc = ret(sale, 2)
    url = f'/api/goods/return-sources/customer/{sale["id"]}'
    assert call('GET', url)['lines'][0]['returnable_quantity'] == 1
    assert call('GET', url + f'?exclude_id={doc["id"]}')['lines'][0]['returnable_quantity'] == 3
    payload = {'kind': 'customer', 'source_id': sale['id'], 'date': '2026-10-03',
               'lines': [{'source_line_id': sale['lines'][0]['id'], 'quantity': 1}]}
    call('PUT', f'/api/goods/returns/{doc["id"]}', 400, json=payload)
    call('DELETE', f'/api/goods/returns/{doc["id"]}', 400)
    call('POST', f'/api/goods/returns/{doc["id"]}/unpost')
    call('PUT', f'/api/goods/returns/{doc["id"]}', json=payload)
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('DELETE', f'/api/goods/issues/{sale["id"]}', 400)
    call('DELETE', f'/api/goods/returns/{doc["id"]}')
    call('DELETE', f'/api/goods/issues/{sale["id"]}')


def test_return_roles_do_not_allow_manager_posting(trade, connection):
    from fastapi import HTTPException
    from api.return_services import save_return
    call, _, goods, ret, _ = trade
    goods('receipts')
    sale = goods('issues', 3, 150)
    doc = ret(sale, post=False)
    manager = UserInfo(id=2, username='manager', role='manager', is_active=True)
    with pytest.raises(HTTPException) as err:
        change_return(connection, document_id=doc['id'], user=manager, action='post')
    assert err.value.status_code == 403
    with pytest.raises(HTTPException) as err:
        save_return(connection, payload={}, user=UserInfo(id=3, username='foreman', role='foreman', is_active=True))
    assert err.value.status_code == 403
    assert not call('GET', f'/api/goods/returns/{doc["id"]}')['is_posted']
