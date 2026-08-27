import { expect, test, type Locator, type Page } from '@playwright/test'

const documentForms = [
  '/documents/estimates/new',
  '/documents/daily-reports/new',
  '/documents/timesheets/new',
  '/documents/material-consumptions/new',
  '/documents/machinery-usage/new',
  '/documents/subcontract-acceptances/new',
  '/documents/overhead-expenses/new',
  '/documents/cost-calculations/new',
  '/payments/schedules/new',
  '/goods/receipts/new',
  '/goods/issues/new',
]

const FIELD_SELECTOR = ':scope > .field'
const CONTROL_SELECTOR = ':scope > .input, :scope > .select, :scope > .entity-picker .ref-input-row'
const PIXEL_TOLERANCE = 1

async function mockApi(page: Page) {
  await page.addInitScript(() => localStorage.setItem('ctm.token', 'layout-test-token'))
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    if (!pathname.startsWith('/api/')) {
      await route.continue()
      return
    }
    const body = pathname === '/api/auth/me'
      ? { id: 1, username: 'layout-test', full_name: 'Layout Test', role: 'admin', is_active: true }
      : { items: [], total: 0, page: 1, page_size: 50, pages: 0 }

    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
}

async function headerGrid(page: Page): Promise<Locator> {
  const grid = page.locator('.panel-body .form-grid').first()
  await expect(grid, `Форма не открылась. URL: ${page.url()}; страница: ${await page.locator('body').innerText()}`).toBeVisible()
  await expect(grid.locator(FIELD_SELECTOR)).not.toHaveCount(0)
  return grid
}

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

for (const path of documentForms) {
  test.describe(path, () => {
    test('поля шапки не перекрывают друг друга', async ({ page }) => {
      await page.goto(`/ctm${path}`)
      const grid = await headerGrid(page)
      const boxes = await grid.locator(FIELD_SELECTOR).evaluateAll((fields) => fields.map((field) => {
        const rect = field.getBoundingClientRect()
        return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }
      }))

      expect(boxes.length).toBeGreaterThan(1)
      for (let left = 0; left < boxes.length; left += 1) {
        for (let right = left + 1; right < boxes.length; right += 1) {
          const a = boxes[left]
          const b = boxes[right]
          const overlapWidth = Math.min(a.right, b.right) - Math.max(a.left, b.left)
          const overlapHeight = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
          expect.soft(overlapWidth > 0 && overlapHeight > 0, `Поля ${left + 1} и ${right + 1} пересекаются`).toBe(false)
        }
      }
    })

    test('поля ввода шапки одинаковой высоты', async ({ page }) => {
      await page.goto(`/ctm${path}`)
      const grid = await headerGrid(page)
      const heights = await grid.locator(FIELD_SELECTOR).evaluateAll((fields, selector) => fields
        .map((field) => field.querySelector<HTMLElement>(selector)?.getBoundingClientRect().height)
        .filter((height): height is number => height !== undefined), CONTROL_SELECTOR)

      expect(heights.length).toBeGreaterThan(1)
      expect(Math.max(...heights) - Math.min(...heights), `Высоты элементов: ${heights.join(', ')}`).toBeLessThanOrEqual(PIXEL_TOLERANCE)
    })
  })
}
