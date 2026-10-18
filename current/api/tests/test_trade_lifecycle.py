"""STEP-03: lifecycle, organization boundaries and rollback invariants."""
import pytest

from api.goods_services import post_goods_issue
from api.models.auth import UserInfo
from api.tests.conftest import login_headers
from api.tests.test_trade_returns import trade
from api.tests.trade_lifecycle_support import FailAfterInventoryInsert, InjectedPostingFailure, competing_issue_requests

ADMIN = UserInfo(id=1, username='admin', role='admin', is_active=True)


def scoped_user(call, client, orgs, role='viewer', name='scoped'):
    doc = call('POST', '/api/users', 201, json=dict(username=name, password='test-password', role=role, organization_ids=orgs))
    return doc, login_headers(client, name, 'test-password')


def test_posted_receipt_cannot_change_cost_or_debt(trade):
    call, _, goods, _, axes = trade
    receipt = goods('receipts')
    payload = dict(date=receipt['date'], **axes, lines=[{**receipt['lines'][0], 'price_without_vat': 200}])
    call('PUT', f'/api/goods/receipts/{receipt["id"]}', 400, json=payload)
    assert call('GET', f'/api/goods/receipts/{receipt["id"]}')['sum_without_vat'] == 1000
    balance = call('GET', '/api/goods/inventory/balances')[0]
    assert balance['quantity_balance'] == 10 and balance['sum_income'] == 1000
    assert call('GET', '/api/settlements/balance', params={'organization_id': axes['organization_id']})[0]['payable_balance'] == 1000


def test_receipt_cannot_be_cancelled_under_posted_issue(trade):
    call, _, goods, _, _ = trade
    receipt = goods('receipts')
    sale = goods('issues', 8, date='2026-10-02')
    path = f'/api/goods/receipts/{receipt["id"]}'
    call('POST', path + '/unpost', 400)
    assert call('GET', path)['is_posted']
    assert call('GET', '/api/goods/inventory/balances')[0]['quantity_balance'] == 2
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('POST', path + '/unpost')
    call('POST', path + '/post?auto_schedule=false')
    assert call('GET', '/api/goods/inventory/balances')[0]['quantity_balance'] == 10


def test_concurrent_last_unit_posts_exactly_once(trade, admin_headers):
    call, _, goods, _, _ = trade
    goods('receipts', 1)
    first = goods('issues', 1, date='2026-10-02', post=False)
    second = goods('issues', 1, date='2026-10-02', post=False)
    assert sorted(competing_issue_requests(first['id'], second['id'], admin_headers)) == [200, 400]
    assert sum(row['quantity_balance'] for row in call('GET', '/api/goods/inventory/balances')) == 0
    assert sum(call('GET', f'/api/goods/issues/{doc["id"]}')['is_posted'] for doc in (first, second)) == 1


def test_fault_after_stock_write_rolls_back_on_same_connection(trade, connection):
    call, _, goods, _, axes = trade
    goods('receipts')
    sale = goods('issues', 3, date='2026-10-02', post=False)
    with pytest.raises(InjectedPostingFailure):
        post_goods_issue(FailAfterInventoryInsert(connection), document_id=sale['id'], user=ADMIN, auto_schedule=False)
    assert not connection.in_transaction
    assert connection.execute('SELECT is_posted FROM goods_issues WHERE id = ?', (sale['id'],)).fetchone()[0] == 0
    for table in ('inventory_register', 'mutual_settlements_register'):
        assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE recorder_type = 'goods_issue' AND recorder_id = ?", (sale['id'],)).fetchone()[0] == 0
    assert call('GET', '/api/goods/inventory/balances')[0]['quantity_balance'] == 10
    assert call('GET', '/api/settlements/balance', params={'organization_id': axes['organization_id']})[0]['receivable_balance'] == 0
    call('POST', f'/api/goods/issues/{sale["id"]}/post?auto_schedule=false')
    assert call('GET', '/api/goods/inventory/balances')[0]['quantity_balance'] == 7


