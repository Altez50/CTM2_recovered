import { test, expect, type Page } from '@playwright/test'

async function setup(page: Page, options: { role?: string; mode?: string; mixed?: boolean; draft?: boolean; reject?: boolean } = {}) {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'sales-test'))
  const goods = { id: 101, order_line_id: 101, line_number: 1, line_type: 'goods', name: 'Product S', material_id: 51, unit_id: 1, quantity: 6,
    price_without_vat: 150, vat_rate: 0, sum_without_vat: 900, vat_amount: 0, sum_with_vat: 900, conversion_factor: 5, base_quantity: 30, base_unit_id: 1,
    package_id: 3, package_name: 'Box 5', characteristic_id: 4, characteristic_name: 'Red', series_id: 5, series_name: 'Batch', object_id: 32,
    drawing_code: 'D-1', note: 'Original', shipped_quantity: 2, financial_quantity: 2, cancelled_quantity: 0, open_quantity: 4, reserved_quantity: 4 }
  const service = { ...goods, id: 102, order_line_id: 102, line_number: 2, line_type: 'service', name: 'Service', quantity: 1, price_without_vat: 500,
    material_id: null, package_id: null, characteristic_id: null, series_id: null, base_quantity: 0 }
  const order = { id: 1, uuid: 'sale-1', kind: 'orders', number: 'ORDER-S', date: '2026-10-02', organization_id: 10, organization_name: 'Organization A',
    counterparty_id: 20, counterparty_name: 'Partner X', contract_id: 21, contract_number: 'AX1', warehouse_id: 2, warehouse_name: 'Warehouse A',
    object_id: 31, estimate_id: 41, issue_mode: options.mode ?? 'direct', is_posted: !options.draft, posted_at: null, lines: options.mixed ? [goods, service] : [goods] }
  const documents: Record<number, any> = { 1: order, 2: { ...order, id: 2, kind: 'realizations', number: 'SALE-2', source_id: 1, order_id: 1,
    is_posted: !options.reject, lines: [{ ...goods, id: 201, source_line_id: 101, quantity: 2 }] },
    3: { ...order, id: 3, kind: 'expense-orders', number: 'ISSUE-3', source_id: 1, order_id: 1, issue_mode: 'order', lines: [{ ...goods, id: 301, source_line_id: 101, quantity: 2 }] } }
  const writes: { path: string; body: any }[] = []
  await page.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname, method = req.method(), body = req.postDataJSON()
    if (!path.startsWith('/api/')) { await route.continue(); return }
    if (path === '/api/auth/me') { await route.fulfill({ json: { id: 1, username: 'seller', role: options.role ?? 'admin', is_active: true, organization_ids: [10] } }); return }
    if (method !== 'GET') writes.push({ path, body })
    let data: any = []
    if (path === '/api/references/organizations') data = [{ id: 10, name: 'Organization A' }]
    if (path === '/api/references/counterparties') data = [{ id: 20, name: 'Partner X' }]
    if (path === '/api/references/contracts') data = [{ id: 21, number: 'AX1' }]
    const match = path.match(/^\/api\/sales\/([^/]+)(?:\/(\d+))?(?:\/(post|unpost|movements))?$/)
    if (match) {
      const [, kind, idText, action] = match, id = Number(idText)
      if (id === 99) { await route.fulfill({ status: 403, json: { detail: 'Нет доступа к организации документа' } }); return }
      if (options.reject && action === 'post') { await route.fulfill({ status: 400, json: { detail: 'Превышен строгий кредитный лимит договора' } }); return }
      if (!idText && method === 'GET') data = Object.values(documents).filter(doc => doc.kind === kind)
      if (!idText && method === 'POST') {
        data = { ...order, ...body, id: 8, kind, number: 'NEW-8', is_posted: false,
          lines: body.lines.map((row: any, index: number) => ({ ...goods, ...row, id: 800+index })) }
        documents[8] = data
        await route.fulfill({ status: 201, json: { success: true, data } }); return
      }
      if (idText && method === 'GET') data = documents[id]
      if (method === 'PUT') { documents[id] = { ...documents[id], ...body }; data = documents[id] }
      if (action === 'post' || action === 'unpost') { documents[id].is_posted = action === 'post'; data = documents[id] }
      if (action === 'movements') data = { inventory: kind === 'expense-orders' ? [{ line_number: 1, quantity_income: 0, quantity_expense: 2, sum_income: 0, sum_expense: 200 }] : [],
        settlements: [], reservations: [{ line_number: 1, reserve_income: kind === 'orders' ? 6 : 0, reserve_expense: kind === 'orders' ? 0 : 2 }], revenue: [] }
    }
    await route.fulfill({ json: { success: true, data, pagination: { page: 1, pages: 1, page_size: 100, total: Array.isArray(data) ? data.length : 1 } } })
  })
  return { writes }
}

