import { defineConfig } from '@playwright/test'
import base from './playwright.config'
export default defineConfig({
  ...base,
  outputDir: 'test-results-step07',
  use: { ...base.use, baseURL: 'http://127.0.0.1:5187' },
  webServer: { command: 'npx vite --host 127.0.0.1 --port 5187 --strictPort', url: 'http://127.0.0.1:5187/ctm/', reuseExistingServer: false },
})
