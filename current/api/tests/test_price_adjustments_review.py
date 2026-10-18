"""Independent STEP-01 regressions: chronology, chain leaves and expense guards."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from api.database import get_connection
from api.models.auth import UserInfo
from api.price_adjustment_services import change_adjustment
from api.return_services import change_return
from api.tests.conftest import login_headers
from api.tests.test_trade_returns import trade
from api.tests.test_price_adjustments import create


@pytest.mark.parametrize('kind', ['sale', 'purchase'])
def test_same_day_chain_follows_posted_predecessors_not_document_ids(trade, kind):
    call, _, goods, _, _ = trade
    receipt = goods('receipts')
    source = goods('issues', 3, 150) if kind == 'sale' else receipt
    earlier_draft = create(call, source, kind=kind, price=130, post=False)
    later_document = create(call, source, kind=kind, price=140)
    path = f'/api/goods/price-adjustments/{earlier_draft["id"]}'
    payload = {'kind': kind, 'source_id': source['id'], 'date': '2026-10-03',
               'lines': [{'source_line_id': source['lines'][0]['id'], 'new_price': 130}]}
    rebased = call('PUT', path, json=payload)
    assert rebased['lines'][0]['previous_line_id'] == later_document['lines'][0]['id']
    call('POST', path + '/post')
    latest = call('GET', f'/api/goods/price-adjustment-sources/{kind}/{source["id"]}')
    assert latest['lines'][0]['effective_price'] == 130
    final = create(call, source, kind=kind, price=120)
    assert final['lines'][0]['old_price'] == 130
    assert final['delta_without_vat'] == -10 * source['lines'][0]['quantity']
    balance = call('GET', '/api/settlements/balance')[0]
    assert balance['receivable_balance' if kind == 'sale' else 'payable_balance'] == 120 * source['lines'][0]['quantity']
    call('POST', path + '/unpost', 400)
    final_path = f'/api/goods/price-adjustments/{final["id"]}'
    call('POST', final_path + '/unpost')
    call('POST', path + '/unpost')
    call('POST', path + '/post')
    call('POST', final_path + '/post')
    assert call('GET', f'/api/goods/price-adjustment-sources/{kind}/{source["id"]}')['lines'][0]['effective_price'] == 120


@pytest.mark.parametrize('unit', ['missing', 'other'])
@pytest.mark.parametrize('date', ['2026-10-02', '2026-10-05'])
def test_sale_cannot_consume_corrected_inventory_under_another_unit(trade, connection, unit, date):
    call, ref, goods, _, _ = trade
    receipt = goods('receipts')
    correction = create(call, receipt, kind='purchase', price=90, date='2026-10-04')
    line = {key: receipt['lines'][0][key] for key in ('line_number', 'name', 'material_id', 'quantity', 'vat_rate')}
    line.update(quantity=1, price_without_vat=150,
                unit_id=None if unit == 'missing' else connection.execute(
                    'SELECT id FROM units WHERE id != ? LIMIT 1', (receipt['lines'][0]['unit_id'],)).fetchone()[0])
    sale = goods('issues', lines=[line], date=date, post=False)
    call('POST', f'/api/goods/issues/{sale["id"]}/post?auto_schedule=false', 400)
    assert call('GET', f'/api/goods/issue/{sale["id"]}/movements')['inventory'] == []
    call('POST', f'/api/goods/price-adjustments/{correction["id"]}/unpost')


def transfer(call, axes, receipt, destination, *, date='2026-10-02'):
    doc = call('POST', '/api/goods/transfers', 201, json={'date': date, 'organization_id': axes['organization_id'],
        'source_warehouse_id': axes['warehouse_id'], 'destination_warehouse_id': destination,
        'lines': [{'line_number': 1, 'material_id': receipt['lines'][0]['material_id'],
                   'unit_id': receipt['lines'][0]['unit_id'], 'quantity': 5}]})
    call('POST', f'/api/goods/transfers/{doc["id"]}/post')
    return doc


@pytest.mark.parametrize('replenish', [False, True])
def test_transfer_cancellation_cannot_hide_consumption_from_purchase_correction(trade, replenish):
    call, ref, goods, _, axes = trade
    receipt = goods('receipts')
    correction = create(call, receipt, kind='purchase', price=90)
    destination = ref('warehouses', name='Destination', organization_id=axes['organization_id'])
    moved = transfer(call, axes, receipt, destination, date='2026-10-04')
    if replenish:
        goods('receipts', 10, 200, date='2026-10-04', warehouse_id=destination)
    sale = goods('issues', 1, 150, date='2026-10-05', warehouse_id=destination)
    path = f'/api/goods/transfers/{moved["id"]}'
    before = call('GET', path + '/movements')
    call('POST', path + '/unpost', 400)
    assert call('GET', path + '/movements') == before
    call('POST', f'/api/goods/price-adjustments/{correction["id"]}/unpost', 400)
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('POST', path + '/unpost')
    call('POST', f'/api/goods/price-adjustments/{correction["id"]}/unpost')


def test_backdated_supplier_return_on_other_receipt_cannot_bypass_cost005(trade):
    call, _, goods, ret, _ = trade
    first = goods('receipts')
    second = goods('receipts')
    create(call, first, kind='purchase', price=90, date='2026-10-04')
    returned = ret(second, kind='supplier', date='2026-10-02', post=False)
    path = f'/api/goods/returns/{returned["id"]}'
    call('POST', path + '/post', 400)
    moves = call('GET', path + '/movements')
    assert moves['inventory'] == moves['settlements'] == []
    assert not moves['document']['is_posted']


@pytest.mark.parametrize('unit', ['missing', 'other'])
def test_legacy_expense_with_mismatched_unit_still_blocks_correction(trade, connection, unit):
    call, _, goods, _, _ = trade
    receipt = goods('receipts')
    draft = create(call, receipt, kind='purchase', price=90, post=False)
    sale = goods('issues', 1, 150, date='2026-10-02')
    legacy_unit = None if unit == 'missing' else connection.execute(
        'SELECT id FROM units WHERE id != ? LIMIT 1', (receipt['lines'][0]['unit_id'],)).fetchone()[0]
    # Model a document posted by the pre-review version which pooled units.
    connection.execute('UPDATE goods_issue_lines SET unit_id = ? WHERE issue_id = ?', (legacy_unit, sale['id']))
    connection.execute("UPDATE inventory_register SET unit_id = ? WHERE recorder_type = 'goods_issue' AND recorder_id = ?",
                       (legacy_unit, sale['id']))
    connection.commit()
    path = f'/api/goods/price-adjustments/{draft["id"]}'
    call('POST', path + '/post', 400)
    assert call('GET', path + '/movements')['inventory'] == []
    call('POST', f'/api/goods/issues/{sale["id"]}/unpost')
    call('POST', path + '/post')


def test_purchase_unpost_failure_restores_both_registers_and_flag(trade, connection):
    call, _, goods, _, _ = trade
    doc = create(call, goods('receipts'), kind='purchase', price=90)
    path = f'/api/goods/price-adjustments/{doc["id"]}'
    before = call('GET', path + '/movements')

    class FaultConnection:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, sql, params=()):
            if sql.startswith('DELETE FROM mutual_settlements_register'):
                raise RuntimeError('unpost after inventory deletion')
            return connection.execute(sql, params)

    with pytest.raises(RuntimeError, match='unpost after inventory deletion'):
        change_adjustment(FaultConnection(), adjustment_id=doc['id'],
            user=UserInfo(id=1, username='admin', role='admin', is_active=True), action='unpost')
    assert call('GET', path + '/movements') == before


def test_return_and_correction_on_different_receipts_serialize_on_inventory(trade):
    call, _, goods, ret, _ = trade
    first, second = goods('receipts'), goods('receipts')
    correction = create(call, first, kind='purchase', price=90, date='2026-10-04', post=False)
    returned = ret(second, kind='supplier', date='2026-10-02', post=False)

    def post(kind):
        connection = get_connection()
        user = UserInfo(id=1, username='admin', role='admin', is_active=True)
        try:
            if kind == 'correction':
                change_adjustment(connection, adjustment_id=correction['id'], user=user, action='post')
            else:
                change_return(connection, document_id=returned['id'], user=user, action='post')
            return 200
        except HTTPException as exc:
            assert 'COST-005' in exc.detail
            return exc.status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(post, ['correction', 'return'])) == [200, 400]
    results = [call('GET', f'/api/goods/{kind}/{doc["id"]}/movements')
               for kind, doc in [('price-adjustments', correction), ('returns', returned)]]
    assert sorted(len(result['inventory']) for result in results) == [0, 1]
    assert sorted(len(result['settlements']) for result in results) == [0, 1]
    assert sum(result['document']['is_posted'] for result in results) == 1


def test_price_adjustment_api_permissions(trade, client):
    call, _, goods, _, _ = trade
    receipt = goods('receipts')
    manager = login_headers(client, 'manager', 'manager')
    foreman = login_headers(client, 'foreman', 'foreman')
    payload = {'kind': 'purchase', 'source_id': receipt['id'], 'date': '2026-10-03',
               'lines': [{'source_line_id': receipt['lines'][0]['id'], 'new_price': 90}]}
    collection = '/api/goods/price-adjustments'
    assert client.post(collection, headers=foreman, json=payload).status_code == 403
    response = client.post(collection, headers=manager, json=payload)
    assert response.status_code == 201, response.text
    path = f'{collection}/{response.json()["data"]["id"]}'
    for headers in (manager, foreman):
        for action in ('post', 'unpost'):
            assert client.post(path + '/' + action, headers=headers).status_code == 403
    assert client.put(path, headers=foreman, json=payload).status_code == 403
    assert client.delete(path, headers=foreman).status_code == 403
    assert client.put(path, headers=manager, json=payload).status_code == 200
    assert call('GET', path + '/movements')['inventory'] == []
    assert client.delete(path, headers=manager).status_code == 200