@pytest.fixture
def two_organizations(trade):
    call, ref, goods, ret, axes = trade
    other = dict(organization_id=ref('organizations', name='Private B'), counterparty_id=axes['counterparty_id'])
    other['contract_id'] = ref('contracts', number='Private B contract', **other)
    other['warehouse_id'] = ref('warehouses', name='Private B warehouse', organization_id=other['organization_id'])
    result = []
    for org in (axes, other):
        receipt = goods('receipts', **org)
        sale = goods('issues', 2, date='2026-10-02', **org)
        paid = call('POST', '/api/payments/transactions', 201, json=dict(date='2026-10-02', direction='incoming', amount=200,
                    counterparty_id=org['counterparty_id'], contract_id=org['contract_id']))
        call('POST', f'/api/payments/transactions/{paid["id"]}/post')
        returned = ret(sale)
        refund = call('POST', '/api/goods/return-refunds', 201,
                      json=dict(return_id=returned['id'], date='2026-10-04', amount=100))
        call('POST', f'/api/goods/return-refunds/{refund["id"]}/post')
        second_sale = goods('issues', 1, date='2026-10-04', **org)
        adjustment = call('POST', '/api/goods/price-adjustments', 201,
            json=dict(kind='sale', source_id=second_sale['id'], date='2026-10-05',
                      lines=[dict(source_line_id=second_sale['lines'][0]['id'], new_price=120)]))
        call('POST', f'/api/goods/price-adjustments/{adjustment["id"]}/post')
        destination = ref('warehouses', name='Owned destination', organization_id=org['organization_id'])
        transfer = call('POST', '/api/goods/transfers', 201, json=dict(date='2026-10-05', organization_id=org['organization_id'],
            source_warehouse_id=org['warehouse_id'], destination_warehouse_id=destination,
            lines=[dict(line_number=1, material_id=receipt['lines'][0]['material_id'], unit_id=receipt['lines'][0]['unit_id'], quantity=1)]))
        call('POST', f'/api/goods/transfers/{transfer["id"]}/post')
        opening = call('POST', '/api/goods/opening-balances', 201, json=dict(date='2026-09-01', organization_id=org['organization_id'],
            settlements=[dict(counterparty_id=org['counterparty_id'], contract_id=org['contract_id'], direction='payable', amount=10)]))
        call('POST', f'/api/goods/opening-balances/{opening["id"]}/post')
        payment = call('POST', '/api/payments/transactions', 201, json=dict(date='2026-10-06', direction='outgoing', amount=50,
            counterparty_id=org['counterparty_id'], contract_id=org['contract_id']))
        call('POST', f'/api/payments/transactions/{payment["id"]}/post')
        schedule = call('POST', '/api/payments/schedules', 201, json=dict(date_from='2026-10-01', date_to='2026-10-31',
            contract_id=org['contract_id'], lines=[]))
        result.append(dict(axes=org, receipt=receipt, sale=sale, returned=returned, refund=refund, adjustment=adjustment,
                           transfer=transfer, opening=opening, payment=payment, schedule=schedule))
    return result


