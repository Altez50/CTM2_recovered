import { expect, test, type Page } from '@playwright/test'

const inventory = { material_id: 51, material_name: 'Product T', unit_id: 1, unit_name: 'pcs', warehouse_id: 2,
  warehouse_name: 'Warehouse A', quantity: 2, cost: 2400, package_id: 3, package_name: 'Box 12', conversion_factor: 12,
  characteristic_id: 4, characteristic_name: 'Red', series_id: 5, series_name: 'S1', base_quantity: 24 }
const initial = { id: 1, number: 'OPEN-1', date: '2026-10-01', organization_id: 10, organization_name: 'Organization A',
  description: '', is_posted: false, inventory: [inventory], settlements: [
    { counterparty_id: 20, counterparty_name: 'Partner X', contract_id: 21, contract_number: 'AX1', direction: 'payable', amount: 1200 },
    { counterparty_id: 20, counterparty_name: 'Partner X', contract_id: 21, contract_number: 'AX1', direction: 'receivable', amount: 540 }] }

async function setup(page: Page, role = 'admin', rejectPost = false) {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'trade-dimensions'))
  let opening = structuredClone(initial)
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    if (!path.startsWith('/api/')) { await route.continue(); return }
    if (path === '/api/auth/me') { await route.fulfill({ json: { id: 1, username: role, role, is_active: true } }); return }
    let data: any = []
    if (path === '/api/references/material-packages') data = [{ id: 6, name: 'Box 6', material_id: 51, factor: 6 }]
    if (path === '/api/references/material-characteristics') data = [{ id: 7, name: 'Blue', material_id: 51 }]
    if (path === '/api/references/material-series') data = [{ id: 8, name: 'S2', material_id: 51, characteristic_id: 7 }]
    if (path === '/api/goods/opening-balances/1') {
      if (method === 'PUT') opening = { ...opening, ...route.request().postDataJSON() }
      data = opening
    }
    if (path === '/api/goods/opening-balances/1/post') {
      if (rejectPost) { await route.fulfill({ status: 400, json: { detail: 'COST-005: есть зависимые движения' } }); return }
      opening.is_posted = true; data = opening
    }
    if (path === '/api/goods/opening-balances/1/unpost') { opening.is_posted = false; data = opening }
    if (path === '/api/goods/receipts/1') data = { ...initial, warehouse_id: 2, counterparty_id: 20, contract_id: 21,
      lines: [{ ...inventory, id: 91, line_number: 1, name: 'Product T', price_without_vat: 1200, vat_rate: 0,
        sum_without_vat: 2400, vat_amount: 0, sum_with_vat: 2400 }] }
    if (path === '/api/goods/inventory/turnover') data = [{ warehouse_name: 'Warehouse A', material_name: 'Product T',
      characteristic_name: 'Red', series_name: 'S1', unit_name: 'pcs', quantity_opening: 10, cost_opening: 1000,
      quantity_income: 0, cost_income: 0, quantity_expense: 0, cost_expense: 0, quantity_closing: 10, cost_closing: 1000 }]
    await route.fulfill({ json: { success: true, data, pagination: { page: 1, pages: 1, total: Array.isArray(data) ? data.length : 1 } } })
  })
}

test('receipt preserves packaging and variants, changes base preview and exports their IDs', async ({ page }) => {
  await setup(page)
  await page.goto('/ctm/goods/receipts/1')
  const editor = page.locator('.stock-dimensions').first()
  await expect(editor).toContainText('Базовое количество: 24')
  await editor.locator('label').filter({ hasText: 'Упаковка' }).locator('.ref-input-field').click()
  await page.getByRole('button', { name: /Box 6.*1 = 6/ }).click()
  await expect(editor).toContainText('Базовое количество: 12')
  await editor.locator('label').filter({ hasText: 'Характеристика' }).locator('.ref-input-field').click()
  await page.getByRole('button', { name: 'Blue', exact: true }).click()
  await expect(editor.locator('label').filter({ hasText: 'Серия' })).not.toContainText('S1')
  await editor.locator('label').filter({ hasText: 'Серия' }).locator('.ref-input-field').click()
  await page.getByRole('button', { name: 'S2', exact: true }).click()
  const saved = page.waitForRequest(r => r.method() === 'PUT' && r.url().endsWith('/api/goods/receipts/1'))
  await page.locator('.document-toolbar').getByTitle('Сохранить', { exact: true }).click()
  expect((await saved).postDataJSON().lines[0]).toMatchObject({ quantity: 2, price_without_vat: 1200, vat_rate: 0,
    package_id: 6, characteristic_id: 7, series_id: 8, unit_id: 1 })
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Выгрузить в Excel', exact: true }).click()
  const file = await download
  expect(file.suggestedFilename()).toMatch(/\.xls$/)
})

test('editing a package from the line keeps its conversion snapshot in the preview', async ({ page }) => {
  await setup(page)
  await page.route('**/api/references/material-packages/3', async route => {
    const record = { id: 3, name: 'Box 12', material_id: 51, material_name: 'Product T', factor: 12,
      ...(route.request().method() === 'PUT' ? route.request().postDataJSON() : {}) }
    await route.fulfill({ json: { success: true, data: record } })
  })
  await page.goto('/ctm/goods/receipts/1')
  const editor = page.locator('.stock-dimensions').first()
  await expect(editor).toContainText('Базовое количество: 24')
  await editor.locator('label').filter({ hasText: 'Упаковка' }).getByRole('button', { name: 'Открыть карточку', exact: true }).click()
  const form = page.locator('.dialog form')
  await expect(form.getByLabel('Наименование', { exact: true })).toHaveValue('Box 12')
  await form.getByLabel('Наименование', { exact: true }).fill('Renamed box')
  await form.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(editor).toContainText('Renamed box')
  await expect(editor).toContainText('Базовое количество: 24')
})

