"""Explicit organization boundaries for the local trade API and SQL queries."""
from functools import wraps

from fastapi import HTTPException


class TradeConnection:
    """Carry authenticated scope without rewriting SQL or changing DB semantics."""
    def __init__(self, connection, user):
        self.connection, self.trade_user = connection, user

    def __getattr__(self, name):
        return getattr(self.connection, name)


def organizations(connection):
    return getattr(getattr(connection, 'trade_user', None), 'organization_ids', None)


def require_organization(connection, organization_id):
    allowed = organizations(connection)
    if allowed is not None and organization_id not in allowed:
        raise HTTPException(status_code=403, detail='Нет доступа к организации документа')


def add_scope(connection, conditions, params, column):
    allowed = organizations(connection)
    if allowed is not None:
        conditions.append(f"{column} IN ({','.join('?' for _ in allowed)})" if allowed else '1 = 0')
        params.extend(allowed)


def contract_organization(connection, contract_id):
    row = connection.execute('SELECT organization_id FROM contracts WHERE id = ?', (contract_id,)).fetchone()
    return row['organization_id'] if row else None


def require_contract(connection, contract_id):
    require_organization(connection, contract_organization(connection, contract_id))


def require_estimate(connection, estimate_id):
    if estimate_id is not None and organizations(connection) is not None:
        row = connection.execute('SELECT contract_id FROM estimates WHERE id = ?', (estimate_id,)).fetchone()
        require_contract(connection, row['contract_id'] if row else None)


def _organization_sql(connection, column, params):
    allowed = organizations(connection)
    params.extend(allowed or [])
    return f"{column} IN ({','.join('?' for _ in allowed)})" if allowed else '1 = 0'


def _contract_sql(connection, column, params, *, optional=False):
    predicate = _organization_sql(connection, f'(SELECT organization_id FROM contracts WHERE id = {column})', params)
    return f'({column} IS NULL OR {predicate})' if optional else predicate


def _estimate_sql(connection, column, params):
    predicate = _organization_sql(connection, f'(SELECT ct.organization_id FROM estimates e JOIN contracts ct ON ct.id = e.contract_id WHERE e.id = {column})', params)
    return f'({column} IS NULL OR {predicate})'


def _source_ref_sql(connection, column, params):
    # Compare complete references, without permissive casts of untrusted text.
    sources = []
    for kind, table, organization in [('goods_receipt', 'goods_receipts', 'src.organization_id'),
                                       ('goods_issue', 'goods_issues', 'src.organization_id'),
                                       ('estimate', 'estimates', '(SELECT organization_id FROM contracts WHERE id = src.contract_id)')]:
        allowed = _organization_sql(connection, organization, params)
        sources.append(f"EXISTS (SELECT 1 FROM {table} src WHERE {column} = '{kind}:' || CAST(src.id AS TEXT) AND {allowed})")
    return f"({column} IS NULL OR {column} = '' OR {' OR '.join(sources)})"


def _schedule_sql(connection, alias, params):
    header = _contract_sql(connection, f'{alias}.contract_id', params)
    contract = _contract_sql(connection, 'acl_line.contract_id', params)
    estimate = _estimate_sql(connection, 'acl_line.estimate_id', params)
    source = _source_ref_sql(connection, 'acl_line.source_ref', params)
    line = f'(((acl_line.is_group = 1 AND acl_line.contract_id IS NULL) OR {contract}) AND {estimate} AND {source})'
    return f'''({header} AND NOT EXISTS (SELECT 1 FROM payment_schedule_lines acl_line
        WHERE acl_line.schedule_id = {alias}.id AND acl_line.marked_for_deletion = 0 AND acl_line.is_deleted = 0
        AND NOT COALESCE({line}, FALSE)))'''


def _payment_sql(connection, alias, params):
    checks = [_contract_sql(connection, f'{alias}.contract_id', params),
              _estimate_sql(connection, f'{alias}.estimate_id', params)]
    schedule = _schedule_sql(connection, 'acl_schedule', params)
    checks.append(f'''({alias}.linked_schedule_id IS NULL OR EXISTS (SELECT 1 FROM payment_schedules acl_schedule
        WHERE acl_schedule.id = {alias}.linked_schedule_id AND {schedule}))''')
    schedule = _schedule_sql(connection, 'acl_parent', params)
    linked_contract = _contract_sql(connection, 'acl_link.contract_id', params)
    checks.append(f'''({alias}.linked_line_id IS NULL OR EXISTS (SELECT 1 FROM payment_schedule_lines acl_link
        JOIN payment_schedules acl_parent ON acl_parent.id = acl_link.schedule_id
        WHERE acl_link.id = {alias}.linked_line_id AND {schedule} AND {linked_contract}))''')
    allowed = _organization_sql(connection, 'acl_history.organization_id', params)
    checks.append(f'''NOT EXISTS (SELECT 1 FROM mutual_settlements_register acl_history
        WHERE acl_history.recorder_type = 'payment_transaction' AND acl_history.recorder_id = {alias}.id
        AND acl_history.is_deleted = 0 AND NOT COALESCE({allowed}, FALSE))''')
    return '(' + ' AND '.join(checks) + ')'


