"""Sales planning/reserves, single physical issue and independent revenue/debt."""
from decimal import Decimal
import json

from fastapi import HTTPException

from api.database import row_to_dict, rows_to_dicts, new_uuid, utcnow_iso
from api.goods_services import _require_write, _require_admin, _inventory_balance
from api.inventory_dimensions import active, validate_snapshot, hydrate_lines, axes, base_unit, base_quantity, lock_material_dimensions
from api.purchase_services import LINE_FIELDS, normalize_order_line, totals
from api.return_services import insert, assert_stock_removal
from api.sales_rules import assert_available, assert_credit
from api.trade_access import require_organization, require_goods_links, add_scope, add_goods_links_scope, rollback_on_error
from api.trade_settlement_rules import money, validate_contract, inventory_cost_share, assert_no_future_price_adjustment, assert_no_inventory_consumption, lock_inventory_warehouses, lock_settlement_contracts

KINDS=('orders','realizations','expense-orders','cancellations')
DIMENSIONS=('organization_id','counterparty_id','contract_id','warehouse_id','object_id','estimate_id','issue_mode')
EPS=Decimal('0.000000001')


def reject(message):
    raise HTTPException(status_code=400,detail=message)


def ensure_schema(connection, ensure_column):
    ensure_column(connection,'warehouses','order_issue_enabled','INTEGER NOT NULL DEFAULT 0')
    ensure_column(connection,'contracts','credit_limit','REAL')
    ensure_column(connection,'contracts','credit_limit_strict','INTEGER NOT NULL DEFAULT 0')
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS sales_documents (
      id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, number TEXT NOT NULL, date TEXT NOT NULL,
      source_id INTEGER REFERENCES sales_documents(id), order_id INTEGER REFERENCES sales_documents(id),
      organization_id INTEGER NOT NULL REFERENCES organizations(id), counterparty_id INTEGER NOT NULL REFERENCES counterparties(id),
      contract_id INTEGER NOT NULL REFERENCES contracts(id), warehouse_id INTEGER REFERENCES warehouses(id),
      object_id INTEGER REFERENCES objects(id), estimate_id INTEGER REFERENCES estimates(id), issue_mode TEXT NOT NULL,
      description TEXT, is_posted INTEGER NOT NULL DEFAULT 0, posted_at TEXT, is_deleted INTEGER NOT NULL DEFAULT 0,
      uuid TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, modified_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sales_lines (
      id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL REFERENCES sales_documents(id), line_number INTEGER NOT NULL,
      source_line_id INTEGER REFERENCES sales_lines(id), order_line_id INTEGER REFERENCES sales_lines(id),
      line_type TEXT NOT NULL, name TEXT NOT NULL, material_id INTEGER REFERENCES materials(id), object_id INTEGER REFERENCES objects(id),
      unit_id INTEGER REFERENCES units(id), unit TEXT, quantity REAL NOT NULL, price_without_vat REAL NOT NULL, vat_rate REAL NOT NULL,
      sum_without_vat REAL NOT NULL, vat_amount REAL NOT NULL, sum_with_vat REAL NOT NULL,
      package_id INTEGER REFERENCES material_packages(id), characteristic_id INTEGER REFERENCES material_characteristics(id),
      series_id INTEGER REFERENCES material_series(id), conversion_factor REAL NOT NULL, base_quantity REAL NOT NULL,
      base_unit_id INTEGER REFERENCES units(id), drawing_code TEXT, note TEXT, inventory_cost REAL,
      is_deleted INTEGER NOT NULL DEFAULT 0, uuid TEXT NOT NULL UNIQUE);
    CREATE INDEX IF NOT EXISTS idx_sales_source ON sales_documents(source_id,is_deleted);
    CREATE INDEX IF NOT EXISTS idx_sales_lines_order ON sales_lines(order_line_id,document_id);
    CREATE TABLE IF NOT EXISTS sales_reservation_register (
      id INTEGER PRIMARY KEY AUTOINCREMENT, recorder_type TEXT NOT NULL, recorder_id INTEGER NOT NULL REFERENCES sales_documents(id),
      order_id INTEGER NOT NULL REFERENCES sales_documents(id), line_number INTEGER NOT NULL, period TEXT NOT NULL,
      organization_id INTEGER NOT NULL REFERENCES organizations(id), warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
      object_id INTEGER REFERENCES objects(id), material_id INTEGER NOT NULL REFERENCES materials(id), unit_id INTEGER NOT NULL REFERENCES units(id),
      characteristic_id INTEGER REFERENCES material_characteristics(id), series_id INTEGER REFERENCES material_series(id),
      reserve_income REAL NOT NULL DEFAULT 0, reserve_expense REAL NOT NULL DEFAULT 0, is_deleted INTEGER NOT NULL DEFAULT 0, uuid TEXT NOT NULL UNIQUE);
    CREATE INDEX IF NOT EXISTS idx_sales_reserve_slice ON sales_reservation_register(warehouse_id,material_id,unit_id,period);
    CREATE TABLE IF NOT EXISTS sales_revenue_register (
      id INTEGER PRIMARY KEY AUTOINCREMENT, recorder_type TEXT NOT NULL, recorder_id INTEGER NOT NULL REFERENCES sales_documents(id),
      line_number INTEGER NOT NULL, period TEXT NOT NULL, organization_id INTEGER NOT NULL REFERENCES organizations(id),
      counterparty_id INTEGER NOT NULL REFERENCES counterparties(id), contract_id INTEGER NOT NULL REFERENCES contracts(id),
      object_id INTEGER REFERENCES objects(id), estimate_id INTEGER REFERENCES estimates(id), source_line_id INTEGER NOT NULL REFERENCES sales_lines(id),
      name TEXT NOT NULL, revenue_amount REAL NOT NULL, vat_amount REAL NOT NULL, is_deleted INTEGER NOT NULL DEFAULT 0, uuid TEXT NOT NULL UNIQUE);
    CREATE TABLE IF NOT EXISTS sales_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL REFERENCES sales_documents(id), operation TEXT NOT NULL,
      user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, snapshot TEXT NOT NULL);
    ''')


def recorder(kind):
    return 'sale_'+{'orders':'order','realizations':'realization','expense-orders':'expense_order','cancellations':'cancellation'}[kind]


def event(connection, doc, operation, user):
    insert(connection,'sales_events',dict(document_id=doc['id'],operation=operation,user_id=user.id,created_at=utcnow_iso(),snapshot=json.dumps(doc,ensure_ascii=False)))


def raw(connection, ident):
    row=connection.execute('SELECT * FROM sales_documents WHERE id = ? AND is_deleted = 0',(ident,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404,detail='Документ продажи не найден')
    return row_to_dict(row)


def progress(connection, line_id):
    result={key:Decimal(0) for key in KINDS}
    for row in connection.execute('''SELECT d.kind,l.quantity FROM sales_lines l JOIN sales_documents d ON d.id = l.document_id
        WHERE l.order_line_id = ? AND l.is_deleted = 0 AND d.is_deleted = 0 AND d.is_posted = 1''',(line_id,)).fetchall():
        result[row['kind']]+=Decimal(str(row['quantity']))
    return result


def physical_quantity(doc,line,p):
    return p['realizations'] if doc['issue_mode']=='direct' or line['line_type']=='service' else p['expense-orders']


def get_document(connection, ident, expected_kind=None):
    doc=raw(connection,ident)
    if expected_kind and expected_kind!=doc['kind']:
        raise HTTPException(status_code=404,detail='Неверный вид документа продажи')
    require_organization(connection,doc['organization_id'])
    require_goods_links(connection,doc)
    if doc['source_id']:
        source=get_document(connection,doc['source_id'],'orders')
        if any(doc[key]!=source[key] for key in DIMENSIONS):
            reject('Аналитики продажи не совпадают с заказом')
        doc['source_number']=source['number']
    doc['is_posted']=bool(doc['is_posted'])
    doc['lines']=hydrate_lines(connection,rows_to_dicts(connection.execute(
        'SELECT * FROM sales_lines WHERE document_id = ? AND is_deleted = 0 ORDER BY line_number',(ident,)).fetchall()))
    for table,key,label in [('organizations','organization_id','organization_name'),('counterparties','counterparty_id','counterparty_name'),
                            ('contracts','contract_id','contract_number'),('warehouses','warehouse_id','warehouse_name'),('objects','object_id','object_name')]:
        found=connection.execute(f'SELECT {"number" if table=="contracts" else "name"} FROM {table} WHERE id = ?',(doc[key],)).fetchone()
        doc[label]=found[0] if found else None
    if doc['kind']=='orders':
        for line in doc['lines']:
            p=progress(connection,line['id'])
            shipped=physical_quantity(doc,line,p)
            opened=max(Decimal(str(line['quantity']))-shipped-p['cancellations'],0)
            line.update(shipped_quantity=float(shipped),financial_quantity=float(p['realizations']),cancelled_quantity=float(p['cancellations']),
                open_quantity=float(opened),reserved_quantity=float(opened) if line['line_type']=='goods' and doc['is_posted'] else 0)
    for field in ('sum_without_vat','vat_amount','sum_with_vat'):
        doc[field]=float(sum((money(line[field]) for line in doc['lines']),Decimal(0)))
    return doc


def locked(connection, ident):
    before=raw(connection,ident)
    root=before['order_id'] or ident
    connection.execute('UPDATE sales_documents SET id = id WHERE id = ?',(root,))
    if ident!=root:
        connection.execute('UPDATE sales_documents SET id = id WHERE id = ?',(ident,))
    doc=get_document(connection,ident)
    if (doc['order_id'] or ident)!=root:
        reject('Основание изменилось во время операции')
    return doc


def dependents(connection, ident):
    return connection.execute('SELECT id FROM sales_documents WHERE source_id = ? AND is_deleted = 0 LIMIT 1',(ident,)).fetchone()


def validate_header(connection,doc):
    require_organization(connection,doc['organization_id'])
    require_goods_links(connection,doc)
    active(connection,'organizations',doc['organization_id'])
    active(connection,'counterparties',doc['counterparty_id'])
    validate_contract(connection,contract_id=doc['contract_id'],organization_id=doc['organization_id'],counterparty_id=doc['counterparty_id'])
    if doc.get('warehouse_id'):
        warehouse=active(connection,'warehouses',doc['warehouse_id'])
        if warehouse['organization_id']!=doc['organization_id'] or ('order' if warehouse['order_issue_enabled'] else 'direct')!=doc['issue_mode']:
            reject('Владелец или схема склада изменилась')
    if doc.get('object_id'):
        active(connection,'objects',doc['object_id'])


def validate_basis(connection,doc,source):
    if not source['is_posted'] or source['kind']!='orders' or doc['date']<source['date']:
        reject('Требуется согласованный заказ с датой не позже продажи')
    if any(doc[key]!=source[key] for key in DIMENSIONS):
        reject('Аналитики продажи не совпадают с заказом')
    originals={line['id']:line for line in source['lines']}
    for line in doc['lines']:
        original=originals.get(line['source_line_id'])
        if not original or line['order_line_id']!=original['id'] or any(line[key]!=original[key] for key in LINE_FIELDS):
            reject('Строка, цена или аналитика не принадлежит заказу')
        p=progress(connection,original['id'])
        physical=physical_quantity(doc,line,p)
        if doc['kind']=='expense-orders':
            if doc['issue_mode']!='order' or line['line_type']!='goods':
                reject('Расходный ордер используется только для товара ордерного склада')
            used=physical
        elif doc['kind']=='realizations':
            used=p['realizations']
        else:
            used=max(physical,p['realizations'])
        if used+Decimal(str(line['quantity']))>Decimal(str(original['quantity']))-p['cancellations']+EPS:
            reject('Количество продажи или отмены превышает остаток заказа')
        if line['line_type']=='goods':
            validate_snapshot(connection,line)


@rollback_on_error
def save_document(connection,kind,payload,user,ident=None):
    _require_write(user)
    existing=locked(connection,ident) if ident else None
    if existing and (existing['kind']!=kind or existing['is_posted'] or dependents(connection,ident)):
        reject('Проведенную продажу или используемый заказ изменять нельзя')
    source=None
    if kind!='orders':
        if existing and existing['source_id']!=payload['source_id']:
            reject('Смена основания требует нового документа')
        source=locked(connection,payload['source_id'])
        values={key:source[key] for key in DIMENSIONS}
        values.update(source_id=source['id'],order_id=source['id'])
    else:
        values={key:payload.get(key) for key in DIMENSIONS if key!='issue_mode'}
        warehouse=active(connection,'warehouses',values['warehouse_id']) if values['warehouse_id'] else None
        values.update(issue_mode='order' if warehouse and warehouse['order_issue_enabled'] else 'direct',source_id=None,order_id=None)
    lock_material_dimensions(connection,*(line.get('material_id') for line in (source['lines'] if source else payload['lines'])))
    lock_inventory_warehouses(connection,values['warehouse_id'])
    lock_settlement_contracts(connection,values['contract_id'])
    validate_header(connection,values)
    stamp=utcnow_iso()
    values.update(kind=kind,number=payload['number'] or (existing['number'] if existing else 'SAL-'+new_uuid()[:8]),date=str(payload['date']),
                  description=payload.get('description'),modified_at=stamp,updated_at=stamp)
    seen=set()
    originals={line['id']:line for line in source['lines']} if source else {}
    lines=[]
    for number,row in enumerate(payload['lines'],1):
        key=row['source_line_id'] if source else row['line_number']
        if key in seen:
            reject('Повторяется строка заказа/номер строки')
        seen.add(key)
        if source:
            original=originals.get(key)
            if not original or row.get('receipt_line_id'):
                reject('Неверная строка основания')
            line=totals({**{k:original[k] for k in LINE_FIELDS},'quantity':row['quantity']})
            line.update(source_line_id=key,order_line_id=key,line_number=number)
        else:
            line=normalize_order_line(connection,row)
        lines.append(line)
    if any(line['line_type']=='goods' for line in lines) and not values['warehouse_id']:
        reject('Для товаров требуется склад')
    if source:
        validate_basis(connection,{**values,'lines':lines},source)
    if existing:
        connection.execute(f"UPDATE sales_documents SET {', '.join(k+' = ?' for k in values)} WHERE id = ?",(*values.values(),ident))
    else:
        ident=insert(connection,'sales_documents',{**values,'uuid':new_uuid(),'created_at':stamp})
    old={row['line_number']:row for row in connection.execute('SELECT id,line_number FROM sales_lines WHERE document_id = ? AND is_deleted = 0',(ident,)).fetchall()}
    connection.execute('UPDATE sales_lines SET is_deleted = 1 WHERE document_id = ?',(ident,))
    for line in lines:
        prior=old.get(line['line_number'])
        if prior:
            connection.execute(f"UPDATE sales_lines SET {', '.join(k+' = ?' for k in line)}, is_deleted = 0, inventory_cost = NULL WHERE id = ?",(*line.values(),prior['id']))
        else:
            line_id=insert(connection,'sales_lines',{**line,'document_id':ident,'uuid':new_uuid()})
            if kind=='orders':
                connection.execute('UPDATE sales_lines SET order_line_id = id WHERE id = ?',(line_id,))
    result=get_document(connection,ident,kind)
    event(connection,result,'update' if existing else 'create',user)
    connection.commit()
    return result


def stock_args(doc,line):
    return dict(warehouse_id=doc['warehouse_id'],object_id=line['object_id'] if line['object_id'] is not None else doc['object_id'],
                material_id=line['material_id'],unit_id=base_unit(line),**axes(line))


def write_movements(connection,doc):
    kind=doc['kind']
    rec=recorder(kind)
    required={}
    allocated={}
    costs={}
    if kind=='realizations':
        assert_credit(connection,doc,[(line['object_id'] if line['object_id'] is not None else doc['object_id'],line['sum_with_vat']) for line in doc['lines']],financial_lines=doc['lines'])
    elif kind=='expense-orders':
        assert_credit(connection,doc,[],physical_lines=doc['lines'])
    # Validate/allocate the complete document against one pre-write snapshot.
    for line in doc['lines']:
        goods=line['line_type']=='goods'
        physical=goods and (kind=='expense-orders' or (kind=='realizations' and doc['issue_mode']=='direct'))
        reserve=goods and kind=='orders'
        args=stock_args(doc,line)
        if reserve or physical:
            key=tuple(args.values())
            required[key]=required.get(key,Decimal(0))+Decimal(str(base_quantity(line)))
            assert_available(connection,**args,on_date=doc['date'],quantity=required[key],exclude_order_id=doc['order_id'] if physical else None)
        if physical:
            assert_no_future_price_adjustment(connection,**args,on_date=doc['date'])
            qty,cost,_=_inventory_balance(connection,**args,on_date=doc['date'])
            total=inventory_cost_share(cost,required[key],qty)
            value=total-allocated.get(key,Decimal(0))
            allocated[key]=total
            assert_stock_removal(connection,doc['warehouse_id'],args['object_id'],line['material_id'],base_unit(line),doc['date'],required[key],total,**axes(line),check_reservations=False)
            costs[line['id']]=value
    for line in doc['lines']:
        goods=line['line_type']=='goods'
        physical=goods and (kind=='expense-orders' or (kind=='realizations' and doc['issue_mode']=='direct'))
        reserve=goods and kind=='orders'
        release=goods and (physical or kind=='cancellations')
        obj=line['object_id'] if line['object_id'] is not None else doc['object_id']
        args=stock_args(doc,line)
        if physical:
            value=costs[line['id']]
            connection.execute('UPDATE sales_lines SET inventory_cost = ? WHERE id = ?',(float(value),line['id']))
            insert(connection,'inventory_register',dict(recorder_type=rec,recorder_id=doc['id'],line_number=line['line_number'],period=doc['date'],
                **args,quantity_income=0,quantity_expense=base_quantity(line),sum_income=0,sum_expense=float(value),uuid=new_uuid()))
        if reserve or release:
            insert(connection,'sales_reservation_register',dict(recorder_type=rec,recorder_id=doc['id'],order_id=doc['order_id'] or doc['id'],
                line_number=line['line_number'],period=doc['date'],organization_id=doc['organization_id'],**args,
                reserve_income=base_quantity(line) if reserve else 0,reserve_expense=base_quantity(line) if release else 0,uuid=new_uuid()))
        if kind=='realizations':
            common=dict(recorder_type=rec,recorder_id=doc['id'],line_number=line['line_number'],period=doc['date'],organization_id=doc['organization_id'],
                        counterparty_id=doc['counterparty_id'],contract_id=doc['contract_id'],object_id=obj,estimate_id=doc['estimate_id'],uuid=new_uuid())
            insert(connection,'mutual_settlements_register',{**common,'direction':'receivable','accrual_amount':line['sum_with_vat']})
            insert(connection,'sales_revenue_register',{**common,'source_line_id':line['source_line_id'],'name':line['name'],
                                                       'revenue_amount':line['sum_without_vat'],'vat_amount':line['vat_amount'],'uuid':new_uuid()})


@rollback_on_error
def change_document(connection,ident,kind,action,user):
    (_require_write if action=='delete' else _require_admin)(user)
    doc=locked(connection,ident)
    if doc['kind']!=kind:
        reject('Неверный вид продажи')
    lock_inventory_warehouses(connection,doc['warehouse_id'])
    lock_settlement_contracts(connection,doc['contract_id'])
    doc=get_document(connection,ident,kind)
    validate_header(connection,doc)
    if action=='post':
        if doc['is_posted']:
            reject('Продажа уже проведена/заказ подтвержден')
        if doc['source_id']:
            validate_basis(connection,doc,get_document(connection,doc['source_id'],'orders'))
        else:
            for line in doc['lines']:
                if line['line_type']=='goods':
                    validate_snapshot(connection,line)
        write_movements(connection,doc)
        connection.execute('UPDATE sales_documents SET is_posted = 1, posted_at = ?, updated_at = ?, modified_at = ? WHERE id = ?',
                           (utcnow_iso(),utcnow_iso(),utcnow_iso(),ident))
    else:
        if dependents(connection,ident):
            reject('Сначала отмените и удалите зависимые продажи')
        if action=='delete':
            if doc['is_posted']:
                reject('Проведенную продажу удалить нельзя')
            connection.execute('UPDATE sales_documents SET is_deleted = 1, updated_at = ?, modified_at = ? WHERE id = ?',(utcnow_iso(),utcnow_iso(),ident))
        else:
            if not doc['is_posted']:
                reject('Продажа не проведена')
            if kind=='realizations' and connection.execute('''SELECT id FROM mutual_settlements_register WHERE organization_id = ? AND counterparty_id = ?
                AND contract_id = ? AND direction = 'receivable' AND recorder_type = 'payment_transaction' AND payment_amount > 0 AND is_deleted = 0 LIMIT 1''',
                (doc['organization_id'],doc['counterparty_id'],doc['contract_id'])).fetchone():
                reject('Сначала отмените оплаты покупателя по договору')
            rec=recorder(kind)
            for move in connection.execute('SELECT * FROM inventory_register WHERE recorder_type = ? AND recorder_id = ?',(rec,ident)).fetchall():
                assert_no_inventory_consumption(connection,warehouse_id=move['warehouse_id'],object_id=move['object_id'],material_id=move['material_id'],
                    unit_id=move['unit_id'],on_date=move['period'],after_movement_id=move['id'],exclude_recorder_type=rec,exclude_recorder_id=ident,**axes(move))
            for table in ('inventory_register','mutual_settlements_register','sales_reservation_register','sales_revenue_register'):
                connection.execute(f'DELETE FROM {table} WHERE recorder_type = ? AND recorder_id = ?',(rec,ident))
            # Undoing releases restores a reservation; validate the resulting
            # entire free-stock timeline after all own movements are removed.
            for line in doc['lines']:
                if line['line_type']=='goods':
                    assert_available(connection,**stock_args(doc,line),on_date=doc['date'],quantity=0)
            connection.execute('UPDATE sales_documents SET is_posted = 0, posted_at = NULL, updated_at = ?, modified_at = ? WHERE id = ?',
                               (utcnow_iso(),utcnow_iso(),ident))
    result={'id':ident} if action=='delete' else get_document(connection,ident,kind)
    event_doc={**doc,**dict(connection.execute('SELECT * FROM sales_documents WHERE id = ?',(ident,)).fetchone())} if action=='delete' else result
    event(connection,event_doc,action,user)
    connection.commit()
    return result


def list_documents(connection,kind,page=1,page_size=20):
    conditions,params=['d.kind = ?','d.is_deleted = 0'],[kind]
    add_scope(connection,conditions,params,'d.organization_id')
    add_goods_links_scope(connection,conditions,params,based_on=False)
    where=' AND '.join(conditions)
    count=connection.execute(f'SELECT COUNT(*) FROM sales_documents d WHERE {where}',params).fetchone()[0]
    ids=connection.execute(f'SELECT d.id FROM sales_documents d WHERE {where} ORDER BY d.date DESC,d.id DESC LIMIT ? OFFSET ?',
                           (*params,page_size,(page-1)*page_size)).fetchall()
    return [get_document(connection,row[0],kind) for row in ids],dict(page=page,page_size=page_size,total=count,pages=max(1,(count+page_size-1)//page_size))


def movements(connection,ident,kind):
    doc=get_document(connection,ident,kind)
    return dict(document=doc,**{key:rows_to_dicts(connection.execute(f'SELECT * FROM {table} WHERE recorder_type = ? AND recorder_id = ? ORDER BY line_number',
        (recorder(kind),ident)).fetchall()) for key,table in [('inventory','inventory_register'),('settlements','mutual_settlements_register'),
                                                           ('reservations','sales_reservation_register'),('revenue','sales_revenue_register')]})


def revenue(connection,date_from,date_to):
    conditions,params=['e.is_deleted = 0','e.period >= ?','e.period <= ?'],[date_from,date_to]
    add_scope(connection,conditions,params,'e.organization_id')
    add_goods_links_scope(connection,conditions,params,alias='e',based_on=False)
    return rows_to_dicts(connection.execute(f"SELECT e.* FROM sales_revenue_register e WHERE {' AND '.join(conditions)} ORDER BY e.period,e.id",params).fetchall())


def reserves(connection,on_date):
    conditions,params=['r.is_deleted = 0','r.period <= ?'],[on_date]
    add_scope(connection,conditions,params,'r.organization_id')
    add_goods_links_scope(connection,conditions,params,alias='d',based_on=False)
    return hydrate_lines(connection,rows_to_dicts(connection.execute(f'''SELECT r.organization_id,r.order_id,r.warehouse_id,r.object_id,
        r.material_id,r.unit_id,r.characteristic_id,r.series_id,SUM(r.reserve_income-r.reserve_expense) AS reserved_quantity
        FROM sales_reservation_register r JOIN sales_documents d ON d.id = r.order_id WHERE {' AND '.join(conditions)}
        GROUP BY r.organization_id,r.order_id,r.warehouse_id,r.object_id,r.material_id,r.unit_id,r.characteristic_id,r.series_id
        HAVING SUM(r.reserve_income-r.reserve_expense) > 0.000000001 ORDER BY r.order_id,r.material_id''',params).fetchall()))
