"""Supplier planning, single physical receipt, invoice debt and explicit expense.

One approved order snapshots price/units and owns the serialization lock. Order
warehouses accept physical quantity through receipt orders and debt through
acquisitions, in either order. No later cost recomputation is implied.
"""
from decimal import Decimal
import json

from fastapi import HTTPException

from api.database import row_to_dict, rows_to_dicts, new_uuid, utcnow_iso
from api.goods_services import _require_write, _require_admin
from api.inventory_dimensions import active, normalize_line, validate_snapshot, hydrate_lines, axes, base_unit, base_quantity, lock_material_dimensions
from api.return_services import insert, assert_stock_removal
from api.trade_access import add_scope, add_goods_links_scope, require_organization, require_goods_links, rollback_on_error
from api.trade_settlement_rules import money, validate_contract, lock_inventory_warehouses, lock_settlement_contracts, assert_no_inventory_consumption

KINDS = ('orders', 'acquisitions', 'receipt-orders', 'cancellations', 'discrepancies', 'quantity-adjustments')
SOURCES = {'acquisitions': 'orders', 'receipt-orders': 'orders', 'cancellations': 'orders',
           'discrepancies': 'acquisitions', 'quantity-adjustments': 'discrepancies'}
DIMENSIONS = ('organization_id', 'counterparty_id', 'contract_id', 'warehouse_id', 'object_id', 'estimate_id', 'receipt_mode')
LINE_FIELDS = ('line_type', 'name', 'material_id', 'object_id', 'unit_id', 'unit', 'price_without_vat',
               'vat_rate', 'package_id', 'characteristic_id', 'series_id', 'conversion_factor', 'base_unit_id', 'drawing_code', 'note')
EPS = Decimal('0.000000001')


def reject(message):
    raise HTTPException(status_code=400, detail=message)