def test_scoped_viewer_cannot_read_foreign_documents_or_write(trade, client, connection, two_organizations):
    call, _, _, _, axes = trade
    _, headers = scoped_user(call, client, [axes['organization_id']])
    own, foreign = two_organizations
    collection_keys = [('receipts', 'receipt'), ('issues', 'sale'), ('transfers', 'transfer'), ('returns', 'returned'),
                       ('return-refunds', 'refund'), ('price-adjustments', 'adjustment'), ('opening-balances', 'opening')]
    before = {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
              for table in ('inventory_register', 'mutual_settlements_register', 'payment_schedule_register')}
    for collection, key in collection_keys:
        for entry, status in [(own, 200), (foreign, 403)]:
            path = f'/api/goods/{collection}/{entry[key]["id"]}'
            assert client.get(path, headers=headers).status_code == status, path
            movement_kind = {'receipts': 'receipt', 'issues': 'issue'}.get(collection, collection)
            assert client.get(f'/api/goods/{movement_kind}/{entry[key]["id"]}/movements', headers=headers).status_code == status, path
        assert client.post(f'/api/goods/{collection}/{own[key]["id"]}/post', headers=headers).status_code == 403
    for collection, key in [('transactions', 'payment'), ('schedules', 'schedule')]:
        assert client.get(f'/api/payments/{collection}/{foreign[key]["id"]}', headers=headers).status_code == 403
        assert client.post(f'/api/payments/{collection}/{own[key]["id"]}/post', headers=headers).status_code == 403
    assert client.get(f'/api/payments/transactions/{foreign["payment"]["id"]}/movements', headers=headers).status_code == 403
    for kind, key in [('receipts', 'receipt'), ('issues', 'sale')]:
        path = f'/api/goods/{kind}/{foreign[key]["id"]}'
        assert client.get(path+'/lines/export', headers=headers).status_code == 403
    for url in [f'/api/goods/return-sources/customer/{foreign["sale"]["id"]}',
                f'/api/goods/return-sources/supplier/{foreign["receipt"]["id"]}',
                f'/api/goods/price-adjustment-sources/purchase/{foreign["receipt"]["id"]}',
                f'/api/goods/price-adjustment-sources/sale/{foreign["sale"]["id"]}']:
        assert client.get(url, headers=headers).status_code == 403, url
    for table, count in before.items():
        assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == count


def test_scope_filters_lists_pagination_reports_and_previews(trade, client, two_organizations):
    call, _, _, _, axes = trade
    _, headers = scoped_user(call, client, [axes['organization_id']], role='manager')
    own, foreign = two_organizations
    for collection, key in [('receipts', 'receipt'), ('issues', 'sale'), ('transfers', 'transfer'), ('returns', 'returned'),
                            ('price-adjustments', 'adjustment'), ('opening-balances', 'opening')]:
        response = client.get(f'/api/goods/{collection}', headers=headers).json()
        assert response['pagination']['total'] == len(response['data'])
        assert own[key]['id'] in [row['id'] for row in response['data']]
        assert all(row['organization_id'] == axes['organization_id'] for row in response['data'])
    for collection in ('transactions', 'schedules'):
        rows = client.get(f'/api/payments/{collection}', headers=headers).json()['data']
        assert rows and all(row['contract_id'] == axes['contract_id'] for row in rows)
    for kind in ('organizations', 'warehouses', 'contracts'):
        rows = client.get(f'/api/references/{kind}', headers=headers).json()['data']
        assert rows and all(row['id' if kind == 'organizations' else 'organization_id'] == axes['organization_id'] for row in rows)
    dates = dict(date_from='2026-09-01', date_to='2026-10-31')
    for path, params in [('/api/goods/inventory/balances', {}), ('/api/goods/inventory/movements', dates),
                         ('/api/goods/inventory/turnover', dates), ('/api/settlements/turnover', dates),
                         ('/api/settlements/overdue', {'date': '2026-10-31'})]:
        rows = client.get(path, params=params, headers=headers).json()['data']
        assert rows and all(row['organization_id'] == axes['organization_id'] for row in rows), path
        rows = client.get(path, params={**params, 'organization_id': foreign['axes']['organization_id']}, headers=headers).json()['data']
        assert not rows or path.endswith('/overdue')
    for direction in ('goods-receipts', 'goods-issues'):
        rows = client.post(f'/api/payments/schedules/preview/{direction}', json=dates, headers=headers).json()['data']
        assert rows and all(row['contract_id'] == axes['contract_id'] for row in rows)


def test_access_grants_are_admin_only_and_effective_for_existing_token(trade, client):
    call, _, goods, _, axes = trade
    receipt = goods('receipts', post=False)
    user, headers = scoped_user(call, client, [], role='admin')
    assert client.get('/api/users', headers=headers).status_code == 403
    assert client.get('/api/engineering/catalog', headers=headers).status_code == 403
    assert client.get('/api/engineering/tables/goods_receipts', headers=headers).status_code == 403
    path = f'/api/goods/receipts/{receipt["id"]}'
    assert client.get(path, headers=headers).status_code == 403
    assert client.put(f'/api/users/{user["id"]}/access', headers=headers,
        json=dict(role='admin', organization_ids=None)).status_code == 403
    call('PUT', f'/api/users/{user["id"]}/access', json=dict(role='manager', organization_ids=[axes['organization_id']]))
    assert client.get(path, headers=headers).status_code == 200
    assert client.post(path+'/post', headers=headers).status_code == 403
    call('PUT', f'/api/users/{user["id"]}/access', json=dict(role='viewer', organization_ids=None))
    assert client.get('/api/auth/me', headers=headers).json()['organization_ids'] is None
    assert client.get('/api/sync/status', headers=headers).status_code == 403