def add_payment_scope(connection, conditions, params, alias='pt'):
    if organizations(connection) is not None:
        conditions.append(_payment_sql(connection, alias, params))


def _basis_sql(connection, alias, params):
    sources = []
    for kind, table in [('goods_receipt', 'goods_receipts'), ('goods_issue', 'goods_issues'),
                        ('goods_transfer', 'goods_transfers'), ('goods_return', 'goods_returns'),
                        ('goods_price_adjustment', 'goods_price_adjustments'), ('opening_balance', 'opening_balances')]:
        allowed = _organization_sql(connection, 'acl_basis.organization_id', params)
        sources.append(f"({alias}.based_on_type = '{kind}' AND EXISTS (SELECT 1 FROM {table} acl_basis WHERE acl_basis.id = {alias}.based_on_id AND {allowed}))")
    estimate = _estimate_sql(connection, f'{alias}.based_on_id', params)
    sources.append(f"({alias}.based_on_type = 'estimate' AND {estimate})")
    for kind, table, predicate in [('payment_schedule', 'payment_schedules', _schedule_sql),
                                  ('payment_transaction', 'payment_transactions', _payment_sql)]:
        allowed = predicate(connection, 'acl_basis', params)
        sources.append(f"({alias}.based_on_type = '{kind}' AND EXISTS (SELECT 1 FROM {table} acl_basis WHERE acl_basis.id = {alias}.based_on_id AND {allowed}))")
    return f"({alias}.based_on_id IS NULL OR {' OR '.join(sources)})"


def add_goods_links_scope(connection, conditions, params, alias='d', *, based_on=True):
    if organizations(connection) is not None:
        conditions.extend([_contract_sql(connection, f'{alias}.contract_id', params, optional=True),
                           _estimate_sql(connection, f'{alias}.estimate_id', params)])
        if based_on:
            conditions.append(_basis_sql(connection, alias, params))


def require_goods_links(connection, payload):
    if payload.get('contract_id') is not None:
        require_contract(connection, payload['contract_id'])
    require_estimate(connection, payload.get('estimate_id'))
    require_based_on(connection, payload)


def require_posted_payment(connection, tx_id):
    for row in connection.execute("SELECT DISTINCT organization_id FROM mutual_settlements_register WHERE recorder_type = 'payment_transaction' AND recorder_id = ? AND is_deleted = 0", (tx_id,)).fetchall():
        require_organization(connection, row['organization_id'])


def add_payment_history_scope(connection, conditions, params):
    allowed = organizations(connection)
    if allowed:
        placeholders = ','.join('?' for _ in allowed)
        conditions.append(f'''NOT EXISTS (SELECT 1 FROM mutual_settlements_register acl
            WHERE acl.recorder_type = 'payment_transaction' AND acl.recorder_id = pt.id AND acl.is_deleted = 0
            AND (acl.organization_id IS NULL OR acl.organization_id NOT IN ({placeholders})))''')
        params.extend(allowed)


def add_cash_history_scope(connection, conditions, params):
    # Cash facts also carry a settlement snapshot. A later contract rebind must
    # not expose facts originally posted in another organization.
    add_scope(connection, conditions, params, '''CASE WHEN psr.recorder_type IN ('payment_transaction', 'goods_return_refund')
        THEN (SELECT organization_id FROM mutual_settlements_register acl WHERE acl.recorder_type = psr.recorder_type
              AND acl.recorder_id = psr.recorder_id AND acl.is_deleted = 0 LIMIT 1)
        ELSE (SELECT organization_id FROM contracts WHERE id = psr.contract_id) END''')
    if organizations(connection) is not None:
        payment = _payment_sql(connection, 'acl_cash_tx', params)
        conditions.append(f"(psr.recorder_type != 'payment_transaction' OR EXISTS (SELECT 1 FROM payment_transactions acl_cash_tx WHERE acl_cash_tx.id = psr.recorder_id AND {payment}))")
        schedule = _schedule_sql(connection, 'acl_cash_plan', params)
        conditions.append(f"(psr.recorder_type != 'payment_schedule' OR EXISTS (SELECT 1 FROM payment_schedules acl_cash_plan WHERE acl_cash_plan.id = psr.recorder_id AND {schedule}))")
        conditions.append(_estimate_sql(connection, 'psr.estimate_id', params))


