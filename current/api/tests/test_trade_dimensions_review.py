"""Independent STEP-02 review: monetary and interleaving invariants."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event

import pytest
from fastapi import HTTPException

from api.database import get_connection
from api.models.auth import UserInfo
from api.tests.test_trade_returns import trade
from api.tests.test_trade_dimensions import line, variants, balances, opening_payload

ADMIN = UserInfo(id=1, username='admin', role='admin', is_active=True)


def perform(action):
    connection = get_connection()
    try:
        action(connection)
        return 200
    except HTTPException as error:
        return error.status_code
    finally:
        connection.close()


def total_cost(rows):
    return sum((Decimal(str(row['sum_income'])) - Decimal(str(row['sum_expense'])) for row in rows), Decimal(0))


@pytest.mark.parametrize('factor,split_lines', [(3, True), (1000000, False)])
def test_full_packaged_issue_and_return_conserve_original_cost(trade, factor, split_lines):
    call, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    red, _ = variants(ref, template)
    package = ref('material-packages', name='Fractional carrying cost', material_id=template['lines'][0]['material_id'], factor=factor)
    goods('receipts', lines=[line(template, quantity=1, price_without_vat=.01, package_id=package, **red)])
    lines = ([line(template, line_number=n, quantity=1, price_without_vat=1, **red) for n in range(1, 4)] if split_lines
             else [line(template, quantity=1, price_without_vat=1, package_id=package, **red)])
    sale = goods('issues', date='2026-10-02', lines=lines)
    assert sum(Decimal(str(row['inventory_cost'])) for row in sale['lines']) == Decimal('.01')
    assert total_cost(balances(call, **red)) == 0
    returned = call('POST', '/api/goods/returns', 201, json=dict(kind='customer', source_id=sale['id'], date='2026-10-03',
        lines=[dict(source_line_id=row['id'], quantity=1) for row in sale['lines']]))
    path = f'/api/goods/returns/{returned["id"]}'
    call('POST', path + '/post')
    assert total_cost(balances(call, **red)) == Decimal('.01')
    assert balances(call, **red)[0]['quantity_balance'] == factor
    call('POST', path + '/unpost')
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('POST', f'/api/goods/issues/{sale["id"]}/post')
    assert total_cost(balances(call, **red)) == 0


def test_full_bulk_package_transfer_conserves_cents(trade):
    call, ref, goods, _, axes = trade
    template = goods('receipts', post=False)
    red, _ = variants(ref, template)
    package = ref('material-packages', name='Million', material_id=template['lines'][0]['material_id'], factor=1000000)
    goods('receipts', lines=[line(template, quantity=1, price_without_vat=.01, package_id=package, **red)])
    destination = ref('warehouses', name='Destination', organization_id=axes['organization_id'])
    doc = call('POST', '/api/goods/transfers', 201, json=dict(date='2026-10-02', organization_id=axes['organization_id'],
        source_warehouse_id=axes['warehouse_id'], destination_warehouse_id=destination,
        lines=[dict(line_number=1, material_id=template['lines'][0]['material_id'], unit_id=template['lines'][0]['unit_id'],
                    quantity=1, package_id=package, **red)]))
    path = f'/api/goods/transfers/{doc["id"]}'
    call('POST', path + '/post')
    assert call('GET', path)['lines'][0]['sum'] == .01
    assert total_cost(balances(call, warehouse_id=axes['warehouse_id'], **red)) == 0
    assert total_cost(balances(call, warehouse_id=destination, **red)) == Decimal('.01')
    call('POST', path + '/unpost')
    call('POST', path + '/post')
    assert total_cost(balances(call)) == Decimal('.01')


def test_cent_allocation_keeps_null_and_different_series_independent(trade):
    call, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    red, blue = variants(ref, template)
    package = ref('material-packages', name='Triple', material_id=template['lines'][0]['material_id'], factor=3)
    goods('receipts', lines=[line(template, quantity=1, price_without_vat=.01, package_id=package, **red),
        line(template, line_number=2, quantity=1, price_without_vat=.02, package_id=package),
        line(template, line_number=3, quantity=1, price_without_vat=7, **blue)])
    rows = [line(template, line_number=n + 1, quantity=1, **axes)
            for n, axes in enumerate([red, {}, blue, red, {}, red, {}])]
    sale = goods('issues', date='2026-10-02', lines=rows)
    costs = {}
    for row in sale['lines']:
        costs[row['series_id']] = costs.get(row['series_id'], Decimal(0)) + Decimal(str(row['inventory_cost']))
    assert costs == {None: Decimal('.02'), red['series_id']: Decimal('.01'), blue['series_id']: Decimal(7)}
    assert all(row['quantity_balance'] == 0 and total_cost([row]) == 0 for row in balances(call))


def test_material_exchange_cannot_change_base_unit_used_by_packages(trade, connection):
    from api.sync_runtime import _serialize_materials, _upsert_material_entity
    call, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    material = template['lines'][0]['material_id']
    package = ref('material-packages', name='Pair', material_id=material, factor=2)
    goods('receipts', lines=[line(template, quantity=1, package_id=package)])
    new_unit = connection.execute('SELECT uuid FROM units WHERE id <> ? ORDER BY id LIMIT 1',
                                  (template['lines'][0]['unit_id'],)).fetchone()
    assert new_unit is not None
    payload = _serialize_materials(connection, call('GET', f'/api/references/materials/{material}')['uuid'])
    payload['unit_uuid'] = new_unit['uuid']
    try:
        with pytest.raises(HTTPException) as error:
            _upsert_material_entity(connection, payload)
        assert error.value.status_code == 400
    finally:
        connection.rollback()
    assert call('GET', f'/api/references/materials/{material}')['unit_id'] == template['lines'][0]['unit_id']


@pytest.mark.parametrize('kind', ['customer', 'supplier', 'purchase'])
def test_return_and_correction_reject_inconsistent_source_conversion_snapshot(trade, connection, kind):
    call, ref, goods, _, _ = trade
    template = goods('receipts', post=False)
    package = ref('material-packages', name='Pair', material_id=template['lines'][0]['material_id'], factor=2)
    receipt = goods('receipts', lines=[line(template, quantity=2, price_without_vat=100, package_id=package)])
    source = (goods('issues', date='2026-10-02', lines=[line(template, quantity=2, package_id=package)])
              if kind == 'customer' else receipt)
    # Simulate an inconsistent historical snapshot. Original register quantity/cost
    # remains correct; a downstream document must not silently accept the mismatch.
    table = 'goods_issue_lines' if kind == 'customer' else 'goods_receipt_lines'
    connection.execute(f'UPDATE {table} SET conversion_factor = 3 WHERE id = ?', (source['lines'][0]['id'],))
    connection.commit()
    if kind == 'purchase':
        call('POST', '/api/goods/price-adjustments', 400, json=dict(kind=kind, source_id=source['id'], date='2026-10-03',
            lines=[dict(source_line_id=source['lines'][0]['id'], new_price=90)]))
    else:
        call('POST', '/api/goods/returns', 400, json=dict(kind=kind, source_id=source['id'], date='2026-10-03',
            lines=[dict(source_line_id=source['lines'][0]['id'], quantity=1)]))


@pytest.mark.parametrize('direction,amount', [('outgoing', 1200), ('incoming', 540)])
def test_payment_cannot_race_opening_debt_cancellation(trade, monkeypatch, direction, amount):
    from api import payment_services
    from api.opening_balance_services import change_opening
    call, _, goods, _, axes = trade
    template = goods('receipts', post=False)
    opening = call('POST', '/api/goods/opening-balances', 201, json=opening_payload(template, axes, inventory=[]))
    path = f'/api/goods/opening-balances/{opening["id"]}'
    call('POST', path + '/post')
    payment = call('POST', '/api/payments/transactions', 201, json=dict(date='2026-10-02', direction=direction,
        amount=amount, counterparty_id=axes['counterparty_id'], contract_id=axes['contract_id']))
    checked, resume, cancelled = Event(), Event(), Event()
    original_check = payment_services._assert_payment_within_accruals

    def paused_check(connection, tx):
        original_check(connection, tx)
        checked.set()
        assert resume.wait(8), 'interleaving did not resume payment'

    monkeypatch.setattr(payment_services, '_assert_payment_within_accruals', paused_check)

    def cancel(connection):
        try:
            change_opening(connection, opening['id'], ADMIN, 'unpost')
        finally:
            cancelled.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        pay = pool.submit(perform, lambda c: payment_services.post_payment_transaction(c, tx_id=payment['id'], user=ADMIN))
        try:
            assert checked.wait(8)
            unpost = pool.submit(perform, cancel)
            # The old code lets cancellation finish while the payment is paused.
            # A protected transaction keeps it waiting until payment commits.
            cancelled.wait(1)
        finally:
            resume.set()
        outcomes = [pay.result(timeout=8), unpost.result(timeout=8)]
    assert sorted(outcomes) == [200, 400], outcomes
    assert call('GET', path)['is_posted']


@pytest.mark.parametrize('direction,amount', [('outgoing', 1200), ('incoming', 540)])
def test_payment_waits_for_opening_cancellation_before_reading_debt(trade, monkeypatch, direction, amount):
    from api import opening_balance_services, payment_services
    call, _, goods, _, axes = trade
    template = goods('receipts', post=False)
    opening = call('POST', '/api/goods/opening-balances', 201, json=opening_payload(template, axes, inventory=[]))
    path = f'/api/goods/opening-balances/{opening["id"]}'
    call('POST', path + '/post')
    payment = call('POST', '/api/payments/transactions', 201, json=dict(date='2026-10-02', direction=direction,
        amount=amount, counterparty_id=axes['counterparty_id'], contract_id=axes['contract_id']))
    checked, resume, payment_started = Event(), Event(), Event()
    original_check = opening_balance_services.assert_no_dependencies

    def paused_check(conn, doc):
        original_check(conn, doc)
        checked.set()
        assert resume.wait(8)

    monkeypatch.setattr(opening_balance_services, 'assert_no_dependencies', paused_check)

    def pay(conn):
        payment_started.set()
        payment_services.post_payment_transaction(conn, tx_id=payment['id'], user=ADMIN)

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel = pool.submit(perform, lambda c: opening_balance_services.change_opening(c, opening['id'], ADMIN, 'unpost'))
        try:
            assert checked.wait(8)
            payment_future = pool.submit(perform, pay)
            assert payment_started.wait(8)
        finally:
            resume.set()
        assert cancel.result(timeout=8) == 200
        assert payment_future.result(timeout=8) == 400
    assert not call('GET', path)['is_posted']
    assert not call('GET', f'/api/payments/transactions/{payment["id"]}')['is_posted']
    assert call('GET', path + '/movements')['settlements'] == []


@pytest.mark.parametrize('document_kind', ['receipts', 'transfers', 'opening-balances'])
def test_package_factor_update_cannot_race_first_document_use(trade, monkeypatch, document_kind):
    from api import services
    call, ref, goods, _, axes = trade
    template = goods('receipts', post=False)
    material = template['lines'][0]['material_id']
    package = ref('material-packages', name='Box', material_id=material, factor=12)
    destination = ref('warehouses', name='Destination', organization_id=axes['organization_id'])
    checked, resume, saved = Event(), Event(), Event()
    original_validate = services.validate_reference

    def paused_validate(connection, kind, payload, existing=None):
        original_validate(connection, kind, payload, existing)
        if existing and kind == 'material-packages':
            checked.set()
            assert resume.wait(8)

    monkeypatch.setattr(services, 'validate_reference', paused_validate)

    def save():
        try:
            if document_kind == 'receipts':
                return goods('receipts', post=False, lines=[line(template, quantity=1, package_id=package)])
            if document_kind == 'transfers':
                return call('POST', '/api/goods/transfers', 201, json=dict(date='2026-10-02', organization_id=axes['organization_id'],
                    source_warehouse_id=axes['warehouse_id'], destination_warehouse_id=destination,
                    lines=[dict(line_number=1, material_id=material, unit_id=template['lines'][0]['unit_id'], quantity=1, package_id=package)]))
            payload = opening_payload(template, axes, settlements=[])
            payload['inventory'][0].update(quantity=1, package_id=package)
            return call('POST', '/api/goods/opening-balances', 201, json=payload)
        finally:
            saved.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        update = pool.submit(perform, lambda c: services.update_reference(c, kind='material-packages', item_id=package,
            payload=dict(name='Box', material_id=material, factor=6)))
        try:
            assert checked.wait(8)
            receipt = pool.submit(save)
            saved.wait(1)
        finally:
            resume.set()
        result, source = update.result(timeout=8), receipt.result(timeout=8)
    actual = call('GET', f'/api/references/material-packages/{package}')
    assert result in (200, 400)
    row = source['inventory' if document_kind == 'opening-balances' else 'lines'][0]
    assert row['conversion_factor'] == actual['factor']
    if document_kind == 'transfers':
        goods('receipts', quantity=6)
    call('POST', f'/api/goods/{document_kind}/{source["id"]}/post?auto_schedule=false')


@pytest.mark.parametrize('kind', ['receipt', 'issue', 'transfer'])
@pytest.mark.parametrize('operation', ['upsert', 'delete', 'export'])
def test_legacy_exchange_cannot_race_local_dimension_edit(trade, connection, monkeypatch, kind, operation):
    from api import inventory_dimensions, sync_runtime, goods_services, warehouse_transfer_services
    call, ref, goods, _, axes = trade
    template = goods('receipts', post=False)
    red, _ = variants(ref, template)
    plural = {'receipt': 'receipts', 'issue': 'issues', 'transfer': 'transfers'}[kind]
    if kind == 'transfer':
        destination = ref('warehouses', name='Destination', organization_id=axes['organization_id'])
        payload = dict(date='2026-10-02', organization_id=axes['organization_id'], source_warehouse_id=axes['warehouse_id'],
                       destination_warehouse_id=destination, lines=[dict(line_number=1, material_id=template['lines'][0]['material_id'],
                       unit_id=template['lines'][0]['unit_id'], quantity=1)])
        source = call('POST', '/api/goods/transfers', 201, json=payload)
    else:
        source = goods(plural, post=False)
        payload = dict(date=source['date'], **axes, lines=[line(source)])
    serialize = getattr(sync_runtime, f'_serialize_goods_{plural}')
    incoming = serialize(connection, source['uuid'])
    payload['lines'][0].update(red)
    checked, resume, saved = Event(), Event(), Event()
    original_guard = inventory_dimensions.guard_legacy_exchange

    def paused_guard(conn, actual_kind, snapshot, **kwargs):
        original_guard(conn, actual_kind, snapshot, **kwargs)
        checked.set()
        assert resume.wait(8)

    monkeypatch.setattr(inventory_dimensions, 'guard_legacy_exchange', paused_guard)

    def exchange(conn):
        if operation == 'delete':
            getattr(sync_runtime, f'_mark_goods_{kind}_deleted')(conn, source['uuid'], '2026-10-03')
        elif operation == 'export':
            serialize(conn, source['uuid'])
        else:
            getattr(sync_runtime, f'_upsert_goods_{kind}_entity')(conn, incoming)
        conn.commit()

    def edit(conn):
        try:
            if kind == 'transfer':
                warehouse_transfer_services.save_transfer(conn, payload=payload, user=ADMIN, transfer_id=source['id'])
            else:
                goods_services._save_document(conn, kind=kind, payload=payload, user=ADMIN, document_id=source['id'])
        finally:
            saved.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        sync = pool.submit(perform, exchange)
        try:
            assert checked.wait(8)
            local = pool.submit(perform, edit)
            saved.wait(1)
        finally:
            resume.set()
        sync_status, edit_status = sync.result(timeout=8), local.result(timeout=8)
    assert sync_status in (200, 409)
    if operation == 'export':
        assert sync_status == 409, 'export must reject the actual dimensional lines it read'
    if edit_status == 200:
        doc = call('GET', f'/api/goods/{plural}/{source["id"]}')
        assert all(doc['lines'][0][key] == value for key, value in red.items())
        with pytest.raises(HTTPException) as error:
            serialize(connection, source['uuid'])
        assert error.value.status_code == 409
    else:
        assert (operation, sync_status, edit_status) == ('delete', 200, 404)
