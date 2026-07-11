# E2E Test Execution Guide

This guide explains how to run the E2E tests for the web client.

## Quick Start (Windows)

### Option 1: Using the Helper Script (Recommended)

1. Run the helper script to start both servers:
   ```cmd
   cd web-client
   start-e2e-servers.bat
   ```

2. In a new terminal, run the E2E tests:
   ```cmd
   cd web-client
   npm run test:e2e
   ```

### Option 2: Manual Setup

1. **Terminal 1 - Start Backend API:**
   ```cmd
   python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
   ```

2. **Terminal 2 - Start Frontend Dev Server:**
   ```cmd
   cd web-client
   npm run dev
   ```

3. **Terminal 3 - Run E2E Tests:**
   ```cmd
   cd web-client
   npm run test:e2e
   ```

## Prerequisites

### 1. Install Dependencies

```cmd
# Install Python dependencies (from project root)
pip install -r requirements.txt

# Install Node dependencies (from web-client directory)
cd web-client
npm install

# Install Playwright browsers
npx playwright install
```

### 2. Setup Test Database

The test database needs to have a test user (admin/admin):

```cmd
# From project root
python api\tests\setup_test_db.py
```

This creates/updates the admin user with the correct password hash.

## Running Tests

### Run All Tests
```cmd
npm run test:e2e
```

### Run Tests in UI Mode (Interactive)
```cmd
npm run test:e2e:ui
```

### Run Tests in Headed Mode (See Browser)
```cmd
npm run test:e2e:headed
```

### Run Tests in Debug Mode
```cmd
npm run test:e2e:debug
```

### Run Specific Test File
```cmd
npx playwright test e2e/login.spec.ts
```

### Run Specific Test
```cmd
npx playwright test e2e/login.spec.ts -g "should successfully login"
```

## Test Coverage

### Current Tests

#### Login Flow (`e2e/login.spec.ts`)
- ✅ Display login form
- ✅ Successfully login with valid credentials
- ✅ Show error message with invalid credentials
- ✅ Show error message with empty fields
- ✅ Disable form during login attempt
- ✅ Redirect to login when accessing protected route without auth
- ✅ Redirect to intended page after login
- ✅ Persist authentication after page reload
- ✅ Logout and redirect to login

## Troubleshooting

### Backend Not Running

**Error:**
```
❌ Backend API is not running!
```

**Solution:**
Start the backend API server:
```cmd
python -m uvicorn api.main:app --reload
```

### Test User Not Found

**Error:**
```
Login fails with 401 Unauthorized
```

**Solution:**
Setup the test database:
```cmd
python api\tests\setup_test_db.py
```

### Port Already in Use

**Error:**
```
Port 8000 is already in use
```

**Solution:**
1. Check if another instance is running:
   ```cmd
   netstat -ano | findstr :8000
   ```

2. Kill the process:
   ```cmd
   taskkill /PID <process_id> /F
   ```

### Frontend Port Already in Use

**Error:**
```
Port 5173 is already in use
```

**Solution:**
The test will automatically reuse the existing dev server if it's already running.

### Timeout Errors

If tests timeout, you can:

1. Increase timeout in `playwright.config.ts`:
   ```typescript
   timeout: 60 * 1000, // 60 seconds
   ```

2. Run tests in headed mode to see what's happening:
   ```cmd
   npm run test:e2e:headed
   ```

3. Run tests in debug mode:
   ```cmd
   npm run test:e2e:debug
   ```

## CI/CD Integration

For CI/CD pipelines, you'll need to:

1. Start the backend API in the background
2. Wait for it to be ready
3. Run the tests
4. Stop the backend API

Example GitHub Actions workflow:

```yaml
- name: Setup test database
  run: python api/tests/setup_test_db.py

- name: Start backend API
  run: |
    python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 &
    sleep 5

- name: Run E2E tests
  run: |
    cd web-client
    npm run test:e2e

- name: Upload test results
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: playwright-report
    path: web-client/playwright-report/
```

## Test Reports

After running tests, you can view the HTML report:

```cmd
npx playwright show-report
```

This will open a browser with detailed test results, including:
- Test execution timeline
- Screenshots of failures
- Traces for debugging

## Writing New Tests

See `e2e/README.md` for guidelines on writing new E2E tests.

## Next Steps

After the login flow tests are passing, the next E2E tests to implement are:

1. ✅ Login flow (COMPLETE)
2. ⏳ Create and edit counterparty
3. ⏳ Create and edit estimate
4. ⏳ Create and edit daily report
5. ⏳ Post document
6. ⏳ Generate print form

## Support

If you encounter issues not covered in this guide:

1. Check the Playwright documentation: https://playwright.dev/
2. Review the test logs in `playwright-report/`
3. Run tests in debug mode to step through them
4. Check the backend API logs for errors
