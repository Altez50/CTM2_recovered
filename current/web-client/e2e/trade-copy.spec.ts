import { expect, test, type Page } from '@playwright/test'

async function setup(page: Page, kind: string, role = 'manager', rejectCopy = false) {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'trade-copy'))
  const source = { id: 1, uuid: 'source-header', number: 'SOURCE-1', date: '2026-10-01',
    organization_id: 10, organization_name: 'Organization A', warehouse_id: 2, warehouse_name: 'Warehouse A',
    counterparty_id: 20, counterparty_name: 'Partner X', contract_id: 21, contract_number: 'AX1',
    object_id: 31, object_name: 'Object A', estimate_id: 41, responsible_id: 42,
    based_on_type: kind === 'issues' ? 'goods_receipt' : null, based_on_id: kind === 'issues' ? 9 : null,
    based_on_number: kind === 'issues' ? 'BASIS-9' : null,
    description: 'Original description', is_posted: true, posted_at: '2026-10-01T10:00:00+00:00',
    sum_without_vat: 1000, vat_amount: 0, sum_with_vat: 1000,
    lines: [{ id: 91, uuid: 'source-line', line_number: 1, name: 'Product T', material_id: 51,
      unit_id: 1, unit: 'pcs', object_id: 32, quantity: 10, price_without_vat: 100, vat_rate: 0,
      sum_without_vat: 1000, vat_amount: 0, sum_with_vat: 1000, drawing_code: 'D-1', note: 'Line note',
      package_id: 3, package_name: 'Box 5', conversion_factor: 5, base_quantity: 50, base_unit_id: 1,
      characteristic_id: 4, characteristic_name: 'Red', series_id: 5, series_name: 'Batch 1' }] }
  let copied = { ...structuredClone(source), id: 2, uuid: 'copy-header', number: 'COPY-2', is_posted: false,
    posted_at: null as string | null, based_on_type: null as string | null, based_on_id: null as number | null,
    based_on_number: null as string | null, lines: [{ ...structuredClone(source.lines[0]), id: 92, uuid: 'copy-line' }] }
  const writes: string[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    if (!path.startsWith('/api/')) { await route.continue(); return }
    if (path === '/api/auth/me') {
      await route.fulfill({ json: { id: 1, username: role, role, is_active: true, organization_ids: [10] } }); return
    }
    let data: unknown = []
    if (method !== 'GET') writes.push(method + ' ' + path)
    if (path === `/api/goods/${kind}`) data = [source]
    if (path === `/api/goods/${kind}/1`) data = source
    if (path === `/api/goods/${kind}/1/copy`) {
      if (rejectCopy) {
        await route.fulfill({ status: 403, json: { detail: 'Нет доступа к организации документа' } }); return
      }
      await route.fulfill({ status: 201, json: { success: true, data: copied } }); return
    }
    if (path === `/api/goods/${kind}/2`) {
      if (method === 'PUT') copied = { ...copied, ...route.request().postDataJSON() }
      data = copied
    }
    await route.fulfill({ json: { success: true, data, pagination: { page: 1, pages: 1, total: Array.isArray(data) ? data.length : 1 } } })
  })
  return { source, writes }
}

for (const kind of ['receipts', 'issues']) {
  for (const role of ['admin', 'manager']) {
    test(`${role} copies a posted ${kind} from its form into an independent editable draft`, async ({ page }) => {
      const { writes } = await setup(page, kind, role)
      await page.goto(`/ctm/goods/${kind}/1`)
      const sourceToolbar = page.locator('.document-toolbar:visible')
      await expect(sourceToolbar.locator('.status-pill')).toHaveText('Проведён')
      await expect(sourceToolbar.getByTitle('Сохранить', { exact: true })).toBeDisabled()
      await sourceToolbar.getByRole('button', { name: 'Копировать', exact: true }).click()
      await expect(page).toHaveURL(new RegExp(`/goods/${kind}/2$`))
      const toolbar = page.locator('.document-toolbar:visible')
      await expect(toolbar.locator('.status-pill')).toHaveText('Черновик')
      await expect(toolbar.getByTitle('Сохранить', { exact: true })).toBeEnabled()
      await expect(page.locator('.form-grid:visible input').first()).toHaveValue('COPY-2')
      await expect(page.locator('.stock-dimensions:visible')).toContainText('Базовое количество: 50')
      await expect(page.locator('.stock-dimensions:visible')).toContainText('Batch 1')
      await page.locator('.goods-lines-editor:visible input[type=number]').first().fill('2')
      const saved = page.waitForRequest(r => r.method() === 'PUT' && r.url().endsWith(`/api/goods/${kind}/2`))
      await toolbar.getByTitle('Сохранить', { exact: true }).click()
      const data = (await saved).postDataJSON()
      expect(data).toMatchObject({ organization_id: 10, warehouse_id: 2, counterparty_id: 20, contract_id: 21,
        object_id: 31, estimate_id: 41, responsible_id: 42, based_on_id: null, based_on_type: null })
      expect(data.lines[0]).toMatchObject({ id: 92, uuid: 'copy-line', unit_id: 1, unit: 'pcs', object_id: 32,
        quantity: 2, package_id: 3, characteristic_id: 4, series_id: 5, drawing_code: 'D-1', note: 'Line note' })
      expect(writes).toEqual([`POST /api/goods/${kind}/1/copy`, `PUT /api/goods/${kind}/2`])
      if (role === 'manager') await expect(toolbar.getByTitle('Провести', { exact: true })).not.toBeVisible()
    })
  }
  test(`viewer cannot copy ${kind} from its form`, async ({ page }) => {
    const { writes } = await setup(page, kind, 'viewer')
    await page.goto(`/ctm/goods/${kind}/1`)
    await expect(page.locator('.document-toolbar:visible .status-pill')).toHaveText('Проведён')
    await expect(page.getByRole('button', { name: 'Копировать', exact: true })).toHaveCount(0)
    expect(writes).toEqual([])
  })
}

test('failed copy keeps the source open and shows the server error', async ({ page }) => {
  const { writes } = await setup(page, 'receipts', 'manager', true)
  await page.goto('/ctm/goods/receipts/1')
  await page.getByRole('button', { name: 'Копировать', exact: true }).click()
  await expect(page.locator('.message-error:visible')).toHaveText('Нет доступа к организации документа')
  await expect(page).toHaveURL(/\/goods\/receipts\/1$/)
  await expect(page.locator('.document-toolbar:visible .status-pill')).toHaveText('Проведён')
  await expect(page.getByRole('button', { name: 'Копировать', exact: true })).toBeEnabled()
  expect(writes).toEqual(['POST /api/goods/receipts/1/copy'])
})

test('existing list copy uses the same API and opens the draft', async ({ page }) => {
  const { writes } = await setup(page, 'receipts')
  await page.goto('/ctm/goods/receipts')
  const row = page.getByRole('row').filter({ hasText: 'SOURCE-1' })
  await row.locator('td').last().click()
  await expect(row).toHaveClass(/row-selected/)
  await page.getByRole('button', { name: 'Копировать', exact: true }).click()
  await expect(page).toHaveURL(/\/goods\/receipts\/2$/)
  await expect(page.locator('.document-toolbar:visible .status-pill')).toHaveText('Черновик')
  expect(writes).toEqual(['POST /api/goods/receipts/1/copy'])
})
