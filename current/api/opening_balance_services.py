"""Auditable initial stock/debt documents, independent of purchases and sales."""
from api.trade_access import add_scope, require_organization
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException

from api.database import row_to_dict, rows_to_dicts, utcnow_iso, new_uuid
from api.goods_services import _require_admin, _require_write, inventory_balances, inventory_movements
from api.inventory_dimensions import active, axes, base_quantity, base_unit, normalize_line, hydrate_lines, reject, lock_material_dimensions
from api.return_services import insert
from api.trade_settlement_rules import money, validate_contract, lock_inventory_warehouses, lock_settlement_contracts


def ensure_schema(connection):
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS opening_balances (
        id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT NOT NULL, date TEXT NOT NULL,
        organization_id INTEGER NOT NULL REFERENCES organizations(id), description TEXT,
        is_posted INTEGER NOT NULL DEFAULT 0, posted_at TEXT,
        marked_for_deletion INTEGER NOT NULL DEFAULT 0, is_deleted INTEGER NOT NULL DEFAULT 0,
        uuid TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        modified_at TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS opening_inventory_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL REFERENCES opening_balances(id),
        line_number INTEGER NOT NULL, material_id INTEGER NOT NULL REFERENCES materials(id),
        warehouse_id INTEGER NOT NULL REFERENCES warehouses(id), object_id INTEGER REFERENCES objects(id),
        unit_id INTEGER NOT NULL REFERENCES units(id), quantity REAL NOT NULL, cost REAL NOT NULL,
        characteristic_id INTEGER REFERENCES material_characteristics(id), series_id INTEGER REFERENCES material_series(id),
        package_id INTEGER REFERENCES material_packages(id), conversion_factor REAL NOT NULL DEFAULT 1,
        base_quantity REAL NOT NULL, base_unit_id INTEGER NOT NULL REFERENCES units(id)
    );
    CREATE TABLE IF NOT EXISTS opening_settlement_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL REFERENCES opening_balances(id),
        line_number INTEGER NOT NULL, counterparty_id INTEGER NOT NULL REFERENCES counterparties(id),
        contract_id INTEGER NOT NULL REFERENCES contracts(id), object_id INTEGER REFERENCES objects(id),
        direction TEXT NOT NULL CHECK(direction IN ('payable', 'receivable')), amount REAL NOT NULL
    );''')


def get_opening(connection, ident):
    row = connection.execute('SELECT * FROM opening_balances WHERE id = ? AND marked_for_deletion = 0', (ident,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='Документ начальных остатков не найден')
    doc = row_to_dict(row)
    require_organization(connection, doc['organization_id'])
    doc['is_posted'] = bool(doc['is_posted'])
    doc['organization_name'] = connection.execute('SELECT name FROM organizations WHERE id = ?', (doc['organization_id'],)).fetchone()[0]
    doc['inventory'] = hydrate_lines(connection, rows_to_dicts(connection.execute('''SELECT l.*, m.name AS material_name,
        w.name AS warehouse_name, u.name AS unit_name FROM opening_inventory_lines l
        JOIN materials m ON m.id = l.material_id JOIN warehouses w ON w.id = l.warehouse_id
        JOIN units u ON u.id = l.unit_id WHERE document_id = ? ORDER BY line_number''', (ident,)).fetchall()))
    doc['settlements'] = rows_to_dicts(connection.execute('''SELECT l.*, c.name AS counterparty_name, ct.number AS contract_number
        FROM opening_settlement_lines l JOIN counterparties c ON c.id = l.counterparty_id
        JOIN contracts ct ON ct.id = l.contract_id WHERE document_id = ? ORDER BY line_number''', (ident,)).fetchall())
    return doc


def list_openings(connection, page=1, page_size=20):
    where, params = ['marked_for_deletion = 0'], []
    add_scope(connection, where, params, 'organization_id')
    clause = ' AND '.join(where)
    total = connection.execute(f'SELECT COUNT(*) FROM opening_balances WHERE {clause}', params).fetchone()[0]
    rows = connection.execute(f'SELECT id FROM opening_balances WHERE {clause} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?',
                              (*params, page_size, (page-1)*page_size)).fetchall()
    return [get_opening(connection, row[0]) for row in rows], dict(page=page, page_size=page_size, total=total, pages=max(1, (total+page_size-1)//page_size))


def validate(connection, payload):
    require_organization(connection, payload['organization_id'])
    active(connection, 'organizations', payload['organization_id'])
    inventories, settlements = [], []
    for number, raw in enumerate(payload['inventory'], 1):
        warehouse = active(connection, 'warehouses', raw['warehouse_id'])
        material = active(connection, 'materials', raw['material_id'])
        active(connection, 'units', raw['unit_id'])
        if warehouse['organization_id'] != payload['organization_id']:
            reject('Склад начального остатка принадлежит другой организации')
        if material['unit_id'] != raw['unit_id'] or material['is_group']:
            reject('Укажите товар и его базовую единицу')
        if raw.get('object_id'):
            active(connection, 'objects', raw['object_id'])
        snapshot = normalize_line(connection, raw)
        inventories.append({key: raw.get(key) for key in ('material_id', 'warehouse_id', 'unit_id', 'object_id', 'quantity')} |
                           dict(line_number=number, cost=float(money(raw['cost'])), **snapshot))
    for number, raw in enumerate(payload['settlements'], 1):
        active(connection, 'counterparties', raw['counterparty_id'])
        validate_contract(connection, contract_id=raw['contract_id'], organization_id=payload['organization_id'], counterparty_id=raw['counterparty_id'])
        if raw.get('object_id'):
            active(connection, 'objects', raw['object_id'])
        settlements.append({key: raw.get(key) for key in ('counterparty_id', 'contract_id', 'object_id', 'direction')} |
                           dict(line_number=number, amount=float(money(raw['amount']))))
    if not inventories and not settlements:
        reject('Начальные остатки пусты')
    if any(line['amount'] <= 0 for line in settlements):
        reject('Начальная задолженность должна быть больше нуля после округления')
    return inventories, settlements


def save_opening(connection, payload, user, ident=None):
    _require_write(user)
    try:
        if ident:
            connection.execute('UPDATE opening_balances SET id = id WHERE id = ?', (ident,))
            if get_opening(connection, ident)['is_posted']:
                reject('Проведенные начальные остатки нельзя изменить')
        lock_material_dimensions(connection, *(line.get('material_id') for line in payload.get('inventory', [])))
        inventories, settlements = validate(connection, payload)
        stamp = utcnow_iso()
        fields = dict(number=payload.get('number') or f'НО-{new_uuid()[:8]}', date=str(payload['date']),
                      organization_id=payload['organization_id'], description=payload.get('description'), modified_at=stamp, updated_at=stamp)
        if ident:
            connection.execute(f"UPDATE opening_balances SET {', '.join(k+' = ?' for k in fields)} WHERE id = ?", (*fields.values(), ident))
            for table in ('opening_inventory_lines', 'opening_settlement_lines'):
                connection.execute(f'DELETE FROM {table} WHERE document_id = ?', (ident,))
        else:
            ident = insert(connection, 'opening_balances', {**fields, 'uuid': new_uuid(), 'created_at': stamp})
        for table, lines in [('opening_inventory_lines', inventories), ('opening_settlement_lines', settlements)]:
            for line in lines:
                insert(connection, table, {'document_id': ident, **line})
        connection.commit()
        return get_opening(connection, ident)
    except Exception:
        connection.rollback()
        raise


def assert_no_dependencies(connection, doc):
    # Adding/removing historical carrying value cannot leave later expenses or
    # revisions untouched. This also checks each characteristic/series slice.
    for line in doc['inventory']:
        if connection.execute('''SELECT id FROM inventory_register WHERE warehouse_id = ? AND material_id = ?
            AND (object_id = ? OR (object_id IS NULL AND ? IS NULL))
            AND (unit_id = ? OR recorder_type = 'goods_issue')
            AND (characteristic_id = ? OR (characteristic_id IS NULL AND ? IS NULL))
            AND (series_id = ? OR (series_id IS NULL AND ? IS NULL))
            AND period >= ? AND is_deleted = 0 AND (quantity_expense > 0 OR recorder_type = 'goods_price_adjustment') LIMIT 1''',
            (line['warehouse_id'], line['material_id'], line['object_id'], line['object_id'], base_unit(line),
             line['characteristic_id'], line['characteristic_id'], line['series_id'], line['series_id'], doc['date'])).fetchone():
            reject('COST-005: сначала отмените зависимый расход или корректировку начального складского остатка')
    for line in doc['settlements']:
        if connection.execute('''SELECT id FROM mutual_settlements_register WHERE organization_id = ? AND counterparty_id = ?
            AND contract_id = ? AND direction = ? AND (object_id = ? OR (object_id IS NULL AND ? IS NULL))
            AND period >= ? AND payment_amount != 0 AND is_deleted = 0 LIMIT 1''',
            (doc['organization_id'], line['counterparty_id'], line['contract_id'], line['direction'], line['object_id'], line['object_id'], doc['date'])).fetchone():
            reject('Сначала отмените оплаты по разрезу начального остатка')


def change_opening(connection, ident, user, action):
    (_require_write if action == 'delete' else _require_admin)(user)
    try:
        connection.execute('UPDATE opening_balances SET id = id WHERE id = ?', (ident,))
        doc = get_opening(connection, ident)
        lock_inventory_warehouses(connection, *(line['warehouse_id'] for line in doc['inventory']))
        lock_settlement_contracts(connection, *(line['contract_id'] for line in doc['settlements']))
        if action == 'delete':
            if doc['is_posted']:
                reject('Сначала отмените проведение')
            connection.execute('UPDATE opening_balances SET marked_for_deletion = 1, is_deleted = 1 WHERE id = ?', (ident,))
        elif action == 'post':
            if doc['is_posted']:
                reject('Начальные остатки уже проведены')
            inventories, settlements = validate(connection, doc)
            if any(any(actual[key] != stored[key] for key in actual) for stored, actual in zip(doc['inventory'], inventories)):
                reject('Аналитики начальных остатков изменились: пересохраните черновик')
            assert_no_dependencies(connection, doc)
            stamp = utcnow_iso()
            for line in inventories:
                insert(connection, 'inventory_register', dict(recorder_type='opening_balance', recorder_id=ident,
                    line_number=line['line_number'], period=doc['date'], material_id=line['material_id'], warehouse_id=line['warehouse_id'],
                    object_id=line['object_id'], unit_id=base_unit(line), **axes(line), quantity_income=base_quantity(line),
                    quantity_expense=0, sum_income=line['cost'], sum_expense=0, uuid=new_uuid(), created_at=stamp, updated_at=stamp))
            for line in settlements:
                insert(connection, 'mutual_settlements_register', dict(recorder_type='opening_balance', recorder_id=ident,
                    line_number=line['line_number'], period=doc['date'], organization_id=doc['organization_id'],
                    **{key: line[key] for key in ('counterparty_id', 'contract_id', 'object_id', 'direction')},
                    accrual_amount=line['amount'], payment_amount=0, uuid=new_uuid(), created_at=stamp, updated_at=stamp))
            connection.execute('UPDATE opening_balances SET is_posted = 1, posted_at = ?, updated_at = ? WHERE id = ?', (stamp, stamp, ident))
        elif action == 'unpost':
            if not doc['is_posted']:
                reject('Начальные остатки не проведены')
            assert_no_dependencies(connection, doc)
            for table in ('inventory_register', 'mutual_settlements_register'):
                connection.execute(f"DELETE FROM {table} WHERE recorder_type = 'opening_balance' AND recorder_id = ?", (ident,))
            connection.execute('UPDATE opening_balances SET is_posted = 0, posted_at = NULL, updated_at = ? WHERE id = ?', (utcnow_iso(), ident))
            from api.sales_rules import assert_available
            for line in doc['inventory']:
                assert_available(connection,warehouse_id=line['warehouse_id'],object_id=line.get('object_id'),material_id=line['material_id'],
                                 unit_id=base_unit(line),on_date=doc['date'],quantity=0,**axes(line))
        else:
            reject('Неизвестное действие')
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def opening_movements(connection, ident):
    return {'document': get_opening(connection, ident), **{key: hydrate_lines(connection, rows_to_dicts(connection.execute(
        f"SELECT * FROM {table} WHERE recorder_type = 'opening_balance' AND recorder_id = ? ORDER BY line_number", (ident,)).fetchall()))
        for key, table in [('inventory', 'inventory_register'), ('settlements', 'mutual_settlements_register')]}}


def inventory_turnover(connection, date_from, date_to, **filters):
    try:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
        if start > end:
            reject('Начало периода позже окончания')
    except ValueError:
        reject('Неверная дата периода')
    opening = inventory_balances(connection, on_date=(start-timedelta(days=1)).isoformat(), **filters)
    closing = inventory_balances(connection, on_date=end.isoformat(), **filters)
    movements = inventory_movements(connection, date_from=date_from, date_to=date_to, **filters)
    fields = ('organization_id', 'warehouse_id', 'object_id', 'material_id', 'unit_id', 'characteristic_id', 'series_id')
    result = {}
    for stage, rows in [('opening', opening), ('closing', closing), ('turnover', movements)]:
        for row in rows:
            key = tuple(row.get(field) for field in fields)
            target = result.setdefault(key, {**{field: value for field, value in row.items() if field in fields or field.endswith('_name')},
                **{name: Decimal(0) for name in ('quantity_opening', 'cost_opening', 'quantity_income', 'quantity_expense', 'cost_income', 'cost_expense', 'quantity_closing', 'cost_closing')}})
            if stage == 'turnover':
                for dest, src in [('quantity_income', 'quantity_income'), ('quantity_expense', 'quantity_expense'), ('cost_income', 'sum_income'), ('cost_expense', 'sum_expense')]:
                    target[dest] += Decimal(str(row[src]))
            else:
                target[f'quantity_{stage}'] = Decimal(str(row['quantity_balance']))
                target[f'cost_{stage}'] = money(row['sum_income']) - money(row['sum_expense'])
    return [{k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()} for row in result.values()]
