# E2E Tests

End-to-end tests for the web client using Playwright.

## Prerequisites

1. **Backend API must be running** on `http://localhost:8000`
   ```bash
   # From project root
   python -m uvicorn api.main:app --reload
   ```

2. **Test database must be set up** with test users
   ```bash
   # From project root
   python api/tests/setup_test_db.py
   ```

3. **Playwright browsers must be installed**
   ```bash
   # From web-client directory
   npx playwright install
   ```

## Running Tests

### Run all E2E tests
```bash
npm run test:e2e
```

### Run tests in UI mode (interactive)
```bash
npm run test:e2e:ui
```

### Run tests in debug mode
```bash
npm run test:e2e:debug
```

### Run specific test file
```bash
npx playwright test e2e/login.spec.ts
```

### Run tests in headed mode (see browser)
```bash
npx playwright test --headed
```

## Test Structure

- `login.spec.ts` - Authentication flow tests
  - Login with valid credentials
  - Login with invalid credentials
  - Protected route access
  - Session persistence
  - Logout flow

## Writing New Tests

1. Create a new `.spec.ts` file in the `e2e` directory
2. Import test utilities: `import { test, expect } from '@playwright/test'`
3. Use `test.describe()` to group related tests
4. Use `test.beforeEach()` for common setup
5. Write test cases with descriptive names

Example:
```typescript
import { test, expect } from '@playwright/test'

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/some-page')
  })

  test('should do something', async ({ page }) => {
    // Test implementation
  })
})
```

## Debugging Tests

### Visual debugging with UI mode
```bash
npm run test:e2e:ui
```

### Step-by-step debugging
```bash
npm run test:e2e:debug
```

### Generate trace for failed tests
Traces are automatically generated for failed tests and can be viewed with:
```bash
npx playwright show-trace trace.zip
```

## CI/CD

Tests run in headless mode on CI with:
- Automatic retries (2 retries)
- HTML report generation
- Trace collection on failures

## Troubleshooting

### Backend not running
Error: `connect ECONNREFUSED 127.0.0.1:8000`

**Solution**: Start the backend API server:
```bash
python -m uvicorn api.main:app --reload
```

### Test user not found
Error: Login fails with 401

**Solution**: Set up test database:
```bash
python api/tests/setup_test_db.py
```

### Port already in use
Error: `Port 5173 is already in use`

**Solution**: The test will reuse the existing dev server if it's already running.

### Timeout errors
If tests timeout, increase the timeout in `playwright.config.ts`:
```typescript
timeout: 60 * 1000, // 60 seconds
```
