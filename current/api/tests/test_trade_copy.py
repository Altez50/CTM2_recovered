"""STEP-04: real API copies are independent drafts and never duplicate facts."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException

from api import goods_services
from api.database import get_connection
from api.models.auth import UserInfo
from api.tests.test_trade_returns import trade
from api.tests.test_trade_dimensions import line
from api.tests.test_trade_lifecycle import scoped_user
from api.trade_access import TradeConnection


def facts(connection):
    return {table: [dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY id')]
            for table in ('inventory_register', 'mutual_settlements_register', 'payment_schedule_register',
                          'payment_schedules', 'payment_schedule_lines')}


def payload(document, **changes):
    keys = ('number', 'date', 'organization_id', 'warehouse_id', 'counterparty_id', 'contract_id',
            'object_id', 'estimate_id', 'responsible_id', 'description', 'lines')
    return {key: document.get(key) for key in keys} | changes


def test_copy_posted_receipt_leaves_exact_original_stock_and_debt(trade, connection):
    call, _, goods, _, axes = trade
    source = goods('receipts', 10, 100, vat=0)
    before = facts(connection)
    copied = call('POST', f'/api/goods/receipts/{source["id"]}/copy', 201)
    assert copied['id'] != source['id'] and copied['uuid'] != source['uuid']
    assert not copied['is_posted'] and copied['posted_at'] is None
    assert copied['lines'][0]['id'] != source['lines'][0]['id']
    assert copied['lines'][0]['uuid'] != source['lines'][0]['uuid']
    assert facts(connection) == before
    balance = call('GET', '/api/goods/inventory/balances')[0]
    assert (balance['quantity_balance'], balance['sum_income'] - balance['sum_expense']) == (10, 1000)
    assert call('GET', '/api/settlements/balance', params={'organization_id': axes['organization_id']})[0]['payable_balance'] == 1000
    assert call('GET', f'/api/goods/receipts/{source["id"]}') == source


@pytest.mark.parametrize('kind', ['receipts', 'issues'])
def test_copy_preserves_all_input_analytics_without_posting_dependencies(trade, connection, kind):
    call, ref, goods, _, axes = trade
    template = goods('receipts', post=False)
    material = template['lines'][0]['material_id']
    package = ref('material-packages', name='Five units', material_id=material, factor=5)
    characteristic = ref('material-characteristics', name='Red', material_id=material)
    series = ref('material-series', name='Batch', material_id=material, characteristic_id=characteristic)
    header_object = ref('objects', name='Header object')
    line_object = ref('objects', name='Line object')
    person = ref('persons', full_name='Copy responsible')
    estimate = call('POST', '/api/documents/estimates', 201, json=dict(number='COPY-ESTIMATE', date='2026-10-01',
                    contract_id=axes['contract_id'], customer_id=axes['counterparty_id'], contractor_id=axes['organization_id'], lines=[]))['id']
    rows = [line(template, line_number=i, quantity=10, object_id=line_object, unit='custom unit',
                 drawing_code=f'D-{i}', note=f'Note {i}', package_id=package,
                 characteristic_id=characteristic, series_id=series) for i in (1, 2)]
    stock = goods('receipts', lines=rows, object_id=header_object)
    extra = dict(based_on_type='goods_receipt', based_on_id=stock['id'], based_on_number=stock['number']) if kind == 'issues' else {}
    source = goods(kind, date='2026-10-02', post=False, lines=rows, object_id=header_object,
                   estimate_id=estimate, responsible_id=person, description='Original description', **extra)
    call('POST', f'/api/goods/{kind}/{source["id"]}/post')
    source = call('GET', f'/api/goods/{kind}/{source["id"]}')
    before = facts(connection)
    copied = call('POST', f'/api/goods/{kind}/{source["id"]}/copy', 201)
    assert copied['id'] != source['id'] and copied['uuid'] != source['uuid']
    assert not copied['is_posted'] and copied['posted_at'] is None
    for key in (*axes, 'object_id', 'estimate_id', 'responsible_id', 'description'):
        assert copied[key] == source[key], key
    assert all(copied.get(key) is None for key in ('based_on_type', 'based_on_id', 'based_on_number'))
    fields = ('line_number', 'name', 'material_id', 'object_id', 'unit_id', 'unit', 'quantity',
              'price_without_vat', 'vat_rate', 'drawing_code', 'note', 'package_id',
              'characteristic_id', 'series_id', 'conversion_factor', 'base_quantity', 'base_unit_id')
    assert not ({row['id'] for row in copied['lines']} & {row['id'] for row in source['lines']})
    assert not ({row['uuid'] for row in copied['lines']} & {row['uuid'] for row in source['lines']})
    for old, new in zip(source['lines'], copied['lines'], strict=True):
        assert {key: new[key] for key in fields} == {key: old[key] for key in fields}
        if kind == 'issues':
            # A draft has no calculated cost until it is posted independently.
            assert new['inventory_cost'] is None and old['inventory_cost'] > 0
    movement = call('GET', f'/api/goods/{"receipt" if kind == "receipts" else "issue"}/{copied["id"]}/movements')
    assert movement['inventory'] == movement['settlements'] == []
    copied['lines'][0]['quantity'] = 1
    copied['lines'][0]['price_without_vat'] = 321
    call('PUT', f'/api/goods/{kind}/{copied["id"]}', json=payload(copied, description='Only the copy changed'))
    assert call('GET', f'/api/goods/{kind}/{source["id"]}') == source
    assert facts(connection) == before


@pytest.mark.parametrize('kind', ['receipts', 'issues'])
def test_changing_original_draft_and_deleting_copy_do_not_cross_document_identity(trade, kind):
    call, _, goods, _, _ = trade
    source = goods(kind, post=False)
    copied = call('POST', f'/api/goods/{kind}/{source["id"]}/copy', 201)
    source['lines'][0]['quantity'] = 2
    call('PUT', f'/api/goods/{kind}/{source["id"]}', json=payload(source, description='Only original changed'))
    assert call('GET', f'/api/goods/{kind}/{copied["id"]}') == copied
    call('DELETE', f'/api/goods/{kind}/{copied["id"]}')
    assert call('GET', f'/api/goods/{kind}/{source["id"]}')['lines'][0]['quantity'] == 2


@pytest.mark.parametrize('role', ['viewer', 'manager', 'admin'])
@pytest.mark.parametrize('foreign', [False, True])
def test_copy_requires_write_role_and_access_to_source(trade, client, connection, role, foreign):
    call, ref, goods, _, axes = trade
    source = goods('receipts')
    org = ref('organizations', name='Other organization') if foreign else axes['organization_id']
    _, headers = scoped_user(call, client, [org], role=role)
    before = facts(connection)
    count = connection.execute('SELECT COUNT(*) FROM goods_receipts').fetchone()[0]
    response = client.post(f'/api/goods/receipts/{source["id"]}/copy', headers=headers)
    allowed = not foreign and role != 'viewer'
    assert response.status_code == (201 if allowed else 403), response.text
    assert connection.execute('SELECT COUNT(*) FROM goods_receipts').fetchone()[0] == count + int(allowed)
    if allowed:
        copied = response.json()['data']
        assert not copied['is_posted'] and copied['posted_at'] is None
        if role == 'manager':
            assert client.post(f'/api/goods/receipts/{copied["id"]}/post', headers=headers).status_code == 403
    assert call('GET', f'/api/goods/receipts/{source["id"]}') == source
    assert facts(connection) == before


def test_copy_failure_rolls_back_new_header_lines_and_sync_on_same_connection(trade, connection, monkeypatch):
    _, _, goods, _, _ = trade
    source = goods('receipts')
    tables = ('goods_receipts', 'goods_receipt_lines', 'sync_changes')
    def snapshot():
        return {name: [dict(row) for row in connection.execute(f'SELECT * FROM {name} ORDER BY id')] for name in tables}
    before = snapshot()
    original = goods_services.register_sync_change
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('after copied header, lines and sync')
    with monkeypatch.context() as patch:
        patch.setattr(goods_services, 'register_sync_change', fail)
        with pytest.raises(RuntimeError, match='after copied'):
            goods_services.copy_goods_receipt(connection, document_id=source['id'],
                user=UserInfo(id=1, username='admin', role='admin', is_active=True))
    assert not connection.in_transaction and snapshot() == before
    copied = goods_services.copy_goods_receipt(connection, document_id=source['id'],
        user=UserInfo(id=1, username='admin', role='admin', is_active=True))
    assert copied['id'] != source['id'] and not copied['is_posted']


@pytest.mark.parametrize('kind', ['receipts', 'issues'])
def test_copy_checks_source_owner_under_the_source_lock(trade, client, connection, monkeypatch, kind):
    call, ref, goods, _, axes = trade
    source = goods(kind, post=False)
    foreign_org = ref('organizations', name='Rebound owner')
    principal, _ = scoped_user(call, client, [axes['organization_id']], role='manager')
    checked, release, rebinding, rebound = Event(), Event(), Event(), Event()
    original = goods_services._get_document
    def pause(conn, **kwargs):
        result = original(conn, **kwargs)
        if kwargs['document_id'] == source['id'] and not checked.is_set():
            checked.set()
            assert release.wait(10)
        return result
    monkeypatch.setattr(goods_services, '_get_document', pause)
    table = 'goods_receipts' if kind == 'receipts' else 'goods_issues'
    def write():
        raw = get_connection()
        try:
            service = goods_services.copy_goods_receipt if kind == 'receipts' else goods_services.copy_goods_issue
            service(TradeConnection(raw, UserInfo(**principal)), document_id=source['id'], user=UserInfo(**principal))
            return 201
        except HTTPException as exc:
            return exc.status_code
        finally:
            raw.close()
    def rebind():
        raw = get_connection()
        try:
            rebinding.set()
            raw.execute(f'UPDATE {table} SET organization_id = ? WHERE id = ?', (foreign_org, source['id']))
            raw.commit()
            rebound.set()
        finally:
            raw.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write)
        assert checked.wait(10)
        second = pool.submit(rebind)
        try:
            assert rebinding.wait(10)
            changed_before_copy = rebound.wait(.3)
        finally:
            release.set()
        status = first.result(timeout=10)
        second.result(timeout=10)
    assert not changed_before_copy, 'Source ownership was not protected while copying its data'
    assert status == 201
    assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 2
