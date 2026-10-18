import { expect, test, type Page } from '@playwright/test'

async function setup(page: Page, options: { role?: string; mode?: string; draftOrder?: boolean; invoiceDraft?: boolean; reject?: boolean; mixed?: boolean; lateReceipt?: boolean } = {}) {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'purchases-test'))
  const rootLine = { id: 101, line_number: 1, line_type: 'goods', order_line_id: 101, name: 'Product T', material_id: 51, unit_id: 1, unit: 'pcs',
    quantity: 10, price_without_vat: 100, vat_rate: 20, sum_without_vat: 1000, vat_amount: 200, sum_with_vat: 1200,
    object_id: 32, package_id: 3, package_name: 'Box 5', characteristic_id: 4, characteristic_name: 'Red', series_id: 5, series_name: 'Batch',
    conversion_factor: 5, base_quantity: 50, base_unit_id: 1, drawing_code: 'D-1', note: 'Original note',
    received_quantity: 4, financial_quantity: 4, cancelled_quantity: 0, shortage_quantity: 0, open_quantity: 6 }
  const order = { id: 1, uuid: 'order-1', kind: 'orders', number: 'ORDER-1', date: '2026-10-01', organization_id: 10, organization_name: 'Organization A',
    counterparty_id: 20, counterparty_name: 'Partner X', contract_id: 21, contract_number: 'AX1', warehouse_id: 2, warehouse_name: 'Warehouse A',
    object_id: 31, estimate_id: 41, description: 'Original description', receipt_mode: options.mode ?? 'direct',
    is_posted: !options.draftOrder, posted_at: options.draftOrder ? null : '2026-10-01T10:00:00+00:00', lines: [rootLine] }
  const serviceLine = { ...rootLine, id: 501, order_line_id: 501, line_type: 'service', name: 'Transport', quantity: 1, price_without_vat: 500, vat_rate: 0,
    material_id: null, unit_id: null, package_id: null, characteristic_id: null, series_id: null, base_unit_id: null, conversion_factor: 1, base_quantity: 0 }
  const serviceOrder = { ...order, id: 5, number: 'SERVICE-ORDER', warehouse_id: null, receipt_mode: 'direct', lines: [serviceLine] }
  if (options.mixed) order.lines.push(serviceLine as any)
  const invoice = { ...order, id: 2, kind: 'acquisitions', number: 'INV-2', source_id: 1, order_id: 1, is_posted: !options.invoiceDraft,
    lines: [{ ...rootLine, id: 201, source_line_id: 101 }] }
  const physical = { ...order, id: 3, kind: 'receipt-orders', number: 'REC-3', order_id: 1, source_id: 1, receipt_mode: 'order',
    lines: [{ ...rootLine, id: 301, source_line_id: 101, quantity: 8 }] }
  const serviceInvoice = { ...serviceOrder, id: 4, kind: 'acquisitions', number: 'SERVICE-INV', order_id: 5, source_id: 5,
    lines: [{ ...serviceLine, id: 401, source_line_id: 501 }] }
  const documents: Record<number, any> = { 1: order, 2: invoice, 3: physical, 4: serviceInvoice, 5: serviceOrder }
  const writes: { method: string; path: string; body: any }[] = []
  let nextId = 8
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    if (!path.startsWith('/api/')) { await route.continue(); return }
    if (path === '/api/auth/me') { await route.fulfill({ json: { id: 1, username: 'buyer', role: options.role ?? 'admin', is_active: true, organization_ids: [10] } }); return }
    const body = route.request().postDataJSON()
    if (method !== 'GET') writes.push({ method, path, body })
    let data: any = []
    if (path === '/api/references/organizations') data = [{ id: 10, name: 'Organization A' }]
    if (path === '/api/references/counterparties') data = [{ id: 20, name: 'Partner X' }]
    if (path === '/api/references/contracts') data = [{ id: 21, number: 'AX1' }]
    if (path === '/api/purchases/expenses') data = [{ id: 1, period: '2026-10-02', name: 'Transport', contract_id: 21, expense_amount: 500, vat_amount: 0 }]
    const match = path.match(/^\/api\/purchases\/([^/]+)(?:\/(\d+))?(?:\/(post|unpost|movements))?$/)
    if (match) {
      const [, kind, idText, action] = match, id = Number(idText)
      if (options.lateReceipt && kind === 'receipt-orders' && !idText && method === 'GET') {
        const requestedPage = Number(new URL(route.request().url()).searchParams.get('page') ?? 1)
        await route.fulfill({ json: { success: true, data: requestedPage === 2 ? [physical] :
          Array.from({ length: 100 }, (_, i) => ({ ...physical, id: 1000+i, order_id: 1000+i })),
          pagination: { page: requestedPage, page_size: 100, pages: 2, total: 101 } } }); return
      }
      if (id === 99) { await route.fulfill({ status: 403, json: { detail: 'Нет доступа к организации документа' } }); return }
      if (!idText && method === 'GET') data = Object.values(documents).filter(doc => doc.kind === kind)
      if (!idText && method === 'POST') {
        if (options.reject) { await route.fulfill({ status: 400, json: { detail: 'Количество превышает остаток строки основания/заказа' } }); return }
        const ident = nextId++, source = documents[body.source_id]
        data = { ...(source ?? order), ...body, id: ident, kind, number: 'NEW-'+ident, is_posted: false, posted_at: null,
          order_id: source ? (source.order_id ?? source.id) : null,
          lines: body.lines.map((line: any, index: number) => ({ ...(source?.lines.find((row: any) => row.id === line.source_line_id) ?? rootLine), ...line, id: ident*100+index })) }
        documents[ident] = data
        await route.fulfill({ status: 201, json: { success: true, data } }); return
      }
      if (idText && method === 'PUT') { documents[id] = { ...documents[id], ...body }; data = documents[id] }
      if (idText && method === 'GET') data = documents[id]
      if (action === 'post' || action === 'unpost') { documents[id].is_posted = action === 'post'; data = documents[id] }
      if (action === 'movements') data = { inventory: kind === 'receipt-orders' ? [{ line_number: 1, quantity_income: 10, quantity_expense: 0, sum_income: 1000, sum_expense: 0 }] : [],
        settlements: kind === 'acquisitions' ? [{ line_number: 1, accrual_amount: 500, payment_amount: 0 }] : [],
        expenses: id === 4 ? [{ id: 1, name: 'Transport', expense_amount: 500, vat_amount: 0 }] : [] }
    }
    await route.fulfill({ json: { success: true, data, pagination: { page: 1, page_size: 100, pages: 1, total: Array.isArray(data) ? data.length : 1 } } })
  })
  return { writes }
}

