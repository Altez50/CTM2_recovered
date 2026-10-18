"""Final STEP-03 review: grant ownership at commit and same-time cost order."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException

from api import goods_services, payment_services, return_services
from api.database import get_connection
from api.models.auth import UserInfo
from api.models.payments import PaymentScheduleCreate, PaymentTransactionCreate
from api.tests.test_trade_returns import trade
from api.tests.test_trade_step03_review import access_case, calendar_payload, payment_payload
from api.tests.test_trade_dimensions import line
from api.trade_access import TradeConnection


@pytest.mark.parametrize('kind', ['payment', 'calendar'])
@pytest.mark.parametrize('editing', [False, True])
def test_payment_document_cannot_commit_with_stale_contract_permission(trade, connection, access_case, monkeypatch, kind, editing):
    call, ref, _, _, axes = trade
    foreign, user, _ = access_case
    candidate = ref('contracts', number='Candidate owned by A', organization_id=axes['organization_id'], counterparty_id=axes['counterparty_id'])
    principal = UserInfo(**user)
    if kind == 'payment':
        endpoint, table, model, guard = '/api/payments/transactions', 'payment_transactions', PaymentTransactionCreate, 'require_payment_links'
        payload = payment_payload(axes)
    else:
        endpoint, table, model, guard = '/api/payments/schedules', 'payment_schedules', PaymentScheduleCreate, 'require_schedule'
        payload = calendar_payload(axes['contract_id'])
    existing = call('POST', endpoint, 201, json=payload) if editing else None
    payload['contract_id'] = candidate
    payload['description' if kind == 'payment' else 'number'] = 'Written after stale check'
    if kind == 'calendar':
        payload['lines'][0]['contract_id'] = candidate
    checked, release, rebinding, rebound = Event(), Event(), Event(), Event()
    original = getattr(payment_services, guard)

    def paused_check(conn, data, *args, **kwargs):
        original(conn, data, *args, **kwargs)
        if data.get('contract_id') == candidate and not checked.is_set():
            checked.set()
            assert release.wait(10), 'permission test did not release the writer'
    monkeypatch.setattr(payment_services, guard, paused_check)

    def write():
        raw = get_connection()
        try:
            scoped = TradeConnection(raw, principal)
            data = model(**payload).model_dump()
            if kind == 'payment':
                payment_services.save_payment_transaction(scoped, payload=data, tx_id=existing['id'] if existing else None, user=principal)
            else:
                payment_services.save_payment_schedule(scoped, payload=data, schedule_id=existing['id'] if existing else None, user=principal)
            return 200
        except HTTPException as exc:
            raw.rollback()
            return exc.status_code
        finally:
            raw.close()

    def rebind():
        raw = get_connection()
        try:
            rebinding.set()
            raw.execute('UPDATE contracts SET organization_id = ? WHERE id = ?', (foreign['organization_id'], candidate))
            raw.commit()
            rebound.set()
        finally:
            raw.close()

    before = [dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY id')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write)
        assert checked.wait(10)
        second = pool.submit(rebind)
        try:
            assert rebinding.wait(10)
            foreign_before_write = rebound.wait(.3)
        finally:
            release.set()
        result = first.result(timeout=10)
        second.result(timeout=10)
    if foreign_before_write:
        assert result == 403
        after = [dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY id')]
        assert after == before, 'Permission denied only after commit: a foreign-owned document was persisted'
    else:
        assert result == 200
    assert connection.execute('SELECT organization_id FROM contracts WHERE id = ?', (candidate,)).fetchone()[0] == foreign['organization_id']


@pytest.mark.parametrize('later', ['none', 'same_day_same_series', 'next_day_same_series', 'same_day_other_series'])
def test_return_dependency_uses_movement_order_with_equal_timestamps(trade, connection, monkeypatch, later):
    call, ref, goods, ret, _ = trade
    timestamp = '2026-10-13T07:30:00+00:00'
    monkeypatch.setattr(goods_services, '_now_iso', lambda: timestamp)
    monkeypatch.setattr(return_services, 'utcnow_iso', lambda: timestamp)
    template = goods('receipts', post=False)
    material = template['lines'][0]['material_id']
    characteristic = ref('material-characteristics', name='Same characteristic', material_id=material)
    first, second = [ref('material-series', name=name, material_id=material, characteristic_id=characteristic) for name in ('First', 'Second')]
    def row(series, **extra):
        return line(template, characteristic_id=characteristic, series_id=series, **extra)
    goods('receipts', lines=[row(first, quantity=10), row(second, quantity=10, line_number=2)])
    source = goods('issues', date='2026-10-02', lines=[row(first, quantity=1)])
    returned = ret(source, date='2026-10-02')
    assert source['posted_at'] == returned['posted_at'] == timestamp
    if later != 'none':
        expense = goods('issues', date='2026-10-03' if later == 'next_day_same_series' else '2026-10-02',
                        lines=[row(second if later == 'same_day_other_series' else first, quantity=1)])
        assert expense['posted_at'] == timestamp
    movements = list(connection.execute('''SELECT id, recorder_type FROM inventory_register
        WHERE (recorder_type = 'goods_issue' AND recorder_id = ?)
           OR (recorder_type = 'goods_return' AND recorder_id = ?) ORDER BY id''', (source['id'], returned['id'])))
    assert [movement['recorder_type'] for movement in movements] == ['goods_issue', 'goods_return']
    assert movements[0]['id'] < movements[1]['id']
    blocked = later in ('same_day_same_series', 'next_day_same_series')
    path = f'/api/goods/returns/{returned["id"]}'
    call('POST', path+'/unpost', 400 if blocked else 200)
    if blocked:
        assert call('GET', path)['is_posted']
        call('POST', f'/api/goods/issues/{expense["id"]}/unpost')
        call('POST', path+'/unpost')
    call('POST', path+'/post')
    assert call('GET', path)['inventory_cost'] == 100
