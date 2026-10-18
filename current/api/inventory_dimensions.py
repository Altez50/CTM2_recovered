"""Stock identity and immutable conversion snapshots for local trade documents."""
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException


REFERENCE_KINDS = ('material-packages', 'material-characteristics', 'material-series')
REFERENCE_TABLES = dict(zip(REFERENCE_KINDS, ('material_packages', 'material_characteristics', 'material_series')))
AXES = ('characteristic_id', 'series_id')


def reject(message):
    raise HTTPException(status_code=400, detail=message)


def lock_material_dimensions(connection, *material_ids):
    """Serialize reference bindings and first document use on their material.

    Call before reading references, in the transaction that saves the document
    or changes a binding. Sorting also covers a reference moved between goods.
    """
    for ident in sorted({item for item in material_ids if item is not None}):
        connection.execute('UPDATE materials SET id = id WHERE id = ?', (ident,))


def validate_material_unit_change(connection, material_id, unit_id):
    """The caller holds the material lock shared with package creation."""
    current = connection.execute('SELECT unit_id FROM materials WHERE id = ?', (material_id,)).fetchone()
    if current and current['unit_id'] != unit_id and connection.execute(
            'SELECT id FROM material_packages WHERE material_id = ? LIMIT 1', (material_id,)).fetchone():
        reject('Базовая единица товара используется упаковками и не может быть изменена')


def ensure_schema(connection, ensure_column, table_exists):
    for table in REFERENCE_TABLES.values():
        extra = 'factor REAL NOT NULL CHECK (factor > 0),' if table == 'material_packages' else ''
        if table == 'material_series':
            extra = 'characteristic_id INTEGER REFERENCES material_characteristics(id),'
        connection.executescript(f'''CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            material_id INTEGER NOT NULL REFERENCES materials(id), {extra}
            marked_for_deletion INTEGER NOT NULL DEFAULT 0,
            uuid TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            modified_at TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_deleted INTEGER NOT NULL DEFAULT 0
        );''')
    line_tables = ('goods_receipt_lines', 'goods_issue_lines', 'goods_transfer_lines')
    for table in (*line_tables, 'inventory_register', 'goods_price_adjustment_lines', 'goods_return_lines'):
        if not table_exists(connection, table):
            continue
        ensure_column(connection, table, 'characteristic_id', 'INTEGER REFERENCES material_characteristics(id)')
        ensure_column(connection, table, 'series_id', 'INTEGER REFERENCES material_series(id)')
    for table in (*line_tables, 'goods_price_adjustment_lines', 'goods_return_lines'):
        if not table_exists(connection, table):
            continue
        ensure_column(connection, table, 'package_id', 'INTEGER REFERENCES material_packages(id)')
        ensure_column(connection, table, 'conversion_factor', 'REAL NOT NULL DEFAULT 1')
        ensure_column(connection, table, 'base_quantity', 'REAL')
        ensure_column(connection, table, 'base_unit_id', 'INTEGER REFERENCES units(id)')
        if table in line_tables:
            connection.execute(f'UPDATE {table} SET base_quantity = quantity WHERE base_quantity IS NULL')
            connection.execute(f'UPDATE {table} SET base_unit_id = unit_id WHERE base_unit_id IS NULL AND package_id IS NULL')
    connection.execute('''CREATE INDEX IF NOT EXISTS idx_inventory_dimensions
        ON inventory_register(warehouse_id, material_id, object_id, unit_id, characteristic_id, series_id, period)''')


def active(connection, table, ident):
    row = connection.execute(f'SELECT * FROM {table} WHERE id = ? AND marked_for_deletion = 0 AND is_deleted = 0', (ident,)).fetchone()
    if row is None:
        reject('Справочник аналитики не найден или помечен на удаление')
    return row


def validate_reference(connection, kind, payload, existing=None):
    material = active(connection, 'materials', payload['material_id'])
    if material['is_group']:
        reject('Укажите товар, а не группу')
    if kind == 'material-packages' and not material['unit_id']:
        reject('Для упаковки нужна базовая единица товара')
    if kind == 'material-series' and payload.get('characteristic_id'):
        characteristic = active(connection, 'material_characteristics', payload['characteristic_id'])
        if characteristic['material_id'] != payload['material_id']:
            reject('Характеристика серии принадлежит другому товару')
    if existing and any(payload.get(key) != existing.get(key) for key in ('material_id', 'factor', 'characteristic_id', 'marked_for_deletion')):
        assert_reference_unused(connection, kind, existing['id'])


