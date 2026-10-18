"""API executor for the explicitly supported subset of the trade contract catalog."""
from decimal import Decimal
import json
from pathlib import Path


def execute_scenario(scenario, client, headers, connection):
    def request(method, url, status=200, **kwargs):
        response = client.request(method, url, headers=headers, **kwargs)
        assert response.status_code == status, f"{scenario['id']} {method} {url}: {response.text}"
        return response.json().get("data")

    def ref(kind, payload):
        return request("POST", f"/api/references/{kind}", json=payload)["id"]

    fixture_path = Path(__file__).resolve().parents[3] / "runner" / "trade_harness" / "scenarios" / "fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    organizations = {name: ref("organizations", {"name": f"Trade {name}"}) for name in fixture["organizations"]}
    counterparties = {name: ref("counterparties", {"name": f"Trade {name}"}) for name in fixture["counterparties"]}
    contract_axes = fixture["contracts"]
    contracts = {name: ref("contracts", {"number": name, "organization_id": organizations[org],
                 "counterparty_id": counterparties[cp], "vat_rate": fixture["vat_rate"], "payment_deferral_days": fixture["payment_deferral_days"]})
                 for name, (org, cp) in contract_axes.items()}
    warehouses = {name: ref("warehouses", {"name": name, "organization_id": organizations[org]})
                  for name, org in fixture["warehouses"].items()}
    unit_id = connection.execute("SELECT id FROM units WHERE name = 'pcs' LIMIT 1").fetchone()[0] if scenario['id'] in ('DIM-006', 'DIM-007', 'DIM-008', 'PUR-005', 'PUR-006', 'PUR-007', 'PUR-008', 'PUR-009', 'PUR-010') else connection.execute("SELECT id FROM units ORDER BY id LIMIT 1").fetchone()[0]
    material_id = ref("materials", {"name": "Trade goods", "code": "TRADE-HARNESS", "unit_id": unit_id})
    saved = {}
    analytics = {}
    movement_paths = {"transfer": "transfers", "return": "returns", "refund": "return-refunds", "adjustment": "price-adjustments", 'opening': 'opening-balances'}
    decimal = lambda value: Decimal(str(value))
    lifecycle_result = None

    def execute_procurement():
        ident = scenario['id']
        order_mode = ident in ('PUR-007', 'PUR-008')
        service = ident == 'PUR-009'
        if order_mode:
            request('PUT', f'/api/references/warehouses/{warehouses["A1"]}', json=dict(name='A1', organization_id=organizations['A'], order_receipt_enabled=True))
        row = dict(line_number=1, name='Transport' if service else 'Trade goods', line_type='service' if service else 'goods',
                   quantity=1 if service else 10, price_without_vat=500 if service else 100, vat_rate=0)
        if not service:
            row.update(material_id=material_id, unit_id=unit_id)
        order = request('POST', '/api/purchases/orders', 201, json=dict(date='2026-10-01', organization_id=organizations['A'],
            counterparty_id=counterparties['X'], contract_id=contracts['AX1'], warehouse_id=None if service else warehouses['A1'], lines=[row]))
        order = request('POST', f'/api/purchases/orders/{order["id"]}/post')

        def state():
            inventory = request('GET', '/api/goods/inventory/balances')
            debts = request('GET', '/api/settlements/balance', params={'organization_id': organizations['A']})
            return (sum(decimal(row['quantity_balance']) for row in inventory),
                    sum(decimal(row['sum_income'])-decimal(row['sum_expense']) for row in inventory),
                    sum(decimal(row['payable_balance']) for row in debts))

        def linked(kind, source, quantity, on_date='2026-10-02', **extra):
            doc = request('POST', '/api/purchases/'+kind, 201, json=dict(date=on_date, source_id=source['id'],
                lines=[dict(source_line_id=source['lines'][0]['id'], quantity=quantity, **extra)]))
            return request('POST', f'/api/purchases/{kind}/{doc["id"]}/post')

        def open_order():
            return request('GET', f'/api/purchases/orders/{order["id"]}')['lines'][0]

        assert state() == (0, 0, 0), 'Supplier order must not create stock or debt'
        if ident == 'PUR-010':
            payment = request('POST', '/api/payments/transactions', 201, json=dict(date='2026-10-01', direction='outgoing',
                category='supplier', amount=400, allow_advance=True, counterparty_id=counterparties['X'], contract_id=contracts['AX1']))
            request('POST', f'/api/payments/transactions/{payment["id"]}/post')
            params = dict(organization_id=organizations['A'], counterparty_id=counterparties['X'], contract_id=contracts['AX1'])
            initial = request('GET', '/api/settlements/balance', params=params)
            assert sum(decimal(row['supplier_advance']) for row in initial) == 400
            assert sum(decimal(row['payable_balance']) for row in initial) == 0
            invoice = linked('acquisitions', order, 10)
            final = request('GET', '/api/settlements/balance', params=params)
            moves = request('GET', f'/api/purchases/acquisitions/{invoice["id"]}/movements')
            assert sum(decimal(row['accrual_amount']) for row in moves['settlements']) == 1000
            facts = connection.execute('SELECT * FROM mutual_settlements_register WHERE contract_id = ?', (contracts['AX1'],)).fetchall()
            assert len(facts) == 2 and {row['recorder_type'] for row in facts} == {'payment_transaction', 'purchase_acquisition'}
            assert state()[:2] == (10, 1000)
            return dict(advance_remaining=sum(decimal(row['supplier_advance']) for row in final),
                        payable=sum(decimal(row['payable_balance']) for row in final))
        if ident in ('PUR-005', 'PUR-006'):
            linked('acquisitions', order, 4)
            first_open = open_order()['open_quantity']
            if ident == 'PUR-005':
                linked('acquisitions', order, 6, '2026-10-03')
                stock, cost, payable = state()
                assert cost == 1000
                return dict(open_after_first=first_open, open_final=open_order()['open_quantity'], stock_final=stock, payable_final=payable)
            cancellation = linked('cancellations', order, 6, '2026-10-03')
            assert request('GET', f'/api/purchases/cancellations/{cancellation["id"]}/movements')['inventory'] == []
            stock, cost, payable = state()
            assert cost == 400
            return dict(open_order=open_order()['open_quantity'], stock=stock, payable=payable)
        if ident == 'PUR-007':
            linked('receipt-orders', order, 10)
            physical, cost, payable = state()
            invoice = linked('acquisitions', order, 10, '2026-10-03')
            final_stock, final_cost, final_payable = state()
            assert final_cost == cost == 1000
            assert request('GET', f'/api/purchases/acquisitions/{invoice["id"]}/movements')['inventory'] == []
            assert connection.execute("SELECT SUM(quantity_income) FROM inventory_register").fetchone()[0] == 10
            return dict(physical_stock_after_order=physical, payable_after_order=payable, physical_stock_final=final_stock, payable_final=final_payable)
        if ident == 'PUR-008':
            received = linked('receipt-orders', order, 8)
            invoice = linked('acquisitions', order, 10)
            act = linked('discrepancies', invoice, 2, '2026-10-03', receipt_line_id=received['lines'][0]['id'])
            linked('quantity-adjustments', act, 2, '2026-10-04')
            stock, cost, payable = state()
            assert cost == 800 and open_order()['open_quantity'] == 0
            return dict(stock=stock, payable=payable, shortage=open_order()['shortage_quantity'])
        if ident == 'PUR-009':
            initial_qty = state()[0]
            invoice = linked('acquisitions', order, 1)
            stock, cost, payable = state()
            expenses = request('GET', '/api/purchases/expenses')
            assert len(expenses) == 1 and expenses[0]['recorder_id'] == invoice['id']
            assert cost == 0
            return dict(inventory_quantity_delta=stock-initial_qty, payable=payable, expense=sum(decimal(row['expense_amount']) for row in expenses))
        raise AssertionError('No procurement adapter for '+ident)

    def execute_sales():
        ident=scenario['id']
        service=ident=='SAL-009'
        mode=ident=='SAL-008'
        if not service:
            request('POST','/api/goods/receipts',201,json=dict(date='2026-10-01',organization_id=organizations['A'],
                counterparty_id=counterparties['X'],contract_id=contracts['AX1'],warehouse_id=warehouses['A1'],auto_schedule=False,
                lines=[dict(line_number=1,name='Trade goods',material_id=material_id,unit_id=unit_id,quantity=10,price_without_vat=100,vat_rate=0)]))
            receipt=connection.execute('SELECT id FROM goods_receipts ORDER BY id DESC LIMIT 1').fetchone()[0]
            request('POST',f'/api/goods/receipts/{receipt}/post',params={'auto_schedule':'false'})
        if mode:
            request('PUT',f'/api/references/warehouses/{warehouses["A1"]}',json=dict(name='A1',organization_id=organizations['A'],order_issue_enabled=True))
        def order(quantity,price):
            row=dict(line_number=1,name='Service' if service else 'Trade goods',line_type='service' if service else 'goods',quantity=quantity,price_without_vat=price,vat_rate=0)
            if not service:row.update(material_id=material_id,unit_id=unit_id)
            doc=request('POST','/api/sales/orders',201,json=dict(date='2026-10-02',organization_id=organizations['A'],counterparty_id=counterparties['X'],
                contract_id=contracts['AX1'],warehouse_id=None if service else warehouses['A1'],lines=[row]))
            return request('POST',f'/api/sales/orders/{doc["id"]}/post')
        def linked(kind,source,quantity,post=True):
            doc=request('POST',f'/api/sales/{kind}',201,json=dict(date='2026-10-03',source_id=source['id'],lines=[dict(source_line_id=source['lines'][0]['id'],quantity=quantity)]))
            return request('POST',f'/api/sales/{kind}/{doc["id"]}/post') if post else doc
        def state():
            stock=request('GET','/api/goods/inventory/balances')
            debt=request('GET','/api/settlements/balance',params=dict(organization_id=organizations['A'],counterparty_id=counterparties['X'],contract_id=contracts['AX1']))
            return sum(decimal(row['quantity_balance']) for row in stock),sum(decimal(row['receivable_balance']) for row in debt)
        def opened(source):
            return request('GET',f'/api/sales/orders/{source["id"]}')['lines'][0]['open_quantity']
        if ident in ('SAL-006','SAL-007'):
            source=order(6,150)
            linked('realizations',source,2)
            if ident=='SAL-006':
                first=opened(source)
                linked('realizations',source,4)
                stock,debt=state()
                return dict(open_after_first=first,stock_final=stock,receivable_final=debt)
            cancellation=linked('cancellations',source,4)
            moves=request('GET',f'/api/sales/cancellations/{cancellation["id"]}/movements')
            return dict(open_order=opened(source),released_reserve=sum(decimal(row['reserve_expense']) for row in moves['reservations']),receivable=state()[1])
        if ident=='SAL-008':
            source=order(3,150)
            finance=linked('realizations',source,3)
            linked('expense-orders',source,3)
            assert request('GET',f'/api/sales/realizations/{finance["id"]}/movements')['inventory']==[]
            stock,debt=state()
            return dict(stock_final=stock,receivable=debt,total_physical_expense=connection.execute('SELECT SUM(quantity_expense) FROM inventory_register').fetchone()[0])
        if ident=='SAL-009':
            before=state()[0]
            linked('realizations',order(1,500),1)
            stock,debt=state()
            return dict(stock_quantity_delta=stock-before,receivable=debt,revenue=sum(decimal(row['revenue_amount']) for row in request('GET','/api/sales/revenue')))
        if ident=='SAL-010':
            request('PUT',f'/api/references/contracts/{contracts["AX1"]}',json=dict(number='AX1',organization_id=organizations['A'],counterparty_id=counterparties['X'],credit_limit=1000,credit_limit_strict=True))
            linked('realizations',order(6,150),6)
            draft=linked('realizations',order(1,200),1,False)
            before=connection.execute('SELECT SUM(quantity_expense) FROM inventory_register').fetchone()[0]
            request('POST',f'/api/sales/realizations/{draft["id"]}/post',400)
            current=request('GET',f'/api/sales/realizations/{draft["id"]}')
            return dict(posting_rejected=not current['is_posted'],receivable=state()[1],
                new_stock_expense=decimal(connection.execute('SELECT SUM(quantity_expense) FROM inventory_register').fetchone()[0])-decimal(before))
        raise AssertionError('Missing sales adapter: '+ident)

    def execute_lifecycle():
        from api.goods_services import post_goods_issue
        from api.models.auth import UserInfo
        from api.tests.trade_lifecycle_support import FailAfterInventoryInsert, InjectedPostingFailure, competing_issue_requests

        def document(kind, quantity, price=100, org='A', post=True):
            contract = 'AX1' if org == 'A' else 'BX1'
            payload = dict(date='2026-10-01' if kind == 'receipts' else '2026-10-02',
                organization_id=organizations[org], counterparty_id=counterparties['X'],
                contract_id=contracts[contract], warehouse_id=warehouses[org+'1'], auto_schedule=False,
                lines=[dict(line_number=1, name='Trade goods', material_id=material_id, unit_id=unit_id, quantity=quantity,
                            price_without_vat=price, vat_rate=0)])
            doc = request('POST', f'/api/goods/{kind}', 201, json=payload)
            if post:
                request('POST', f'/api/goods/{kind}/{doc["id"]}/post?auto_schedule=false')
            return doc, payload

        def stock():
            return sum(decimal(row['quantity_balance']) for row in request('GET', '/api/goods/inventory/balances'))

        ident = scenario['id']
        if ident == 'LIFE-011':
            receipt, _ = document('receipts', 10, 100)
            source = request('GET', f'/api/goods/receipts/{receipt["id"]}')
            source_movements = request('GET', f'/api/goods/receipt/{receipt["id"]}/movements')
            copied = request('POST', f'/api/goods/receipts/{receipt["id"]}/copy', 201)
            copied = request('GET', f'/api/goods/receipts/{copied["id"]}')
            assert copied['id'] != source['id'] and copied['posted_at'] is None
            assert not ({row['id'] for row in source['lines']} & {row['id'] for row in copied['lines']})
            assert not ({row['uuid'] for row in source['lines']} & {row['uuid'] for row in copied['lines']})
            movements = request('GET', f'/api/goods/receipt/{copied["id"]}/movements')
            assert movements['inventory'] == movements['settlements'] == []
            assert request('GET', f'/api/goods/receipts/{source["id"]}') == source
            assert request('GET', f'/api/goods/receipt/{source["id"]}/movements') == source_movements
            inventory = request('GET', '/api/goods/inventory/balances')
            assert sum(decimal(row['sum_income'])-decimal(row['sum_expense']) for row in inventory) == 1000
            debts = request('GET', '/api/settlements/balance', params={'organization_id': organizations['A']})
            return dict(distinct_uuid=copied['uuid'] != source['uuid'], copy_posted=copied['is_posted'],
                        stock=stock(), payable=sum(decimal(row['payable_balance']) for row in debts))
        if ident == 'LIFE-005':
            receipt, payload = document('receipts', 10)
            payload['lines'][0]['price_without_vat'] = 200
            response = client.put(f'/api/goods/receipts/{receipt["id"]}', headers=headers, json=payload)
            inventory = request('GET', '/api/goods/inventory/balances')
            debts = request('GET', '/api/settlements/balance', params={'organization_id': organizations['A']})
            return dict(edit_rejected=response.status_code == 400,
                        stock_cost=sum(decimal(row['sum_income'])-decimal(row['sum_expense']) for row in inventory),
                        payable=sum(decimal(row['payable_balance']) for row in debts))
        if ident == 'LIFE-006':
            receipt, _ = document('receipts', 10)
            document('issues', 8)
            response = client.post(f'/api/goods/receipts/{receipt["id"]}/unpost', headers=headers)
            return dict(unpost_rejected=response.status_code == 400, stock=stock())
        if ident == 'LIFE-008':
            own, _ = document('receipts', 10, post=False)
            foreign, _ = document('receipts', 10, org='B', post=False)
            request('POST', '/api/users', 201, json=dict(username='life-viewer', password='test-password', role='viewer', organization_ids=[organizations['A']]))
            token = client.post('/api/auth/login', json=dict(username='life-viewer', password='test-password')).json()['access_token']
            viewer = {'Authorization': 'Bearer '+token}
            before = sum(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('inventory_register', 'mutual_settlements_register'))
            write = client.post(f'/api/goods/receipts/{own["id"]}/post', headers=viewer)
            read = client.get(f'/api/goods/receipts/{foreign["id"]}', headers=viewer)
            after = sum(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('inventory_register', 'mutual_settlements_register'))
            return dict(write_forbidden=write.status_code == 403, foreign_organization_read_forbidden=read.status_code == 403, register_delta=after-before)
        if ident == 'LIFE-009':
            document('receipts', 1)
            first, _ = document('issues', 1, post=False)
            second, _ = document('issues', 1, post=False)
            statuses = competing_issue_requests(first['id'], second['id'], headers)
            assert sorted(statuses) == [200, 400], statuses
            return dict(successful_posts=statuses.count(200), failed_posts=statuses.count(400), stock=stock())
        if ident == 'LIFE-010':
            document('receipts', 10)
            sale, _ = document('issues', 3, post=False)
            try:
                post_goods_issue(FailAfterInventoryInsert(connection), document_id=sale['id'],
                    user=UserInfo(id=1, username='admin', role='admin', is_active=True), auto_schedule=False)
            except InjectedPostingFailure:
                pass
            else:
                raise AssertionError('fault injection did not run')
            rows = sum(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE recorder_type = 'goods_issue' AND recorder_id = ?", (sale['id'],)).fetchone()[0]
                       for table in ('inventory_register', 'mutual_settlements_register'))
            debts = request('GET', '/api/settlements/balance', params={'organization_id': organizations['A']})
            return dict(document_posted=request('GET', f'/api/goods/issues/{sale["id"]}')['is_posted'], stock=stock(),
                        new_debt=sum(decimal(row['receivable_balance']) for row in debts), partial_register_rows=rows)
        raise AssertionError(f'No authored lifecycle executor for {ident}')

    def check(expected, stage):
        if 'dimensions' in expected:
            rows = request('GET', '/api/goods/inventory/balances')
            for key, target in expected['dimensions'].items():
                if key == 'stock_base_units':
                    actual = sum(decimal(row['quantity_balance']) for row in rows)
                elif key.startswith('opening_'):
                    inventory = request('GET', '/api/goods/inventory/turnover', params={'date_from': '2026-10-02', 'date_to': '2026-10-02'})
                    settlements = request('GET', '/api/settlements/turnover', params={'date_from': '2026-10-02', 'date_to': '2026-10-02'})
                    actual = sum(decimal(row[{'opening_qty': 'quantity_opening', 'opening_stock_cost': 'cost_opening'}[key]]) for row in inventory) if key in ('opening_qty', 'opening_stock_cost') else sum(decimal(row['payable_opening' if key == 'opening_payable' else 'receivable_opening']) for row in settlements)
                else:
                    characteristic, series = key.split('_')
                    selected = [row for row in rows if row['characteristic_id'] == analytics[characteristic] and row['series_id'] == analytics[series]]
                    assert len(selected) == 1, f'{stage}: missing or mixed analytic slice {key}'
                    actual = decimal(selected[0]['quantity_balance'])
                assert actual == decimal(target), f'{stage}: {key} differs'
        if "debts" in expected:
            rows = request("GET", "/api/settlements/balance")
            actual = {}
            for row in rows:
                axes = (row["organization_id"], row["counterparty_id"], row["contract_id"])
                assert axes not in actual, f"{stage}: duplicate settlement slice"
                actual[axes] = (decimal(row["payable_balance"]), decimal(row["receivable_balance"]))
            actual = {key: value for key, value in actual.items() if any(value)}
            target = {}
            for name, values in expected["debts"].items():
                org, cp = contract_axes[name]
                value = tuple(decimal(v) for v in values)
                if any(value):
                    target[(organizations[org], counterparties[cp], contracts[name])] = value
            assert actual == target, f"{stage}: debt slices differ"
        if "stock" in expected:
            rows = request("GET", "/api/goods/inventory/balances")
            actual = {}
            for row in rows:
                assert row["material_id"] == material_id
                assert row["object_id"] is None
                assert row["warehouse_id"] not in actual, f"{stage}: duplicate stock slice"
                actual[row["warehouse_id"]] = (decimal(row["quantity_balance"]),
                                                decimal(row["sum_income"]) - decimal(row["sum_expense"]))
            target = {warehouses[name]: tuple(decimal(v) for v in values)
                      for name, values in expected["stock"].items() if any(decimal(v) for v in values)}
            assert actual == target, f"{stage}: stock slices differ"
        if "advances" in expected:
            rows = request("GET", "/api/settlements/balance")
            actual = {(r["organization_id"], r["counterparty_id"], r["contract_id"]):
                      (decimal(r["supplier_advance"]), decimal(r["customer_advance"])) for r in rows
                      if r["supplier_advance"] or r["customer_advance"]}
            target = {}
            for name, values in expected["advances"].items():
                org, cp = contract_axes[name]
                if any(values):
                    target[(organizations[org], counterparties[cp], contracts[name])] = tuple(decimal(v) for v in values)
            assert actual == target, f"{stage}: advance slices differ"
        for name, counts in expected.get("movements", {}).items():
            kind, ident = saved[name]
            url = f"/api/payments/transactions/{ident}/movements" if kind == "payment" else f"/api/goods/{movement_paths.get(kind, kind)}/{ident}/movements"
            result = request("GET", url)
            for register, count in counts.items():
                assert len(result[register]) == count, f"{stage}: {name}/{register} movement count"
        if "financials" in expected:
            # Real posted source/return resources, independent of UI totals.
            sale = connection.execute("SELECT COALESCE(SUM(sum_without_vat), 0) FROM goods_issues WHERE is_posted = 1").fetchone()[0]
            cogs = connection.execute("SELECT COALESCE(SUM(l.inventory_cost), 0) FROM goods_issue_lines l JOIN goods_issues d ON d.id = l.issue_id WHERE d.is_posted = 1 AND l.marked_for_deletion = 0").fetchone()[0]
            returned = connection.execute("SELECT COALESCE(SUM(sum_without_vat), 0), COALESCE(SUM(inventory_cost), 0) FROM goods_returns WHERE kind = 'customer' AND is_posted = 1").fetchone()
            adjustment = connection.execute("SELECT COALESCE(SUM(delta_without_vat), 0) FROM goods_price_adjustments WHERE kind = 'sale' AND is_posted = 1").fetchone()[0]
            actual = {"net_revenue": decimal(sale) - decimal(returned[0]) + decimal(adjustment), "net_cogs": decimal(cogs) - decimal(returned[1]), "revenue_delta": decimal(adjustment)}
            for field, target in expected["financials"].items():
                assert actual[field] == decimal(target), f"{stage}: {field} differs"
        if "turnover" in expected:
            spec = expected["turnover"]
            rows = request("GET", "/api/settlements/turnover", params={
                "date_from": spec["from"], "date_to": spec["to"], "contract_id": contracts[spec["contract"]],
            })
            assert len(rows) == 1
            for field, value in spec["values"].items():
                assert decimal(rows[0][field]) == decimal(value), f"{stage}: turnover {field}"

    for index, step in enumerate(scenario["steps"]):
        op = step["op"]
        if op == 'business_contract':
            if lifecycle_result is None:
                lifecycle_result = execute_sales() if scenario['id'] in ('SAL-006','SAL-007','SAL-008','SAL-009','SAL-010') else execute_procurement() if scenario['id'] in ('PUR-005', 'PUR-006', 'PUR-007', 'PUR-008', 'PUR-009', 'PUR-010') else execute_lifecycle()
        elif op == 'observe':
            assert lifecycle_result is not None
            assert lifecycle_result == step['expect'], (lifecycle_result, step['expect'])
            continue
        elif op == 'reference':
            payload = {'name': step['name'], 'material_id': material_id}
            if 'factor' in step:
                payload['factor'] = step['factor']
            if 'characteristic' in step:
                payload['characteristic_id'] = analytics[step['characteristic']]
            analytics[step['ref']] = ref(step['kind'], payload)
        elif op in ("receipt", "issue", "payment", "transfer", "return", "refund", "adjustment", 'opening'):
            contract = step.get("contract", "AX1")
            org, cp = contract_axes[contract]
            org, cp = step.get("organization", org), step.get("counterparty", cp)
            common = {"number": f"{scenario['id']}-{index}", "date": step.get("date", "2026-10-02")}
            if op == 'opening':
                payload = {**common, 'organization_id': organizations[org],
                    'inventory': [{'warehouse_id': warehouses[step.get('warehouse', org+'1')], 'material_id': material_id,
                                   'unit_id': unit_id, 'quantity': step['quantity'], 'cost': step['cost']}],
                    'settlements': [{'counterparty_id': counterparties[cp], 'contract_id': contracts[contract], 'direction': direction, 'amount': step[direction]}
                                    for direction in ('payable', 'receivable')]}
                collection = '/api/goods/opening-balances'
            elif op == "adjustment":
                source_kind, source_id = saved[step["source"]]
                source = request("GET", f"/api/goods/{'issues' if source_kind == 'issue' else 'receipts'}/{source_id}")
                payload = {**common, "kind": "sale" if source_kind == "issue" else "purchase", "source_id": source_id,
                           "lines": [{"source_line_id": source["lines"][0]["id"], "new_price": step["price"]}]}
                collection = "/api/goods/price-adjustments"
            elif op == "return":
                source_kind, source_id = saved[step["source"]]
                source = request("GET", f"/api/goods/{'issues' if source_kind == 'issue' else 'receipts'}/{source_id}")
                payload = {**common, "kind": "customer" if source_kind == "issue" else "supplier", "source_id": source_id,
                           "lines": [{"source_line_id": source["lines"][0]["id"], "quantity": step["quantity"]}]}
                collection = "/api/goods/returns"
            elif op == "refund":
                payload = {**common, "return_id": saved[step["source"]][1], "amount": step["amount"]}
                collection = "/api/goods/return-refunds"
            elif op == "payment":
                payload = {**common, "counterparty_id": counterparties[cp], "contract_id": contracts[contract],
                           "direction": step["direction"], "amount": step["amount"], "category": "other",
                           "allow_advance": step.get("allow_advance", False)}
                collection = "/api/payments/transactions"
            elif op == "transfer":
                payload = {**common, "organization_id": organizations[step.get("organization", "A")],
                           "source_warehouse_id": warehouses[step.get("source", "A1")],
                           "destination_warehouse_id": warehouses[step.get("destination", "A2")],
                           "lines": [{"line_number": 1, "material_id": material_id, "unit_id": unit_id,
                                      "quantity": step["quantity"]}]}
                collection = "/api/goods/transfers"
            else:
                payload = {**common, "organization_id": organizations[org], "counterparty_id": counterparties[cp],
                           "contract_id": contracts[contract], "warehouse_id": warehouses[step.get("warehouse", org + "1")],
                           "auto_schedule": False, "lines": [{"line_number": 1, "material_id": material_id,
                           "unit_id": unit_id, "name": "Trade goods", "quantity": step["quantity"],
                           "price_without_vat": step.get("price", 100), "vat_rate": step.get("vat", 20)}]}
                collection = "/api/goods/" + ("receipts" if op == "receipt" else "issues")
            if op in ('receipt', 'issue', 'transfer'):
                for key in ('package', 'characteristic', 'series'):
                    if key in step:
                        payload['lines'][0][key+'_id'] = analytics[step[key]]
            created = request("POST", collection, status=step.get("create_status", 201), json=payload)
            if step.get("create_status", 201) != 201:
                if "expect" in step:
                    check(step["expect"], f"{scenario['id']} step {index + 1}")
                continue
            saved[step["ref"]] = (op, created["id"])
            if step.get("post", True):
                request("POST", f"{collection}/{created['id']}/post", status=step.get("post_status", 200),
                        params={"auto_schedule": "false"})
        elif op in ("post", "unpost", "delete"):
            kind, ident = saved[step["ref"]]
            collection = {"receipt": "/api/goods/receipts", "issue": "/api/goods/issues",
                          "transfer": "/api/goods/transfers", "payment": "/api/payments/transactions", "return": "/api/goods/returns", "refund": "/api/goods/return-refunds", "adjustment": "/api/goods/price-adjustments", 'opening': '/api/goods/opening-balances'}[kind]
            request("DELETE" if op == "delete" else "POST", f"{collection}/{ident}" + ("" if op == "delete" else f"/{op}"),
                    status=step.get("status", 200), params={"auto_schedule": "false"})
        elif op != "assert":
            raise AssertionError(f"No API executor for {op}")
        if "expect" in step:
            check(step["expect"], f"{scenario['id']} step {index + 1}")
