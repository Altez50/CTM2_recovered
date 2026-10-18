"""Price revisions are explicit delta documents; invoices remain immutable."""
from __future__ import annotations
from api.trade_access import add_scope, require_organization

from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from api.database import row_to_dict, rows_to_dicts, new_uuid, utcnow_iso
from api.goods_services import _require_admin, _require_write
from api.return_services import (
    DIMENSIONS, insert, lock_source, source_document, validate_source,
    reject, assert_stock_removal,
)
from api.trade_settlement_rules import money, assert_no_inventory_consumption, lock_settlement_contracts
from api.inventory_dimensions import normalize_line, validate_snapshot, base_quantity, base_unit, axes, hydrate_lines


def source_kind(kind: str) -> str:
    return 'customer' if kind == 'sale' else 'supplier'


def get_source(connection, kind: str, source_id: int, exclude_id: int | None = None) -> dict[str, Any]:
    source = source_document(connection, source_kind(kind), source_id)
    for line in source['lines']:
        # Creation IDs do not define posting order: an older draft may be
        # explicitly rebased and posted after a newer document on the same day.
        leaves = connection.execute('''SELECT l.*, d.date AS adjustment_date
            FROM goods_price_adjustment_lines l JOIN goods_price_adjustments d ON d.id = l.adjustment_id
            WHERE d.kind = ? AND d.source_id = ? AND d.is_posted = 1 AND d.id != ? AND l.source_line_id = ?
            AND NOT EXISTS (SELECT 1 FROM goods_price_adjustment_lines child
                JOIN goods_price_adjustments child_doc ON child_doc.id = child.adjustment_id
                WHERE child.previous_line_id = l.id AND child_doc.is_posted = 1 AND child_doc.id != ?)''',
            (kind, source_id, exclude_id or -1, line['id'], exclude_id or -1)).fetchall()
        if len(leaves) > 1:
            reject('Нарушена цепочка проведенных корректировок строки: несколько действующих цен')
        previous = leaves[0] if leaves else None
        line['effective_price'] = previous['new_price'] if previous else line['price_without_vat']
        line['effective_sum_without_vat'] = previous['new_sum_without_vat'] if previous else line['sum_without_vat']
        line['effective_vat_amount'] = previous['new_vat_amount'] if previous else line['vat_amount']
        line['previous_line_id'] = previous['id'] if previous else None
        line['previous_date'] = previous['adjustment_date'] if previous else None
    return source


