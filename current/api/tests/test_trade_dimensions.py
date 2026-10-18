"""STEP-02 real API and accounting invariants across every local trade path."""
import sqlite3

import pytest
from fastapi import HTTPException

from api.database import initialize_database
from api.inventory_dimensions import ensure_schema
from api.models.auth import UserInfo
from api.opening_balance_services import change_opening
from api.sync_runtime import _serialize_goods_receipts, _upsert_goods_receipt_entity, _mark_goods_receipt_deleted
from api.tests.conftest import login_headers
from api.tests.test_trade_returns import trade
from api.tests.test_price_adjustments import create


def line(source, **extra):
    return {key: source['lines'][0][key] for key in ('line_number', 'name', 'material_id', 'unit_id', 'quantity', 'price_without_vat', 'vat_rate')} | extra


def variants(ref, source):
    material = source['lines'][0]['material_id']
    red = ref('material-characteristics', name='Red', material_id=material)
    blue = ref('material-characteristics', name='Blue', material_id=material)
    s1 = ref('material-series', name='S1', material_id=material, characteristic_id=red)
    s2 = ref('material-series', name='S2', material_id=material, characteristic_id=blue)
    return dict(characteristic_id=red, series_id=s1), dict(characteristic_id=blue, series_id=s2)


def balances(call, **params):
    return call('GET', '/api/goods/inventory/balances', params=params)


def opening_payload(source, axes, **extra):
    return dict(date='2026-10-01', organization_id=axes['organization_id'],
        inventory=[dict(material_id=source['lines'][0]['material_id'], unit_id=source['lines'][0]['unit_id'],
                        warehouse_id=axes['warehouse_id'], quantity=10, cost=1000)],
        settlements=[dict(counterparty_id=axes['counterparty_id'], contract_id=axes['contract_id'], direction=direction, amount=amount)
                     for direction, amount in [('payable', 1200), ('receivable', 540)]]) | extra


def test_packages_use_base_stock_and_price_per_package(trade):
    call, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    package = ref('material-packages', name='Box of 12', material_id=template['lines'][0]['material_id'], factor=12)
    receipt = goods('receipts', lines=[line(template, quantity=2, price_without_vat=1200, package_id=package)])
    assert receipt['sum_without_vat'] == 2400
    assert receipt['lines'][0]['quantity'] == 2
    assert receipt['lines'][0]['base_quantity'] == 24
    sale = goods('issues', 5, 150, date='2026-10-02')
    assert sale['lines'][0]['inventory_cost'] == 500
    row = balances(call)[0]
    assert (row['quantity_balance'], row['sum_income']-row['sum_expense'], row['average_price']) == (19, 1900, 100)
    copy = call('POST', f'/api/goods/receipts/{receipt["id"]}/copy', 201)
    assert copy['lines'][0]['package_id'] == package
    assert copy['lines'][0]['base_quantity'] == 24
    call('PUT', f'/api/references/material-packages/{package}', 400,
         json=dict(name='Box of 10', material_id=template['lines'][0]['material_id'], factor=10))
    call('DELETE', f'/api/references/material-packages/{package}', 400)


@pytest.mark.parametrize('kind', ['customer', 'supplier'])
def test_packaged_returns_reverse_base_quantity_and_original_cost(trade, kind):
    call, ref, goods, ret, _ = trade
    template = goods('receipts', post=False)
    package = ref('material-packages', name='12 units', material_id=template['lines'][0]['material_id'], factor=12)
    receipt = goods('receipts', lines=[line(template, quantity=2, price_without_vat=1200, package_id=package)])
    source = goods('issues', date='2026-10-02', lines=[line(template, quantity=1, price_without_vat=1800, package_id=package)]) if kind == 'customer' else receipt
    returned = ret(source, quantity=.5, kind=kind)
    assert returned['inventory_cost'] == 600
    move = call('GET', f'/api/goods/returns/{returned["id"]}/movements')['inventory'][0]
    assert move['quantity_income' if kind == 'customer' else 'quantity_expense'] == 6
    assert returned['lines'][0]['base_quantity'] == 6
    call('POST', f'/api/goods/returns/{returned["id"]}/unpost')
    call('POST', f'/api/goods/returns/{returned["id"]}/post')
    assert len(call('GET', f'/api/goods/returns/{returned["id"]}/movements')['inventory']) == 1


