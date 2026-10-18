"""Linked trade returns and cash refunds. All lifecycle writes are atomic."""
from api.trade_access import add_scope, require_organization
from decimal import Decimal

from fastapi import HTTPException

from api.database import last_insert_id, new_uuid, row_to_dict, rows_to_dicts, utcnow_iso
from api.goods_services import _get_document, _require_admin, _require_write
from api.trade_settlement_rules import money, validate_contract, assert_no_future_price_adjustment, assert_no_inventory_consumption, lock_inventory_warehouses, lock_settlement_contracts
from api.inventory_dimensions import normalize_line, validate_snapshot, base_quantity, base_unit, axes, hydrate_lines


DIMENSIONS = ('organization_id', 'counterparty_id', 'contract_id', 'warehouse_id', 'object_id', 'estimate_id')


def reject(message):
    raise HTTPException(status_code=400, detail=message)


def source_document(connection, kind, source_id):
    return _get_document(connection, kind='issue' if kind == 'customer' else 'receipt', document_id=source_id)


def return_source(connection, kind, source_id, exclude_id=None):
    doc = source_document(connection, kind, source_id)
    for line in doc['lines']:
        rows = connection.execute('''SELECT l.quantity FROM goods_return_lines l
            JOIN goods_returns r ON r.id = l.return_id WHERE r.kind = ? AND r.source_id = ?
            AND r.is_posted = 1 AND r.id != ? AND l.source_line_id = ?''',
            (kind, source_id, exclude_id or -1, line['id'])).fetchall()
        returned = sum((Decimal(str(row['quantity'])) for row in rows), Decimal(0))
        line['returned_quantity'] = float(returned)
        line['returnable_quantity'] = float(Decimal(str(line['quantity'])) - returned)
    return doc


def lock_source(connection, kind, source_id):
    # UPDATE obtains a SQLite write lock / PostgreSQL row lock before reading
    # the quantity cap. Two returns against the same invoice cannot race.
    table = 'goods_issues' if kind == 'customer' else 'goods_receipts'
    connection.execute(f'UPDATE {table} SET id = id WHERE id = ?', (source_id,))


