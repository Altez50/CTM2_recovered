"""Adversarial regressions found during the independent STEP-03 review."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
import sqlite3

import pytest
from fastapi import HTTPException

from api import goods_services
from api.database import ensure_runtime_schema, get_connection, SCHEMA_TABLES_SQL, new_uuid
from api import services
from api.trade_access import TradeConnection
from api.models.auth import UserInfo
from api.tests.test_trade_returns import trade
from api.tests.test_trade_lifecycle import scoped_user
from api.tests.trade_lifecycle_support import competing_issue_requests
from api.warehouse_transfer_services import save_transfer

ADMIN = UserInfo(id=1, username='admin', role='admin', is_active=True)


@pytest.fixture
def access_case(trade, client):
    call, ref, goods, ret, axes = trade
    foreign = dict(organization_id=ref('organizations', name='Secret organization'),
                   counterparty_id=axes['counterparty_id'])
    foreign['contract_id'] = ref('contracts', number='SECRET CONTRACT', **foreign)
    foreign['warehouse_id'] = ref('warehouses', name='Secret warehouse', organization_id=foreign['organization_id'])
    user, headers = scoped_user(call, client, [axes['organization_id']], role='admin')
    return foreign, user, headers


def calendar_payload(contract_id, **line):
    return dict(date_from='2026-10-01', date_to='2026-10-31', contract_id=contract_id,
                lines=[dict(line_number=1, planned_date='2026-10-10', planned_amount=10,
                            contract_id=contract_id, **line)])


def payment_payload(axes, **extra):
    return dict(date='2026-10-10', direction='outgoing', amount=1,
                counterparty_id=axes['counterparty_id'], contract_id=axes['contract_id'], **extra)


def test_role_only_update_preserves_explicit_organization_restriction(trade, client, access_case):
    call, _, _, _, axes = trade
    _, user, headers = access_case
    result = call('PUT', f'/api/users/{user["id"]}/access', json={'role': 'viewer'})
    assert result['organization_ids'] == [axes['organization_id']]
    assert client.get('/api/auth/me', headers=headers).json()['organization_ids'] == [axes['organization_id']]


def test_foreign_contract_cannot_be_attached_to_own_goods_draft(trade, client, access_case):
    _, _, goods, _, axes = trade
    foreign, _, headers = access_case
    own = goods('receipts', post=False)
    response = client.post('/api/goods/issues', headers=headers,
        json=dict(date='2026-10-10', **{**axes, 'contract_id': foreign['contract_id']}, lines=own['lines']))
    assert response.status_code == 403, response.text


@pytest.mark.parametrize('link', ['linked_schedule_id', 'linked_line_id'])
def test_payment_rejects_foreign_calendar_even_with_own_line_contract(trade, client, access_case, link):
    call, _, _, _, axes = trade
    foreign, _, headers = access_case
    payload = calendar_payload(foreign['contract_id'])
    payload['lines'][0]['contract_id'] = axes['contract_id']
    hidden = call('POST', '/api/payments/schedules', 201, json=payload)
    ident = hidden['id'] if link == 'linked_schedule_id' else hidden['lines'][0]['id']
    response = client.post('/api/payments/transactions', headers=headers, json=payment_payload(axes, **{link: ident}))
    assert response.status_code == 403, response.text


@pytest.mark.parametrize('link', ['linked_schedule_id', 'linked_line_id'])
def test_existing_payment_foreign_links_are_checked_on_read_list_and_post(trade, client, access_case, link):
    call, _, _, _, axes = trade
    foreign, _, headers = access_case
    hidden = call('POST', '/api/payments/schedules', 201, json=calendar_payload(foreign['contract_id']))
    ident = hidden['id'] if link == 'linked_schedule_id' else hidden['lines'][0]['id']
    tx = call('POST', '/api/payments/transactions', 201, json=payment_payload(axes, allow_advance=True, **{link: ident}))
    path = f'/api/payments/transactions/{tx["id"]}'
    assert client.get(path, headers=headers).status_code == 403
    assert client.get(path+'/movements', headers=headers).status_code == 403
    listed = client.get('/api/payments/transactions?page_size=1', headers=headers).json()
    assert listed['pagination']['total'] == 0 and listed['data'] == []
    assert client.post(path+'/post', headers=headers).status_code == 403


@pytest.mark.parametrize('group', [True, False])
def test_calendar_rejects_foreign_references_including_groups(trade, client, access_case, group):
    call, _, goods, _, axes = trade
    foreign, _, headers = access_case
    source = goods('receipts', **foreign)
    payload = calendar_payload(axes['contract_id'], is_group=group,
                               source_ref=f'goods_receipt:{source["id"]}')
    if group:
        payload['lines'][0]['contract_id'] = foreign['contract_id']
    response = client.post('/api/payments/schedules', headers=headers, json=payload)
    assert response.status_code == 403, response.text


@pytest.mark.parametrize('group', [True, False])
def test_calendar_list_does_not_disclose_foreign_source_or_group(trade, client, access_case, group):
    call, _, goods, _, axes = trade
    foreign, _, headers = access_case
    source = goods('receipts', **foreign)
    payload = calendar_payload(axes['contract_id'], is_group=group, source_ref=f'goods_receipt:{source["id"]}')
    hidden = call('POST', '/api/payments/schedules', 201, json=payload)
    assert client.get(f'/api/payments/schedules/{hidden["id"]}', headers=headers).status_code == 403
    listed = client.get('/api/payments/schedules?page_size=1', headers=headers).json()
    assert listed['data'] == [] and listed['pagination']['total'] == 0


def test_goods_basis_must_check_complete_calendar_access(trade, client, access_case):
    call, _, goods, _, axes = trade
    foreign, _, headers = access_case
    payload = calendar_payload(axes['contract_id'])
    payload['lines'][0]['contract_id'] = foreign['contract_id']
    hidden = call('POST', '/api/payments/schedules', 201, json=payload)
    draft = goods('receipts', post=False)
    response = client.post('/api/goods/issues', headers=headers, json=dict(date='2026-10-10', **axes,
        lines=draft['lines'], based_on_type='payment_schedule', based_on_id=hidden['id']))
    assert response.status_code == 403, response.text


def test_post_revalidates_warehouse_owner(trade, access_case):
    call, _, goods, _, axes = trade
    foreign, _, _ = access_case
    draft = goods('receipts', post=False)
    call('PUT', f'/api/references/warehouses/{axes["warehouse_id"]}', json=dict(name='Reassigned', organization_id=foreign['organization_id']))
    call('POST', f'/api/goods/receipts/{draft["id"]}/post?auto_schedule=false', 400)
    assert call('GET', f'/api/goods/receipt/{draft["id"]}/movements')['inventory'] == []


def test_cannot_remove_payment_that_funded_posted_cash_refund(trade):
    call, _, goods, ret, axes = trade
    goods('receipts')
    sale = goods('issues', 1, date='2026-10-02')
    tx = call('POST', '/api/payments/transactions', 201, json={**payment_payload(axes), 'date':'2026-10-02', 'direction':'incoming', 'amount':100})
    call('POST', f'/api/payments/transactions/{tx["id"]}/post')
    returned = ret(sale)
    refund = call('POST', '/api/goods/return-refunds', 201, json=dict(return_id=returned['id'], date='2026-10-04', amount=100))
    call('POST', f'/api/goods/return-refunds/{refund["id"]}/post')
    call('POST', f'/api/payments/transactions/{tx["id"]}/unpost', 400)
    call('POST', f'/api/goods/return-refunds/{refund["id"]}/unpost')
    call('POST', f'/api/payments/transactions/{tx["id"]}/unpost')


def test_cannot_cancel_customer_return_used_in_later_cost(trade):
    call, _, goods, ret, _ = trade
    goods('receipts', 1)
    sale = goods('issues', 1, date='2026-10-02')
    returned = ret(sale)
    goods('receipts', 10, 300, date='2026-10-04')
    dependent = goods('issues', 1, date='2026-10-05')
    call('POST', f'/api/goods/returns/{returned["id"]}/unpost', 400)
    call('POST', f'/api/goods/issues/{dependent["id"]}/unpost')
    call('POST', f'/api/goods/returns/{returned["id"]}/unpost')


def test_failed_transfer_validation_releases_same_connection_transaction(trade, connection):
    _, _, goods, _, axes = trade
    source = goods('receipts')
    payload = dict(date='2026-10-10', organization_id=axes['organization_id'],
                   source_warehouse_id=axes['warehouse_id'], destination_warehouse_id=axes['warehouse_id'],
                   lines=[dict(line_number=1, material_id=source['lines'][0]['material_id'], unit_id=source['lines'][0]['unit_id'], quantity=1)])
    with pytest.raises(HTTPException):
        save_transfer(connection, payload=payload, user=ADMIN)
    assert not connection.in_transaction


def test_concurrent_requests_both_finish_auth_before_first_stock_read(trade, admin_headers):
    _, _, goods, _, _ = trade
    goods('receipts', 1)
    drafts = [goods('issues', 1, date='2026-10-02', post=False) for _ in range(2)]
    entered = []
    original_admin, original_balance = goods_services._require_admin, goods_services._inventory_balance
    def on_admin(user):
        original_admin(user)
        entered.append(user.id)
    def on_balance(*args, **kwargs):
        assert len(entered) == 2, 'Stock read started before both real HTTP sessions completed authentication'
        return original_balance(*args, **kwargs)
    with patch.object(goods_services, '_require_admin', on_admin), patch.object(goods_services, '_inventory_balance', on_balance):
        assert sorted(competing_issue_requests(drafts[0]['id'], drafts[1]['id'], admin_headers)) == [200, 400]


def test_runtime_migration_preserves_explicit_and_empty_grants(trade, client, connection, access_case):
    call, _, _, _, axes = trade
    _, user, headers = access_case
    empty, empty_headers = scoped_user(call, client, [], name='empty')
    ensure_runtime_schema(connection)
    connection.commit()
    assert client.get('/api/auth/me', headers=headers).json()['organization_ids'] == [axes['organization_id']]
    assert client.get('/api/auth/me', headers=empty_headers).json()['organization_ids'] == []


@pytest.mark.parametrize('action', ['update', 'delete'])
def test_reference_ownership_is_locked_before_permission_check(trade, connection, access_case, action):
    _, _, _, _, axes = trade
    foreign, user, _ = access_case
    principal = UserInfo(**user)
    selected, release, rebound = Event(), Event(), Event()
    original_get = services.get_reference
    def pause_read(conn, **kwargs):
        result = original_get(conn, **kwargs)
        if isinstance(conn, TradeConnection) and not selected.is_set():
            selected.set()
            assert release.wait(10)
        return result
    def change():
        raw = get_connection()
        try:
            scoped = TradeConnection(raw, principal)
            if action == 'update':
                services.update_reference(scoped, kind='contracts', item_id=axes['contract_id'],
                    payload=dict(number='Overwrite', organization_id=axes['organization_id'], counterparty_id=axes['counterparty_id']))
            else:
                services.soft_delete_reference(scoped, kind='contracts', item_id=axes['contract_id'])
            return 200
        except HTTPException as exc:
            raw.rollback()
            return exc.status_code
        finally:
            raw.close()
    def rebind():
        raw = get_connection()
        try:
            raw.execute('UPDATE contracts SET organization_id = ? WHERE id = ?', (foreign['organization_id'], axes['contract_id']))
            raw.commit()
            rebound.set()
        finally:
            raw.close()
    with patch.object(services, 'get_reference', pause_read), ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(change)
        assert selected.wait(10)
        second = pool.submit(rebind)
        won_before_release = rebound.wait(.3)
        release.set()
        result = first.result(timeout=10)
        second.result(timeout=10)
    if won_before_release:
        assert result == 403, 'A stale permission check mutated a reference now owned by another organization'
    row = connection.execute('SELECT organization_id FROM contracts WHERE id = ?', (axes['contract_id'],)).fetchone()
    assert row[0] == foreign['organization_id']


def test_current_migration_adds_legacy_warehouse_before_dimension_index():
    # A synthetic pre-warehouse schema, never a working/production database.
    legacy = SCHEMA_TABLES_SQL
    start = legacy.index('CREATE TABLE IF NOT EXISTS inventory_register (')
    end = legacy.index('\n);', start) + 3
    table = legacy[start:end].replace('    warehouse_id INTEGER,\n', '').replace('    movement_side TEXT,\n', '')
    table = table.replace('    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),\n', '')
    legacy = legacy[:start] + table + legacy[end:]
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(legacy)
        conn.execute('INSERT INTO organizations (id, name, uuid) VALUES (1, ?, ?)', ('Legacy', new_uuid()))
        conn.execute('INSERT INTO goods_receipts (id, number, date, organization_id, warehouse, uuid) VALUES (1, ?, ?, 1, ?, ?)',
                     ('Legacy receipt', '2026-10-01', 'Legacy warehouse', new_uuid()))
        conn.execute('''INSERT INTO inventory_register (recorder_type, recorder_id, line_number, period, quantity_income, uuid)
                        VALUES ('goods_receipt', 1, 1, '2026-10-01', 3, ?)''', (new_uuid(),))
        assert 'warehouse_id' not in [row['name'] for row in conn.execute('PRAGMA table_info(inventory_register)')]
        for _ in range(2):
            ensure_runtime_schema(conn)
            conn.commit()
            row = conn.execute('SELECT quantity_income, warehouse_id FROM inventory_register').fetchone()
            assert row['quantity_income'] == 3 and row['warehouse_id'] is not None
            assert conn.execute('SELECT COUNT(*) FROM warehouses').fetchone()[0] == 1
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        conn.close()


def lifecycle_document(trade, kind):
    call, ref, goods, ret, axes = trade
    receipt = goods('receipts')
    if kind == 'receipt':
        doc = goods('receipts', post=False)
        return f'/api/goods/receipts/{doc["id"]}', 'goods_receipts'
    if kind == 'issue':
        doc = goods('issues', 1, date='2026-10-02', post=False)
        return f'/api/goods/issues/{doc["id"]}', 'goods_issues'
    if kind == 'transfer':
        destination = ref('warehouses', name='Destination', organization_id=axes['organization_id'])
        doc = call('POST', '/api/goods/transfers', 201, json=dict(date='2026-10-02', organization_id=axes['organization_id'],
            source_warehouse_id=axes['warehouse_id'], destination_warehouse_id=destination,
            lines=[{key: receipt['lines'][0][key] for key in ('line_number', 'material_id', 'unit_id', 'quantity')}]))
        return f'/api/goods/transfers/{doc["id"]}', 'goods_transfers'
    if kind in ('return', 'refund'):
        sale = goods('issues', 1, date='2026-10-02')
        doc = ret(sale, post=kind == 'refund')
        if kind == 'return':
            return f'/api/goods/returns/{doc["id"]}', 'goods_returns'
        tx = call('POST', '/api/payments/transactions', 201,
            json={**payment_payload(axes), 'direction':'incoming', 'date':'2026-10-02', 'amount':100})
        call('POST', f'/api/payments/transactions/{tx["id"]}/post')
        refund = call('POST', '/api/goods/return-refunds', 201, json=dict(return_id=doc['id'], date='2026-10-04', amount=100))
        return f'/api/goods/return-refunds/{refund["id"]}', 'goods_return_refunds'
    if kind == 'adjustment':
        doc = call('POST', '/api/goods/price-adjustments', 201, json=dict(kind='purchase', source_id=receipt['id'], date='2026-10-02',
            lines=[dict(source_line_id=receipt['lines'][0]['id'], new_price=120)]))
        return f'/api/goods/price-adjustments/{doc["id"]}', 'goods_price_adjustments'
    if kind == 'opening':
        doc = call('POST', '/api/goods/opening-balances', 201, json=dict(date='2026-09-01', organization_id=axes['organization_id'],
            settlements=[dict(counterparty_id=axes['counterparty_id'], contract_id=axes['contract_id'], direction='payable', amount=10)]))
        return f'/api/goods/opening-balances/{doc["id"]}', 'opening_balances'
    if kind == 'payment':
        doc = call('POST', '/api/payments/transactions', 201, json=payment_payload(axes))
        return f'/api/payments/transactions/{doc["id"]}', 'payment_transactions'
    if kind == 'calendar':
        doc = call('POST', '/api/payments/schedules', 201, json=calendar_payload(axes['contract_id']))
        return f'/api/payments/schedules/{doc["id"]}', 'payment_schedules'
    raise AssertionError(kind)


@pytest.mark.parametrize('kind', ['receipt', 'issue', 'transfer', 'return', 'refund', 'adjustment', 'opening', 'payment', 'calendar'])
@pytest.mark.parametrize('action', ['post', 'unpost'])
def test_every_accounting_lifecycle_rolls_back_header_registers_and_sync(trade, connection, kind, action):
    call, _, _, _, _ = trade
    path, table = lifecycle_document(trade, kind)
    if action == 'unpost':
        call('POST', path+'/post?auto_schedule=false')
    ident = int(path.rsplit('/', 1)[1])
    tables = (table, 'inventory_register', 'mutual_settlements_register', 'payment_schedule_register', 'sync_changes')
    def snapshot():
        return {name: [dict(row) for row in connection.execute(f'SELECT * FROM {name} ORDER BY id')] for name in tables}
    before = snapshot()
    fired = []
    def fail_after_header(self, sql, params=()):
        result = self.connection.execute(sql, params)
        compact = ' '.join(sql.split())
        if compact.startswith(f'UPDATE {table} SET') and 'is_posted =' in compact:
            fired.append(True)
            raise RuntimeError('test-only fault after header and register writes')
        return result
    with patch.object(TradeConnection, 'execute', fail_after_header, create=True), pytest.raises(RuntimeError):
        call('POST', path+f'/{action}?auto_schedule=false')
    assert fired and snapshot() == before
    call('POST', path+f'/{action}?auto_schedule=false')
    assert bool(connection.execute(f'SELECT is_posted FROM {table} WHERE id = ?', (ident,)).fetchone()[0]) == (action == 'post')


def test_originating_sale_before_return_on_same_day_allows_unpost_and_repost(trade):
    call, _, goods, ret, _ = trade
    goods('receipts')
    sale = goods('issues', 1, date='2026-10-02')
    returned = ret(sale, date='2026-10-02')
    path = f'/api/goods/returns/{returned["id"]}'
    for _ in range(2):
        call('POST', path+'/unpost')
        call('POST', path+'/post')
    assert call('GET', path)['inventory_cost'] == 100
    balance = call('GET', '/api/goods/inventory/balances')[0]
    assert (balance['quantity_balance'], balance['sum_income']-balance['sum_expense']) == (10, 1000)


@pytest.mark.parametrize('expense_date', ['2026-10-02', '2026-10-03'])
def test_expense_after_return_same_or_later_day_keeps_cost_dependency(trade, expense_date):
    call, _, goods, ret, _ = trade
    goods('receipts', 10)
    sale = goods('issues', 1, date='2026-10-02')
    returned = ret(sale, date='2026-10-02')
    expense = goods('issues', 1, date=expense_date)
    call('POST', f'/api/goods/returns/{returned["id"]}/unpost', 400)
    assert call('GET', f'/api/goods/returns/{returned["id"]}')['is_posted']
    call('POST', f'/api/goods/issues/{expense["id"]}/unpost')
    call('POST', f'/api/goods/returns/{returned["id"]}/unpost')


def test_later_expense_of_another_series_does_not_block_return_cancellation(trade):
    from api.tests.test_trade_dimensions import line
    call, ref, goods, ret, _ = trade
    template = goods('receipts', post=False)
    material = template['lines'][0]['material_id']
    characteristic = ref('material-characteristics', name='Same characteristic', material_id=material)
    first, second = [ref('material-series', name=name, material_id=material, characteristic_id=characteristic) for name in ('First', 'Second')]
    goods('receipts', lines=[line(template, quantity=10, characteristic_id=characteristic, series_id=first),
                             line(template, line_number=2, quantity=10, characteristic_id=characteristic, series_id=second)])
    sale = goods('issues', date='2026-10-02', lines=[line(template, quantity=1, characteristic_id=characteristic, series_id=first)])
    returned = ret(sale, date='2026-10-02')
    goods('issues', date='2026-10-02', lines=[line(template, quantity=1, characteristic_id=characteristic, series_id=second)])
    call('POST', f'/api/goods/returns/{returned["id"]}/unpost')