def test_series_stock_cost_availability_and_reports_are_isolated(trade):
    call, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    red, blue = variants(ref, template)
    goods('receipts', lines=[line(template, quantity=5, price_without_vat=100, **red),
                            line(template, line_number=2, quantity=7, price_without_vat=300, **blue)])
    sale = goods('issues', date='2026-10-02', lines=[line(template, quantity=2, price_without_vat=150, **red)])
    assert sale['lines'][0]['inventory_cost'] == 200
    rows = balances(call)
    assert {(r['characteristic_id'], r['series_id']): (r['quantity_balance'], r['average_price']) for r in rows} == {
        tuple(red.values()): (3, 100), tuple(blue.values()): (7, 300)}
    excess = goods('issues', date='2026-10-02', post=False, lines=[line(template, quantity=4, **red)])
    call('POST', f'/api/goods/issues/{excess["id"]}/post', 400)
    unspecified = goods('issues', 1, post=False)
    call('POST', f'/api/goods/issues/{unspecified["id"]}/post', 400)
    assert len(balances(call, **red)) == 1
    moves = call('GET', '/api/goods/inventory/movements', params=dict(date_from='2026-10-02', date_to='2026-10-02', **red))
    assert len(moves) == 1 and moves[0]['series_name'] == 'S1'
    doc_moves = call('GET', f'/api/goods/issue/{sale["id"]}/movements')['inventory']
    assert doc_moves[0]['series_id'] == red['series_id']
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('POST', f'/api/goods/issues/{sale["id"]}/post')
    assert balances(call, **red)[0]['quantity_balance'] == 3


def test_new_dimensions_are_preserved_in_transfer_return_and_price_corrections(trade):
    call, ref, goods, ret, axes = trade
    template = goods('receipts', post=False)
    red, blue = variants(ref, template)
    package = ref('material-packages', name='Pair', material_id=template['lines'][0]['material_id'], factor=2)
    receipt = goods('receipts', lines=[line(template, quantity=5, price_without_vat=200, package_id=package, **red),
                            line(template, line_number=2, quantity=7, price_without_vat=300, **blue)])
    # A red expense does not block a blue-only purchase correction.
    sale = goods('issues', date='2026-10-02', lines=[line(template, quantity=1, **red)])
    adjustment = create(call, receipt, kind='purchase', date='2026-10-04', lines=[{'source_line_id': receipt['lines'][1]['id'], 'new_price': 250}])
    assert adjustment['lines'][0]['series_id'] == blue['series_id']
    call('POST', f'/api/goods/price-adjustments/{adjustment["id"]}/unpost')
    call('POST', f'/api/goods/price-adjustments/{adjustment["id"]}/post')
    backdated = goods('issues', date='2026-10-03', post=False, lines=[line(template, quantity=1, **blue)])
    call('POST', f'/api/goods/issues/{backdated["id"]}/post', 400)
    customer_return = ret(sale)
    assert customer_return['lines'][0]['series_id'] == red['series_id']
    returned_move = call('GET', f'/api/goods/returns/{customer_return["id"]}/movements')['inventory'][0]
    assert returned_move['characteristic_id'] == red['characteristic_id']
    destination = ref('warehouses', name='New warehouse', organization_id=axes['organization_id'])
    transfer = call('POST', '/api/goods/transfers', 201, json=dict(date='2026-10-05', organization_id=axes['organization_id'],
        source_warehouse_id=axes['warehouse_id'], destination_warehouse_id=destination,
        lines=[dict(line_number=1, material_id=template['lines'][0]['material_id'], unit_id=template['lines'][0]['unit_id'],
                    quantity=2, package_id=package, **red)]))
    path = f'/api/goods/transfers/{transfer["id"]}'
    call('POST', path + '/post')
    moves = call('GET', path + '/movements')['inventory']
    assert sum(m['quantity_income'] for m in moves) == 4
    assert sum(m['sum_income'] for m in moves) == 400
    assert all(m['series_id'] == red['series_id'] for m in moves)
    assert call('POST', path + '/copy', 201)['lines'][0]['series_id'] == red['series_id']
    assert balances(call, warehouse_id=destination, **red)[0]['quantity_balance'] == 4
    call('POST', path + '/unpost')
    call('POST', path + '/post')
    assert len(call('GET', path + '/movements')['inventory']) == 2


