import { expect, test, type Page, type Route } from '@playwright/test'

const admin = { id: 1, username: 'admin', full_name: 'CTM Administrator', role: 'admin', is_active: true }
const manager = { id: 2, username: 'manager', full_name: 'Project Manager', role: 'manager', is_active: true }

const emptyEstimate = {
  id: 5,
  number: 'P0-5',
  date: '2026-09-02',
  customer_id: null,
  object_id: null,
  contractor_id: null,
  responsible_id: null,
  contract_id: null,
  total_sum: 0,
  total_labor: 0,
  is_posted: false,
  marked_for_deletion: false,
  lines: [],
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function mockAuthenticatedApi(page: Page, user = admin) {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'p0-smoke-token'))
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (!url.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }
    if (url.pathname === '/api/auth/me') {
      await fulfillJson(route, user)
      return
    }
    if (/\/api\/documents\/estimates\/\d+$/.test(url.pathname) && route.request().method() === 'GET') {
      const id = Number(url.pathname.split('/').at(-1))
      await fulfillJson(route, { success: true, data: { ...emptyEstimate, id } })
      return
    }
    if (url.pathname === '/api/documents/estimates' && route.request().method() === 'POST') {
      const submitted = route.request().postDataJSON()
      await fulfillJson(route, { success: true, data: { ...emptyEstimate, ...submitted, id: 42 } }, 201)
      return
    }
    if (url.pathname === '/api/dashboard/summary') {
      await fulfillJson(route, {
        success: true,
        data: {
          documents: { estimates: 0, daily_reports: 0, timesheets: 0 },
          references: { counterparties: 0, objects: 0, works: 0, persons: 0, organizations: 0 },
          register_totals: { sum_income: 0, sum_expense: 0 },
        },
      })
      return
    }
    await fulfillJson(route, { success: true, data: [], pagination: { page: 1, page_size: 50, total: 0, pages: 1 } })
  })
}

test('protected routes redirect to login and login reports invalid credentials', async ({ page }) => {
  await page.route('**/api/auth/login', (route) => fulfillJson(route, { detail: 'Invalid username or password' }, 401))
  await page.goto('/ctm/documents/estimates')
  await expect(page).toHaveURL(/\/ctm\/login\?redirect=/)
  await page.getByLabel('Пароль').fill('wrong')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByText('Invalid username or password')).toBeVisible()
})

test('successful login stores the session and opens the protected workspace', async ({ page }) => {
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    if (!pathname.startsWith('/api/')) {
      await route.continue()
      return
    }
    if (pathname === '/api/auth/login') {
      await fulfillJson(route, { access_token: 'login-token', token_type: 'bearer', expires_in: 3600, user: admin })
    } else if (pathname === '/api/dashboard/summary') {
      await fulfillJson(route, {
        success: true,
        data: {
          documents: { estimates: 0, daily_reports: 0, timesheets: 0 },
          references: { counterparties: 0, objects: 0, works: 0, persons: 0, organizations: 0 },
          register_totals: { sum_income: 0, sum_expense: 0 },
        },
      })
    } else {
      await fulfillJson(route, admin)
    }
  })
  await page.goto('/ctm/login')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL(/\/ctm\/$/)
  await expect(page.getByRole('main').getByRole('link', { name: 'Сметы' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ctm.token'))).toBe('login-token')
})

test('estimate create/save clears dirty state and attaches the saved id', async ({ page }) => {
  await mockAuthenticatedApi(page)
  await page.goto('/ctm/documents/estimates/new')
  await page.locator('.doc-header-grid input').first().fill('P0-created')
  await expect(page.locator('.tab-dirty-marker')).toBeVisible()
  await page.getByTitle('Сохранить').click()
  await expect(page).toHaveURL(/\/ctm\/documents\/estimates\/42$/)
  await expect(page.locator('.tab-dirty-marker')).toHaveCount(0)
})

test('closing a dirty estimate asks for confirmation', async ({ page }) => {
  await mockAuthenticatedApi(page)
  await page.goto('/ctm/documents/estimates/new')
  await page.locator('.doc-header-grid input').first().fill('unsaved')
  await expect(page.locator('.tab-dirty-marker')).toBeVisible()
  let dialogMessage = ''
  page.once('dialog', async (dialog) => {
    dialogMessage = dialog.message()
    await dialog.dismiss()
  })
  await page.locator('.tab-close').click()
  expect(dialogMessage).toContain('несохранённые изменения')
  await expect(page).toHaveURL(/\/ctm\/documents\/estimates\/new$/)
})

test('posting action is visible only to an administrator', async ({ page }) => {
  await mockAuthenticatedApi(page, admin)
  await page.goto('/ctm/documents/estimates/5')
  await expect(page.getByTitle('Провести')).toBeVisible()
})

test('manager cannot see the administrator-only posting action', async ({ page }) => {
  await mockAuthenticatedApi(page, manager)
  await page.goto('/ctm/documents/estimates/5')
  await expect(page.getByTitle('Провести')).toHaveCount(0)
})

test('estimate list sends its search filter to the backend', async ({ page }) => {
  await mockAuthenticatedApi(page)
  await page.goto('/ctm/documents/estimates')
  const filteredRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return url.pathname === '/api/documents/estimates' && url.searchParams.get('search') === 'P0-filter'
  })
  await page.getByPlaceholder('Поиск по номеру, заказчику, объекту').fill('P0-filter')
  await filteredRequest
})

