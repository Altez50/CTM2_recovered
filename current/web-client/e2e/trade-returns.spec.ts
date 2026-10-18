import { expect, test, type Page } from '@playwright/test'

async function setup(page: Page, kind: 'customer' | 'supplier') {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'trade-returns'))
  const source = { id: 41, number: 'SOURCE-41', date: '2026-10-01', organization_id: 10,
    organization_name: 'Organization A', counterparty_name: 'Partner X', contract_number: 'AX1', warehouse_name: 'Warehouse A',
    lines: [{ id: 91, line_number: 1, name: 'Product', material_id: 51, unit_id: 1,
      quantity: 3, returnable_quantity: 2, price_without_vat: 150, vat_rate: 0 }] }
  let returned: any = null
  let refund: any = null
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()
    if (!path.startsWith('/api/')) { await route.continue(); return }
    if (path === '/api/auth/me') {
      await route.fulfill({ json: { id: 1, username: 'admin', role: 'admin', is_active: true } }); return
    }
    let data: any = []
    let status = 200
    if (path === '/api/goods/issues' || path === '/api/goods/receipts') data = [source]
    if (path.startsWith('/api/goods/return-sources/')) data = source
    if (path === '/api/goods/returns' && method === 'POST') {
      returned = { ...route.request().postDataJSON(), id: 1, number: 'RET-1', source_number: source.number,
        is_posted: false, sum_with_vat: 150, inventory_cost: 100, refunds: [] }
      data = returned; status = 201
    }
    if (path === '/api/goods/returns/1' && method === 'PUT') returned = { ...returned, ...route.request().postDataJSON() }
    if (path === '/api/goods/returns/1/post') returned.is_posted = true
    if (path === '/api/goods/returns/1/unpost') returned.is_posted = false
    if (path.startsWith('/api/goods/returns/1')) data = { ...returned, refunds: refund ? [refund] : [] }
    if (path === '/api/goods/return-refunds' && method === 'POST') {
      refund = { ...route.request().postDataJSON(), id: 2, number: 'REFUND-2', is_posted: false }; data = refund; status = 201
    }
    if (path === '/api/goods/return-refunds/2/post') { refund.is_posted = true; data = refund }
    if (path === '/api/goods/return-refunds/2/unpost') { refund.is_posted = false; data = refund }
    await route.fulfill({ status, json: { success: true, data, pagination: { page: 1, pages: 1, total: 1 } } })
  })
  await page.goto('/ctm/goods/returns/new')
  await page.getByLabel('Вид возврата').selectOption(kind)
  await page.getByLabel('Основание', { exact: true }).selectOption('41')
  await expect(page.getByText('Organization A · Partner X')).toBeVisible()
}

for (const kind of ['customer', 'supplier'] as const) {
  test(`${kind} return form links source lines, posts, refunds and cancels`, async ({ page }) => {
    await setup(page, kind)
    const quantity = page.getByRole('spinbutton', { name: 'Вернуть Product', exact: true })
    await expect(quantity).toHaveAttribute('max', '2')
    await quantity.fill('1')
    const request = page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith('/api/goods/returns'))
    await page.getByRole('button', { name: 'Провести', exact: true }).click()
    expect((await request).postDataJSON()).toMatchObject({ kind, source_id: 41, lines: [{ source_line_id: 91, quantity: 1 }] })
    await expect(page.getByRole('heading', { name: /RET-1 Проведен/ })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
    await page.getByLabel('Сумма', { exact: true }).fill('150')
    await page.getByRole('button', { name: 'Создать возврат денег', exact: true }).click()
    const row = page.getByRole('row').filter({ hasText: 'REFUND-2' })
    await row.getByRole('button', { name: 'Провести', exact: true }).click()
    await expect(row).toContainText('Проведен')
    await row.getByRole('button', { name: 'Отменить', exact: true }).click()
    await expect(row).toContainText('Черновик')
    await page.getByRole('button', { name: 'Отменить проведение', exact: true }).click()
    await expect(page.getByRole('heading', { name: /RET-1 Черновик/ })).toBeVisible()
  })
}

test('return form displays posting rejection and remains editable', async ({ page }) => {
  await setup(page, 'customer')
  await page.route('**/api/goods/returns/1/post', route => route.fulfill({ status: 400, json: { detail: 'Количество возвратов превышает основание' } }))
  await page.getByRole('spinbutton', { name: 'Вернуть Product', exact: true }).fill('1')
  await page.getByRole('button', { name: 'Провести', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Количество возвратов превышает основание')
  await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
})