def test_packaged_purchase_correction_revalues_cost_without_quantity(trade):
    call, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    package = ref('material-packages', name='12', material_id=template['lines'][0]['material_id'], factor=12)
    receipt = goods('receipts', lines=[line(template, quantity=2, price_without_vat=1200, package_id=package)])
    correction = create(call, receipt, kind='purchase', price=1080)
    assert correction['delta_without_vat'] == -240
    row = balances(call)[0]
    assert row['quantity_balance'] == 24 and row['average_price'] == 90
    sale = goods('issues', 1, 150, date='2026-10-04')
    assert sale['lines'][0]['inventory_cost'] == 90
    call('POST', f'/api/goods/price-adjustments/{correction["id"]}/unpost', 400)


def test_invalid_analytic_ownership_and_reference_permissions(trade, connection, client):
    call, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    red, blue = variants(ref, template)
    call('POST', '/api/goods/receipts', 400, json=dict(date='2026-10-01', organization_id=template['organization_id'],
        warehouse_id=template['warehouse_id'], lines=[line(template, **(red | {'series_id': blue['series_id']}))]))
    other = ref('materials', name='Other', unit_id=template['lines'][0]['unit_id'])
    foreign = ref('material-characteristics', name='Foreign', material_id=other)
    call('POST', '/api/goods/receipts', 400, json=dict(date='2026-10-01', organization_id=template['organization_id'],
        warehouse_id=template['warehouse_id'], lines=[line(template, characteristic_id=foreign)]))
    foreman = login_headers(client, 'foreman', 'foreman')
    assert client.post('/api/references/material-packages', headers=foreman, json=dict(name='x', material_id=other, factor=12)).status_code == 403
    call('POST', '/api/references/material-packages', 422, json=dict(name='x', material_id=other, factor=0))
    rows = call('GET', '/api/references/material-characteristics', params=dict(material_id=other))
    assert [row['id'] for row in rows] == [foreign]


def test_initial_balances_have_own_recorder_and_next_day_opening_resources(trade):
    call, _, goods, _, axes = trade
    template = goods('receipts', post=False)
    doc = call('POST', '/api/goods/opening-balances', 201, json=opening_payload(template, axes))
    path = f'/api/goods/opening-balances/{doc["id"]}'
    call('POST', path + '/post')
    rows = call('GET', '/api/goods/inventory/turnover', params=dict(date_from='2026-10-02', date_to='2026-10-02'))
    assert len(rows) == 1
    assert (rows[0]['quantity_opening'], rows[0]['cost_opening'], rows[0]['quantity_income']) == (10, 1000, 0)
    turnover = call('GET', '/api/settlements/turnover', params=dict(date_from='2026-10-02', date_to='2026-10-02'))[0]
    assert (turnover['payable_opening'], turnover['receivable_opening'], turnover['payable_accrual_turnover'], turnover['receivable_accrual_turnover']) == (1200, 540, 0, 0)
    moves = call('GET', path + '/movements')
    assert len(moves['inventory']) == 1 and len(moves['settlements']) == 2
    assert all(row['recorder_type'] == 'opening_balance' for row in moves['inventory'] + moves['settlements'])
    assert all(not row['is_posted'] for row in call('GET', '/api/goods/receipts'))
    call('POST', path + '/post', 400)
    call('PUT', path, 400, json=opening_payload(template, axes))
    call('POST', path + '/unpost')
    assert balances(call) == []
    call('POST', path + '/post')
    assert balances(call)[0]['quantity_balance'] == 10
    initialize_database()
    initialize_database()
    assert call('GET', path)['is_posted']