def ensure_schema(connection, ensure_column):
    ensure_column(connection, 'warehouses', 'order_receipt_enabled', 'INTEGER NOT NULL DEFAULT 0')
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS purchase_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, number TEXT NOT NULL, date TEXT NOT NULL,
        source_id INTEGER REFERENCES purchase_documents(id), order_id INTEGER REFERENCES purchase_documents(id),
        organization_id INTEGER NOT NULL REFERENCES organizations(id), counterparty_id INTEGER NOT NULL REFERENCES counterparties(id),
        contract_id INTEGER NOT NULL REFERENCES contracts(id), warehouse_id INTEGER REFERENCES warehouses(id),
        object_id INTEGER REFERENCES objects(id), estimate_id INTEGER REFERENCES estimates(id), receipt_mode TEXT NOT NULL,
        description TEXT, is_posted INTEGER NOT NULL DEFAULT 0, posted_at TEXT, is_deleted INTEGER NOT NULL DEFAULT 0,
        uuid TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, modified_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS purchase_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL REFERENCES purchase_documents(id),
        line_number INTEGER NOT NULL, source_line_id INTEGER REFERENCES purchase_lines(id),
        order_line_id INTEGER REFERENCES purchase_lines(id), receipt_line_id INTEGER REFERENCES purchase_lines(id),
        line_type TEXT NOT NULL, name TEXT NOT NULL, material_id INTEGER REFERENCES materials(id),
        object_id INTEGER REFERENCES objects(id), unit_id INTEGER REFERENCES units(id), unit TEXT,
        quantity REAL NOT NULL, price_without_vat REAL NOT NULL, vat_rate REAL NOT NULL,
        sum_without_vat REAL NOT NULL, vat_amount REAL NOT NULL, sum_with_vat REAL NOT NULL,
        package_id INTEGER REFERENCES material_packages(id), characteristic_id INTEGER REFERENCES material_characteristics(id),
        series_id INTEGER REFERENCES material_series(id), conversion_factor REAL NOT NULL, base_quantity REAL NOT NULL,
        base_unit_id INTEGER REFERENCES units(id), drawing_code TEXT, note TEXT,
        is_deleted INTEGER NOT NULL DEFAULT 0, uuid TEXT NOT NULL UNIQUE
    );
    CREATE INDEX IF NOT EXISTS idx_purchase_basis ON purchase_documents(source_id, is_posted, is_deleted);
    CREATE INDEX IF NOT EXISTS idx_purchase_order_lines ON purchase_lines(order_line_id, document_id);
    CREATE TABLE IF NOT EXISTS purchase_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL REFERENCES purchase_documents(id),
        operation TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
        snapshot TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS purchase_expense_register (
        id INTEGER PRIMARY KEY AUTOINCREMENT, recorder_type TEXT NOT NULL, recorder_id INTEGER NOT NULL REFERENCES purchase_documents(id),
        line_number INTEGER NOT NULL, period TEXT NOT NULL, organization_id INTEGER NOT NULL REFERENCES organizations(id),
        counterparty_id INTEGER NOT NULL REFERENCES counterparties(id), contract_id INTEGER NOT NULL REFERENCES contracts(id),
        object_id INTEGER REFERENCES objects(id), estimate_id INTEGER REFERENCES estimates(id),
        source_line_id INTEGER NOT NULL REFERENCES purchase_lines(id), name TEXT NOT NULL, expense_amount REAL NOT NULL,
        vat_amount REAL NOT NULL, uuid TEXT NOT NULL UNIQUE, is_deleted INTEGER NOT NULL DEFAULT 0
    );''')


def recorder(kind):
    return 'purchase_' + {'discrepancies': 'discrepancy'}.get(kind, kind.replace('-', '_').rstrip('s'))


def record_event(connection, doc, operation, user):
    # New procurement documents need a dedicated inter-node adapter. Keep
    # their durable local audit out of the legacy serializer's change queue.
    insert(connection, 'purchase_events', dict(document_id=doc['id'], operation=operation, user_id=user.id,
        created_at=utcnow_iso(), snapshot=json.dumps(doc, ensure_ascii=False)))


def raw_document(connection, ident):
    row = connection.execute('SELECT * FROM purchase_documents WHERE id = ? AND is_deleted = 0', (ident,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='Закупочный документ не найден')
    return row_to_dict(row)


def locked_document(connection, ident):
    original = raw_document(connection, ident)
    root = original['order_id'] or original['id']
    connection.execute('UPDATE purchase_documents SET id = id WHERE id = ?', (root,))
    if ident != root:
        connection.execute('UPDATE purchase_documents SET id = id WHERE id = ?', (ident,))
    current = raw_document(connection, ident)
    if (current['order_id'] or current['id']) != root:
        reject('Основание изменилось во время операции')
    return get_document(connection, ident)


def progress(connection, order_line_id):
    rows = connection.execute('''SELECT d.kind, SUM(l.quantity) AS quantity
        FROM purchase_lines l JOIN purchase_documents d ON d.id = l.document_id
        WHERE l.order_line_id = ? AND d.is_posted = 1 AND d.is_deleted = 0 AND l.is_deleted = 0
        GROUP BY d.kind''', (order_line_id,)).fetchall()
    amounts = {row['kind']: Decimal(str(row['quantity'])) for row in rows}
    return {kind: amounts.get(kind, Decimal(0)) for kind in KINDS}


def get_document(connection, ident, expected_kind=None):
    doc = raw_document(connection, ident)
    if expected_kind and doc['kind'] != expected_kind:
        raise HTTPException(status_code=404, detail='Вид закупочного документа не совпадает')
    require_organization(connection, doc['organization_id'])
    require_goods_links(connection, doc)
    if doc['source_id']:
        source = get_document(connection, doc['source_id'], SOURCES[doc['kind']])
        if any(doc[key] != source[key] for key in DIMENSIONS):
            reject('Аналитики документа не совпадают с основанием')
        doc['source_number'] = source['number']
    doc['is_posted'] = bool(doc['is_posted'])
    doc['lines'] = hydrate_lines(connection, rows_to_dicts(connection.execute(
        'SELECT * FROM purchase_lines WHERE document_id = ? AND is_deleted = 0 ORDER BY line_number', (ident,)).fetchall()))
    for table, key, label in [('organizations', 'organization_id', 'organization_name'), ('counterparties', 'counterparty_id', 'counterparty_name'),
                               ('contracts', 'contract_id', 'contract_number'), ('warehouses', 'warehouse_id', 'warehouse_name'),
                               ('objects', 'object_id', 'object_name')]:
        row = connection.execute(f'SELECT {"number" if table == "contracts" else "name"} FROM {table} WHERE id = ?', (doc[key],)).fetchone()
        doc[label] = row[0] if row else None
    if doc['kind'] == 'orders':
        for line in doc['lines']:
            p = progress(connection, line['id'])
            received = p['acquisitions'] - p['quantity-adjustments'] if doc['receipt_mode'] == 'direct' or line['line_type'] == 'service' else p['receipt-orders']
            line.update(received_quantity=float(received), cancelled_quantity=float(p['cancellations']),
                        shortage_quantity=float(p['discrepancies']), financial_quantity=float(p['acquisitions'] - p['quantity-adjustments']),
                        open_quantity=float(max(Decimal(str(line['quantity'])) - received - p['cancellations'] - p['discrepancies'], 0)))
    doc['sum_without_vat'] = float(sum((money(line['sum_without_vat']) for line in doc['lines']), Decimal(0)))
    doc['vat_amount'] = float(sum((money(line['vat_amount']) for line in doc['lines']), Decimal(0)))
    doc['sum_with_vat'] = float(sum((money(line['sum_with_vat']) for line in doc['lines']), Decimal(0)))
    return doc


def list_documents(connection, kind, page=1, page_size=20):
    conditions, params = ['d.kind = ?', 'd.is_deleted = 0'], [kind]
    add_scope(connection, conditions, params, 'd.organization_id')
    add_goods_links_scope(connection, conditions, params, based_on=False)
    clause = ' AND '.join(conditions)
    total = connection.execute(f'SELECT COUNT(*) FROM purchase_documents d WHERE {clause}', params).fetchone()[0]
    ids = connection.execute(f'SELECT d.id FROM purchase_documents d WHERE {clause} ORDER BY d.date DESC, d.id DESC LIMIT ? OFFSET ?',
                             (*params, page_size, (page-1)*page_size)).fetchall()
    return [get_document(connection, row[0], kind) for row in ids], dict(page=page, page_size=page_size, total=total, pages=max(1, (total+page_size-1)//page_size))


def validate_header(connection, doc):
    require_organization(connection, doc['organization_id'])
    require_goods_links(connection, doc)
    active(connection, 'organizations', doc['organization_id'])
    active(connection, 'counterparties', doc['counterparty_id'])
    validate_contract(connection, contract_id=doc['contract_id'], counterparty_id=doc['counterparty_id'], organization_id=doc['organization_id'])
    if doc.get('warehouse_id'):
        warehouse = active(connection, 'warehouses', doc['warehouse_id'])
        if warehouse['organization_id'] != doc['organization_id']:
            reject('Склад принадлежит другой организации')
        mode = 'order' if warehouse['order_receipt_enabled'] else 'direct'
        if mode != doc['receipt_mode']:
            reject('Схема приемки склада не совпадает с документом')
    if doc.get('object_id'):
        active(connection, 'objects', doc['object_id'])


def totals(line):
    quantity = Decimal(str(line['quantity']))
    net = money(quantity * Decimal(str(line['price_without_vat'])))
    vat = money(net * Decimal(str(line['vat_rate'])) / 100)
    line.update(sum_without_vat=float(net), vat_amount=float(vat), sum_with_vat=float(net+vat),
                base_quantity=float(quantity * Decimal(str(line['conversion_factor']))) if line['line_type'] == 'goods' else 0)
    return line


def allocate_adjustment_values(connection, doc):
    """Reverse the posted invoice's cents across all its shortage acts.

    Recompute at posting under the root lock: draft allocations are previews.
    Fixed source value reversals do not consume stock at its average cost.
    """
    if doc['kind'] != 'quantity-adjustments':
        return
    for line in doc['lines']:
        original = dict(connection.execute('''SELECT invoice.* FROM purchase_lines act
            JOIN purchase_lines invoice ON invoice.id = act.source_line_id WHERE act.id = ?''',
            (line['source_line_id'],)).fetchone())
        header = raw_document(connection, original['document_id'])
        obj = original['object_id'] if original['object_id'] is not None else header['object_id']
        common = dict(period=header['date'], organization_id=header['organization_id'],
                      counterparty_id=header['counterparty_id'], contract_id=header['contract_id'],
                      object_id=obj, estimate_id=header['estimate_id'])
        expected = [('mutual_settlements_register', {**common, 'direction': 'payable'},
                     dict(accrual_amount=original['sum_with_vat'], payment_amount=0))]
        if original['line_type'] == 'goods' and header['receipt_mode'] == 'direct':
            expected.append(('inventory_register', dict(period=header['date'], warehouse_id=header['warehouse_id'],
                object_id=obj, material_id=original['material_id'], unit_id=base_unit(original), **axes(original)),
                dict(quantity_income=base_quantity(original), quantity_expense=0, sum_income=original['sum_without_vat'], sum_expense=0)))
        elif original['line_type'] == 'service':
            expected.append(('purchase_expense_register', common,
                dict(expense_amount=original['sum_without_vat'], vat_amount=original['vat_amount'])))
        for table, dimensions, values in expected:
            facts = connection.execute(f'''SELECT * FROM {table} WHERE recorder_type = 'purchase_acquisition'
                AND recorder_id = ? AND line_number = ? AND is_deleted = 0''',
                (header['id'], original['line_number'])).fetchall()
            if len(facts) != 1 or any(facts[0][key] != value for key, value in dimensions.items()) or any(
                    Decimal(str(facts[0][key])) != Decimal(str(value)) for key, value in values.items()):
                reject('Исходная стоимость или аналитика не совпадает с движениями приобретения')
        used = connection.execute('''SELECT l.quantity, l.sum_without_vat, l.vat_amount FROM purchase_lines l
            JOIN purchase_documents d ON d.id = l.document_id JOIN purchase_lines act ON act.id = l.source_line_id
            WHERE d.kind = 'quantity-adjustments' AND d.is_posted = 1 AND d.is_deleted = 0 AND l.is_deleted = 0
            AND act.source_line_id = ? AND d.id != ?''', (original['id'], doc.get('id', -1))).fetchall()
        initial = Decimal(str(original['quantity']))
        cumulative = sum((Decimal(str(row['quantity'])) for row in used), Decimal(0)) + Decimal(str(line['quantity']))
        if cumulative > initial + EPS:
            reject('Корректировки превышают исходное количество приобретения')
        for field in ('sum_without_vat', 'vat_amount'):
            base = money(original[field])
            allocated = sum((money(row[field]) for row in used), Decimal(0))
            if allocated < 0 or allocated > base:
                reject('Ранее распределенные суммы превышают исходную сумму приобретения')
            # Arbitrary unposting may leave an uneven cent allocation. Keep
            # posted siblings fixed and allocate only the available remainder.
            value = money(base * min(cumulative, initial) / initial) - allocated
            line[field] = float(min(base - allocated, max(Decimal(0), value)))
        line['sum_with_vat'] = float(money(line['sum_without_vat']) + money(line['vat_amount']))


def normalize_order_line(connection, raw):
    line = {key: raw.get(key) for key in LINE_FIELDS if key not in ('conversion_factor', 'base_unit_id')}
    line.update(line_number=raw['line_number'], quantity=raw['quantity'])
    if line['object_id']:
        active(connection, 'objects', line['object_id'])
    if raw['line_type'] == 'goods':
        if not raw.get('material_id') or not raw.get('unit_id'):
            reject('Товарная строка требует материал и единицу')
        material = active(connection, 'materials', raw['material_id'])
        active(connection, 'units', raw['unit_id'])
        if material['is_group']:
            reject('Укажите товар, а не группу')
        line.update(normalize_line(connection, raw))
    else:
        if any(raw.get(key) for key in ('material_id', 'package_id', 'characteristic_id', 'series_id')):
            reject('Некапитализируемая услуга не содержит складских аналитик')
        line.update(conversion_factor=1, base_unit_id=None)
    return totals(line)


def has_dependents(connection, ident):
    return connection.execute('''SELECT d.id FROM purchase_documents d
        WHERE d.is_deleted = 0 AND (d.source_id = ? OR EXISTS (
          SELECT 1 FROM purchase_lines l JOIN purchase_lines receipt ON receipt.id = l.receipt_line_id
          WHERE l.document_id = d.id AND l.is_deleted = 0 AND receipt.document_id = ?)) LIMIT 1''', (ident, ident)).fetchone()


def validate_basis(connection, doc, source):
    if not source['is_posted']:
        reject('Основание должно быть согласовано/проведено')
    if doc['date'] < source['date']:
        reject('Дата документа раньше основания')
    if doc['kind'] == 'receipt-orders' and doc['receipt_mode'] != 'order':
        reject('Приходный ордер используется на ордерном складе')
    if any(doc[key] != source[key] for key in DIMENSIONS):
        reject('Аналитики не совпадают с основанием')
    source_lines = {line['id']: line for line in source['lines']}
    for line in doc['lines']:
        original = source_lines.get(line['source_line_id'])
        if original is None or line['order_line_id'] != original['order_line_id']:
            reject('Строка не принадлежит основанию')
        if any(line[key] != original[key] for key in LINE_FIELDS):
            reject('Снимок аналитик/цены строки не совпадает с основанием')
        if line['line_type'] == 'goods':
            validate_snapshot(connection, line)
        if doc['kind'] == 'receipt-orders' and line['line_type'] != 'goods':
            reject('Услуга не принимается складским ордером')
        if line.get('receipt_line_id') and not (doc['kind'] == 'discrepancies' and doc['receipt_mode'] == 'order' and line['line_type'] == 'goods'):
            reject('Строка ордера используется только в товарном акте ордерной приемки')
        if doc['kind'] == 'discrepancies' and doc['receipt_mode'] == 'order' and line['line_type'] == 'goods':
            receipt = connection.execute('''SELECT l.*, d.date, d.is_posted, d.kind, d.is_deleted AS document_deleted
                FROM purchase_lines l JOIN purchase_documents d ON d.id = l.document_id WHERE l.id = ?''', (line['receipt_line_id'],)).fetchone()
            if receipt is None or receipt['kind'] != 'receipt-orders' or not receipt['is_posted'] or receipt['document_deleted'] or receipt['is_deleted']:
                reject('Акт требует строку проведенного приходного ордера')
            get_document(connection, receipt['document_id'], 'receipt-orders')
            if receipt['order_line_id'] != line['order_line_id'] or doc['date'] < receipt['date']:
                reject('Строка ордера или дата не соответствует приобретению')
            # Physical batches and invoices may be split differently. The
            # immutable order-line totals in validate_limits reconcile them;
            # the selected physical line identifies the batch and its owner.


def validate_limits(connection, doc):
    for line in doc['lines']:
        qty = Decimal(str(line['quantity']))
        order_line = connection.execute('SELECT quantity FROM purchase_lines WHERE id = ? AND is_deleted = 0', (line['order_line_id'],)).fetchone()
        if order_line is None:
            reject('Строка заказа удалена')
        ordered = Decimal(str(order_line['quantity']))
        p = progress(connection, line['order_line_id'])
        financial = p['acquisitions'] - p['quantity-adjustments']
        physical = financial if doc['receipt_mode'] == 'direct' or line['line_type'] == 'service' else p['receipt-orders']
        kind = doc['kind']
        if kind in ('acquisitions', 'receipt-orders'):
            already = financial if kind == 'acquisitions' else physical
            limit = ordered - p['cancellations'] - p['discrepancies']
        elif kind == 'cancellations':
            already = max(physical, financial)
            limit = ordered - p['cancellations'] - p['discrepancies']
        else:
            original = connection.execute('SELECT quantity FROM purchase_lines WHERE id = ?', (line['source_line_id'],)).fetchone()
            limit = Decimal(str(original['quantity']))
            already = Decimal(str(connection.execute('''SELECT COALESCE(SUM(l.quantity), 0) FROM purchase_lines l
                JOIN purchase_documents d ON d.id = l.document_id WHERE l.source_line_id = ? AND d.kind = ?
                AND d.is_posted = 1 AND d.is_deleted = 0 AND l.is_deleted = 0''', (line['source_line_id'], kind)).fetchone()[0]))
            if kind == 'discrepancies' and doc['receipt_mode'] == 'order' and line['line_type'] == 'goods':
                if p['discrepancies'] + qty > p['acquisitions'] - p['receipt-orders'] + EPS:
                    reject('Недопоставка превышает неполученное количество')
        if already + qty > limit + EPS:
            reject('Количество превышает остаток строки основания/заказа')


@rollback_on_error
def save_document(connection, kind, payload, user, ident=None):
    _require_write(user)
    if kind not in KINDS:
        reject('Неизвестный закупочный документ')
    existing = locked_document(connection, ident) if ident else None
    if existing and (existing['kind'] != kind or existing['is_posted'] or has_dependents(connection, ident)):
        reject('Проведенный документ или используемое основание изменять нельзя')
    source = None
    if kind != 'orders':
        if existing and existing['source_id'] != payload['source_id']:
            reject('Смена основания требует нового документа')
        source = locked_document(connection, payload['source_id'])
        if source['kind'] != SOURCES[kind]:
            reject('Неверный вид основания')
        values = {key: source[key] for key in DIMENSIONS}
        values.update(source_id=source['id'], order_id=source['order_id'] or source['id'])
    else:
        values = {key: payload.get(key) for key in DIMENSIONS if key != 'receipt_mode'}
        warehouse = active(connection, 'warehouses', values['warehouse_id']) if values['warehouse_id'] else None
        values.update(receipt_mode='order' if warehouse and warehouse['order_receipt_enabled'] else 'direct', source_id=None, order_id=None)
    lock_material_dimensions(connection, *(line.get('material_id') for line in (source['lines'] if source else payload['lines'])))
    lock_inventory_warehouses(connection, values['warehouse_id'])
    lock_settlement_contracts(connection, values['contract_id'])
    validate_header(connection, values)
    stamp = utcnow_iso()
    values.update(kind=kind, number=payload['number'] or (existing['number'] if existing else f'PUR-{kind}-{new_uuid()[:8]}'),
                  date=str(payload['date']), description=payload.get('description'), modified_at=stamp, updated_at=stamp)
    lines = []
    seen = set()
    originals = {line['id']: line for line in source['lines']} if source else {}
    for number, raw in enumerate(payload['lines'], 1):
        key = raw['source_line_id'] if source else raw['line_number']
        if key in seen:
            reject('Строка основания/номер строки повторяется')
        seen.add(key)
        if source:
            original = originals.get(key)
            if original is None:
                reject('Строка не принадлежит основанию')
            if raw.get('receipt_line_id') and kind != 'discrepancies':
                reject('Строка ордера указывается только в акте расхождений')
            line = {field: original[field] for field in LINE_FIELDS}
            line.update(line_number=number, quantity=raw['quantity'], source_line_id=key,
                        order_line_id=original['order_line_id'], receipt_line_id=raw.get('receipt_line_id'))
            lines.append(totals(line))
        else:
            lines.append(normalize_order_line(connection, raw))
    if any(line['line_type'] == 'goods' for line in lines) and not values['warehouse_id']:
        reject('Для товаров нужен склад')
    check = {**values, 'lines': lines}
    if source:
        validate_basis(connection, check, source)
        validate_limits(connection, check)
        allocate_adjustment_values(connection, check)
    if existing:
        connection.execute(f"UPDATE purchase_documents SET {', '.join(key+' = ?' for key in values)} WHERE id = ?", (*values.values(), ident))
    else:
        ident = insert(connection, 'purchase_documents', {**values, 'uuid': new_uuid(), 'created_at': stamp})
    old_lines = {row['line_number']: row for row in connection.execute('SELECT id, uuid, line_number FROM purchase_lines WHERE document_id = ? AND is_deleted = 0', (ident,)).fetchall()}
    connection.execute('UPDATE purchase_lines SET is_deleted = 1 WHERE document_id = ?', (ident,))
    for line in lines:
        old = old_lines.get(line['line_number'])
        if old:
            connection.execute(f"UPDATE purchase_lines SET {', '.join(key+' = ?' for key in line)}, is_deleted = 0 WHERE id = ?", (*line.values(), old['id']))
        else:
            line_id = insert(connection, 'purchase_lines', {**line, 'document_id': ident, 'uuid': new_uuid()})
            if kind == 'orders':
                connection.execute('UPDATE purchase_lines SET order_line_id = id WHERE id = ?', (line_id,))
    result = get_document(connection, ident, kind)
    record_event(connection, result, 'update' if existing else 'create', user)
    connection.commit()
    return result


def inventory_guard(connection, doc, line, on_date, cancelling=False):
    assert_no_inventory_consumption(connection, warehouse_id=doc['warehouse_id'],
        object_id=line['object_id'] if line['object_id'] is not None else doc['object_id'],
        material_id=line['material_id'], unit_id=base_unit(line), on_date=on_date,
        exclude_recorder_type=recorder(doc['kind']) if cancelling else None,
        exclude_recorder_id=doc['id'] if cancelling else None,
        # Other quantity reversals retain their own original invoice value;
        # sales, transfers and supplier returns still block this operation.
        ignore_purchase_quantity_reversals=doc['kind'] == 'quantity-adjustments', **axes(line))


def write_movements(connection, doc):
    kind = doc['kind']
    rec = recorder(kind)
    for line in doc['lines']:
        sign = -1 if kind == 'quantity-adjustments' else 1
        object_id = line['object_id'] if line['object_id'] is not None else doc['object_id']
        physical = line['line_type'] == 'goods' and (kind == 'receipt-orders' or (kind in ('acquisitions', 'quantity-adjustments') and doc['receipt_mode'] == 'direct'))
        if physical:
            basis_date = doc['date']
            if sign < 0:
                act = raw_document(connection, doc['source_id'])
                basis_date = raw_document(connection, act['source_id'])['date']
            # Multiple source lines can share a stock slice. Ignore only this
            # document's earlier lines, while retaining all external expenses.
            inventory_guard(connection, doc, line, basis_date, cancelling=True)
            if sign < 0:
                assert_stock_removal(connection, doc['warehouse_id'], object_id, line['material_id'], base_unit(line),
                                     doc['date'], base_quantity(line), line['sum_without_vat'], **axes(line))
            insert(connection, 'inventory_register', dict(recorder_type=rec, recorder_id=doc['id'], line_number=line['line_number'],
                period=doc['date'], material_id=line['material_id'], warehouse_id=doc['warehouse_id'], object_id=object_id,
                unit_id=base_unit(line), quantity_income=base_quantity(line) if sign > 0 else 0,
                quantity_expense=base_quantity(line) if sign < 0 else 0,
                sum_income=line['sum_without_vat'] if sign > 0 else 0, sum_expense=line['sum_without_vat'] if sign < 0 else 0,
                uuid=new_uuid(), **axes(line)))
        if kind in ('acquisitions', 'quantity-adjustments'):
            insert(connection, 'mutual_settlements_register', dict(recorder_type=rec, recorder_id=doc['id'], line_number=line['line_number'],
                period=doc['date'], organization_id=doc['organization_id'], counterparty_id=doc['counterparty_id'], contract_id=doc['contract_id'],
                object_id=object_id, estimate_id=doc['estimate_id'], direction='payable', accrual_amount=sign * line['sum_with_vat'], uuid=new_uuid()))
            if line['line_type'] == 'service':
                insert(connection, 'purchase_expense_register', dict(recorder_type=rec, recorder_id=doc['id'], line_number=line['line_number'],
                    period=doc['date'], organization_id=doc['organization_id'], counterparty_id=doc['counterparty_id'], contract_id=doc['contract_id'],
                    object_id=object_id, estimate_id=doc['estimate_id'], source_line_id=line['source_line_id'], name=line['name'],
                    expense_amount=sign * line['sum_without_vat'], vat_amount=sign * line['vat_amount'], uuid=new_uuid()))


@rollback_on_error
def change_document(connection, ident, kind, action, user):
    (_require_write if action == 'delete' else _require_admin)(user)
    doc = locked_document(connection, ident)
    if doc['kind'] != kind:
        reject('Вид документа не совпадает')
    lock_inventory_warehouses(connection, doc['warehouse_id'])
    lock_settlement_contracts(connection, doc['contract_id'])
    doc = get_document(connection, ident, kind)
    validate_header(connection, doc)
    if action == 'post':
        if doc['is_posted']:
            reject('Документ уже проведен/согласован')
        if doc['source_id']:
            source = get_document(connection, doc['source_id'], SOURCES[kind])
            validate_basis(connection, doc, source)
            validate_limits(connection, doc)
            allocate_adjustment_values(connection, doc)
            if kind == 'quantity-adjustments':
                for line in doc['lines']:
                    connection.execute('''UPDATE purchase_lines SET sum_without_vat = ?, vat_amount = ?, sum_with_vat = ? WHERE id = ?''',
                        (line['sum_without_vat'], line['vat_amount'], line['sum_with_vat'], line['id']))
        else:
            for line in doc['lines']:
                if line['line_type'] == 'goods':
                    validate_snapshot(connection, line)
        write_movements(connection, doc)
        connection.execute('UPDATE purchase_documents SET is_posted = 1, posted_at = ?, updated_at = ?, modified_at = ? WHERE id = ?',
                           (utcnow_iso(), utcnow_iso(), utcnow_iso(), ident))
    else:
        if has_dependents(connection, ident):
            reject('Сначала отмените и удалите зависимые документы')
        if action == 'delete':
            if doc['is_posted']:
                reject('Проведенный документ удалить нельзя')
            connection.execute('UPDATE purchase_documents SET is_deleted = 1, updated_at = ?, modified_at = ? WHERE id = ?', (utcnow_iso(), utcnow_iso(), ident))
        else:
            if not doc['is_posted']:
                reject('Документ не проведен/согласован')
            if kind in ('acquisitions', 'quantity-adjustments') and connection.execute('''SELECT id FROM mutual_settlements_register
                WHERE recorder_type = 'payment_transaction' AND is_deleted = 0 AND payment_amount > 0
                AND organization_id = ? AND counterparty_id = ? AND contract_id = ? AND direction = 'payable' LIMIT 1''',
                (doc['organization_id'], doc['counterparty_id'], doc['contract_id'])).fetchone():
                reject('Сначала отмените оплаты по договору')
            rec = recorder(kind)
            movements = connection.execute('SELECT * FROM inventory_register WHERE recorder_type = ? AND recorder_id = ?', (rec, ident)).fetchall()
            for move in movements:
                inventory_guard(connection, doc, dict(move), doc['date'], cancelling=True)
            for table in ('inventory_register', 'mutual_settlements_register', 'purchase_expense_register'):
                connection.execute(f'DELETE FROM {table} WHERE recorder_type = ? AND recorder_id = ?', (rec, ident))
            # Verify the entire resulting stock timeline after deleting all lines.
            for move in movements:
                assert_stock_removal(connection, move['warehouse_id'], move['object_id'], move['material_id'], move['unit_id'],
                                     doc['date'], 0, 0, **axes(move))
            connection.execute('UPDATE purchase_documents SET is_posted = 0, posted_at = NULL, updated_at = ?, modified_at = ? WHERE id = ?',
                               (utcnow_iso(), utcnow_iso(), ident))
    result = {'id': ident} if action == 'delete' else get_document(connection, ident, kind)
    event_document = {**doc, **dict(connection.execute('SELECT * FROM purchase_documents WHERE id = ?', (ident,)).fetchone())} if action == 'delete' else result
    record_event(connection, event_document, action, user)
    connection.commit()
    return result


def movements(connection, ident, kind):
    doc = get_document(connection, ident, kind)
    return {'document': doc, **{name: rows_to_dicts(connection.execute(
        f'SELECT * FROM {table} WHERE recorder_type = ? AND recorder_id = ? ORDER BY line_number', (recorder(kind), ident)).fetchall())
        for name, table in [('inventory', 'inventory_register'), ('settlements', 'mutual_settlements_register'), ('expenses', 'purchase_expense_register')]}}


def expenses(connection, date_from, date_to):
    conditions, params = ['e.is_deleted = 0', 'e.period >= ?', 'e.period <= ?'], [date_from, date_to]
    add_scope(connection, conditions, params, 'e.organization_id')
    add_goods_links_scope(connection, conditions, params, alias='e', based_on=False)
    return rows_to_dicts(connection.execute(f"SELECT e.* FROM purchase_expense_register e WHERE {' AND '.join(conditions)} ORDER BY e.period, e.id", params).fetchall())