def get_adjustment(connection, adjustment_id: int) -> dict[str, Any]:
    row = connection.execute('SELECT * FROM goods_price_adjustments WHERE id = ? AND marked_for_deletion = 0', (adjustment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='Корректировка цены не найдена')
    doc = row_to_dict(row)
    require_organization(connection, doc['organization_id'])
    source = source_document(connection, source_kind(doc['kind']), doc['source_id'])
    for field in ('organization_name', 'counterparty_name', 'contract_number', 'warehouse_name', 'object_name'):
        doc[field] = source.get(field)
    doc['source_number'] = source['number']
    doc['is_posted'] = bool(doc['is_posted'])
    doc['lines'] = rows_to_dicts(connection.execute('SELECT * FROM goods_price_adjustment_lines WHERE adjustment_id = ? ORDER BY line_number', (adjustment_id,)).fetchall())
    originals = {line['id']: line for line in source['lines']}
    for line in doc['lines']:
        original = originals.get(line['source_line_id'], {})
        for field in ('name', 'unit_name'):
            line[field] = original.get(field)
    hydrate_lines(connection, doc['lines'])
    return doc


def list_adjustments(connection, *, page: int = 1, page_size: int = 20, kind: str | None = None, search: str | None = None):
    conditions, params = ['marked_for_deletion = 0'], []
    add_scope(connection, conditions, params, 'organization_id')
    if kind:
        conditions.append('kind = ?')
        params.append(kind)
    if search:
        conditions.append('number LIKE ?')
        params.append(f'%{search}%')
    where = ' AND '.join(conditions)
    total = connection.execute(f'SELECT COUNT(*) FROM goods_price_adjustments WHERE {where}', params).fetchone()[0]
    rows = connection.execute(f'SELECT id FROM goods_price_adjustments WHERE {where} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?', (*params, page_size, (page-1)*page_size)).fetchall()
    return [get_adjustment(connection, row['id']) for row in rows], {'page': page, 'page_size': page_size, 'total': total, 'pages': max(1, (total+page_size-1)//page_size)}


def assert_no_returns(connection, kind: str, source_id: int) -> None:
    if connection.execute('SELECT id FROM goods_returns WHERE kind = ? AND source_id = ? AND is_posted = 1 LIMIT 1', (source_kind(kind), source_id)).fetchone():
        reject('Сначала отмените возвраты по основанию: совместный перерасчет возвратов и корректировки цены пока не поддерживается')


def assert_no_consumption(connection, source: dict, originals: list[dict]) -> None:
    # Weighted-average inventory has no batch allocation. Any consumption from
    # the affected slice since the receipt requires the future COST-005 engine.
    for line in originals:
        obj = line.get('object_id') if line.get('object_id') is not None else source.get('object_id')
        assert_no_inventory_consumption(connection, warehouse_id=source['warehouse_id'], object_id=obj,
            material_id=line['material_id'], unit_id=base_unit(line), on_date=str(source['date']), **axes(line))


def calculate(connection, payload: dict, adjustment_id: int | None = None) -> tuple[dict, list[dict]]:
    source = get_source(connection, payload['kind'], payload['source_id'], adjustment_id)
    validate_source(connection, {k: v for k, v in payload.items() if v is not None}, source)
    assert_no_returns(connection, payload['kind'], payload['source_id'])
    originals = {line['id']: line for line in source['lines']}
    lines, seen = [], set()
    for number, raw in enumerate(payload['lines'], 1):
        source_id = raw['source_line_id']
        if source_id in seen or source_id not in originals:
            reject('Повторная строка или строка другого основания')
        seen.add(source_id)
        original = originals[source_id]
        validate_snapshot(connection, original)
        if not original.get('material_id') or not original.get('unit_id') or original['quantity'] <= 0:
            reject('Корректировка требует товарную строку с положительным количеством')
        if original['previous_date'] and str(payload['date']) < original['previous_date']:
            reject('Дата корректировки раньше предыдущей корректировки строки')
        quantity = Decimal(str(original['quantity']))
        new_price = Decimal(str(raw['new_price']))
        if not new_price.is_finite() or new_price < 0:
            reject('Новая цена должна быть конечной и неотрицательной')
        new_sum = money(quantity * new_price)
        new_vat = money(new_sum * Decimal(str(original['vat_rate'])) / 100)
        old_sum = money(original['effective_sum_without_vat'])
        old_vat = money(original['effective_vat_amount'])
        lines.append({
            'source_line_id': source_id, 'previous_line_id': original['previous_line_id'],
            'material_id': original['material_id'], 'unit_id': original['unit_id'],
            'object_id': original.get('object_id') if original.get('object_id') is not None else source.get('object_id'),
            'line_number': number, 'quantity': float(quantity), 'old_price': original['effective_price'],
            'new_price': float(new_price), 'vat_rate': original['vat_rate'],
            'old_sum_without_vat': float(old_sum), 'old_vat_amount': float(old_vat),
            'new_sum_without_vat': float(new_sum), 'new_vat_amount': float(new_vat),
            'delta_without_vat': float(new_sum-old_sum), 'delta_vat': float(new_vat-old_vat),
            'delta_with_vat': float(new_sum+new_vat-old_sum-old_vat),
            **normalize_line(connection, original),
        })
    if not lines or not any(line['delta_without_vat'] or line['delta_vat'] for line in lines):
        reject('Корректировка не изменяет сумму ни одной строки')
    if payload['kind'] == 'purchase':
        assert_no_consumption(connection, source, [originals[line['source_line_id']] for line in lines])
    return source, lines


def totals(lines: list[dict]) -> dict[str, float]:
    return {field: float(sum((money(line[field]) for line in lines), Decimal(0))) for field in ('delta_without_vat', 'delta_vat', 'delta_with_vat')}


def save_adjustment(connection, *, payload: dict, user, adjustment_id: int | None = None) -> dict:
    _require_write(user)
    try:
        lock_source(connection, source_kind(payload['kind']), payload['source_id'])
        if adjustment_id:
            existing = get_adjustment(connection, adjustment_id)
            if existing['is_posted']:
                reject('Проведенную корректировку нельзя изменить')
            if existing['kind'] != payload['kind'] or existing['source_id'] != payload['source_id']:
                reject('Для смены основания создайте новую корректировку')
            if connection.execute('''SELECT l.id FROM goods_price_adjustment_lines l
                JOIN goods_price_adjustment_lines parent ON parent.id = l.previous_line_id WHERE parent.adjustment_id = ? LIMIT 1''', (adjustment_id,)).fetchone():
                reject('Сначала удалите зависимые черновики корректировок')
        source, lines = calculate(connection, payload, adjustment_id)
        values = {key: source.get(key) for key in DIMENSIONS}
        values.update(kind=payload['kind'], source_id=payload['source_id'], number=payload.get('number') or f'КЦ-{new_uuid()[:8]}',
                      date=str(payload['date']), description=payload.get('description'), modified_at=utcnow_iso(), updated_at=utcnow_iso(), **totals(lines))
        if adjustment_id:
            connection.execute(f"UPDATE goods_price_adjustments SET {', '.join(key+' = ?' for key in values)} WHERE id = ?", (*values.values(), adjustment_id))
            connection.execute('DELETE FROM goods_price_adjustment_lines WHERE adjustment_id = ?', (adjustment_id,))
        else:
            adjustment_id = insert(connection, 'goods_price_adjustments', {**values, 'uuid': new_uuid()})
        for line in lines:
            insert(connection, 'goods_price_adjustment_lines', {'adjustment_id': adjustment_id, **line})
        connection.commit()
        return get_adjustment(connection, adjustment_id)
    except Exception:
        connection.rollback()
        raise


def change_adjustment(connection, *, adjustment_id: int, user, action: str) -> None:
    (_require_write if action == 'delete' else _require_admin)(user)
    try:
        snapshot = get_adjustment(connection, adjustment_id)
        lock_source(connection, source_kind(snapshot['kind']), snapshot['source_id'])
        doc = get_adjustment(connection, adjustment_id)
        if doc['kind'] == 'purchase':
            # Serialize cost revisions with sales/transfers from this warehouse.
            connection.execute('UPDATE warehouses SET id = id WHERE id = ?', (doc['warehouse_id'],))
        lock_settlement_contracts(connection, doc.get('contract_id'))
        if action == 'post':
            if doc['is_posted']:
                reject('Корректировка уже проведена')
            source, lines = calculate(connection, doc, adjustment_id)
            for stored, actual in zip(doc['lines'], lines):
                if any(stored[field] != actual[field] for field in actual):
                    reject('Основание или действующая цена изменились. Пересохраните корректировку')
            if doc['kind'] == 'purchase':
                originals = {line['id']: line for line in source['lines']}
                for line in lines:
                    original = originals[line['source_line_id']]
                    obj = original.get('object_id') if original.get('object_id') is not None else doc['object_id']
                    delta = money(line['delta_without_vat'])
                    if delta < 0:
                        assert_stock_removal(connection, doc['warehouse_id'], obj, original['material_id'], base_unit(original), doc['date'], 0, -delta, **axes(original))
                    insert(connection, 'inventory_register', {
                        'recorder_type': 'goods_price_adjustment', 'recorder_id': adjustment_id, 'line_number': line['line_number'], 'period': doc['date'],
                        'material_id': original['material_id'], 'warehouse_id': doc['warehouse_id'], 'object_id': obj, 'unit_id': base_unit(original), **axes(original),
                        'quantity_income': 0, 'quantity_expense': 0, 'sum_income': float(max(delta, 0)), 'sum_expense': float(max(-delta, 0)),
                        'uuid': new_uuid(), 'created_at': utcnow_iso(), 'updated_at': utcnow_iso(),
                    })
            insert(connection, 'mutual_settlements_register', {
                'recorder_type': 'goods_price_adjustment', 'recorder_id': adjustment_id, 'line_number': 1, 'period': doc['date'],
                **{key: doc.get(key) for key in DIMENSIONS if key != 'warehouse_id'},
                'direction': 'receivable' if doc['kind'] == 'sale' else 'payable', 'accrual_amount': doc['delta_with_vat'],
                'payment_amount': 0, 'uuid': new_uuid(), 'created_at': utcnow_iso(), 'updated_at': utcnow_iso(),
            })
            connection.execute('UPDATE goods_price_adjustments SET is_posted = 1, posted_at = ?, updated_at = ? WHERE id = ?', (utcnow_iso(), utcnow_iso(), adjustment_id))
        elif action in ('unpost', 'delete'):
            if action == 'unpost' and not doc['is_posted']:
                reject('Корректировка не проведена')
            if action == 'delete' and doc['is_posted']:
                reject('Сначала отмените проведение корректировки')
            dependents = connection.execute('''SELECT d.id, d.is_posted FROM goods_price_adjustment_lines l
                JOIN goods_price_adjustments d ON d.id = l.adjustment_id
                JOIN goods_price_adjustment_lines parent ON parent.id = l.previous_line_id
                WHERE parent.adjustment_id = ? AND d.marked_for_deletion = 0''', (adjustment_id,)).fetchall()
            if any(row['is_posted'] for row in dependents) or (action == 'delete' and dependents):
                reject('Сначала отмените или удалите последующие корректировки этих строк')
            if action == 'unpost':
                source = source_document(connection, source_kind(doc['kind']), doc['source_id'])
                assert_no_returns(connection, doc['kind'], doc['source_id'])
                if doc['kind'] == 'purchase':
                    originals = {line['id']: line for line in source['lines']}
                    assert_no_consumption(connection, source, [originals[line['source_line_id']] for line in doc['lines']])
                for table in ('inventory_register', 'mutual_settlements_register'):
                    connection.execute(f"DELETE FROM {table} WHERE recorder_type = 'goods_price_adjustment' AND recorder_id = ?", (adjustment_id,))
                connection.execute('UPDATE goods_price_adjustments SET is_posted = 0, posted_at = NULL, modified_at = ?, updated_at = ? WHERE id = ?', (utcnow_iso(), utcnow_iso(), adjustment_id))
            else:
                connection.execute('UPDATE goods_price_adjustment_lines SET previous_line_id = NULL WHERE adjustment_id = ?', (adjustment_id,))
                connection.execute('UPDATE goods_price_adjustments SET marked_for_deletion = 1, is_deleted = 1, updated_at = ? WHERE id = ?', (utcnow_iso(), adjustment_id))
        else:
            reject('Неизвестная операция корректировки')
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def adjustment_movements(connection, adjustment_id: int) -> dict:
    return {'document': get_adjustment(connection, adjustment_id), **{name: hydrate_lines(connection, rows_to_dicts(connection.execute(
        f"SELECT * FROM {table} WHERE recorder_type = 'goods_price_adjustment' AND recorder_id = ? ORDER BY line_number", (adjustment_id,)).fetchall())
        )
        for name, table in (('inventory', 'inventory_register'), ('settlements', 'mutual_settlements_register'))}}