test('sales order keeps VAT, packaging, series and line object while manager edits', async ({ page }) => {
  const { writes } = await setup(page, { role: 'manager', draft: true })
  await page.goto('/ctm/sales/orders/1')
  await expect(page.locator('.stock-dimensions:visible')).toContainText('Базовое количество: 30')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Сохранено')
  expect(writes[0].body.lines[0]).toMatchObject({ material_id: 51, quantity: 6, vat_rate: 0, package_id: 3, characteristic_id: 4, series_id: 5, object_id: 32 })
  await expect(page.getByRole('button', { name: 'Подтвердить', exact: true })).toHaveCount(0)
})

test('partial realization uses remaining unbilled quantity and exact source line', async ({ page }) => {
  const { writes } = await setup(page)
  await page.goto('/ctm/sales/realizations/new?source=1')
  await expect(page.getByLabel('Количество строки 1', { exact: true })).toHaveValue('4')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/\/sales\/realizations\/8$/)
  expect(writes[0].body.lines).toEqual([{ source_line_id: 101, quantity: 4 }])
  expect(writes[0].body).not.toHaveProperty('organization_id')
})

test('expense order excludes mixed service and displays physical cost and release', async ({ page }) => {
  const { writes } = await setup(page, { mode: 'order', mixed: true })
  await page.goto('/ctm/sales/expense-orders/new?source=1')
  await expect(page.getByLabel('Количество строки 2', { exact: true })).toHaveValue('0')
  await expect(page.getByLabel('Количество строки 2', { exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/\/sales\/expense-orders\/8$/)
  expect(writes[0].body.lines).toEqual([{ source_line_id: 101, quantity: 4 }])
  await page.getByRole('button', { name: 'Движения', exact: true }).click()
  await expect(page.getByText('Резерв: 0 · Освобождено: 2', { exact: true })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Стоимость расхода', exact: true })).toBeVisible()
})

test('credit rejection keeps saved draft available and shows server reason', async ({ page }) => {
  await setup(page, { reject: true })
  await page.goto('/ctm/sales/realizations/2')
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Превышен строгий кредитный лимит договора')
  await expect(page.getByRole('button', { name: 'Провести', exact: true })).toBeEnabled()
})

for (const role of ['viewer', 'manager']) {
  test(`${role} cannot post sales from form`, async ({ page }) => {
    await setup(page, { role, reject: true })
    await page.goto('/ctm/sales/realizations/2')
    await expect(page.getByLabel('Количество строки 1', { exact: true })).toHaveValue('2')
    await expect(page.getByRole('button', { name: 'Провести', exact: true })).toHaveCount(0)
    if (role === 'viewer') await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toHaveCount(0)
  })
}

test('foreign sales source is denied and cannot become editable', async ({ page }) => {
  await setup(page, { role: 'manager' })
  await page.goto('/ctm/sales/orders/99')
  await expect(page.getByRole('alert')).toHaveText('Нет доступа к организации документа')
  await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
})

test('new service order sends explicit revenue service without a material', async ({ page }) => {
  const { writes } = await setup(page, { role: 'manager' })
  await page.goto('/ctm/sales/orders/new')
  for (const [label, name] of [['Организация', 'Organization A'], ['Контрагент', 'Partner X'], ['Договор', 'AX1']]) {
    await page.locator('fieldset > label').filter({ hasText: label }).locator('.ref-input-field').click()
    await page.getByRole('button', { name, exact: true }).click()
  }
  await page.getByRole('button', { name: '+ Услуга', exact: true }).click()
  await page.getByLabel('Услуга', { exact: true }).fill('Service')
  await page.getByLabel('Цена услуги без НДС', { exact: true }).fill('500')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/\/sales\/orders\/8$/)
  expect(writes[0].body.lines).toEqual([{ line_number: 1, line_type: 'service', name: 'Service', quantity: 1, price_without_vat: 500, vat_rate: 0 }])
})
