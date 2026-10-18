<template>
  <div class="page-shell">
    <section class="metric-grid">
      <article class="panel metric-card">
        <RouterLink class="metric-label metric-label-link" to="/documents/estimates">Сметы</RouterLink>
        <div class="metric-value">{{ summary?.documents.estimates ?? '—' }}</div>
      </article>
      <article class="panel metric-card">
        <RouterLink class="metric-label metric-label-link" to="/documents/daily-reports">Отчёты прораба</RouterLink>
        <div class="metric-value">{{ summary?.documents.daily_reports ?? '—' }}</div>
      </article>
      <article class="panel metric-card">
        <RouterLink class="metric-label metric-label-link" to="/documents/timesheets">Табели</RouterLink>
        <div class="metric-value">{{ summary?.documents.timesheets ?? '—' }}</div>
      </article>
      <article class="panel metric-card">
        <div class="metric-label">Приход по регистру</div>
        <div class="metric-value">{{ formatNumber(summary?.register_totals.sum_income) }}</div>
      </article>
      <article class="panel metric-card">
        <div class="metric-label">Расход по регистру</div>
        <div class="metric-value">{{ formatNumber(summary?.register_totals.sum_expense) }}</div>
      </article>
    </section>

    <section class="panel">
      <div class="panel-body">
        <h2 class="page-title" style="font-size: 1.25rem">Справочники</h2>
        <div class="metric-grid">
          <article v-for="item in referenceCards" :key="item.label" class="panel metric-card inner-card">
            <RouterLink class="metric-label metric-label-link" :to="item.to">{{ item.label }}</RouterLink>
            <div class="metric-value">{{ summary?.references[item.key] ?? '—' }}</div>
          </article>
        </div>
      </div>
    </section>

    <section v-if="error" class="panel">
      <div class="panel-body">
        <strong>Не удалось загрузить сводку.</strong>
        <p class="page-subtitle">{{ error }}</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { fetchDashboardSummary } from '../api/system'
import { useHeaderBar } from '../composables/useHeaderBar'
import type { HeaderAction } from '../stores/headerBar'
import type { DashboardSummary } from '../types/models'

const props = defineProps<{ tabId?: string }>()

const headerActions = computed<HeaderAction[]>(() => [
  { key: 'estimate', icon: '+', title: 'Новая смета', to: '/documents/estimates/new' },
  { key: 'report', icon: '+', title: 'Новый отчет', variant: 'primary', to: '/documents/daily-reports/new' },
  { key: 'timesheet', icon: '+', title: 'Новый табель', to: '/documents/timesheets/new' },
])
useHeaderBar(props.tabId, computed(() => 'Рабочее место'), headerActions)

const summary = ref<DashboardSummary | null>(null)
const error = ref('')

const referenceCards = computed(() => [
  { key: 'counterparties', label: 'Контрагенты', to: '/references/counterparties' },
  { key: 'objects', label: 'Объекты', to: '/references/objects' },
  { key: 'works', label: 'Работы', to: '/references/works' },
  { key: 'persons', label: 'Физлица', to: '/references/persons' },
  { key: 'organizations', label: 'Организации', to: '/references/organizations' },
])

function formatNumber(value?: number) {
  if (value === undefined) {
    return '—'
  }
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 2,
  }).format(value)
}

onMounted(async () => {
  try {
    const response = await fetchDashboardSummary()
    summary.value = response.data
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  }
})
</script>

<style scoped>
.inner-card {
  background: rgba(255, 255, 255, 0.7);
}

.metric-label-link {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  text-decoration: underline;
  text-decoration-color: transparent;
  text-underline-offset: 0.14em;
  transition:
    color 140ms ease,
    text-decoration-color 140ms ease;
}

.metric-label-link:hover,
.metric-label-link:focus-visible {
  color: var(--accent);
  text-decoration-color: currentColor;
}

.metric-label-link:focus-visible {
  outline: 2px solid rgba(178, 76, 45, 0.24);
  outline-offset: 3px;
  border-radius: 8px;
}
</style>