def inventory_organization(alias='ir'):
    # Organization is the posted document's analytic, not the mutable current
    # owner of its warehouse. Unknown/orphan registrars fail closed for ACL.
    tables = {'goods_receipt': 'goods_receipts', 'goods_issue': 'goods_issues',
              'goods_transfer': 'goods_transfers', 'goods_return': 'goods_returns',
              'goods_price_adjustment': 'goods_price_adjustments', 'opening_balance': 'opening_balances',
              'purchase_acquisition': 'purchase_documents', 'purchase_receipt_order': 'purchase_documents',
              'purchase_quantity_adjustment': 'purchase_documents'}
    tables.update(sale_realization='sales_documents', sale_expense_order='sales_documents')
    return 'CASE '+alias+'.recorder_type '+ ' '.join(
        f"WHEN '{kind}' THEN (SELECT organization_id FROM {table} WHERE id = {alias}.recorder_id)"
        for kind, table in tables.items()) + ' ELSE NULL END'


def require_based_on(connection, payload):
    if organizations(connection) is None or not payload.get('based_on_id'):
        return
    kind, ident = payload.get('based_on_type'), payload['based_on_id']
    tables = {'goods_receipt': 'goods_receipts', 'goods_issue': 'goods_issues',
              'goods_transfer': 'goods_transfers', 'goods_return': 'goods_returns',
              'goods_price_adjustment': 'goods_price_adjustments', 'opening_balance': 'opening_balances'}
    if kind in tables:
        row = connection.execute(f'SELECT organization_id FROM {tables[kind]} WHERE id = ?', (ident,)).fetchone()
        require_organization(connection, row['organization_id'] if row else None)
    elif kind == 'estimate':
        require_estimate(connection, ident)
    elif kind in ('payment_transaction', 'payment_schedule'):
        # A header contract alone does not prove access to linked/mixed data.
        from api.payment_services import get_payment_transaction, get_payment_schedule
        (get_payment_transaction if kind == 'payment_transaction' else get_payment_schedule)(connection, ident)
    else:
        raise HTTPException(status_code=403, detail='Организацию документа-основания определить нельзя')


def require_payment_links(connection, payload, *, group=False):
    if organizations(connection) is None:
        return
    if not group or payload.get('contract_id') is not None:
        require_contract(connection, payload.get('contract_id'))
    require_estimate(connection, payload.get('estimate_id'))
    schedule_ids = set()
    if payload.get('linked_schedule_id') is not None:
        schedule_ids.add(payload['linked_schedule_id'])
    if payload.get('linked_line_id'):
        row = connection.execute('SELECT contract_id, schedule_id FROM payment_schedule_lines WHERE id = ?', (payload['linked_line_id'],)).fetchone()
        require_contract(connection, row['contract_id'] if row else None)
        schedule_ids.add(row['schedule_id'])
    if schedule_ids:
        from api.payment_services import get_payment_schedule
        for ident in sorted(schedule_ids):
            get_payment_schedule(connection, ident)
    if payload.get('source_ref'):
        kind, sep, ident = payload['source_ref'].partition(':')
        if not sep or not ident.isascii() or not ident.isdigit() or ident != str(int(ident)) or kind not in ('goods_receipt', 'goods_issue', 'estimate'):
            raise HTTPException(status_code=403, detail='Неизвестное основание строки платежа')
        require_based_on(connection, {'based_on_type': kind, 'based_on_id': int(ident)})


def require_schedule(connection, schedule):
    if organizations(connection) is None:
        return
    require_contract(connection, schedule.get('contract_id'))
    for line in schedule['lines']:
        require_payment_links(connection, line, group=bool(line.get('is_group')))


def add_schedule_scope(connection, conditions, params, alias='ps'):
    if organizations(connection) is not None:
        conditions.append(_schedule_sql(connection, alias, params))


def rollback_on_error(function):
    @wraps(function)
    def guarded(connection, *args, **kwargs):
        try:
            return function(connection, *args, **kwargs)
        except Exception:
            connection.rollback()
            raise
    return guarded


def read_organization_ids(connection, user_id):
    row = connection.execute('SELECT organizations_restricted FROM users WHERE id = ?', (user_id,)).fetchone()
    if row is None or not row['organizations_restricted']:
        return None
    return [row['organization_id'] for row in connection.execute(
        'SELECT organization_id FROM user_organizations WHERE user_id = ? ORDER BY organization_id', (user_id,)).fetchall()]


def ensure_schema(connection, ensure_column):
    ensure_column(connection, 'users', 'organizations_restricted', 'INTEGER NOT NULL DEFAULT 0')
    connection.executescript('''CREATE TABLE IF NOT EXISTS user_organizations (
        user_id INTEGER NOT NULL REFERENCES users(id),
        organization_id INTEGER NOT NULL REFERENCES organizations(id),
        PRIMARY KEY (user_id, organization_id)
    );''')
