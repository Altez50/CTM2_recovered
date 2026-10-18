import { defineConfig } from '@playwright/test'
import base from './playwright.config'

// Keep this package's API-mock checks separate from other local dev servers.
export default defineConfig({
  ...base,
  outputDir: 'test-results-step04',
  use: { ...base.use, baseURL: 'http://127.0.0.1:5184' },
  webServer: {
    command: 'npx vite --host 127.0.0.1 --port 5184 --strictPort',
    url: 'http://127.0.0.1:5184/ctm/',
    reuseExistingServer: false,
  },
})
