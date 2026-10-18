import { expect, test, type Page } from '@playwright/test'

async function setup(page: Page, role = 'admin', denyDocument = false, restrictedAdmin = false) {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'trade-access'))
  const users = [{ id: 1, username: 'admin', role: 'admin', is_active: true, organization_ids: null as number[] | null },
    { id: 2, username: 'reader', role: 'viewer', is_active: true, organization_ids: [10] as number[] | null }]
  const orgs = [{ id: 10, name: 'Organization A' }, { id: 11, name: 'Organization B' }]
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    if (!path.startsWith('/api/')) { await route.continue(); return }
    if (path === '/api/auth/me') {
      await route.fulfill({ json: { id: 1, username: role, role, is_active: true, organization_ids: role === 'admin' && !restrictedAdmin ? null : [10] } }); return
    }
    let data: unknown = []
    if (path === '/api/users') data = users
    if (path === '/api/users/2/access' && method === 'PUT') { Object.assign(users[1], route.request().postDataJSON()); data = users[1] }
    if (path === '/api/references/organizations') data = orgs
    if (path === '/api/goods/receipts/1') {
      if (denyDocument) { await route.fulfill({ status: 403, json: { detail: 'Нет доступа к организации документа' } }); return }
      data = { id: 1, number: 'RECEIPT-A', date: '2026-10-01', organization_id: 10, organization_name: 'Organization A',
        warehouse_id: 2, warehouse_name: 'Warehouse A', counterparty_id: 20, contract_id: 21, is_posted: false,
        sum_without_vat: 0, vat_amount: 0, sum_with_vat: 0, lines: [] }
    }
    await route.fulfill({ json: { success: true, data, pagination: { page: 1, pages: 1, total: Array.isArray(data) ? data.length : 1 } } })
  })
}

test('administrator saves explicit organizations, empty access and unrestricted access', async ({ page }) => {
  await setup(page)
  await page.goto('/ctm/administration/users')
  await page.getByLabel('Пользователь', { exact: true }).selectOption('2')
  await expect(page.getByLabel('Роль', { exact: true })).toHaveValue('viewer')
  await page.getByLabel('Роль', { exact: true }).selectOption('manager')
  await page.getByLabel('Organization A', { exact: true }).uncheck()
  await page.getByLabel('Organization B', { exact: true }).check()
  const save = async (ids: number[] | null) => {
    const request = page.waitForRequest(r => r.method() === 'PUT' && r.url().endsWith('/api/users/2/access'))
    await page.getByRole('button', { name: 'Сохранить доступ', exact: true }).click()
    expect((await request).postDataJSON()).toEqual({ role: 'manager', organization_ids: ids })
    await expect(page.getByRole('status')).toHaveText('Доступ сохранен')
  }
  await save([11])
  await page.getByLabel('Organization B', { exact: true }).uncheck()
  await save([])
  await page.getByLabel('Все организации', { exact: true }).check()
  await save(null)
})

test('viewer cannot open access management or trigger its API', async ({ page }) => {
  await setup(page, 'viewer')
  const requests: string[] = []
  page.on('request', request => requests.push(new URL(request.url()).pathname))
  await page.goto('/ctm/administration/users')
  await expect(page.getByText('Настройка доступа доступна администратору без ограничения организаций.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Сохранить доступ' })).toHaveCount(0)
  expect(requests).not.toContain('/api/users')
})

test('viewer reads receipt with disabled fields and no posting commands', async ({ page }) => {
  await setup(page, 'viewer')
  await page.goto('/ctm/goods/receipts/1')
  await expect(page.locator('.document-toolbar').getByTitle('Сохранить', { exact: true })).toBeDisabled()
  await expect(page.locator('.form-grid input').first()).toBeDisabled()
  await expect(page.locator('.document-toolbar').getByTitle('Провести', { exact: true })).not.toBeVisible()
  await expect(page.getByRole('button', { name: 'Загрузить из Excel…', exact: true })).toBeDisabled()
})

test('manager can prepare receipt but cannot post it', async ({ page }) => {
  await setup(page, 'manager')
  await page.goto('/ctm/goods/receipts/1')
  await expect(page.locator('.document-toolbar').getByTitle('Сохранить', { exact: true })).toBeEnabled()
  await expect(page.locator('.document-toolbar').getByTitle('Провести', { exact: true })).not.toBeVisible()
})

test('foreign document rejection is shown without foreign details', async ({ page }) => {
  await setup(page, 'viewer', true)
  await page.goto('/ctm/goods/receipts/1')
  await expect(page.getByText('Нет доступа к организации документа', { exact: true })).toBeVisible()
  await expect(page.locator('.form-grid input').first()).not.toHaveValue('RECEIPT-A')
})

test('scoped administrator cannot use the global engineering console', async ({ page }) => {
  await setup(page, 'admin', false, true)
  await page.goto('/ctm/engineering/tables')
  await expect(page).toHaveURL(/\/ctm\/$/)
  await expect(page.getByRole('link', { name: 'Доступ пользователей', exact: true })).toHaveCount(0)
})