def test_scoped_admin_cannot_mutate_foreign_documents_or_forge_links(trade, client, two_organizations):
    call, _, _, _, axes = trade
    _, headers = scoped_user(call, client, [axes['organization_id']], role='admin')
    own, foreign = two_organizations
    for collection, key in [('receipts', 'receipt'), ('issues', 'sale'), ('transfers', 'transfer'), ('returns', 'returned'),
                            ('return-refunds', 'refund'), ('price-adjustments', 'adjustment'), ('opening-balances', 'opening')]:
        path = f'/api/goods/{collection}/{foreign[key]["id"]}'
        assert client.post(path+'/unpost', headers=headers).status_code == 403, path
        assert client.delete(path, headers=headers).status_code == 403, path
        if collection in ('receipts', 'issues', 'transfers'):
            assert client.post(path+'/copy', headers=headers).status_code == 403, path
    for collection, key in [('transactions', 'payment'), ('schedules', 'schedule')]:
        path = f'/api/payments/{collection}/{foreign[key]["id"]}'
        assert client.post(path+'/unpost', headers=headers).status_code == 403
        assert client.delete(path, headers=headers).status_code == 403
    payload = dict(date='2026-10-10', **axes, lines=[{key: own['receipt']['lines'][0][key]
                   for key in ('line_number', 'name', 'material_id', 'unit_id', 'quantity', 'price_without_vat', 'vat_rate')}])
    for forged in [dict(organization_id=foreign['axes']['organization_id']),
                   dict(based_on_type='goods_receipt', based_on_id=foreign['receipt']['id'])]:
        assert client.post('/api/goods/issues', headers=headers, json={**payload, **forged}).status_code == 403
    for kind, key in [('sale', 'sale'), ('purchase', 'receipt')]:
        response = client.post('/api/goods/price-adjustments', headers=headers,
            json=dict(kind=kind, source_id=foreign[key]['id'], date='2026-10-10',
                      lines=[dict(source_line_id=foreign[key]['lines'][0]['id'], new_price=90)]))
        assert response.status_code == 403
    assert client.post('/api/goods/return-refunds', headers=headers,
        json=dict(return_id=foreign['returned']['id'], date='2026-10-10', amount=1)).status_code == 403
    assert client.post('/api/payments/transactions', headers=headers,
        json=dict(date='2026-10-10', direction='outgoing', amount=1, counterparty_id=axes['counterparty_id'],
                  contract_id=foreign['axes']['contract_id'])).status_code == 403


def test_scope_cannot_be_expanded_by_user_settings_or_invalid_grants(trade, client):
    call, _, goods, _, axes = trade
    user, headers = scoped_user(call, client, [], role='manager')
    call('PUT', f'/api/users/{user["id"]}/access', 400, json=dict(role='admin', organization_ids=[999999]))
    me = client.get('/api/auth/me', headers=headers).json()
    assert me['role'] == 'manager' and me['organization_ids'] == []
    assert client.put('/api/system/user-settings/security', headers=headers,
                      json=dict(organization_ids=[axes['organization_id']], role='admin')).status_code == 200
    assert client.get('/api/auth/me', headers=headers).json()['organization_ids'] == []
    source = goods('receipts', post=False)
    assert client.get(f'/api/goods/receipts/{source["id"]}', headers=headers).status_code == 403
    assert client.get('/api/goods/receipts', headers=headers).json()['pagination']['total'] == 0
    assert client.get('/api/goods/inventory/balances', headers=headers).json()['data'] == []
    assert client.get('/api/sync/status').status_code == 401