def test_initial_balances_roles_foreign_axes_dependencies_and_atomicity(trade, client, connection):
    call, ref, goods, _, axes = trade
    template = goods('receipts', post=False)
    other_org = ref('organizations', name='Other')
    call('POST', '/api/goods/opening-balances', 400, json=opening_payload(template, axes, organization_id=other_org))
    bad_settlement = opening_payload(template, axes)['settlements'][0] | {'counterparty_id': ref('counterparties', name='Other')}
    call('POST', '/api/goods/opening-balances', 400, json=opening_payload(template, axes, settlements=[bad_settlement]))
    payload = opening_payload(template, axes)
    manager = login_headers(client, 'manager', 'manager')
    result = client.post('/api/goods/opening-balances', headers=manager, json=payload)
    assert result.status_code == 201
    ident = result.json()['data']['id']
    path = f'/api/goods/opening-balances/{ident}'
    assert client.post(path + '/post', headers=manager).status_code == 403

    class FaultConnection:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, sql, params=()):
            if sql.startswith('INSERT INTO mutual_settlements_register'):
                raise RuntimeError('opening fault')
            return connection.execute(sql, params)

    with pytest.raises(RuntimeError, match='opening fault'):
        change_opening(FaultConnection(), ident, UserInfo(id=1, username='admin', role='admin', is_active=True), 'post')
    moves = call('GET', path + '/movements')
    assert moves['inventory'] == moves['settlements'] == [] and not moves['document']['is_posted']
    call('POST', path + '/post')
    sale = goods('issues', 2, 150, date='2026-10-02')
    call('POST', path + '/unpost', 400)
    assert balances(call)[0]['quantity_balance'] == 8
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('POST', path + '/unpost')
    call('DELETE', path)


def test_legacy_schema_migration_is_idempotent(tmp_path):
    from api.database import _ensure_column, _table_exists
    db = sqlite3.connect(tmp_path / 'legacy.db')
    db.row_factory = sqlite3.Row
    db.executescript('''CREATE TABLE materials(id INTEGER PRIMARY KEY, name TEXT, unit_id INTEGER);
        CREATE TABLE units(id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO units VALUES(1, 'piece'); INSERT INTO materials VALUES(1, 'Legacy', 1);
        CREATE TABLE goods_receipt_lines(id INTEGER PRIMARY KEY, quantity REAL, unit_id INTEGER);
        INSERT INTO goods_receipt_lines VALUES(1, 10, 1);
        CREATE TABLE inventory_register(id INTEGER PRIMARY KEY, warehouse_id INTEGER, material_id INTEGER,
        object_id INTEGER, unit_id INTEGER, period TEXT);''')
    ensure_schema(db, _ensure_column, _table_exists)
    ensure_schema(db, _ensure_column, _table_exists)
    row = db.execute('SELECT * FROM goods_receipt_lines').fetchone()
    assert row['quantity'] == row['base_quantity'] == 10 and row['unit_id'] == row['base_unit_id'] == 1
    assert row['conversion_factor'] == 1 and row['series_id'] is None
    db.close()


def test_exchange_explicitly_rejects_new_dimensions_and_old_overwrite(trade, connection):
    _, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    red, _ = variants(ref, template)
    source = goods('receipts', lines=[line(template, **red)])
    with pytest.raises(HTTPException) as error:
        _serialize_goods_receipts(connection, source['uuid'])
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        _upsert_goods_receipt_entity(connection, {'uuid': source['uuid'], 'lines': []})
    assert error.value.status_code == 409
    assert connection.execute('SELECT is_posted FROM goods_receipts WHERE id = ?', (source['id'],)).fetchone()[0] == 1
    with pytest.raises(HTTPException) as error:
        _mark_goods_receipt_deleted(connection, source['uuid'], '2026-10-02')
    assert error.value.status_code == 409
    assert connection.execute('SELECT is_posted FROM goods_receipts WHERE id = ?', (source['id'],)).fetchone()[0] == 1


def test_excel_roundtrip_preserves_base_unit_variants_packages_and_zero_vat(trade, connection):
    from api.goods_services import export_goods_document_lines, preview_goods_lines_import
    call, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    red, _ = variants(ref, template)
    package = ref('material-packages', name='Box 12', material_id=template['lines'][0]['material_id'], factor=12)
    source = goods('receipts', post=False, lines=[line(template, quantity=2, price_without_vat=1200, package_id=package, **red)])
    content = export_goods_document_lines(connection, kind='receipt', document_id=source['id'])
    preview = preview_goods_lines_import(connection, kind='receipt', filename='stock.xls', content=content)
    row = preview['rows'][0]
    assert (row['quantity'], row['base_quantity'], row['vat_rate'], row['sum_with_vat']) == (2, 24, 0, 2400)
    assert row['unit_id'] == source['lines'][0]['unit_id'] and row['package_id'] == package
    assert all(row[key] == value for key, value in red.items())
    call('PUT', f'/api/goods/receipts/{source["id"]}', json=dict(date=source['date'], organization_id=source['organization_id'],
        warehouse_id=source['warehouse_id'], lines=preview['rows']))
    call('POST', f'/api/goods/receipts/{source["id"]}/post?auto_schedule=false')
    assert balances(call)[0]['quantity_balance'] == 24
    invalid = content.replace(str(package).encode() + b'</Data>', b'not-an-id</Data>')
    with pytest.raises(HTTPException):
        preview_goods_lines_import(connection, kind='receipt', filename='invalid.xls', content=invalid)


