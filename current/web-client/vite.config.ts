import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync } from 'node:fs'

const devProxyTarget = process.env.VITE_DEV_PROXY_TARGET || 'http://localhost:8000'
const packageJson = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as {
  version?: string
}

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function buildTimestampLabel(date: Date) {
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join('-') + ' ' + [
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join(':')
}

const buildTimestamp = buildTimestampLabel(new Date())
const appVersion = packageJson.version || '0.0.0'
const buildLabel = `v${appVersion} · ${buildTimestamp}`

export default defineConfig({
  base: '/ctm/',
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
    __APP_BUILD_TIMESTAMP__: JSON.stringify(buildTimestamp),
    __APP_BUILD_LABEL__: JSON.stringify(buildLabel),
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: devProxyTarget,
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
