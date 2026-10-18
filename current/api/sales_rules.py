"""Shared reservation availability and contract credit limits for all writers."""
from decimal import Decimal

from fastapi import HTTPException

from api.trade_settlement_rules import money


def assert_available(connection, *, warehouse_id, object_id, material_id, unit_id, on_date, quantity,
                     characteristic_id=None, series_id=None, exclude_order_id=None):
    """Preserve free stock at every later date, including future reservations."""
    args=(warehouse_id, material_id, unit_id, unit_id, object_id, object_id, characteristic_id, characteristic_id, series_id, series_id)
    predicate='''warehouse_id = ? AND material_id = ? AND (unit_id = ? OR (unit_id IS NULL AND ? IS NULL))
        AND (object_id = ? OR (object_id IS NULL AND ? IS NULL))
        AND (characteristic_id = ? OR (characteristic_id IS NULL AND ? IS NULL))
        AND (series_id = ? OR (series_id IS NULL AND ? IS NULL)) AND is_deleted = 0'''
    rows=connection.execute(f'''SELECT period, SUM(delta) AS delta FROM (
        SELECT period, quantity_income-quantity_expense AS delta FROM inventory_register WHERE {predicate}
        UNION ALL SELECT period, reserve_expense-reserve_income AS delta FROM sales_reservation_register
        WHERE {predicate} AND (? IS NULL OR order_id != ?)) changes GROUP BY period ORDER BY period''',
        (*args,*args,exclude_order_id,exclude_order_id)).fetchall()
    balance=Decimal(0)
    checks=[]
    for row in rows:
        if row['period']>on_date and not checks:
            checks.append(balance)
        balance+=Decimal(str(row['delta']))
        if row['period']>=on_date:
            checks.append(balance)
    if not checks:
        checks.append(balance)
    if any(value+Decimal('0.000000001')<Decimal(str(quantity)) for value in checks):
        raise HTTPException(status_code=400,detail='Недостаточно свободного остатка с учетом резервов на дату или последующие даты')


def assert_credit(connection, doc, amounts, *, financial_lines=(), physical_lines=()):
    """Caller holds the contract lock; check gross debt per object over time."""
    if not doc.get('contract_id'):
        return
    contract=connection.execute('SELECT credit_limit, credit_limit_strict FROM contracts WHERE id = ?', (doc['contract_id'],)).fetchone()
    if not contract or not contract['credit_limit_strict'] or contract['credit_limit'] is None:
        return
    rows=connection.execute('''SELECT period, object_id, accrual_amount, payment_amount FROM mutual_settlements_register
        WHERE organization_id = ? AND counterparty_id = ? AND contract_id = ? AND direction = 'receivable'
        AND is_deleted = 0 ORDER BY period, id''', (doc['organization_id'],doc['counterparty_id'],doc['contract_id'])).fetchall()
    shipments=connection.execute('''SELECT d.kind,d.date,l.order_line_id,l.quantity,l.sum_with_vat,
        COALESCE(l.object_id,d.object_id) AS object_id FROM sales_documents d JOIN sales_lines l ON l.document_id = d.id
        WHERE d.organization_id = ? AND d.counterparty_id = ? AND d.contract_id = ? AND d.issue_mode = 'order'
        AND d.kind IN ('expense-orders','realizations') AND d.is_posted = 1 AND d.is_deleted = 0 AND l.is_deleted = 0
        AND l.line_type = 'goods' ''',(doc['organization_id'],doc['counterparty_id'],doc['contract_id'])).fetchall()
    dates=sorted({str(doc['date'])}|{row['period'] for row in rows if row['period']>=str(doc['date'])}
                 |{row['date'] for row in shipments if row['date']>=str(doc['date'])})
    for date in dates:
        slices={}
        for row in rows:
            if row['period']<=date:
                key=row['object_id']
                slices[key]=slices.get(key,Decimal(0))+money(row['accrual_amount'])-money(row['payment_amount'])
        for obj, amount in amounts:
            slices[obj]=slices.get(obj,Decimal(0))+money(amount)
        # Physical-first delivery also uses credit. Invoice posting replaces
        # its pending exposure with actual debt instead of counting it twice.
        pending={}
        for row in shipments:
            if row['date']<=date:
                key=(row['order_line_id'],row['object_id'])
                values=pending.setdefault(key,[Decimal(0),Decimal(0),Decimal(0),Decimal(0)])
                index=0 if row['kind']=='expense-orders' else 2
                values[index]+=Decimal(str(row['quantity']))
                values[index+1]+=money(row['sum_with_vat'])
        for proposed,index in [(physical_lines,0),(financial_lines,2)]:
            for line in proposed:
                if line['line_type']=='goods' and doc.get('issue_mode')=='order':
                    obj=line['object_id'] if line['object_id'] is not None else doc['object_id']
                    values=pending.setdefault((line['order_line_id'],obj),[Decimal(0),Decimal(0),Decimal(0),Decimal(0)])
                    values[index]+=Decimal(str(line['quantity']))
                    values[index+1]+=money(line['sum_with_vat'])
        for (_,obj),(shipped,shipped_amount,invoiced,invoiced_amount) in pending.items():
            if shipped>invoiced:
                slices[obj]=slices.get(obj,Decimal(0))+max(shipped_amount-invoiced_amount,0)
        if sum((max(value,0) for value in slices.values()),Decimal(0))>money(contract['credit_limit']):
            raise HTTPException(status_code=400,detail='Превышен строгий кредитный лимит договора')
