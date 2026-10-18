import { expect, test, type Page } from '@playwright/test'

async function setup(page: Page, kind: 'sale' | 'purchase', role = 'admin') {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'step01-price-adjustments'))
  const source = { id: 41, number: 'SOURCE-41', date: '2026-10-01', organization_name: 'Organization A',
    counterparty_name: 'Partner X', contract_number: 'AX1', warehouse_name: 'Warehouse A',
    lines: [{ id: 91, line_number: 1, name: 'Product', material_id: 51, unit_id: 1,
      quantity: kind === 'sale' ? 3 : 10, price_without_vat: kind === 'sale' ? 150 : 100,
      effective_price: kind === 'sale' ? 150 : 100, vat_rate: 0 }] }
  let adjustment: any = null
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (!path.startsWith('/api/')) { await route.continue(); return }
    if (path === '/api/auth/me') {
      await route.fulfill({ json: { id: 1, username: role, role, is_active: true } }); return
    }
    let data: any = []
    let status = 200
    if (path === '/api/goods/issues' || path === '/api/goods/receipts') data = [source]
    if (path.startsWith('/api/goods/price-adjustment-sources/')) data = source
    if (path === '/api/goods/price-adjustments' && method === 'POST') {
      const payload = route.request().postDataJSON()
      adjustment = { ...payload, id: 1, number: 'ADJ-1', source_number: source.number,
        is_posted: false, delta_without_vat: kind === 'sale' ? -30 : -100,
        delta_vat: 0, delta_with_vat: kind === 'sale' ? -30 : -100,
        lines: payload.lines.map((line: any) => ({ ...line, old_price: source.lines[0].effective_price,
          quantity: source.lines[0].quantity, vat_rate: 0, name: 'Product' })) }
      data = adjustment; status = 201
    }
    if (path === '/api/goods/price-adjustments/1' && method === 'PUT') {
      const payload = route.request().postDataJSON()
      adjustment = { ...adjustment, ...payload, lines: payload.lines.map((line: any) => ({ ...adjustment.lines[0], ...line })) }
    }
    if (path === '/api/goods/price-adjustments/1/post') adjustment.is_posted = true
    if (path === '/api/goods/price-adjustments/1/unpost') adjustment.is_posted = false
    if (path.startsWith('/api/goods/price-adjustments/1')) data = adjustment
    await route.fulfill({ status, json: { success: true, data, pagination: { page: 1, pages: 1, total: 1 } } })
  })
  await page.goto('/ctm/goods/price-adjustments/new')
  await page.getByLabel('Вид корректировки', { exact: true }).selectOption(kind)
  await page.getByLabel('Основание', { exact: true }).selectOption('41')
  await expect(page.getByText('Organization A · Partner X')).toBeVisible()
}

for (const kind of ['sale', 'purchase'] as const) {
  test(`${kind} price correction sends only new price and linked row, posts and reposts`, async ({ page }) => {
    await setup(page, kind)
    await page.getByRole('spinbutton', { name: 'Новая цена Product', exact: true }).fill(kind === 'sale' ? '140' : '90')
    const request = page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith('/api/goods/price-adjustments'))
    await page.getByRole('button', { name: 'Провести', exact: true }).click()
    expect((await request).postDataJSON()).toMatchObject({ kind, source_id: 41, lines: [{ source_line_id: 91, new_price: kind === 'sale' ? 140 : 90 }] })
    expect((await request).postDataJSON().lines[0]).not.toHaveProperty('quantity')
    await expect(page.getByRole('heading', { name: /ADJ-1 Проведена/ })).toBeVisible()
    await expect(page.getByRole('spinbutton', { name: 'Новая цена Product', exact: true })).toBeDisabled()
    await page.getByRole('button', { name: 'Отменить проведение', exact: true }).click()
    await expect(page.getByRole('heading', { name: /ADJ-1 Черновик/ })).toBeVisible()
    await page.getByRole('button', { name: 'Провести', exact: true }).click()
    await expect(page.getByRole('heading', { name: /ADJ-1 Проведена/ })).toBeVisible()
  })
}

test('unsupported consumed purchase explains rejection and preserves editable correction', async ({ page }) => {
  await setup(page, 'purchase')
  await page.route('**/api/goods/price-adjustments/1/post', route => route.fulfill({ status: 400, json: { detail: 'COST-005: необходим пересчет себестоимости' } }))
  await page.getByRole('spinbutton', { name: 'Новая цена Product', exact: true }).fill('90')
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('COST-005')
  await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
})

test('manager can prepare correction and cannot post it', async ({ page }) => {
  await setup(page, 'sale', 'manager')
  await expect(page.getByRole('button', { name: 'Провести', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
})

test('posting saved stale correction preserves baseline instead of automatically rebasing', async ({ page }) => {
  await setup(page, 'sale')
  await page.getByRole('spinbutton', { name: 'Новая цена Product', exact: true }).fill('140')
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page).toHaveURL(/price-adjustments\/1$/)
  const updates: string[] = []
  page.on('request', request => { if (request.method() === 'PUT') updates.push(request.url()) })
  await page.route('**/api/goods/price-adjustments/1/post', route => route.fulfill({ status: 400, json: { detail: 'Действующая цена изменилась. Пересохраните корректировку' } }))
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Действующая цена изменилась')
  expect(updates).toEqual([])
})
