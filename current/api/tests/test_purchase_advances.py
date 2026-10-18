"""PUR-010: real payments and acquisitions share one settlement fact stream."""
from decimal import Decimal
import json

import pytest

from api import payment_services, purchase_services
from api.models.auth import UserInfo
from api.tests.test_purchases import purchase
from api.tests.test_trade_returns import trade
from api.tests.test_trade_lifecycle import scoped_user


def advance(call, axes, amount=400, date='2026-10-01', post=True, **extra):
    doc = call('POST', '/api/payments/transactions', 201, json=dict(date=date, direction='outgoing',
        category='supplier', amount=amount, allow_advance=True, counterparty_id=axes['counterparty_id'],
        contract_id=axes['contract_id']) | extra)
    if post:
        call('POST', f'/api/payments/transactions/{doc["id"]}/post')
    return doc


def settlement(call, axes, **params):
    rows = call('GET', '/api/settlements/balance', params={k:axes[k] for k in ('organization_id','counterparty_id','contract_id')} | params)
    return tuple(sum((Decimal(str(row[key])) for row in rows), Decimal(0)) for key in ('supplier_advance','payable_balance'))


@pytest.mark.parametrize('scheme', ['direct', 'order', 'service'])
@pytest.mark.parametrize('amount', [.01, 400, 1000, 1400])
def test_purchase_auto_offsets_only_real_payment_once(purchase, connection, record_property, scheme, amount):
    call, _, _, order, child, balance, axes, _ = purchase
    source = order(mode='order' if scheme == 'order' else 'direct', service=scheme == 'service',
                   quantity=1 if scheme == 'service' else 10, price=1000 if scheme == 'service' else 100)
    payment = advance(call, axes, amount)
    initial = settlement(call, axes)
    assert initial == (Decimal(str(amount)), 0)
    if scheme == 'order':
        child('receipt-orders', source, 10)
        assert balance() == (10, 1000, 0)
        assert settlement(call, axes) == (Decimal(str(amount)), 0)
    invoice = child('acquisitions', source, 1 if scheme == 'service' else 10)
    final = settlement(call, axes)
    assert final == (max(Decimal(str(amount))-1000, 0), max(1000-Decimal(str(amount)), 0))
    call('POST', f'/api/payments/transactions/{payment["id"]}/post', 400)
    call('POST', f'/api/purchases/acquisitions/{invoice["id"]}/post', 400)
    facts = [dict(row) for row in connection.execute('SELECT * FROM mutual_settlements_register WHERE contract_id = ?', (axes['contract_id'],))]
    assert len(facts) == 2
    assert {row['recorder_type'] for row in facts} == {'payment_transaction','purchase_acquisition'}
    assert sum(Decimal(str(row['payment_amount'])) for row in facts) == Decimal(str(amount))
    assert sum(Decimal(str(row['accrual_amount'])) for row in facts) == 1000
    if amount == 400:
        record_property('pur010_api_trace', json.dumps(dict(scheme=scheme, organization_id=axes['organization_id'],
            counterparty_id=axes['counterparty_id'], contract_id=axes['contract_id'],
            advance_before=float(initial[0]), payable_before=float(initial[1]),
            advance_remaining=float(final[0]), payable=float(final[1]),
            payment_total=float(sum(Decimal(str(row['payment_amount'])) for row in facts)),
            accrual_total=float(sum(Decimal(str(row['accrual_amount'])) for row in facts)),
            registrar_count=len(facts), recorders=sorted(row['recorder_type'] for row in facts))))
    if scheme == 'service':
        assert balance()[:2] == (0, 0)
        assert sum(row['expense_amount'] for row in call('GET','/api/purchases/expenses')) == 1000


@pytest.mark.parametrize('scheme', ['direct','order','service'])
@pytest.mark.parametrize('timing', ['after','future'])
def test_advance_date_and_financial_order_control_offset(purchase, scheme, timing):
    call, _, _, order, child, balance, axes, _ = purchase
    source = order(mode='order' if scheme == 'order' else 'direct', service=scheme == 'service',
                   quantity=1 if scheme == 'service' else 10, price=1000 if scheme == 'service' else 100)
    if timing == 'future':
        advance(call, axes, date='2026-10-04')
    child('acquisitions', source, 1 if scheme == 'service' else 10)
    assert settlement(call, axes, date='2026-10-02') == (0, 1000)
    if timing == 'after':
        advance(call, axes, date='2026-10-04', allow_advance=False)
    assert settlement(call, axes, date='2026-10-03') == (0, 1000)
    assert settlement(call, axes, date='2026-10-04') == (0, 600)
    if scheme == 'order':
        assert balance()[:2] == (0, 0)
        child('receipt-orders', source, 10, date='2026-10-05')
        assert balance() == (10, 1000, 600)


