import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { useUiDensity } from './composables/useUiDensity'
import './styles.css'

useUiDensity()

if (typeof document !== 'undefined') {
  document.title = `CTM Web Client ${__APP_BUILD_LABEL__}`
}

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.mount('#app')