def assert_reference_unused(connection, kind, ident):
    column = dict(zip(REFERENCE_KINDS, ('package_id', 'characteristic_id', 'series_id')))[kind]
    for table in ('sales_lines', 'purchase_lines', 'goods_receipt_lines', 'goods_issue_lines', 'goods_transfer_lines', 'goods_price_adjustment_lines',
                  'goods_return_lines', 'opening_inventory_lines'):
        if connection.execute(f'SELECT id FROM {table} WHERE {column} = ? LIMIT 1', (ident,)).fetchone():
            reject('Аналитика используется документом: нельзя изменить принадлежность, коэффициент или удалить запись')
    if kind == 'material-characteristics' and connection.execute(
            'SELECT id FROM material_series WHERE characteristic_id = ? LIMIT 1', (ident,)).fetchone():
        reject('Характеристика используется серией')


def normalize_line(connection, line):
    material_id = line.get('material_id')
    characteristic_id, series_id = (line.get(key) for key in AXES)
    package_id = line.get('package_id')
    if not material_id and any((characteristic_id, series_id, package_id)):
        reject('Упаковка, характеристика и серия требуют указания товара')
    for table, ident in (('material_characteristics', characteristic_id), ('material_series', series_id)):
        if ident:
            record = active(connection, table, ident)
            if record['material_id'] != material_id:
                reject('Характеристика или серия принадлежит другому товару')
            if table == 'material_series' and record['characteristic_id'] is not None and record['characteristic_id'] != characteristic_id:
                reject('Серия не соответствует характеристике')
    factor, unit_id = Decimal(1), line.get('unit_id')
    if package_id:
        package = active(connection, 'material_packages', package_id)
        material = active(connection, 'materials', material_id)
        if package['material_id'] != material_id or unit_id != material['unit_id']:
            reject('Упаковка или базовая единица не соответствует товару')
        factor = Decimal(str(package['factor']))
    try:
        quantity = Decimal(str(line.get('quantity') or 0)) * factor
        if not quantity.is_finite() or quantity < 0 or quantity != quantity.quantize(Decimal('.000001')):
            reject('Базовое количество должно быть конечным, неотрицательным и содержать не более 6 знаков после запятой')
    except InvalidOperation:
        reject('Базовое количество выходит за поддерживаемую точность')
    return dict(characteristic_id=characteristic_id, series_id=series_id, package_id=package_id,
                conversion_factor=float(factor), base_quantity=float(quantity), base_unit_id=unit_id)


def validate_snapshot(connection, line):
    actual = normalize_line(connection, line)
    for key, value in actual.items():
        stored = line.get(key)
        if key in ('base_unit_id', 'base_quantity') and stored is None and not line.get('package_id'):
            stored = line.get('unit_id' if key == 'base_unit_id' else 'quantity')
        if stored != value:
            reject('Упаковка или складская аналитика изменилась: пересохраните черновик')


def base_quantity(line):
    return line['base_quantity'] if line.get('base_quantity') is not None else line['quantity']


def base_unit(line):
    return line.get('base_unit_id') if line.get('base_unit_id') is not None else line.get('unit_id')


def axes(line):
    return {key: dict(line).get(key) for key in AXES}


def hydrate_lines(connection, lines):
    for line in lines:
        for column, table, label in (('package_id', 'material_packages', 'package_name'),
                                    ('characteristic_id', 'material_characteristics', 'characteristic_name'),
                                    ('series_id', 'material_series', 'series_name')):
            row = connection.execute(f'SELECT name FROM {table} WHERE id = ?', (line.get(column),)).fetchone()
            line[label] = row['name'] if row else None
    return lines


def guard_legacy_exchange(connection, kind, payload, *, for_write=False):
    """Until the exchange protocol carries reference UUIDs, fail explicitly.

    Also protect a local dimensional document from an older incoming snapshot
    which omits the new fields. Local numeric reference IDs are never portable.
    """
    headers, lines, fk = {
        'receipt': ('goods_receipts', 'goods_receipt_lines', 'receipt_id'),
        'issue': ('goods_issues', 'goods_issue_lines', 'issue_id'),
        'transfer': ('goods_transfers', 'goods_transfer_lines', 'transfer_id'),
    }[kind]
    if for_write:
        # Share the local editor's header lock before checking persisted axes.
        connection.execute(f'UPDATE {headers} SET id = id WHERE uuid = ?', (payload.get('uuid'),))
    fields = ('package_id', 'characteristic_id', 'series_id', 'package_uuid', 'characteristic_uuid', 'series_uuid')
    unsupported = any(any(line.get(field) is not None for field in fields) or line.get('conversion_factor', 1) != 1
                      for line in payload.get('lines', []))
    local = connection.execute(f'''SELECT l.id FROM {lines} l JOIN {headers} d ON d.id = l.{fk}
        WHERE d.uuid = ? AND (l.package_id IS NOT NULL OR l.characteristic_id IS NOT NULL OR l.series_id IS NOT NULL)
        LIMIT 1''', (payload.get('uuid'),)).fetchone()
    if unsupported or local:
        raise HTTPException(status_code=409, detail='STEP-02: обмен документов с упаковками, характеристиками или сериями пока не поддерживается; аналитики не будут отброшены')
