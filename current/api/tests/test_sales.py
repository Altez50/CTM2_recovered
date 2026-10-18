"""STEP-07 real API sales, source limits, reserves, credit and rollback."""
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.tests.conftest import login_headers
from api import sales_services
from api.models.auth import UserInfo
from api.tests.test_trade_returns import trade
from api.tests.test_trade_dimensions import line
from api.tests.test_trade_lifecycle import scoped_user


@pytest.fixture
def sale(trade):
    call,ref,goods,ret,axes=trade
    receipt=goods('receipts')
    def order(mode='direct',service=False,quantity=6,price=150,post=True,**extra):
        if mode=='order':
            call('PUT',f'/api/references/warehouses/{axes["warehouse_id"]}',json=dict(name='Order issue warehouse',organization_id=axes['organization_id'],order_issue_enabled=True))
        row=dict(line_number=1,line_type='service',name='Service',quantity=quantity,price_without_vat=price,vat_rate=0) if service else line(receipt,quantity=quantity,price_without_vat=price)
        payload=dict(date='2026-10-02',**axes,lines=[row])|extra
        if service:
            payload['warehouse_id']=None
        doc=call('POST','/api/sales/orders',201,json=payload)
        return call('POST',f'/api/sales/orders/{doc["id"]}/post') if post else doc
    def child(kind,source,quantity,date='2026-10-03',post=True):
        doc=call('POST',f'/api/sales/{kind}',201,json=dict(date=date,source_id=source['id'],lines=[dict(source_line_id=source['lines'][0]['id'],quantity=quantity)]))
        return call('POST',f'/api/sales/{kind}/{doc["id"]}/post') if post else doc
    def state():
        stock=call('GET','/api/goods/inventory/balances')
        debts=call('GET','/api/settlements/balance')
        return (sum(row['quantity_balance'] for row in stock),sum(row['sum_income']-row['sum_expense'] for row in stock),sum(row['receivable_balance'] for row in debts))
    return call,ref,goods,order,child,state,axes,receipt,ret


def test_partial_sales_and_cancel_release_exact_reserve(sale,connection):
    call,_,_,order,child,state,_,_,_=sale
    source=order()
    first=child('realizations',source,2)
    assert state()==(8,800,300)
    assert first['lines'][0]['inventory_cost']==200
    assert call('GET',f'/api/sales/orders/{source["id"]}')['lines'][0]['open_quantity']==4
    cancel=child('cancellations',source,4)
    assert state()==(8,800,300)
    assert call('GET',f'/api/sales/orders/{source["id"]}')['lines'][0]['open_quantity']==0
    moves=call('GET',f'/api/sales/cancellations/{cancel["id"]}/movements')
    assert sum(row['reserve_expense'] for row in moves['reservations'])==4
    assert moves['inventory']==moves['settlements']==[]
    call('POST',f'/api/sales/cancellations/{cancel["id"]}/unpost')
    second=child('realizations',source,4,date='2026-10-04')
    assert state()==(4,400,900)
    call('POST',f'/api/sales/realizations/{second["id"]}/unpost')
    call('POST',f'/api/sales/realizations/{second["id"]}/post')
    assert state()==(4,400,900)
    assert connection.execute('SELECT SUM(reserve_income-reserve_expense) FROM sales_reservation_register').fetchone()[0]==0


@pytest.mark.parametrize('finance_first',[False,True])
def test_order_issue_and_finance_are_independent_single_expense(sale,finance_first):
    call,_,_,order,child,state,_,_,_=sale
    source=order(mode='order',quantity=3)
    a,b=('realizations','expense-orders') if finance_first else ('expense-orders','realizations')
    first=child(a,source,3)
    assert state()==((10,1000,450) if finance_first else (7,700,0))
    second=child(b,source,3,date='2026-10-04')
    assert state()==(7,700,450)
    finance=first if finance_first else second
    physical=second if finance_first else first
    assert call('GET',f'/api/sales/realizations/{finance["id"]}/movements')['inventory']==[]
    call('POST',f'/api/sales/expense-orders/{physical["id"]}/unpost')
    assert state()==(10,1000,450)
    call('POST',f'/api/sales/expense-orders/{physical["id"]}/post')
    assert state()==(7,700,450)