test('manager edits goods order without losing source analytics, VAT, packaging or line details', async ({ page }) => {
  const { writes } = await setup(page, { role: 'manager', draftOrder: true })
  await page.goto('/ctm/purchases/orders/1')
  await expect(page.locator('.stock-dimensions:visible')).toContainText('Базовое количество: 50')
  await page.locator('.goods-lines-editor:visible input[type=number]').first().fill('2')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Сохранено')
  expect(writes[0].body).toMatchObject({ organization_id: 10, counterparty_id: 20, contract_id: 21, warehouse_id: 2, object_id: 31, estimate_id: 41 })
  expect(writes[0].body.lines[0]).toMatchObject({ line_type: 'goods', quantity: 2, price_without_vat: 100, vat_rate: 20, unit_id: 1,
    object_id: 32, package_id: 3, characteristic_id: 4, series_id: 5, drawing_code: 'D-1', note: 'Original note' })
  expect(writes[0].body.lines[0]).not.toHaveProperty('id')
  await expect(page.getByRole('button', { name: 'Согласовать', exact: true })).toHaveCount(0)
})

test('pure service order sends explicit service quantity and price without stock material', async ({ page }) => {
  const { writes } = await setup(page, { role: 'manager' })
  await page.goto('/ctm/purchases/orders/new')
  for (const [label, name] of [['Организация', 'Organization A'], ['Контрагент', 'Partner X'], ['Договор', 'AX1']]) {
    await page.locator('fieldset > label').filter({ hasText: label }).locator('.ref-input-field').click()
    await page.getByRole('button', { name, exact: true }).click()
  }
  await page.getByRole('button', { name: '+ Услуга', exact: true }).click()
  await page.getByLabel('Услуга', { exact: true }).fill('Transport')
  await page.getByLabel('Цена услуги без НДС', { exact: true }).fill('500')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/\/purchases\/orders\/8$/)
  expect(writes[0].body.lines).toEqual([{ line_number: 1, line_type: 'service', name: 'Transport', quantity: 1, price_without_vat: 500, vat_rate: 0 }])
  expect(writes[0].body.warehouse_id).toBeNull()
})

test('partial acquisition defaults to unbilled order quantity and posts its own saved draft', async ({ page }) => {
  const { writes } = await setup(page)
  await page.goto('/ctm/purchases/acquisitions/new?source=1')
  await expect(page.getByLabel('Количество строки 1', { exact: true })).toHaveValue('6')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/\/purchases\/acquisitions\/8$/)
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Отменить проведение', exact: true })).toBeVisible()
  expect(writes.map(row => [row.method, row.path])).toEqual([['POST', '/api/purchases/acquisitions'], ['POST', '/api/purchases/acquisitions/8/post']])
  expect(writes[0].body.lines).toEqual([{ source_line_id: 101, quantity: 6 }])
  expect(writes[0].body).not.toHaveProperty('organization_id')
})

