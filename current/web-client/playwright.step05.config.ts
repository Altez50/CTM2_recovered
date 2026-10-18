import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({
  ...base,
  outputDir: 'test-results-step05',
  use: { ...base.use, baseURL: 'http://127.0.0.1:5185' },
  webServer: { command: 'npx vite --host 127.0.0.1 --port 5185 --strictPort', url: 'http://127.0.0.1:5185/ctm/', reuseExistingServer: false },
})