@pytest.mark.parametrize('direction,amount', [('outgoing', 1200), ('incoming', 540)])
def test_opening_debts_can_be_paid_and_cannot_be_cancelled_before_payment(trade, direction, amount):
    call, _, goods, _, axes = trade
    template = goods('receipts', post=False)
    doc = call('POST', '/api/goods/opening-balances', 201, json=opening_payload(template, axes, inventory=[]))
    path = f'/api/goods/opening-balances/{doc["id"]}'
    call('POST', path + '/post')
    payment = call('POST', '/api/payments/transactions', 201, json=dict(date='2026-10-02', direction=direction,
        amount=amount, counterparty_id=axes['counterparty_id'], contract_id=axes['contract_id']))
    payment_path = f'/api/payments/transactions/{payment["id"]}'
    call('POST', payment_path + '/post')
    rows = call('GET', '/api/settlements/turnover', params=dict(date_from='2026-10-02', date_to='2026-10-02'))
    key = 'payable' if direction == 'outgoing' else 'receivable'
    assert rows[0][key + '_payment_turnover'] == amount and rows[0][key + '_closing'] == 0
    call('POST', path + '/unpost', 400)
    assert len(call('GET', path + '/movements')['settlements']) == 2
    call('POST', payment_path + '/unpost')
    call('POST', path + '/unpost')
    assert call('GET', path + '/movements')['settlements'] == []


def test_opening_cost_dependency_isolated_by_series_and_unpost_is_atomic(trade, connection):
    call, ref, goods, _, axes = trade
    template = goods('receipts', post=False)
    red, blue = variants(ref, template)
    payload = opening_payload(template, axes, settlements=[])
    payload['inventory'][0].update(red)
    doc = call('POST', '/api/goods/opening-balances', 201, json=payload)
    path = f'/api/goods/opening-balances/{doc["id"]}'
    call('POST', path + '/post')
    goods('receipts', lines=[line(template, quantity=7, price_without_vat=300, **blue)])
    goods('issues', date='2026-10-02', lines=[line(template, quantity=2, price_without_vat=500, **blue)])

    class FaultConnection:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, sql, params=()):
            if sql.startswith('DELETE FROM mutual_settlements_register'):
                raise RuntimeError('unpost fault')
            return connection.execute(sql, params)

    with pytest.raises(RuntimeError, match='unpost fault'):
        change_opening(FaultConnection(), doc['id'], UserInfo(id=1, username='admin', role='admin', is_active=True), 'unpost')
    assert call('GET', path)['is_posted'] and len(call('GET', path + '/movements')['inventory']) == 1
    call('POST', path + '/unpost')
    assert [(row['series_id'], row['quantity_balance']) for row in balances(call)] == [(blue['series_id'], 5)]
    call('POST', path + '/post')
    assert balances(call, series_id=red['series_id'])[0]['quantity_balance'] == 10


def test_package_precision_and_historical_reference_binding_are_guarded(trade):
    call, ref, goods, _, axes = trade
    template = goods('receipts', post=False)
    material = template['lines'][0]['material_id']
    red, blue = variants(ref, template)
    package = ref('material-packages', name='Third', material_id=material, factor=0.333333)
    call('POST', '/api/goods/receipts', 400, json=dict(date='2026-10-01', **axes,
         lines=[line(template, quantity=0.1, package_id=package)]))
    source = goods('receipts', lines=[line(template, **red)])
    call('PUT', f'/api/references/material-series/{red["series_id"]}', 400,
         json=dict(name='S1', material_id=material, characteristic_id=blue['characteristic_id']))
    call('DELETE', f'/api/references/material-characteristics/{red["characteristic_id"]}', 400)
    call('POST', f'/api/goods/receipts/{source["id"]}/unpost')
    call('POST', f'/api/goods/receipts/{source["id"]}/post?auto_schedule=false')