@pytest.mark.parametrize('axis', ['organization','counterparty','contract','object'])
def test_advance_is_not_used_by_another_settlement_slice(purchase, axis):
    call, ref, _, order, child, _, axes, _ = purchase
    payment_axes = axes.copy()
    extra = {}
    if axis == 'organization':
        payment_axes['organization_id'] = ref('organizations', name='Other advance owner')
    if axis == 'counterparty':
        payment_axes['counterparty_id'] = ref('counterparties', name='Other advance partner')
    if axis != 'object':
        payment_axes['contract_id'] = ref('contracts', number='Other advance contract', organization_id=payment_axes['organization_id'],counterparty_id=payment_axes['counterparty_id'])
    else:
        extra['object_id'] = ref('objects', name='Other advance object')
    advance(call, payment_axes, **extra)
    child('acquisitions', order(), 10)
    rows = call('GET','/api/settlements/balance')
    assert sum(row['supplier_advance'] for row in rows) == 400
    assert sum(row['payable_balance'] for row in rows) == 1000
    matching = next(row for row in rows if row['payable_balance'])
    assert matching['contract_id'] == axes['contract_id'] and matching['supplier_advance'] == 0


def test_advance_and_acquisition_cancel_repost_without_duplicate_offset(purchase):
    call, _, _, order, child, _, axes, _ = purchase
    payment = advance(call, axes)
    source = order()
    invoice = child('acquisitions', source, 10)
    assert settlement(call, axes) == (0,600)
    call('POST', f'/api/purchases/acquisitions/{invoice["id"]}/unpost',400)
    call('POST', f'/api/payments/transactions/{payment["id"]}/unpost')
    assert settlement(call, axes) == (0,1000)
    call('POST', f'/api/payments/transactions/{payment["id"]}/post')
    assert settlement(call, axes) == (0,600)
    call('POST', f'/api/payments/transactions/{payment["id"]}/unpost')
    call('POST', f'/api/purchases/acquisitions/{invoice["id"]}/unpost')
    assert settlement(call, axes) == (0,0)
    call('POST', f'/api/payments/transactions/{payment["id"]}/post')
    assert settlement(call, axes) == (400,0)
    call('POST', f'/api/purchases/acquisitions/{invoice["id"]}/post')
    assert settlement(call, axes) == (0,600)


@pytest.mark.parametrize('role', ['viewer','manager','admin'])
@pytest.mark.parametrize('foreign', [False,True])
def test_advance_creation_and_posting_enforce_scope_and_roles(purchase, client, role, foreign):
    call, ref, _, _, _, _, axes, _ = purchase
    org = ref('organizations',name='Foreign reader') if foreign else axes['organization_id']
    _, headers = scoped_user(call,client,[org],role=role)
    response=client.post('/api/payments/transactions',headers=headers,json=dict(date='2026-10-01',direction='outgoing',amount=400,
        allow_advance=True,counterparty_id=axes['counterparty_id'],contract_id=axes['contract_id']))
    assert response.status_code == (403 if foreign or role=='viewer' else 201),response.text
    if response.status_code==201:
        ident=response.json()['data']['id']
        posted=client.post(f'/api/payments/transactions/{ident}/post',headers=headers)
        assert posted.status_code == (200 if role=='admin' else 403),posted.text


@pytest.mark.parametrize('operation',['payment-post','payment-unpost','acquisition-post'])
def test_advance_offset_failure_rolls_back_facts_and_audit(purchase, connection, monkeypatch, operation):
    call, _, _, order, child, _, axes, _ = purchase
    payment=advance(call,axes,post=operation!='payment-post')
    invoice=child('acquisitions',order(),10,post=False)
    tables=('purchase_documents','purchase_lines','payment_transactions','payment_schedule_register','inventory_register',
            'mutual_settlements_register','purchase_expense_register','purchase_events','sync_changes')
    def snapshot():
        return {table:[dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY id')] for table in tables}
    before=snapshot()
    target=purchase_services if operation=='acquisition-post' else payment_services
    name='record_event' if operation=='acquisition-post' else 'register_sync_change'
    real=getattr(target,name)
    def fail(*args,**kwargs):
        real(*args,**kwargs)
        raise RuntimeError('advance offset fault after actual writes')
    user=UserInfo(id=1,username='admin',role='admin',is_active=True)
    with monkeypatch.context() as patch:
        patch.setattr(target,name,fail)
        with pytest.raises(RuntimeError,match='advance offset fault'):
            if operation=='acquisition-post':
                purchase_services.change_document(connection,invoice['id'],'acquisitions','post',user)
            else:
                fn=payment_services.unpost_payment_transaction if operation=='payment-unpost' else payment_services.post_payment_transaction
                fn(connection,tx_id=payment['id'],user=user)
    assert not connection.in_transaction and snapshot()==before
    if operation=='acquisition-post':
        call('POST',f'/api/purchases/acquisitions/{invoice["id"]}/post')
        assert settlement(call,axes)==(0,600)
    else:
        call('POST',f'/api/payments/transactions/{payment["id"]}/'+('unpost' if operation=='payment-unpost' else 'post'))


def test_advance_requires_explicit_permission_and_matching_contract_partner(purchase):
    call, ref, _, _, _, _, axes, _ = purchase
    draft=advance(call,axes,post=False,allow_advance=False)
    call('POST',f'/api/payments/transactions/{draft["id"]}/post',400)
    call('POST','/api/payments/transactions',400,json=dict(date='2026-10-01',direction='outgoing',amount=400,allow_advance=True))
    other=ref('counterparties',name='Wrong advance partner')
    call('POST','/api/payments/transactions',400,json=dict(date='2026-10-01',direction='outgoing',amount=400,allow_advance=True,
         contract_id=axes['contract_id'],counterparty_id=other))
    assert settlement(call,axes)==(0,0)
