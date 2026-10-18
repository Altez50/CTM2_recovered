import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({
  ...base,
  outputDir: 'test-results-step05-review',
  use: { ...base.use, baseURL: 'http://127.0.0.1:5186' },
  webServer: { command: 'npx vite --host 127.0.0.1 --port 5186 --strictPort', url: 'http://127.0.0.1:5186/ctm/', reuseExistingServer: false },
})