def get_return(connection, document_id):
    row = connection.execute('SELECT * FROM goods_returns WHERE id = ? AND marked_for_deletion = 0', (document_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='Возврат не найден')
    doc = row_to_dict(row)
    require_organization(connection, doc['organization_id'])
    source = source_document(connection, doc['kind'], doc['source_id'])
    for field in ('organization_name', 'counterparty_name', 'contract_number', 'warehouse_name', 'object_name'):
        doc[field] = source.get(field)
    doc['source_number'] = source['number']
    doc['is_posted'] = bool(doc['is_posted'])
    doc['lines'] = rows_to_dicts(connection.execute('SELECT * FROM goods_return_lines WHERE return_id = ? ORDER BY line_number', (document_id,)).fetchall())
    source_lines = {line['id']: line for line in source['lines']}
    for line in doc['lines']:
        original = source_lines.get(line['source_line_id'], {})
        for field in ('name', 'material_id', 'unit_id', 'unit_name', 'object_id', 'price_without_vat', 'vat_rate'):
            line[field] = original.get(field)
    doc['refunds'] = rows_to_dicts(connection.execute('SELECT * FROM goods_return_refunds WHERE return_id = ? AND marked_for_deletion = 0 ORDER BY id', (document_id,)).fetchall())
    hydrate_lines(connection, doc['lines'])
    return doc


def list_returns(connection, *, page=1, page_size=20, kind=None, search=None):
    where, params = ['marked_for_deletion = 0'], []
    add_scope(connection, where, params, 'organization_id')
    if kind:
        where.append('kind = ?')
        params.append(kind)
    if search:
        where.append('number LIKE ?')
        params.append(f'%{search}%')
    clause = ' AND '.join(where)
    total = connection.execute(f'SELECT COUNT(*) FROM goods_returns WHERE {clause}', params).fetchone()[0]
    ids = connection.execute(f'SELECT id FROM goods_returns WHERE {clause} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?', (*params, page_size, (page-1)*page_size)).fetchall()
    return [get_return(connection, row['id']) for row in ids], {'page': page, 'page_size': page_size, 'total': total, 'pages': max(1, (total+page_size-1)//page_size)}


def validate_source(connection, doc, source):
    if doc.get('kind') in ('customer', 'supplier') and connection.execute(
        "SELECT id FROM goods_price_adjustments WHERE kind = ? AND source_id = ? AND is_posted = 1 LIMIT 1",
        ('sale' if doc['kind'] == 'customer' else 'purchase', source['id']),
    ).fetchone():
        reject('Сначала отмените корректировки цены: совместный перерасчет возвратов пока не поддерживается')
    if not source['is_posted']:
        reject('Основание должно быть проведено')
    if str(doc['date']) < str(source['date']):
        reject('Дата возврата раньше основания')
    for field in DIMENSIONS:
        if field in doc and doc[field] != source.get(field):
            reject(f'Аналитика {field} не совпадает с основанием')
    validate_contract(connection, contract_id=source.get('contract_id'), organization_id=source['organization_id'], counterparty_id=source.get('counterparty_id'))
    warehouse = connection.execute('SELECT organization_id, marked_for_deletion, is_deleted FROM warehouses WHERE id = ?', (source.get('warehouse_id'),)).fetchone()
    if warehouse is None or warehouse['organization_id'] != source['organization_id'] or warehouse['marked_for_deletion'] or warehouse['is_deleted']:
        reject('Склад основания недоступен или принадлежит другой организации')


def calculate_lines(connection, doc, source, document_id=None):
    originals = {line['id']: line for line in source['lines']}
    seen, result = set(), []
    for index, line in enumerate(doc['lines'], 1):
        source_id = line['source_line_id']
        if source_id in seen or source_id not in originals:
            reject('Повторная строка или строка другого основания')
        seen.add(source_id)
        original = originals[source_id]
        validate_snapshot(connection, original)
        quantity = Decimal(str(line['quantity']))
        initial = Decimal(str(original['quantity']))
        if quantity <= 0 or not original.get('material_id') or not original.get('unit_id'):
            reject('Возврат требует товарную строку с положительным количеством')
        source_type = 'goods_issue' if doc['kind'] == 'customer' else 'goods_receipt'
        movement = connection.execute('''SELECT * FROM inventory_register WHERE recorder_type = ?
            AND recorder_id = ? AND line_number = ? AND is_deleted = 0''',
            (source_type, source['id'], original['line_number'])).fetchone()
        expected_cost = original.get('inventory_cost') if doc['kind'] == 'customer' else original['sum_without_vat']
        cost_field = 'sum_expense' if doc['kind'] == 'customer' else 'sum_income'
        quantity_field = 'quantity_expense' if doc['kind'] == 'customer' else 'quantity_income'
        if (movement is None or expected_cost is None or money(movement[cost_field]) != money(expected_cost)
                or Decimal(str(movement[quantity_field])) != Decimal(str(base_quantity(original)))
                or movement['material_id'] != original['material_id']
                or movement['unit_id'] != base_unit(original) or movement['warehouse_id'] != source['warehouse_id']
                or any(movement[key] != original.get(key) for key in ('characteristic_id', 'series_id'))
                or movement['object_id'] != (original.get('object_id') if original.get('object_id') is not None else source.get('object_id'))):
            reject('Исходная себестоимость или аналитика не совпадает с движением основания')
        used = connection.execute('''SELECT COALESCE(SUM(l.quantity), 0) AS quantity,
            COALESCE(SUM(l.sum_without_vat), 0) AS sum_without_vat,
            COALESCE(SUM(l.vat_amount), 0) AS vat_amount,
            COALESCE(SUM(l.inventory_cost), 0) AS inventory_cost
            FROM goods_return_lines l JOIN goods_returns r ON r.id = l.return_id
            WHERE r.kind = ? AND r.source_id = ? AND l.source_line_id = ?
            AND r.is_posted = 1 AND r.id != ?''', (doc['kind'], doc['source_id'], source_id, document_id or -1)).fetchone()
        quantities = connection.execute("""SELECT l.quantity FROM goods_return_lines l JOIN goods_returns r ON r.id = l.return_id
            WHERE r.kind = ? AND r.source_id = ? AND l.source_line_id = ? AND r.is_posted = 1 AND r.id != ?""",
            (doc['kind'], doc['source_id'], source_id, document_id or -1)).fetchall()
        cumulative = sum((Decimal(str(row['quantity'])) for row in quantities), Decimal(0)) + quantity
        if cumulative > initial:
            reject('Количество возвратов превышает количество строки основания')
        # Allocate cents cumulatively so a complete return exactly reverses
        # the original line, including a sequence of fractional returns.
        amounts = {}
        for field in ('sum_without_vat', 'vat_amount', 'inventory_cost'):
            if field == 'inventory_cost':
                base = original.get('inventory_cost') if doc['kind'] == 'customer' else original['sum_without_vat']
                if base is None:
                    reject('В основании отсутствует исходная себестоимость')
            else:
                base = original[field]
            amounts[field] = float(money(Decimal(str(base))*cumulative/initial) - money(used[field]))
        amounts['sum_with_vat'] = float(money(amounts['sum_without_vat']) + money(amounts['vat_amount']))
        result.append({'source_line_id': source_id, 'line_number': index, 'quantity': float(quantity), **amounts,
                       **normalize_line(connection, {**original, 'quantity': float(quantity)})})
    if not result:
        reject('Нет строк возврата')
    return result


def insert(connection, table, values):
    connection.execute(f"INSERT INTO {table} ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})", tuple(values.values()))
    return last_insert_id(connection)


def save_return(connection, *, payload, user, document_id=None):
    _require_write(user)
    try:
        lock_source(connection, payload['kind'], payload['source_id'])
        if document_id:
            old = get_return(connection, document_id)
            if (old['kind'], old['source_id']) != (payload['kind'], payload['source_id']):
                reject('Для смены основания создайте новый возврат')
            if old['is_posted']:
                reject('Проведенный возврат нельзя изменить')
            if old['refunds']:
                reject('Сначала удалите связанные документы возврата денег')
        source = source_document(connection, payload['kind'], payload['source_id'])
        validate_source(connection, {k: v for k, v in payload.items() if v is not None}, source)
        lines = calculate_lines(connection, payload, source, document_id)
        stamp = utcnow_iso()
        values = {key: source.get(key) for key in DIMENSIONS}
        values.update(kind=payload['kind'], source_id=payload['source_id'], date=str(payload['date']),
                      description=payload.get('description'), number=payload.get('number') or f'ВЗ-{new_uuid()[:8]}', modified_at=stamp, updated_at=stamp)
        for field in ('sum_without_vat', 'vat_amount', 'sum_with_vat', 'inventory_cost'):
            values[field] = float(sum((money(line[field]) for line in lines), Decimal(0)))
        if document_id:
            connection.execute(f"UPDATE goods_returns SET {', '.join(key+' = ?' for key in values)} WHERE id = ?", (*values.values(), document_id))
            connection.execute('DELETE FROM goods_return_lines WHERE return_id = ?', (document_id,))
        else:
            document_id = insert(connection, 'goods_returns', {**values, 'uuid': new_uuid(), 'created_at': stamp})
        for line in lines:
            insert(connection, 'goods_return_lines', {'return_id': document_id, **line})
        connection.commit()
        return get_return(connection, document_id)
    except Exception:
        connection.rollback()
        raise


def assert_stock_removal(connection, warehouse_id, object_id, material_id, unit_id, date, quantity, cost, characteristic_id=None, series_id=None, check_reservations=True):
    if check_reservations:
        from api.sales_rules import assert_available
        assert_available(connection,warehouse_id=warehouse_id,object_id=object_id,material_id=material_id,unit_id=unit_id,
                         on_date=date,quantity=quantity,characteristic_id=characteristic_id,series_id=series_id)
    # Check the running stock at every later date as well as the operation date.
    rows = connection.execute('''SELECT period, SUM(quantity_income-quantity_expense) AS qty,
        SUM(sum_income-sum_expense) AS amount FROM inventory_register
        WHERE warehouse_id = ? AND material_id = ? AND unit_id = ?
        AND (characteristic_id = ? OR (characteristic_id IS NULL AND ? IS NULL))
        AND (series_id = ? OR (series_id IS NULL AND ? IS NULL))
        AND (object_id = ? OR (object_id IS NULL AND ? IS NULL)) AND is_deleted = 0
        GROUP BY period ORDER BY period''', (warehouse_id, material_id, unit_id, characteristic_id, characteristic_id, series_id, series_id, object_id, object_id)).fetchall()
    qty, amount = Decimal(0), Decimal(0)
    checkpoints = []
    for row in rows:
        if str(row['period']) > date and not checkpoints:
            checkpoints.append((qty, amount))
        qty += Decimal(str(row['qty']))
        amount += money(row['amount'])
        if str(row['period']) >= date:
            checkpoints.append((qty, amount))
    if not checkpoints:
        checkpoints.append((qty, amount))
    if any(q + Decimal('0.000000001') < Decimal(str(quantity)) or a < money(cost) for q, a in checkpoints):
        reject('Недостаточно количества или стоимости склада на дату операции или последующих движений')


def settlement(connection, doc, recorder, recorder_id, date, *, accrual=0, payment=0):
    stamp = utcnow_iso()
    insert(connection, 'mutual_settlements_register', {
        'recorder_type': recorder, 'recorder_id': recorder_id, 'line_number': 1, 'period': date,
        **{key: doc.get(key) for key in DIMENSIONS if key != 'warehouse_id'},
        'direction': 'receivable' if doc['kind'] == 'customer' else 'payable',
        'accrual_amount': accrual, 'payment_amount': payment,
        'uuid': new_uuid(), 'created_at': stamp, 'updated_at': stamp,
    })


def change_return(connection, *, document_id, user, action):
    (_require_write if action == 'delete' else _require_admin)(user)
    try:
        snapshot = get_return(connection, document_id)
        lock_source(connection, snapshot['kind'], snapshot['source_id'])
        doc = get_return(connection, document_id)
        if action in ('post', 'unpost'):
            lock_inventory_warehouses(connection, doc['warehouse_id'])
            lock_settlement_contracts(connection, doc.get('contract_id'))
        posted = doc['is_posted']
        if action == 'delete':
            if posted or doc['refunds']:
                reject('Сначала отмените проведение и удалите возвраты денег')
            connection.execute('UPDATE goods_returns SET marked_for_deletion = 1, is_deleted = 1 WHERE id = ?', (document_id,))
        elif action == 'post':
            if posted:
                reject('Возврат уже проведен')
            source = source_document(connection, doc['kind'], doc['source_id'])
            validate_source(connection, doc, source)
            lines = calculate_lines(connection, doc, source, document_id)
            originals = {line['id']: line for line in source['lines']}
            for line in lines:
                original = originals[line['source_line_id']]
                obj = original.get('object_id') if original.get('object_id') is not None else doc['object_id']
                expense = doc['kind'] == 'supplier'
                if expense:
                    assert_no_future_price_adjustment(connection, warehouse_id=doc['warehouse_id'], object_id=obj,
                        material_id=original['material_id'], unit_id=base_unit(original), on_date=doc['date'], **axes(original))
                    assert_stock_removal(connection, doc['warehouse_id'], obj, original['material_id'], base_unit(original), doc['date'], base_quantity(line), line['inventory_cost'], **axes(original))
                stamp = utcnow_iso()
                insert(connection, 'inventory_register', {
                    'recorder_type': 'goods_return', 'recorder_id': document_id, 'line_number': line['line_number'], 'period': doc['date'],
                    'material_id': original['material_id'], 'warehouse_id': doc['warehouse_id'], 'object_id': obj, 'unit_id': base_unit(original), **axes(original),
                    'quantity_income': 0 if expense else base_quantity(line), 'quantity_expense': base_quantity(line) if expense else 0,
                    'sum_income': 0 if expense else line['inventory_cost'], 'sum_expense': line['inventory_cost'] if expense else 0,
                    'uuid': new_uuid(), 'created_at': stamp, 'updated_at': stamp,
                })
                connection.execute('''UPDATE goods_return_lines SET sum_without_vat = ?, vat_amount = ?, sum_with_vat = ?, inventory_cost = ?
                    WHERE return_id = ? AND source_line_id = ?''', (line['sum_without_vat'], line['vat_amount'], line['sum_with_vat'], line['inventory_cost'], document_id, line['source_line_id']))
                snapshot = {key: line[key] for key in ('characteristic_id', 'series_id', 'package_id', 'conversion_factor', 'base_quantity', 'base_unit_id')}
                connection.execute(f"UPDATE goods_return_lines SET {', '.join(key+' = ?' for key in snapshot)} WHERE return_id = ? AND source_line_id = ?",
                                   (*snapshot.values(), document_id, line['source_line_id']))
            totals = {field: float(sum((money(line[field]) for line in lines), Decimal(0))) for field in ('sum_without_vat', 'vat_amount', 'sum_with_vat', 'inventory_cost')}
            settlement(connection, doc, 'goods_return', document_id, doc['date'], accrual=-totals['sum_with_vat'])
            connection.execute('UPDATE goods_returns SET sum_without_vat = ?, vat_amount = ?, sum_with_vat = ?, inventory_cost = ?, is_posted = 1, posted_at = ?, updated_at = ? WHERE id = ?', (*totals.values(), utcnow_iso(), utcnow_iso(), document_id))
        elif action == 'unpost':
            if not posted:
                reject('Возврат не проведен')
            if any(refund['is_posted'] for refund in doc['refunds']):
                reject('Сначала отмените возврат денег')
            if doc['kind'] == 'customer':
                movements = connection.execute("SELECT * FROM inventory_register WHERE recorder_type = 'goods_return' AND recorder_id = ?", (document_id,)).fetchall()
                for move in movements:
                    assert_no_inventory_consumption(connection, warehouse_id=move['warehouse_id'], object_id=move['object_id'],
                        material_id=move['material_id'], unit_id=move['unit_id'], on_date=doc['date'], after_movement_id=move['id'], **axes(move))
                # Remove all lines first; checking the resulting timeline also
                # catches duplicate materials on distinct source lines.
                connection.execute("DELETE FROM inventory_register WHERE recorder_type = 'goods_return' AND recorder_id = ?", (document_id,))
                for move in movements:
                    assert_stock_removal(connection, move['warehouse_id'], move['object_id'], move['material_id'], move['unit_id'], doc['date'], 0, 0, **axes(move))
            connection.execute("DELETE FROM inventory_register WHERE recorder_type = 'goods_return' AND recorder_id = ?", (document_id,))
            connection.execute("DELETE FROM mutual_settlements_register WHERE recorder_type = 'goods_return' AND recorder_id = ?", (document_id,))
            connection.execute('UPDATE goods_returns SET is_posted = 0, posted_at = NULL, updated_at = ? WHERE id = ?', (utcnow_iso(), document_id))
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def return_movements(connection, document_id):
    return {'document': get_return(connection, document_id), **{name: rows_to_dicts(connection.execute(f"SELECT * FROM {table} WHERE recorder_type = 'goods_return' AND recorder_id = ? ORDER BY line_number", (document_id,)).fetchall()) for name, table in (('inventory', 'inventory_register'), ('settlements', 'mutual_settlements_register'))}}


def get_refund(connection, refund_id):
    row = connection.execute('SELECT * FROM goods_return_refunds WHERE id = ? AND marked_for_deletion = 0', (refund_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='Возврат денег не найден')
    doc = row_to_dict(row)
    get_return(connection, doc['return_id'])
    doc['is_posted'] = bool(doc['is_posted'])
    return doc


def save_refund(connection, *, payload, user, refund_id=None):
    _require_write(user)
    try:
        parent = get_return(connection, payload['return_id'])
        lock_source(connection, parent['kind'], parent['source_id'])
        parent = get_return(connection, payload['return_id'])
        if not parent['is_posted'] or str(payload['date']) < parent['date']:
            reject('Нужен проведенный возврат с датой не позже возврата денег')
        if refund_id:
            old = get_refund(connection, refund_id)
            if old['is_posted']:
                reject('Проведенный возврат денег нельзя изменить')
            if old['return_id'] != payload['return_id']:
                reject('Для смены основания создайте новый возврат денег')
        amount = money(payload['amount'])
        if amount <= 0:
            reject('Сумма должна быть не меньше копейки')
        values = {'return_id': payload['return_id'], 'number': payload.get('number') or f'ВД-{new_uuid()[:8]}', 'date': str(payload['date']), 'amount': float(amount), 'description': payload.get('description'), 'updated_at': utcnow_iso()}
        if refund_id:
            connection.execute(f"UPDATE goods_return_refunds SET {', '.join(key+' = ?' for key in values)} WHERE id = ?", (*values.values(), refund_id))
        else:
            refund_id = insert(connection, 'goods_return_refunds', {**values, 'uuid': new_uuid()})
        connection.commit()
        return get_refund(connection, refund_id)
    except Exception:
        connection.rollback()
        raise


def change_refund(connection, *, refund_id, user, action):
    (_require_write if action == 'delete' else _require_admin)(user)
    try:
        refund = get_refund(connection, refund_id)
        doc = get_return(connection, refund['return_id'])
        lock_source(connection, doc['kind'], doc['source_id'])
        refund = get_refund(connection, refund_id)
        doc = get_return(connection, refund['return_id'])
        connection.execute('UPDATE organizations SET id = id WHERE id = ?', (doc['organization_id'],))
        lock_settlement_contracts(connection, doc.get('contract_id'))
        if action == 'delete':
            if refund['is_posted']:
                reject('Сначала отмените возврат денег')
            connection.execute('UPDATE goods_return_refunds SET marked_for_deletion = 1, is_deleted = 1 WHERE id = ?', (refund_id,))
        elif action == 'post':
            if refund['is_posted'] or not doc['is_posted'] or refund['date'] < doc['date']:
                reject('Возврат денег уже проведен, основание не проведено или дата неверна')
            validate_source(connection, doc, source_document(connection, doc['kind'], doc['source_id']))
            refunded = sum((money(r['amount']) for r in doc['refunds'] if r['is_posted']), Decimal(0))
            if refunded + money(refund['amount']) > money(doc['sum_with_vat']):
                reject('Возврат денег превышает сумму возврата товаров')
            direction = 'receivable' if doc['kind'] == 'customer' else 'payable'
            balance = connection.execute('''SELECT COALESCE(SUM(payment_amount-accrual_amount), 0) AS due
                FROM mutual_settlements_register WHERE organization_id = ? AND direction = ?
                AND (counterparty_id = ? OR (counterparty_id IS NULL AND ? IS NULL))
                AND (contract_id = ? OR (contract_id IS NULL AND ? IS NULL))
                AND (object_id = ? OR (object_id IS NULL AND ? IS NULL)) AND period <= ? AND is_deleted = 0''',
                (doc['organization_id'], direction, doc['counterparty_id'], doc['counterparty_id'], doc['contract_id'], doc['contract_id'], doc['object_id'], doc['object_id'], refund['date'])).fetchone()
            if money(balance['due']) < money(refund['amount']):
                reject('Нет достаточной суммы к возврату в аналитике основания')
            settlement(connection, doc, 'goods_return_refund', refund_id, refund['date'], payment=-refund['amount'])
            stamp = utcnow_iso()
            insert(connection, 'payment_schedule_register', {
                'recorder_type': 'goods_return_refund', 'recorder_id': refund_id, 'line_number': 1, 'period': refund['date'],
                'direction': 'outgoing' if doc['kind'] == 'customer' else 'incoming', 'category': 'other',
                'counterparty_id': doc['counterparty_id'], 'contract_id': doc['contract_id'], 'object_id': doc['object_id'],
                'estimate_id': doc['estimate_id'], 'fact_amount': refund['amount'], 'uuid': new_uuid(), 'created_at': stamp, 'modified_at': stamp, 'updated_at': stamp,
            })
            connection.execute('UPDATE goods_return_refunds SET is_posted = 1, posted_at = ?, updated_at = ? WHERE id = ?', (stamp, stamp, refund_id))
        elif action == 'unpost':
            if not refund['is_posted']:
                reject('Возврат денег не проведен')
            for table in ('mutual_settlements_register', 'payment_schedule_register'):
                connection.execute(f"DELETE FROM {table} WHERE recorder_type = 'goods_return_refund' AND recorder_id = ?", (refund_id,))
            connection.execute('UPDATE goods_return_refunds SET is_posted = 0, posted_at = NULL, updated_at = ? WHERE id = ?', (utcnow_iso(), refund_id))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