test('receipt order describes physical-only receipt and shows no invoice debt movement', async ({ page }) => {
  await setup(page, { mode: 'order' })
  await page.goto('/ctm/purchases/receipt-orders/3')
  await expect(page.getByText('Ордер отражает физическое количество по цене согласованного заказа.', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Движения', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'Приход', exact: true })).toBeVisible()
  await expect(page.getByText('Начисление долга:', { exact: false })).toHaveCount(0)
})

test('discrepancy links invoice and exact physical line, then creates a separate quantity adjustment', async ({ page }) => {
  const { writes } = await setup(page, { mode: 'order' })
  await page.goto('/ctm/purchases/discrepancies/new?source=2')
  await page.getByLabel('Количество строки 1', { exact: true }).fill('2')
  await page.getByLabel('Строка ордера 1', { exact: true }).selectOption('301')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/\/purchases\/discrepancies\/8$/)
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await page.getByRole('link', { name: 'Корректировки количества', exact: true }).click()
  await expect(page.locator('.workspace-pane:visible').getByLabel('Количество строки 1', { exact: true })).toHaveValue('2')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/\/purchases\/quantity-adjustments\/9$/)
  expect(writes[0].body.lines).toEqual([{ source_line_id: 201, quantity: 2, receipt_line_id: 301 }])
  expect(writes[2].body).toMatchObject({ source_id: 8, lines: [{ source_line_id: 800, quantity: 2 }] })
})

test('service acquisition shows actual expense separately from debt and physical stock', async ({ page }) => {
  await setup(page, { role: 'viewer' })
  await page.goto('/ctm/purchases/acquisitions/4')
  await page.getByRole('button', { name: 'Движения', exact: true }).click()
  await expect(page.getByText('Transport · Расход без НДС: 500', { exact: true })).toBeVisible()
  await expect(page.getByText('Начисление долга: 500', { exact: true })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Приход', exact: true })).toHaveCount(0)
})

for (const role of ['viewer', 'manager']) {
  test(`${role} cannot post acquisitions from the form`, async ({ page }) => {
    const { writes } = await setup(page, { role, invoiceDraft: true })
    await page.goto('/ctm/purchases/acquisitions/2')
    await expect(page.getByLabel('Количество строки 1', { exact: true })).toHaveValue('10')
    await expect(page.getByRole('button', { name: 'Провести', exact: true })).toHaveCount(0)
    if (role === 'viewer') {
      await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toHaveCount(0)
      await expect(page.getByLabel('Количество строки 1', { exact: true })).toBeDisabled()
    }
    expect(writes).toEqual([])
  })
}

test('quantity rejection keeps entered source and quantity available for correction', async ({ page }) => {
  await setup(page, { reject: true })
  await page.goto('/ctm/purchases/acquisitions/new?source=1')
  await page.getByLabel('Количество строки 1', { exact: true }).fill('11')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Количество превышает остаток строки основания/заказа')
  await expect(page.getByLabel('Количество строки 1', { exact: true })).toHaveValue('11')
  await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
})

test('foreign source stays hidden when server denies access', async ({ page }) => {
  await setup(page, { role: 'manager' })
  await page.goto('/ctm/purchases/orders/99')
  await expect(page.getByRole('alert')).toHaveText('Нет доступа к организации документа')
  await expect(page.locator('.goods-lines-table tbody')).not.toContainText('Product T')
})

test('mixed order excludes service from physical receipt by default', async ({ page }) => {
  const { writes } = await setup(page, { mode: 'order', mixed: true })
  await page.goto('/ctm/purchases/receipt-orders/new?source=1')
  await expect(page.getByLabel('Количество строки 2', { exact: true })).toHaveValue('0')
  await expect(page.getByLabel('Количество строки 2', { exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/\/purchases\/receipt-orders\/8$/)
  expect(writes[0].body.lines).toEqual([{ source_line_id: 101, quantity: 6 }])
})

test('discrepancy can select its physical batch beyond the first receipt page', async ({ page }) => {
  const { writes } = await setup(page, { mode: 'order', lateReceipt: true })
  await page.goto('/ctm/purchases/discrepancies/new?source=2')
  const picker = page.getByLabel('Строка ордера 1', { exact: true })
  await expect(picker.locator('option[value="301"]')).toHaveCount(1)
  await picker.selectOption('301')
  await page.getByLabel('Количество строки 1', { exact: true }).fill('2')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/\/purchases\/discrepancies\/8$/)
  expect(writes[0].body.lines).toEqual([{ source_line_id: 201, quantity: 2, receipt_line_id: 301 }])
})
