<template>
  <main class="login-shell">
    <section class="login-card panel">
      <div class="panel-body login-body">
        <div>
          <div class="login-kicker">Строительные сметы и рабочее время</div>
          <h1 class="login-title">Вход в CTM</h1>
        </div>

        <form class="login-form" @submit.prevent="submit">
          <FormField label="Логин">
            <input v-model="username" class="input" autocomplete="username" placeholder="admin" />
          </FormField>

          <FormField label="Пароль">
            <input
              v-model="password"
              class="input"
              type="password"
              autocomplete="current-password"
              placeholder="Введите пароль"
            />
          </FormField>

          <p v-if="error" class="error-text">{{ error }}</p>

          <button class="button button-primary" type="submit" :disabled="loading">
            {{ loading ? 'Входим…' : 'Войти' }}
          </button>
        </form>

        <div class="hint-box">
          <strong>Демо-учетные записи</strong>
          <div>`admin / admin`, `manager / manager`, `foreman / foreman`</div>
        </div>

        <a class="product-link" href="/ctm/ctm-one-pager.html" target="_blank" rel="noopener">
          О CTM: возможности для строительного подрядчика
        </a>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FormField from '../components/common/FormField.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('admin')
const password = ref('admin')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось войти'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 1.5rem;
}

.login-card {
  width: min(560px, 100%);
}

.login-body {
  display: grid;
  gap: 1.4rem;
}

.login-kicker {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.8rem;
  color: var(--text-soft);
}

.login-title {
  margin: 0.4rem 0 0;
  font-size: clamp(2rem, 2vw + 1.3rem, 3rem);
}

.login-form {
  display: grid;
  gap: 1rem;
}

.error-text {
  margin: 0;
  color: var(--danger);
}

.hint-box {
  border-radius: 18px;
  padding: 1rem;
  background: var(--accent-ghost);
  color: var(--text-soft);
}

.product-link {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}

.product-link:hover {
  text-decoration: underline;
}
</style>
