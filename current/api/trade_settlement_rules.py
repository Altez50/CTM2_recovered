"""Shared contract ownership and balance projection rules for trade accounting."""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from fastapi import HTTPException


def money(value):
    try:
        number = Decimal(str(value or 0))
        if not number.is_finite():
            raise InvalidOperation
        return number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail='Денежная сумма выходит за поддерживаемую точность') from exc


def split_balance(accrual, payment):
    """Debt and advance are separate positive resources within one settlement slice."""
    net = money(accrual) - money(payment)
    return float(max(net, 0)), float(max(-net, 0))


def inventory_cost_share(amount, quantity, available):
    """Round the allocated value, never the intermediate cost per base unit."""
    available = Decimal(str(available))
    return money(money(amount) * Decimal(str(quantity)) / available) if available > 0 else money(0)


def validate_contract(connection, *, contract_id, counterparty_id, organization_id=None):
    if contract_id is None:
        return
    contract = connection.execute(
        "SELECT organization_id, counterparty_id, marked_for_deletion, is_deleted FROM contracts WHERE id = ?",
        (contract_id,),
    ).fetchone()
    if contract is None or contract["marked_for_deletion"] or contract["is_deleted"]:
        raise HTTPException(status_code=400, detail="Договор не найден или помечен на удаление")
    if organization_id is not None and contract["organization_id"] != organization_id:
        raise HTTPException(status_code=400, detail="Договор не принадлежит выбранной организации")
    if contract["counterparty_id"] != counterparty_id:
        raise HTTPException(status_code=400, detail="Договор не принадлежит выбранному контрагенту")
    return contract


def assert_no_future_price_adjustment(connection, *, warehouse_id, object_id, material_id, unit_id, on_date, characteristic_id=None, series_id=None):
    """A backdated expense would require revaluing an already posted correction."""
    if connection.execute('''SELECT id FROM inventory_register
        WHERE recorder_type IN ('goods_price_adjustment', 'purchase_quantity_adjustment') AND warehouse_id = ?
        AND material_id = ? AND unit_id = ? AND period > ? AND is_deleted = 0
        AND (characteristic_id = ? OR (characteristic_id IS NULL AND ? IS NULL))
        AND (series_id = ? OR (series_id IS NULL AND ? IS NULL))
        AND (object_id = ? OR (object_id IS NULL AND ? IS NULL)) LIMIT 1''',
        (warehouse_id, material_id, unit_id, on_date, characteristic_id, characteristic_id, series_id, series_id, object_id, object_id)).fetchone():
        raise HTTPException(status_code=400, detail='COST-005: расход раньше проведенной закупочной корректировки требует пересчета себестоимости')


def assert_no_inventory_consumption(connection, *, warehouse_id, object_id, material_id, unit_id, on_date, characteristic_id=None, series_id=None, after_movement_id=None, exclude_recorder_type=None, exclude_recorder_id=None, ignore_purchase_quantity_reversals=False):
    """Do not alter carrying cost while a dependent expense remains posted.

    Older goods issues calculated their cost across units of a material. Include
    those expenses conservatively even if their stored unit differs or is NULL.
    A return's incoming movement has an actual posting order within its date.
    Earlier same-day expenses (including its original sale) did not consume it.
    Warehouse locks serialize writers of the same stock slice; later movement
    IDs within that day identify expenses posted after the returned stock.
    """
    if connection.execute('''SELECT id FROM inventory_register
        WHERE warehouse_id = ? AND material_id = ?
        AND (unit_id = ? OR (unit_id IS NULL AND ? IS NULL) OR recorder_type = 'goods_issue')
        AND (period > ? OR (period = ? AND (? IS NULL OR id > ?)))
        AND (object_id = ? OR (object_id IS NULL AND ? IS NULL))
        AND (characteristic_id = ? OR (characteristic_id IS NULL AND ? IS NULL))
        AND (series_id = ? OR (series_id IS NULL AND ? IS NULL))
        AND (? IS NULL OR recorder_type != ? OR recorder_id != ?)
        AND (? = 0 OR recorder_type != 'purchase_quantity_adjustment')
        AND quantity_expense > 0 AND is_deleted = 0 LIMIT 1''',
        (warehouse_id, material_id, unit_id, unit_id, on_date, on_date, after_movement_id, after_movement_id,
         object_id, object_id, characteristic_id, characteristic_id, series_id, series_id,
         exclude_recorder_type, exclude_recorder_type, exclude_recorder_id, int(ignore_purchase_quantity_reversals))).fetchone():
        raise HTTPException(status_code=400, detail='COST-005: сначала отмените зависимые расходные документы; изменение стоимости требует пересчета себестоимости')


def lock_inventory_warehouses(connection, *warehouse_ids):
    # One order for transfers touching two warehouses, shared by every local
    # trade inventory writer. The transaction retains these locks until commit.
    for warehouse_id in sorted({item for item in warehouse_ids if item is not None}):
        connection.execute('UPDATE warehouses SET id = id WHERE id = ?', (warehouse_id,))


def lock_settlement_contracts(connection, *contract_ids):
    # Opening debt and its payments must validate balances under the same lock.
    for contract_id in sorted({item for item in contract_ids if item is not None}):
        connection.execute('UPDATE contracts SET id = id WHERE id = ?', (contract_id,))
