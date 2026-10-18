import { expect, test, type Page } from '@playwright/test'

async function mockApi(page: Page) {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'trade-stage1'))
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (!url.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }
    let data: unknown = []
    if (url.pathname === '/api/auth/me') {
      await route.fulfill({ json: { id: 1, username: 'admin', full_name: 'Admin', role: 'admin', is_active: true } })
      return
    }
    if (url.pathname === '/api/references/organizations') data = [{ id: 10, name: 'Organization A' }]
    if (url.pathname === '/api/references/counterparties') data = [{ id: 20, name: 'Buyer X' }, { id: 21, name: 'Buyer Y' }]
    if (url.pathname === '/api/references/contracts') {
      data = url.searchParams.get('organization_id') === '10' && url.searchParams.get('counterparty_id') === '20'
        ? [{ id: 30, number: 'AX1', organization_id: 10, counterparty_id: 20 }] : []
    }
    if (url.pathname === '/api/settlements/turnover') {
      data = [{ organization_id: 10, organization_name: 'Organization A', counterparty_name: 'Buyer X', contract_number: 'AX1',
        receivable_opening: 0, receivable_accrual_turnover: 540, receivable_payment_turnover: 600, receivable_closing: 0,
        payable_opening: 0, payable_accrual_turnover: 0, payable_payment_turnover: 0, payable_closing: 0,
        customer_advance_opening: 0, customer_advance_closing: 60, supplier_advance_opening: 0, supplier_advance_closing: 0 }]
    }
    if (route.request().method() === 'POST' && url.pathname === '/api/payments/transactions') {
      await route.fulfill({ status: 201, json: { success: true, data: { ...route.request().postDataJSON(), id: 1 } } })
      return
    }
    await route.fulfill({ json: { success: true, data, pagination: { page: 1, pages: 1, total: Array.isArray(data) ? data.length : 0 } } })
  })
}

test('payment form sends contract and explicit advance permission, clears changed owner', async ({ page }) => {
  await mockApi(page)
  await page.goto('/ctm/payments/transactions')
  await page.getByRole('button', { name: '+ Платёж', exact: true }).click()
  await page.getByLabel('Организация', { exact: true }).selectOption('10')
  await page.getByLabel('Контрагент', { exact: true }).selectOption('20')
  await page.getByLabel('Договор', { exact: true }).selectOption('30')
  await page.getByLabel('Контрагент', { exact: true }).selectOption('21')
  await expect(page.getByLabel('Договор', { exact: true })).toHaveValue('')
  await page.getByLabel('Контрагент', { exact: true }).selectOption('20')
  await page.getByLabel('Договор', { exact: true }).selectOption('30')
  await page.getByLabel('Направление', { exact: true }).selectOption('incoming')
  await page.getByLabel('Сумма', { exact: true }).fill('600')
  await page.getByRole('checkbox', { name: /Разрешить аванс/ }).check()
  const request = page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith('/api/payments/transactions'))
  await page.getByRole('button', { name: 'Создать', exact: true }).click()
  expect((await request).postDataJSON()).toMatchObject({ contract_id: 30, counterparty_id: 20, amount: 600, allow_advance: true })
})

test('turnover shows overpayment as customer advance separately from debt and exports it', async ({ page }) => {
  await mockApi(page)
  await page.goto('/ctm/reports/settlements-turnover')
  await expect(page.getByRole('columnheader', { name: 'Аванс покупателя кон.', exact: true })).toBeVisible()
  await expect(page.getByText('Авансы покупателей:', { exact: false })).toContainText('60,00')
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Выгрузить в CSV' }).click()
  const download = await downloadEvent
  expect(download.suggestedFilename()).toContain('ОСВ_взаиморасчеты')
})