def test_service_records_real_net_revenue_and_vat_without_inventory(sale):
    call,_,_,order,child,state,_,_,_=sale
    source=order(service=True,quantity=1,price=500)
    invoice=child('realizations',source,1)
    assert state()==(10,1000,500)
    moves=call('GET',f'/api/sales/realizations/{invoice["id"]}/movements')
    assert moves['inventory']==moves['reservations']==[]
    assert moves['revenue'][0]['revenue_amount']==500
    assert sum(row['revenue_amount'] for row in call('GET','/api/sales/revenue'))==500
    call('POST',f'/api/sales/realizations/{invoice["id"]}/unpost')
    assert state()==(10,1000,0) and call('GET','/api/sales/revenue')==[]


@pytest.mark.parametrize('legacy',[False,True])
def test_strict_credit_limit_blocks_new_and_legacy_sales_atomically(sale,legacy):
    call,_,goods,order,child,state,axes,_receipt,_=sale
    call('PUT',f'/api/references/contracts/{axes["contract_id"]}',json=dict(number='Limited',organization_id=axes['organization_id'],
         counterparty_id=axes['counterparty_id'],credit_limit=1000,credit_limit_strict=True))
    child('realizations',order(quantity=6),6)
    before=state()
    assert before==(4,400,900)
    if legacy:
        doc=goods('issues',quantity=1,price=200,date='2026-10-04',post=False)
        call('POST',f'/api/goods/issues/{doc["id"]}/post?auto_schedule=false',400)
    else:
        doc=child('realizations',order(quantity=1,price=200),1,date='2026-10-04',post=False)
        call('POST',f'/api/sales/realizations/{doc["id"]}/post',400)
        assert call('GET',f'/api/sales/realizations/{doc["id"]}/movements')['inventory']==[]
    assert state()==before


def test_reservation_protects_stock_from_other_orders_legacy_sales_and_supplier_return(sale):
    call,_,goods,order,child,state,_,receipt,ret=sale
    source=order()
    before=state()
    call('POST',f'/api/goods/receipts/{receipt["id"]}/unpost',400)
    assert state()==before
    other=order(quantity=5,post=False)
    call('POST',f'/api/sales/orders/{other["id"]}/post',400)
    legacy=goods('issues',quantity=5,post=False,date='2026-10-03')
    call('POST',f'/api/goods/issues/{legacy["id"]}/post?auto_schedule=false',400)
    returned=ret(receipt,5,kind='supplier',post=False)
    call('POST',f'/api/goods/returns/{returned["id"]}/post',400)
    child('realizations',source,6)
    assert state()==(4,400,900)


@pytest.mark.parametrize('role',['viewer','manager','admin'])
@pytest.mark.parametrize('foreign',[False,True])
def test_sales_scope_and_role_on_server(sale,client,role,foreign):
    call,ref,_,order,_,_,axes,_,_=sale
    source=order()
    org=ref('organizations',name='Other') if foreign else axes['organization_id']
    _,headers=scoped_user(call,client,[org],role=role)
    response=client.post('/api/sales/realizations',headers=headers,json=dict(date='2026-10-03',source_id=source['id'],
        lines=[dict(source_line_id=source['lines'][0]['id'],quantity=1)]))
    assert response.status_code==(403 if foreign or role=='viewer' else 201),response.text
    if response.status_code==201:
        doc=response.json()['data']
        posted=client.post(f'/api/sales/realizations/{doc["id"]}/post',headers=headers)
        assert posted.status_code==(200 if role=='admin' else 403),posted.text
    if foreign:
        assert client.get('/api/sales/orders',headers=headers).json()['pagination']['total']==0
        assert client.get(f'/api/sales/orders/{source["id"]}',headers=headers).status_code==403


