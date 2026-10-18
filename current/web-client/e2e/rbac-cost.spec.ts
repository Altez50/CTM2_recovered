import { expect, test, type Page, type Route } from '@playwright/test'

// Отрицательные UI-сценарии RBAC=B для cost-документов (DEVELOPMENT_PLAN.md, P1 п.5):
// прораб управляет только своими полевыми документами и не видит офисных команд,
// менеджер сохраняет полный lifecycle. API замокан, как в p0-smoke.spec.ts.

const foreman = {
  id: 3, username: 'foreman', full_name: 'Site Foreman', role: 'foreman',
  is_active: true, person_id: 7,
}
const manager = {
  id: 2, username: 'manager', full_name: 'Project Manager', role: 'manager',
  is_active: true, person_id: null,
}

function emptyList() {
  return { success: true, data: [], pagination: { page: 1, page_size: 50, total: 0, pages: 1 } }
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function mockCostApi(
  page: Page,
  user: typeof foreman,
  lists: Record<string, unknown[]>,
  documents: Record<string, unknown> = {},
) {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'rbac-cost-token'))
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
    for (const [pathname, rows] of Object.entries(lists)) {
      if (url.pathname === pathname && route.request().method() === 'GET') {
        await fulfillJson(route, {
          success: true,
          data: rows,
          pagination: { page: 1, page_size: 50, total: rows.length, pages: 1 },
        })
        return
      }
    }
    for (const [pathname, doc] of Object.entries(documents)) {
      if (url.pathname === pathname && route.request().method() === 'GET') {
        await fulfillJson(route, { success: true, data: doc })
        return
      }
    }
    await fulfillJson(route, emptyList())
  })
}

const ownDraft = {
  id: 11, number: 'OWN-1', date: '2026-09-01', is_posted: false, marked_for_deletion: false,
  foreman_id: 7, object_name: 'Своя стройка', warehouse: 'Склад 1',
}
const othersDraft = {
  id: 12, number: 'OTHER-1', date: '2026-09-02', is_posted: false, marked_for_deletion: false,
  foreman_id: 99, object_name: 'Чужая стройка', warehouse: 'Склад 2',
}

test('foreman on the field cost list can only delete their own drafts', async ({ page }) => {
  await mockCostApi(page, foreman, { '/api/cost/material-consumptions': [ownDraft, othersDraft] })
  await page.goto('/ctm/documents/material-consumptions')

  // Полевые документы прораб может создавать.
  await expect(page.locator('.command-bar .button-primary')).toBeEnabled()

  // Свой черновик: удалить можно, проводить — нет (lifecycle только офис).
  await page.getByRole('cell', { name: 'Своя стройка' }).click()
  await expect(page.getByRole('button', { name: 'Удалить' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Провести' })).toBeDisabled()

  // Чужой черновик: удаление недоступно.
  await page.getByRole('cell', { name: 'Чужая стройка' }).click()
  await expect(page.getByRole('button', { name: 'Удалить' })).toBeDisabled()
})

test('foreman cannot create or delete office cost documents', async ({ page }) => {
  await mockCostApi(page, foreman, {
    '/api/cost/subcontract-acceptances': [
      { id: 21, number: 'SA-1', date: '2026-09-01', is_posted: false, marked_for_deletion: false },
    ],
  })
  await page.goto('/ctm/documents/subcontract-acceptances')

  await expect(page.locator('.command-bar .button-primary')).toBeDisabled()
  await page.getByRole('cell', { name: 'SA-1' }).click()
  await expect(page.getByRole('button', { name: 'Удалить' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Провести' })).toBeDisabled()
})

test('manager keeps the full lifecycle on the field cost list', async ({ page }) => {
  await mockCostApi(page, manager, {
    '/api/cost/material-consumptions': [
      ownDraft,
      { ...othersDraft, is_posted: true },
    ],
  })
  await page.goto('/ctm/documents/material-consumptions')

  await expect(page.locator('.command-bar .button-primary')).toBeEnabled()

  await page.getByRole('cell', { name: 'Своя стройка' }).click()
  await expect(page.getByRole('button', { name: 'Провести' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Удалить' })).toBeEnabled()

  // Проведённый документ нельзя удалить, но можно отменить проведение.
  await page.getByRole('cell', { name: 'Чужая стройка' }).click()
  await expect(page.getByRole('button', { name: 'Отменить' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Удалить' })).toBeDisabled()
})

test('foreman sees an office cost form read-only', async ({ page }) => {
  await mockCostApi(
    page,
    foreman,
    {},
    {
      '/api/cost/subcontract-acceptances/5': {
        id: 5, number: 'SA-5', date: '2026-09-02', is_posted: false,
        marked_for_deletion: false, lines: [],
      },
    },
  )
  await page.goto('/ctm/documents/subcontract-acceptances/5')

  await expect(page.locator('.doc-header-grid input').first()).toBeDisabled()
  await expect(page.getByTitle('Сохранить')).toBeDisabled()
  await expect(page.getByTitle('Провести')).toHaveCount(0)
})