test('opening balances save explicit stock/debt lines and post, cancel and repost', async ({ page }) => {
  await setup(page)
  await page.goto('/ctm/goods/opening-balances/1')
  await expect(page.getByRole('heading', { name: /OPEN-1.*Черновик/ })).toBeVisible()
  await expect(page.locator('.stock-dimensions')).toContainText('Базовое количество: 24')
  await page.getByLabel('Начальное количество', { exact: true }).fill('3')
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Сначала сохраните')
  const saved = page.waitForRequest(r => r.method() === 'PUT' && r.url().endsWith('/api/goods/opening-balances/1'))
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  const payload = (await saved).postDataJSON()
  expect(payload.inventory[0]).toEqual({ material_id: 51, warehouse_id: 2, unit_id: 1, object_id: null, quantity: 3, cost: 2400,
    package_id: 3, characteristic_id: 4, series_id: 5 })
  expect(payload.settlements.map((x: any) => [x.direction, x.amount])).toEqual([['payable', 1200], ['receivable', 540]])
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await expect(page.getByRole('heading', { name: /OPEN-1.*Проведен/ })).toBeVisible()
  await expect(page.getByLabel('Начальное количество', { exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Отменить проведение', exact: true }).click()
  await expect(page.getByRole('heading', { name: /OPEN-1.*Черновик/ })).toBeVisible()
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await expect(page.getByRole('heading', { name: /OPEN-1.*Проведен/ })).toBeVisible()
})

test('opening balance COST-005 failure stays editable', async ({ page }) => {
  await setup(page, 'admin', true)
  await page.goto('/ctm/goods/opening-balances/1')
  await expect(page.getByRole('heading', { name: /OPEN-1/ })).toBeVisible()
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('COST-005')
  await expect(page.getByLabel('Начальное количество', { exact: true })).toBeEnabled()
})

test('manager can edit opening balances but cannot post them', async ({ page }) => {
  await setup(page, 'manager')
  await page.goto('/ctm/goods/opening-balances/1')
  await expect(page.getByRole('heading', { name: /OPEN-1/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Провести', exact: true })).toHaveCount(0)
})

test('inventory turnover displays opening cost and separate characteristic/series and exports CSV', async ({ page }) => {
  await setup(page)
  await page.goto('/ctm/reports/inventory-turnover')
  await expect(page.getByRole('columnheader', { name: 'Входящая стоимость', exact: true })).toBeVisible()
  const row = page.getByRole('row').filter({ hasText: 'Product T' })
  await expect(row).toContainText('Red'); await expect(row).toContainText('S1')
  await expect(row).toContainText('1000')
  const request = page.waitForRequest(r => r.url().includes('/api/goods/inventory/turnover?'))
  await page.getByLabel('Начало периода', { exact: true }).fill('2026-10-02')
  await page.getByLabel('Окончание периода', { exact: true }).fill('2026-10-02')
  await page.getByRole('button', { name: 'Показать', exact: true }).click()
  expect((await request).url()).toContain('date_from=2026-10-02')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Выгрузить CSV', exact: true }).click()
  expect((await download).suggestedFilename()).toMatch(/\.csv$/)
})

for (const kind of ['material-packages', 'material-characteristics', 'material-series']) {
  test(`${kind} reference form saves an explicit material binding`, async ({ page }) => {
    await setup(page)
    await page.route('**/api/references/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/references/materials') {
        await route.fulfill({ json: { success: true, data: [{ id: 51, name: 'Product T', unit_id: 1 }], pagination: { pages: 1 } } }); return
      }
      if (path === `/api/references/${kind}` && route.request().method() === 'POST') {
        await route.fulfill({ json: { success: true, data: { id: 100, ...route.request().postDataJSON() } } }); return
      }
      await route.fallback()
    })
    await page.goto(`/ctm/references/${kind}`)
    await page.locator('.panel-body .toolbar').first().getByTitle('Добавить', { exact: true }).click()
    const form = page.locator('.dialog form')
    await form.getByLabel('Наименование', { exact: true }).fill('New reference')
    await form.locator('label.field').filter({ has: page.locator('.field-label', { hasText: /^Товар$/ }) }).locator('.ref-input-field').click()
    await page.getByRole('button', { name: 'Product T', exact: true }).click()
    if (kind === 'material-packages') await form.getByLabel('Базовых единиц в упаковке', { exact: true }).fill('12')
    if (kind === 'material-series') {
      await form.locator('label.field').filter({ has: page.locator('.field-label', { hasText: /^Характеристика$/ }) }).locator('.ref-input-field').click()
      await page.getByRole('button', { name: 'Blue', exact: true }).click()
    }
    const request = page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith(`/api/references/${kind}`))
    await form.getByTitle('Сохранить', { exact: true }).click()
    const payload = (await request).postDataJSON()
    expect(payload).toEqual({ name: 'New reference', material_id: 51,
      ...(kind === 'material-packages' ? { factor: 12 } : kind === 'material-series' ? { characteristic_id: 7 } : {}) })
  })
}