test('administrator can post and unpost an estimate from the form', async ({ page }) => {
  let posted = false
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'p0-smoke-token'))
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (!url.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }
    if (url.pathname === '/api/auth/me') {
      await fulfillJson(route, admin)
    } else if (url.pathname === '/api/documents/estimates/5' && route.request().method() === 'GET') {
      await fulfillJson(route, { success: true, data: { ...emptyEstimate, is_posted: posted } })
    } else if (url.pathname === '/api/documents/estimates/5/post') {
      posted = true
      await fulfillJson(route, { success: true, message: 'posted' })
    } else if (url.pathname === '/api/documents/estimates/5/unpost') {
      posted = false
      await fulfillJson(route, { success: true, message: 'unposted' })
    } else if (url.pathname === '/api/documents/estimates/5' && route.request().method() === 'PUT') {
      await fulfillJson(route, { success: true, data: { ...emptyEstimate, ...route.request().postDataJSON() } })
    } else {
      await fulfillJson(route, { success: true, data: [], pagination: { page: 1, page_size: 50, total: 0, pages: 1 } })
    }
  })
  await page.goto('/ctm/documents/estimates/5')
  await page.getByTitle('Провести').click()
  await expect(page.getByTitle('Отменить проведение')).toBeVisible()
  await page.getByTitle('Отменить проведение').click()
  await expect(page.getByTitle('Провести')).toBeVisible()
})

test('document import requires preview before apply', async ({ page }) => {
  const previewValues: string[] = []
  await mockAuthenticatedApi(page)
  await page.route('**/api/documents/estimates/5/import-text**', async (route) => {
    const url = new URL(route.request().url())
    previewValues.push(url.searchParams.get('preview') ?? '')
    await fulfillJson(route, {
      success: true,
      data: { imported: 1, warnings: [], format: 'json', preview: url.searchParams.get('preview') === 'true' },
    })
  })
  await page.goto('/ctm/documents/estimates/5')
  await page.getByTitle('Импорт/экспорт строк').click()
  await page.locator('.format-row select').selectOption('json')
  await page.locator('.import-section textarea').fill('[{"work_name":"P0 import","quantity":1}]')
  await page.getByRole('button', { name: 'Проверить' }).click()
  await expect(page.getByText('Проверено строк: 1')).toBeVisible()
  await page.getByRole('button', { name: 'Применить' }).click()
  await expect(page.getByText('Импортировано строк: 1')).toBeVisible()
  expect(previewValues).toEqual(['true', 'false'])
})