@pytest.mark.parametrize('action',['post','unpost'])
@pytest.mark.parametrize('kind',['orders','realizations','expense-orders','cancellations'])
def test_sales_lifecycle_fault_rolls_back_all_actual_writes(sale,connection,monkeypatch,kind,action):
    call,_,_,order,child,_,_,_,_=sale
    source=order(mode='order' if kind=='expense-orders' else 'direct',post=kind!='orders')
    doc=source if kind=='orders' else child(kind,source,2,post=False)
    if action=='unpost':
        call('POST',f'/api/sales/{kind}/{doc["id"]}/post')
    tables=('sales_documents','sales_lines','sales_events','sales_reservation_register','sales_revenue_register','inventory_register','mutual_settlements_register','sync_changes')
    def snapshot():
        return {table:[dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY id')] for table in tables}
    before=snapshot()
    real=sales_services.event
    def fail(*args):
        real(*args)
        raise RuntimeError('sales failure after actual facts')
    with monkeypatch.context() as patch:
        patch.setattr(sales_services,'event',fail)
        with pytest.raises(RuntimeError,match='after actual facts'):
            sales_services.change_document(connection,doc['id'],kind,action,UserInfo(id=1,username='admin',role='admin',is_active=True))
    assert not connection.in_transaction and snapshot()==before
    call('POST',f'/api/sales/{kind}/{doc["id"]}/{action}')


def test_same_material_multiline_cost_is_allocated_against_original_snapshot(sale):
    call,_,_,order,_,state,_,receipt,_=sale
    source=order(lines=[line(receipt,line_number=1,quantity=3,price_without_vat=150),line(receipt,line_number=2,quantity=3,price_without_vat=200)])
    doc=call('POST','/api/sales/realizations',201,json=dict(date='2026-10-03',source_id=source['id'],
         lines=[dict(source_line_id=row['id'],quantity=3) for row in source['lines']]))
    doc=call('POST',f'/api/sales/realizations/{doc["id"]}/post')
    assert [row['inventory_cost'] for row in doc['lines']]==[300,300]
    assert state()==(4,400,1050)


def test_packages_series_vat_and_line_object_isolate_reserve_cost(sale):
    call,ref,goods,order,_,state,axes,receipt,_=sale
    material=receipt['lines'][0]['material_id']
    package=ref('material-packages',name='Five',material_id=material,factor=5)
    characteristic=ref('material-characteristics',name='Red',material_id=material)
    series=ref('material-series',name='Batch',material_id=material,characteristic_id=characteristic)
    obj=ref('objects',name='Line object')
    goods('receipts',date='2026-10-01',lines=[line(receipt,quantity=2,price_without_vat=.17,vat_rate=20,package_id=package,characteristic_id=characteristic,series_id=series,object_id=obj)])
    source=order(lines=[line(receipt,quantity=2,price_without_vat=150,vat_rate=20,package_id=package,characteristic_id=characteristic,series_id=series,object_id=obj)])
    def linked(q):
        doc=call('POST','/api/sales/realizations',201,json=dict(date='2026-10-03',source_id=source['id'],lines=[dict(source_line_id=source['lines'][0]['id'],quantity=q)]))
        return call('POST',f'/api/sales/realizations/{doc["id"]}/post')
    a,b=linked(.3),linked(1.7)
    assert Decimal(str(a['lines'][0]['inventory_cost']))+Decimal(str(b['lines'][0]['inventory_cost']))==Decimal('.34')
    moves=call('GET',f'/api/sales/realizations/{a["id"]}/movements')
    row=moves['inventory'][0]
    assert (row['quantity_expense'],row['characteristic_id'],row['series_id'],row['object_id'])==(1.5,characteristic,series,obj)
    assert a['vat_amount']==9 and b['vat_amount']==51
    assert state()==(10,1000,360)


def test_source_limits_dates_dependencies_and_payment_unwind(sale):
    call,_,_,order,child,state,axes,_,_=sale
    source=order()
    other=order(quantity=1)
    for source_line,quantity,date in [(source['lines'][0]['id'],7,'2026-10-03'),(other['lines'][0]['id'],1,'2026-10-03'),(source['lines'][0]['id'],1,'2026-10-01')]:
        call('POST','/api/sales/realizations',400,json=dict(date=date,source_id=source['id'],lines=[dict(source_line_id=source_line,quantity=quantity)]))
    draft=child('realizations',source,2,post=False)
    call('POST',f'/api/sales/orders/{source["id"]}/unpost',400)
    doc=call('POST',f'/api/sales/realizations/{draft["id"]}/post')
    payment=call('POST','/api/payments/transactions',201,json=dict(date='2026-10-04',direction='incoming',amount=100,counterparty_id=axes['counterparty_id'],contract_id=axes['contract_id']))
    call('POST',f'/api/payments/transactions/{payment["id"]}/post')
    call('POST',f'/api/sales/realizations/{doc["id"]}/unpost',400)
    call('POST',f'/api/payments/transactions/{payment["id"]}/unpost')
    call('POST',f'/api/sales/realizations/{doc["id"]}/unpost')
    assert state()==(10,1000,0)


def test_credit_policy_requires_admin_and_omitted_values_survive_manager_edits(sale,client):
    call,_,_,_,_,_,axes,_,_=sale
    payload=dict(number='Limited',organization_id=axes['organization_id'],counterparty_id=axes['counterparty_id'])
    call('PUT',f'/api/references/contracts/{axes["contract_id"]}',json={**payload,'credit_limit':1000,'credit_limit_strict':True})
    _,headers=scoped_user(call,client,[axes['organization_id']],role='manager')
    path=f'/api/references/contracts/{axes["contract_id"]}'
    assert client.put(path,headers=headers,json={**payload,'credit_limit':None}).status_code==403
    response=client.put(path,headers=headers,json={**payload,'number':'Renamed'})
    assert response.status_code==200,response.text
    assert response.json()['data']['credit_limit']==1000 and response.json()['data']['credit_limit_strict']


def test_legacy_backdated_income_cannot_revalue_already_consumed_sales_stock(sale):
    call,_,goods,order,child,state,_,_,_=sale
    child('realizations',order(),2)
    late=goods('receipts',quantity=1,price=200,date='2026-10-02',post=False)
    before=state()
    call('POST',f'/api/goods/receipts/{late["id"]}/post?auto_schedule=false',400)
    assert state()==before


@pytest.mark.parametrize('price',[100,200])
def test_credit_limit_covers_physical_first_unbilled_shipments_without_double_count(sale,price):
    call,ref,goods,order,child,state,axes,_,_=sale
    call('PUT',f'/api/references/contracts/{axes["contract_id"]}',json=dict(number='Limited',organization_id=axes['organization_id'],
         counterparty_id=axes['counterparty_id'],credit_limit=1000,credit_limit_strict=True))
    child('realizations',order(quantity=6),6)
    warehouse=ref('warehouses',name='Physical first',organization_id=axes['organization_id'],order_issue_enabled=True)
    goods('receipts',warehouse_id=warehouse)
    source=order(quantity=1,price=price,warehouse_id=warehouse)
    draft=child('expense-orders',source,1,post=False)
    if price==200:
        before=state()
        call('POST',f'/api/sales/expense-orders/{draft["id"]}/post',400)
        assert state()==before
    else:
        call('POST',f'/api/sales/expense-orders/{draft["id"]}/post')
        other=order(quantity=1,price=100,warehouse_id=warehouse)
        second=child('expense-orders',other,1,post=False)
        call('POST',f'/api/sales/expense-orders/{second["id"]}/post',400)
        child('realizations',source,1)
        assert state()[2]==1000


@pytest.mark.parametrize('race',['reserve','credit'])
def test_competing_sales_sessions_share_warehouse_and_contract_locks(sale,client,admin_headers,monkeypatch,race):
    call,_,_,order,child,state,axes,_,_=sale
    if race=='reserve':
        docs=[order(quantity=6,post=False) for _ in range(2)]
        kind='orders'
    else:
        call('PUT',f'/api/references/contracts/{axes["contract_id"]}',json=dict(number='Limited',organization_id=axes['organization_id'],
             counterparty_id=axes['counterparty_id'],credit_limit=1000,credit_limit_strict=True))
        child('realizations',order(quantity=6),6)
        docs=[child('realizations',order(quantity=1,price=100),1,post=False) for _ in range(2)]
        kind='realizations'
    headers2=login_headers(client)
    assert headers2['Authorization']!=admin_headers['Authorization']
    authenticated=Barrier(2)
    checked,release,attempted,finished=Event(),Event(),Event(),Event()
    owners={}
    real_admin,real_locked,real_locks,real_write=sales_services._require_admin,sales_services.locked,sales_services.lock_inventory_warehouses,sales_services.write_movements
    def admin(user):
        real_admin(user)
        authenticated.wait(10)
    def locked(conn,ident):
        owners[id(conn)]=ident
        if ident==docs[1]['id']:
            assert checked.wait(10)
            attempted.set()
        return real_locked(conn,ident)
    def locks(conn,*ids):
        return real_locks(conn,*ids)
    def write(conn,doc):
        real_write(conn,doc)
        if doc['id']==docs[0]['id']:
            checked.set()
            assert release.wait(10)
    def post(doc,headers,last=False):
        try:
            with TestClient(app) as http:
                return http.post(f'/api/sales/{kind}/{doc["id"]}/post',headers=headers).status_code
        finally:
            if last:finished.set()
    monkeypatch.setattr(sales_services,'_require_admin',admin)
    monkeypatch.setattr(sales_services,'locked',locked)
    monkeypatch.setattr(sales_services,'lock_inventory_warehouses',locks)
    monkeypatch.setattr(sales_services,'write_movements',write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(post,docs[0],admin_headers)
        b=pool.submit(post,docs[1],headers2,True)
        try:
            assert attempted.wait(10) and not finished.is_set()
        finally:
            release.set()
        assert [a.result(timeout=10),b.result(timeout=10)]==[200,400]
    assert state()==((10,1000,0) if race=='reserve' else (3,300,1000))
