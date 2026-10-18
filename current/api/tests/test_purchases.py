"""STEP-05 procurement: real API, precise source quantities and account slices."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from api import purchase_services
from api.database import get_connection
from api.models.auth import UserInfo
from api.tests.test_trade_returns import trade
from api.tests.test_trade_dimensions import line
from api.tests.test_trade_lifecycle import scoped_user
from api.trade_access import TradeConnection
from fastapi.testclient import TestClient
from api.main import app
from api.tests.conftest import login_headers


@pytest.fixture
def purchase(trade):
    call, ref, goods, _, axes = trade
    template = goods('receipts', post=False)
    def order(mode='direct', quantity=10, price=100, service=False, post=True, **extra):
        warehouse = axes['warehouse_id']
        if mode == 'order':
            warehouse = ref('warehouses', name='Order warehouse', organization_id=axes['organization_id'], order_receipt_enabled=True)
        row = dict(line_number=1, name='Transport', line_type='service', quantity=quantity, price_without_vat=price, vat_rate=0) if service else line(template, quantity=quantity, price_without_vat=price)
        payload = dict(date='2026-10-01', **axes, lines=[row]) | extra
        payload['warehouse_id'] = None if service else warehouse
        doc = call('POST', '/api/purchases/orders', 201, json=payload)
        if post:
            doc = call('POST', f'/api/purchases/orders/{doc["id"]}/post')
        return doc
    def child(kind, source, quantity, date='2026-10-02', post=True, **extra):
        payload = dict(date=date, source_id=source['id'], lines=[dict(source_line_id=source['lines'][0]['id'], quantity=quantity, **extra)])
        doc = call('POST', f'/api/purchases/{kind}', 201, json=payload)
        if post:
            doc = call('POST', f'/api/purchases/{kind}/{doc["id"]}/post')
        return doc
    def balances():
        stock = call('GET', '/api/goods/inventory/balances')
        debt = call('GET', '/api/settlements/balance', params={'organization_id': axes['organization_id']})
        return (sum(row['quantity_balance'] for row in stock), sum(row['sum_income']-row['sum_expense'] for row in stock),
                sum(row['payable_balance'] for row in debt))
    return call, ref, goods, order, child, balances, axes, template


def test_partial_order_acceptance_and_remaining_cancellation(purchase):
    call, _, _, order, child, balance, _, _ = purchase
    source = order()
    assert balance() == (0, 0, 0)
    first = child('acquisitions', source, 4)
    assert balance() == (4, 400, 400)
    assert call('GET', f'/api/purchases/orders/{source["id"]}')['lines'][0]['open_quantity'] == 6
    cancel = child('cancellations', source, 6)
    assert call('GET', f'/api/purchases/orders/{source["id"]}')['lines'][0]['open_quantity'] == 0
    assert balance() == (4, 400, 400)
    call('POST', f'/api/purchases/cancellations/{cancel["id"]}/unpost')
    second = child('acquisitions', source, 6, date='2026-10-03')
    assert balance() == (10, 1000, 1000)
    assert call('GET', f'/api/purchases/orders/{source["id"]}')['lines'][0]['open_quantity'] == 0
    call('POST', f'/api/purchases/acquisitions/{second["id"]}/unpost')
    call('POST', f'/api/purchases/acquisitions/{second["id"]}/post')
    assert balance() == (10, 1000, 1000)


@pytest.mark.parametrize('finance_first', [False, True])
def test_order_warehouse_separates_physical_receipt_and_invoice_in_either_order(purchase, finance_first):
    call, _, _, order, child, balance, _, _ = purchase
    source = order(mode='order')
    first_kind, second_kind = ('acquisitions', 'receipt-orders') if finance_first else ('receipt-orders', 'acquisitions')
    first = child(first_kind, source, 10)
    assert balance() == ((0, 0, 1000) if finance_first else (10, 1000, 0))
    second = child(second_kind, source, 10, date='2026-10-03')
    assert balance() == (10, 1000, 1000)
    physical = first if first_kind == 'receipt-orders' else second
    finance = first if first_kind == 'acquisitions' else second
    assert call('GET', f'/api/purchases/acquisitions/{finance["id"]}/movements')['inventory'] == []
    call('POST', f'/api/purchases/acquisitions/{finance["id"]}/unpost')
    assert balance() == (10, 1000, 0)
    call('POST', f'/api/purchases/acquisitions/{finance["id"]}/post')
    call('POST', f'/api/purchases/receipt-orders/{physical["id"]}/unpost')
    assert balance() == (0, 0, 1000)
    call('POST', f'/api/purchases/receipt-orders/{physical["id"]}/post')
    assert balance() == (10, 1000, 1000)


@pytest.mark.parametrize('mode', ['direct', 'order'])
def test_agreed_shortage_has_separate_act_and_invoice_adjustment(purchase, mode):
    call, _, _, order, child, balance, _, _ = purchase
    source = order(mode=mode)
    physical = child('receipt-orders', source, 8) if mode == 'order' else None
    invoice = child('acquisitions', source, 10)
    act = child('discrepancies', invoice, 2, date='2026-10-03',
                **({'receipt_line_id': physical['lines'][0]['id']} if physical else {}))
    adjustment = child('quantity-adjustments', act, 2, date='2026-10-04')
    assert balance() == (8, 800, 800)
    status = call('GET', f'/api/purchases/orders/{source["id"]}')['lines'][0]
    assert status['shortage_quantity'] == 2 and status['open_quantity'] == 0
    call('POST', f'/api/purchases/acquisitions/{invoice["id"]}/unpost', 400)
    if physical:
        call('POST', f'/api/purchases/receipt-orders/{physical["id"]}/unpost', 400)
    call('POST', f'/api/purchases/quantity-adjustments/{adjustment["id"]}/unpost')
    call('POST', f'/api/purchases/quantity-adjustments/{adjustment["id"]}/post')
    assert balance() == (8, 800, 800)


def test_service_posts_actual_expense_and_debt_without_stock(purchase):
    call, _, _, order, child, balance, _, _ = purchase
    source = order(service=True, quantity=1, price=500)
    invoice = child('acquisitions', source, 1)
    assert balance() == (0, 0, 500)
    moves = call('GET', f'/api/purchases/acquisitions/{invoice["id"]}/movements')
    assert moves['inventory'] == [] and moves['expenses'][0]['expense_amount'] == 500
    assert sum(row['expense_amount'] for row in call('GET', '/api/purchases/expenses')) == 500
    call('POST', f'/api/purchases/acquisitions/{invoice["id"]}/unpost')
    assert balance() == (0, 0, 0) and call('GET', '/api/purchases/expenses') == []
    call('POST', f'/api/purchases/acquisitions/{invoice["id"]}/post')
    assert balance() == (0, 0, 500)


@pytest.mark.parametrize('mode', ['direct', 'order'])
def test_physical_cancellation_and_quantity_correction_obey_cost005(purchase, mode):
    call, _, goods, order, child, balance, axes, template = purchase
    source = order(mode=mode)
    physical = child('receipt-orders' if mode == 'order' else 'acquisitions', source, 10)
    sale = goods('issues', date='2026-10-04', warehouse_id=source['warehouse_id'], lines=[line(template, quantity=1)])
    before = balance()
    call('POST', f'/api/purchases/{physical["kind"]}/{physical["id"]}/unpost', 400)
    if mode == 'direct':
        act = child('discrepancies', physical, 2, date='2026-10-05')
        correction = child('quantity-adjustments', act, 2, date='2026-10-06', post=False)
        call('POST', f'/api/purchases/quantity-adjustments/{correction["id"]}/post', 400)
    assert balance() == before


def test_source_lines_dates_limits_and_duplicate_invoice_are_validated(purchase):
    call, _, _, order, child, balance, _, _ = purchase
    source = order()
    other = order()
    for quantity, source_line_id, date in [(11, source['lines'][0]['id'], '2026-10-02'),
                                          (1, other['lines'][0]['id'], '2026-10-02'),
                                          (1, source['lines'][0]['id'], '2026-09-30')]:
        call('POST', '/api/purchases/acquisitions', 400, json=dict(date=date, source_id=source['id'],
             lines=[dict(source_line_id=source_line_id, quantity=quantity)]))
    doc = child('acquisitions', source, 10)
    call('POST', f'/api/purchases/acquisitions/{doc["id"]}/post', 400)
    call('POST', '/api/purchases/acquisitions', 400, json=dict(date='2026-10-03', source_id=source['id'],
         lines=[dict(source_line_id=source['lines'][0]['id'], quantity=1)]))
    assert balance() == (10, 1000, 1000)


@pytest.mark.parametrize('role', ['viewer', 'manager', 'admin'])
@pytest.mark.parametrize('foreign', [False, True])
def test_purchase_access_and_role_are_checked_on_server(purchase, client, role, foreign):
    call, ref, _, order, _, _, axes, _ = purchase
    source = order()
    _, headers = scoped_user(call, client, [ref('organizations', name='Other') if foreign else axes['organization_id']], role=role)
    response = client.post('/api/purchases/acquisitions', headers=headers,
        json=dict(date='2026-10-02', source_id=source['id'], lines=[dict(source_line_id=source['lines'][0]['id'], quantity=1)]))
    allowed = not foreign and role != 'viewer'
    assert response.status_code == (201 if allowed else 403), response.text
    if allowed:
        ident = response.json()['data']['id']
        post = client.post(f'/api/purchases/acquisitions/{ident}/post', headers=headers)
        assert post.status_code == (200 if role == 'admin' else 403)
    if foreign:
        assert client.get(f'/api/purchases/orders/{source["id"]}', headers=headers).status_code == 403
        assert client.get('/api/purchases/orders', headers=headers).json()['pagination']['total'] == 0


@pytest.mark.parametrize('action', ['post', 'unpost'])
@pytest.mark.parametrize('kind', ['orders', 'acquisitions', 'receipt-orders', 'cancellations', 'discrepancies', 'quantity-adjustments', 'service-acquisition'])
def test_purchase_lifecycle_failure_rolls_back_all_actual_writes(purchase, connection, monkeypatch, kind, action):
    call, _, _, order, child, _, _, _ = purchase
    service = kind == 'service-acquisition'
    source = order(mode='direct' if service else 'order', post=kind != 'orders', service=service,
                   quantity=1 if service else 10, price=500 if service else 100)
    if service:
        kind = 'acquisitions'
        doc = child(kind, source, 1, post=False)
    elif kind == 'orders':
        doc = source
    elif kind in ('acquisitions', 'receipt-orders', 'cancellations'):
        doc = child(kind, source, 2, post=False)
    else:
        physical = child('receipt-orders', source, 8)
        invoice = child('acquisitions', source, 10)
        act = child('discrepancies', invoice, 2, receipt_line_id=physical['lines'][0]['id'], post=kind != 'discrepancies')
        doc = act if kind == 'discrepancies' else child(kind, act, 2, post=False)
    if action == 'unpost':
        call('POST', f'/api/purchases/{kind}/{doc["id"]}/post')
    tables = ('purchase_documents', 'purchase_lines', 'inventory_register', 'mutual_settlements_register', 'purchase_expense_register', 'purchase_events', 'sync_changes')
    def snapshot():
        return {table: [dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY id')] for table in tables}
    before = snapshot()
    original = purchase_services.record_event
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('fault after actual procurement writes')
    with monkeypatch.context() as patch:
        patch.setattr(purchase_services, 'record_event', fail)
        with pytest.raises(RuntimeError, match='actual procurement'):
            purchase_services.change_document(connection, doc['id'], kind, action,
                UserInfo(id=1, username='admin', role='admin', is_active=True))
    assert not connection.in_transaction and snapshot() == before
    call('POST', f'/api/purchases/{kind}/{doc["id"]}/{action}')


def test_packages_series_and_line_objects_are_preserved_in_physical_financial_and_shortage(purchase):
    call, ref, _, order, child, balance, _, template = purchase
    material = template['lines'][0]['material_id']
    package = ref('material-packages', name='Five units', material_id=material, factor=5)
    characteristic = ref('material-characteristics', name='Red', material_id=material)
    series = ref('material-series', name='Batch', material_id=material, characteristic_id=characteristic)
    object_id = ref('objects', name='Line object')
    source = order(mode='order', lines=[line(template, quantity=2, price_without_vat=500, vat_rate=20, package_id=package,
        characteristic_id=characteristic, series_id=series, object_id=object_id)])
    receipt = child('receipt-orders', source, 1.5)
    invoice = child('acquisitions', source, 2)
    act = child('discrepancies', invoice, .5, receipt_line_id=receipt['lines'][0]['id'])
    adjustment = child('quantity-adjustments', act, .5)
    assert balance() == (7.5, 750, 900)
    for doc in (receipt, invoice, act, adjustment):
        row = doc['lines'][0]
        assert (row['package_id'], row['characteristic_id'], row['series_id'], row['object_id'], row['vat_rate']) == (package, characteristic, series, object_id, 20)
    move = call('GET', f'/api/purchases/receipt-orders/{receipt["id"]}/movements')['inventory'][0]
    assert (move['quantity_income'], move['sum_income'], move['characteristic_id'], move['series_id'], move['object_id']) == (7.5, 750, characteristic, series, object_id)


def test_competing_partial_acceptances_reach_business_lock_after_both_authentications(purchase, client, admin_headers, monkeypatch):
    _, _, _, order, child, balance, _, _ = purchase
    source = order(quantity=1)
    first, second = [child('acquisitions', source, 1, post=False) for _ in range(2)]
    second_headers = login_headers(client)
    assert second_headers['Authorization'] != admin_headers['Authorization']
    authenticated = Barrier(2)
    checked, release, attempted, finished = Event(), Event(), Event(), Event()
    connections = {}
    original_admin, original_locked, original_limits = purchase_services._require_admin, purchase_services.locked_document, purchase_services.validate_limits
    def admin(user):
        original_admin(user)
        authenticated.wait(10)
    def locked(conn, ident):
        connections[ident] = conn.connection
        if ident == second['id']:
            assert checked.wait(10)
            attempted.set()
        return original_locked(conn, ident)
    def limits(conn, doc):
        original_limits(conn, doc)
        if doc['id'] == first['id']:
            checked.set()
            assert release.wait(10)
    def post(doc, headers, last=False):
        try:
            with TestClient(app) as http:
                return http.post(f'/api/purchases/acquisitions/{doc["id"]}/post', headers=headers).status_code
        finally:
            if last:
                finished.set()
    monkeypatch.setattr(purchase_services, '_require_admin', admin)
    monkeypatch.setattr(purchase_services, 'locked_document', locked)
    monkeypatch.setattr(purchase_services, 'validate_limits', limits)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(post, first, admin_headers)
        b = pool.submit(post, second, second_headers, True)
        try:
            assert checked.wait(10) and attempted.wait(10)
            assert connections[first['id']] is not connections[second['id']]
            assert not finished.wait(.1)
        finally:
            release.set()
        assert [a.result(timeout=10), b.result(timeout=10)] == [200, 400]
    assert balance() == (1, 100, 100)


def test_order_scheme_does_not_allow_cancel_of_already_invoiced_unreceived_goods(purchase):
    call, _, _, order, child, balance, _, _ = purchase
    source = order(mode='order')
    child('receipt-orders', source, 4)
    child('acquisitions', source, 10)
    call('POST', '/api/purchases/cancellations', 400, json=dict(date='2026-10-03', source_id=source['id'],
         lines=[dict(source_line_id=source['lines'][0]['id'], quantity=6)]))
    assert balance() == (4, 400, 1000)


def test_backdated_physical_receipt_cannot_revalue_consumed_stock(purchase):
    call, _, goods, order, child, balance, _, template = purchase
    source = order(mode='order', quantity=20)
    child('receipt-orders', source, 10)
    goods('issues', date='2026-10-04', warehouse_id=source['warehouse_id'], lines=[line(template, quantity=1)])
    late = child('receipt-orders', source, 5, date='2026-10-03', post=False)
    call('POST', f'/api/purchases/receipt-orders/{late["id"]}/post', 400)
    assert balance() == (9, 900, 0)


def test_order_warehouse_legacy_receipt_and_mode_changes_cannot_double_physical_stock(purchase):
    call, _, goods, order, child, balance, axes, template = purchase
    source = order(mode='order')
    legacy = goods('receipts', warehouse_id=source['warehouse_id'], post=False)
    call('POST', f'/api/goods/receipts/{legacy["id"]}/post?auto_schedule=false', 400)
    call('PUT', f'/api/references/warehouses/{source["warehouse_id"]}', 400,
         json=dict(name='Changed mode', organization_id=axes['organization_id'], order_receipt_enabled=False))
    renamed = call('PUT', f'/api/references/warehouses/{source["warehouse_id"]}',
         json=dict(name='Renamed without changing mode', organization_id=axes['organization_id']))
    assert renamed['order_receipt_enabled']
    child('receipt-orders', source, 10)
    child('acquisitions', source, 10)
    assert balance() == (10, 1000, 1000)


@pytest.mark.parametrize('owner', ['warehouse', 'contract'])
def test_post_revalidates_reference_owner_and_does_not_leave_partial_facts(purchase, owner):
    call, ref, _, order, child, balance, axes, _ = purchase
    source = order()
    draft = child('acquisitions', source, 1, post=False)
    foreign = ref('organizations', name='Rebound owner')
    if owner == 'warehouse':
        call('PUT', f'/api/references/warehouses/{source["warehouse_id"]}', json=dict(name='Rebound', organization_id=foreign))
    else:
        call('PUT', f'/api/references/contracts/{source["contract_id"]}', json=dict(number='Rebound', organization_id=foreign, counterparty_id=axes['counterparty_id']))
    call('POST', f'/api/purchases/acquisitions/{draft["id"]}/post', 400)
    assert balance() == (0, 0, 0)


def test_new_local_audit_does_not_break_legacy_sync_serializer(purchase, connection):
    from api.sync_runtime import collect_outgoing_changes
    _, _, _, order, child, _, _, _ = purchase
    source = order(service=True, quantity=1, price=500)
    child('acquisitions', source, 1)
    changes, cursor = collect_outgoing_changes(connection, since_change_id=0, limit=1000)
    assert cursor > 0 and changes
    assert all(row['entity_type'] != 'purchase_documents' for row in changes)
    assert connection.execute('SELECT COUNT(*) FROM purchase_events').fetchone()[0] == 4


def test_backdated_sale_cannot_bypass_posted_purchase_quantity_correction(purchase):
    call, _, goods, order, child, balance, _, template = purchase
    source = order()
    invoice = child('acquisitions', source, 10)
    act = child('discrepancies', invoice, 2, date='2026-10-03')
    child('quantity-adjustments', act, 2, date='2026-10-04')
    sale = goods('issues', date='2026-10-03', post=False, lines=[line(template, quantity=1)])
    call('POST', f'/api/goods/issues/{sale["id"]}/post?auto_schedule=false', 400)
    assert balance() == (8, 800, 800)


@pytest.mark.parametrize('mode', ['direct', 'order'])
def test_discrepancy_cannot_bind_foreign_physical_line(purchase, client, connection, mode):
    call, ref, _, order, child, _, axes, template = purchase
    source = order(mode=mode)
    invoice = child('acquisitions', source, 10)
    foreign = ref('organizations', name='Private physical owner')
    contract = ref('contracts', number='Private physical contract', organization_id=foreign, counterparty_id=axes['counterparty_id'])
    warehouse = ref('warehouses', name='Private physical warehouse', organization_id=foreign, order_receipt_enabled=True)
    other = call('POST', '/api/purchases/orders', 201, json=dict(date='2026-10-01', organization_id=foreign,
        counterparty_id=axes['counterparty_id'], contract_id=contract, warehouse_id=warehouse, lines=[line(template)]))
    other = call('POST', f'/api/purchases/orders/{other["id"]}/post')
    receipt = child('receipt-orders', other, 8)
    _, headers = scoped_user(call, client, [axes['organization_id']], role='manager')
    before = connection.execute('SELECT COUNT(*) FROM purchase_documents').fetchone()[0]
    response = client.post('/api/purchases/discrepancies', headers=headers, json=dict(date='2026-10-03', source_id=invoice['id'],
        lines=[dict(source_line_id=invoice['lines'][0]['id'], quantity=2, receipt_line_id=receipt['lines'][0]['id'])]))
    assert response.status_code == (400 if mode == 'direct' else 403), response.text
    assert connection.execute('SELECT COUNT(*) FROM purchase_documents').fetchone()[0] == before


def test_shortage_reconciles_split_invoices_against_a_single_physical_batch(purchase):
    call, _, _, order, child, balance, _, _ = purchase
    source = order(mode='order')
    child('acquisitions', source, 4)
    receipt = child('receipt-orders', source, 8, date='2026-10-03')
    invoice = child('acquisitions', source, 6, date='2026-10-03')
    act = child('discrepancies', invoice, 2, date='2026-10-04', receipt_line_id=receipt['lines'][0]['id'])
    child('quantity-adjustments', act, 2, date='2026-10-05')
    assert balance() == (8, 800, 800)
    call('POST', '/api/purchases/discrepancies', 400, json=dict(date='2026-10-05', source_id=invoice['id'],
         lines=[dict(source_line_id=invoice['lines'][0]['id'], quantity=1, receipt_line_id=receipt['lines'][0]['id'])]))


def test_multiline_direct_quantity_adjustment_ignores_own_prior_line_but_preserves_cost(purchase):
    call, _, _, order, _, balance, _, template = purchase
    source = order(lines=[line(template, line_number=1, quantity=10, price_without_vat=100),
                          line(template, line_number=2, quantity=10, price_without_vat=200)])
    def linked(kind, source, quantity, date):
        doc = call('POST', f'/api/purchases/{kind}', 201, json=dict(date=date, source_id=source['id'],
                   lines=[dict(source_line_id=line['id'], quantity=quantity) for line in source['lines']]))
        return call('POST', f'/api/purchases/{kind}/{doc["id"]}/post')
    invoice = linked('acquisitions', source, 10, '2026-10-02')
    assert balance() == (20, 3000, 3000)
    act = linked('discrepancies', invoice, 2, '2026-10-03')
    correction = linked('quantity-adjustments', act, 2, '2026-10-04')
    assert balance() == (16, 2400, 2400)
    call('POST', f'/api/purchases/quantity-adjustments/{correction["id"]}/unpost')
    assert balance() == (20, 3000, 3000)
    call('POST', f'/api/purchases/quantity-adjustments/{correction["id"]}/post')
    assert balance() == (16, 2400, 2400)