def test_payment_reports_exclude_other_organizations(trade, client, two_organizations):
    call, _, _, _, axes = trade
    _, headers = scoped_user(call, client, [axes['organization_id']], role='viewer')
    response = client.get('/api/payments/register', headers=headers).json()['data']
    assert response['items'] and all(row['contract_id'] == axes['contract_id'] for row in response['items'])
    own = client.get('/api/payments/cashflow', headers=headers, params=dict(date_from='2026-10-01', date_to='2026-10-31')).json()['data']
    all_rows = call('GET', '/api/payments/cashflow', params=dict(date_from='2026-10-01', date_to='2026-10-31'))
    assert own and all_rows
    # Identical fixtures in two organizations: every numeric resource is doubled
    # only for the unrestricted administrator, including return-refund cash rows.
    for row, full in zip(own, all_rows):
        for key, value in row.items():
            if isinstance(value, (int, float)):
                assert full[key] == 2*value, (key, row, full)


def test_payment_history_scope_survives_legacy_contract_rebinding(trade, client, connection, two_organizations):
    call, _, _, _, axes = trade
    foreign = two_organizations[1]
    # Historical database inconsistency: ownership changed after posting facts.
    connection.execute('UPDATE contracts SET organization_id = ? WHERE id = ?',
                       (axes['organization_id'], foreign['axes']['contract_id']))
    connection.commit()
    _, headers = scoped_user(call, client, [axes['organization_id']])
    path = f'/api/payments/transactions/{foreign["payment"]["id"]}'
    assert client.get(path, headers=headers).status_code == 403
    assert client.get(path+'/movements', headers=headers).status_code == 403
    rows = client.get('/api/payments/transactions', headers=headers).json()['data']
    assert foreign['payment']['id'] not in [row['id'] for row in rows]
    rows = client.get('/api/payments/register', headers=headers).json()['data']['items']
    assert all(row['contract_id'] == axes['contract_id'] for row in rows)


def test_scoped_calendar_rejects_mixed_lines_and_unknown_organization(trade, client, two_organizations):
    call, _, _, _, axes = trade
    foreign = two_organizations[1]
    mixed = call('POST', '/api/payments/schedules', 201, json=dict(date_from='2026-10-01', date_to='2026-10-31',
        contract_id=axes['contract_id'], lines=[dict(line_number=1, direction='outgoing', category='other',
        planned_date='2026-10-10', planned_amount=10, contract_id=foreign['axes']['contract_id'])]))
    unknown = call('POST', '/api/payments/transactions', 201,
                   json=dict(date='2026-10-10', direction='outgoing', amount=1))
    _, headers = scoped_user(call, client, [axes['organization_id']], role='admin')
    assert client.get(f'/api/payments/schedules/{mixed["id"]}', headers=headers).status_code == 403
    assert mixed['id'] not in [row['id'] for row in client.get('/api/payments/schedules', headers=headers).json()['data']]
    assert client.get(f'/api/payments/transactions/{unknown["id"]}', headers=headers).status_code == 403
    assert client.post('/api/payments/transactions', headers=headers,
                       json=dict(date='2026-10-10', direction='outgoing', amount=1)).status_code == 403


def test_inventory_scope_uses_document_organization_after_warehouse_rebinding(trade, client, connection, two_organizations):
    call, _, _, _, axes = trade
    foreign = two_organizations[1]
    connection.execute('UPDATE warehouses SET organization_id = ? WHERE id = ?',
                       (axes['organization_id'], foreign['axes']['warehouse_id']))
    connection.commit()
    _, headers = scoped_user(call, client, [axes['organization_id']])
    for path, params in [('/api/goods/inventory/balances', {}),
                         ('/api/goods/inventory/movements', dict(date_from='2026-09-01', date_to='2026-10-31')),
                         ('/api/goods/inventory/turnover', dict(date_from='2026-09-01', date_to='2026-10-31'))]:
        rows = client.get(path, headers=headers, params=params).json()['data']
        assert rows and all(row['organization_id'] == axes['organization_id'] for row in rows)
        assert all(row['warehouse_id'] != foreign['axes']['warehouse_id'] for row in rows)
