<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body page-shell">
        <div class="form-grid">
          <FormField label="Период с">
            <input v-model="filters.period_from" class="input" type="date" />
          </FormField>
          <FormField label="Период по">
            <input v-model="filters.period_to" class="input" type="date" />
          </FormField>
          <FormField label="Объект">
            <select v-model="filters.object_id" class="select">
              <option value="">Все</option>
              <option v-for="item in objects" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </FormField>
          <FormField label="Смета">
            <select v-model="filters.estimate_id" class="select">
              <option value="">Все</option>
              <option v-for="item in estimates" :key="item.id" :value="item.id">{{ item.number }}</option>
            </select>
          </FormField>
          <FormField label="Работа">
            <select v-model="filters.work_id" class="select">
              <option value="">Все</option>
              <option v-for="item in works" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </FormField>
          <FormField label="Заказчик">
            <select v-model="filters.customer_id" class="select">
              <option value="">Все</option>
              <option v-for="item in counterparties" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </FormField>
          <FormField label="Договор">
            <select v-model="filters.contract_id" class="select">
              <option value="">Все</option>
              <option v-for="item in contracts" :key="item.id" :value="item.id">{{ item.number }}</option>
            </select>
          </FormField>
          <FormField label="Группировка">
            <select v-model="filters.group_by" class="select">
              <option value="">Без группировки</option>
              <option value="object">По объекту</option>
              <option value="estimate">По смете</option>
              <option value="work">По работе</option>
              <option value="customer">По заказчику</option>
              <option value="contract">По договору</option>
              <option value="object,estimate">Объект + смета</option>
              <option value="customer,contract">Заказчик + договор</option>
            </select>
          </FormField>
        </div>

        <div class="toolbar">
          <button class="button button-primary" type="button" @click="loadRegister">Показать</button>
        </div>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <DataTable :columns="columns" :rows="rows as Record<string, unknown>[]" :loading="loading" empty-text="Движений не найдено">
          <template #cell-recorder="{ row }">
            <RouterLink
              v-if="(row as unknown as WorkExecutionItem).recorder_type === 'estimate'"
              :to="`/documents/estimates/${(row as unknown as WorkExecutionItem).recorder_id}`"
              class="registrar-link"
            >
              {{ `Смета ${(row as unknown as WorkExecutionItem).recorder_number || `#${(row as unknown as WorkExecutionItem).recorder_id}`}` }}
            </RouterLink>
            <RouterLink
              v-else-if="(row as unknown as WorkExecutionItem).recorder_type === 'daily_report'"
              :to="`/documents/daily-reports/${(row as unknown as WorkExecutionItem).recorder_id}`"
              class="registrar-link"
            >
              {{ `Рапорт ${(row as unknown as WorkExecutionItem).recorder_number || `#${(row as unknown as WorkExecutionItem).recorder_id}`}` }}
            </RouterLink>
            <span v-else class="muted">—</span>
          </template>
          <template #cell-quantity_income="{ row }">{{ formatNumber((row as unknown as WorkExecutionItem).quantity_income) }}</template>
          <template #cell-quantity_expense="{ row }">{{ formatNumber((row as unknown as WorkExecutionItem).quantity_expense) }}</template>
          <template #cell-sum_income="{ row }">{{ formatNumber((row as unknown as WorkExecutionItem).sum_income) }}</template>
          <template #cell-sum_expense="{ row }">{{ formatNumber((row as unknown as WorkExecutionItem).sum_expense) }}</template>
          <template #cell-balance_sum="{ row }">{{ formatNumber((row as unknown as WorkExecutionItem).balance_sum) }}</template>
        </DataTable>

        <div class="metric-grid">
          <article class="panel metric-card inner-card">
            <div class="metric-label">Итого приход</div>
            <div class="metric-value">{{ formatNumber(totals.sum_income) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Итого расход</div>
            <div class="metric-value">{{ formatNumber(totals.sum_expense) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Баланс</div>
            <div class="metric-value">{{ formatNumber(totals.balance_sum) }}</div>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import { listEstimates } from '../../api/documents'
import { queryWorkExecution } from '../../api/registers'
import { listReferences } from '../../api/references'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import type { ContractRecord, Counterparty, Estimate, ObjectRecord, WorkExecutionItem, WorkRecord } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, computed(() => 'Регистр выполнения работ'), computed<HeaderAction[]>(() => []))

const rows = ref<WorkExecutionItem[]>([])
const loading = ref(false)
const error = ref('')
const objects = ref<ObjectRecord[]>([])
const estimates = ref<Estimate[]>([])
const works = ref<WorkRecord[]>([])
const counterparties = ref<Counterparty[]>([])
const contracts = ref<ContractRecord[]>([])
const totals = reactive({
  sum_income: 0,
  sum_expense: 0,
  balance_sum: 0,
})

const filters = reactive<{
  period_from: string
  period_to: string
  object_id: number | ''
  estimate_id: number | ''
  work_id: number | ''
  customer_id: number | ''
  contract_id: number | ''
  group_by: string
}>({
  period_from: '',
  period_to: '',
  object_id: '',
  estimate_id: '',
  work_id: '',
  customer_id: '',
  contract_id: '',
  group_by: '',
})

const columns = [
  { key: 'period', label: 'Период' },
  { key: 'recorder', label: 'Регистратор' },
  { key: 'customer_name', label: 'Заказчик' },
  { key: 'contract_number', label: 'Договор' },
  { key: 'object_name', label: 'Объект' },
  { key: 'estimate_number', label: 'Смета' },
  { key: 'work_name', label: 'Работа' },
  { key: 'quantity_income', label: 'Приход кол-во' },
  { key: 'quantity_expense', label: 'Расход кол-во' },
  { key: 'sum_income', label: 'Приход сумма' },
  { key: 'sum_expense', label: 'Расход сумма' },
  { key: 'balance_sum', label: 'Баланс' },
]

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value || 0)
}

async function loadOptions() {
  const [objectResult, estimateResult, workResult, counterpartyResult, contractResult] = await Promise.all([
    listReferences('objects', { page_size: 50 }),
    listEstimates({ page_size: 50 }),
    listReferences('works', { page_size: 50 }),
    listReferences('counterparties', { page_size: 50 }),
    listReferences('contracts', { page_size: 50 }),
  ])
  objects.value = objectResult.data as ObjectRecord[]
  estimates.value = estimateResult.data as Estimate[]
  works.value = workResult.data as WorkRecord[]
  counterparties.value = counterpartyResult.data as Counterparty[]
  contracts.value = contractResult.data as ContractRecord[]
}

async function loadRegister() {
  loading.value = true
  error.value = ''
  try {
    const response = await queryWorkExecution({
      page: 1,
      page_size: 50,
      period_from: filters.period_from,
      period_to: filters.period_to,
      object_id: filters.object_id,
      estimate_id: filters.estimate_id,
      work_id: filters.work_id,
      customer_id: filters.customer_id,
      contract_id: filters.contract_id,
      group_by: filters.group_by,
    })
    rows.value = response.data.items
    totals.sum_income = response.data.totals.sum_income
    totals.sum_expense = response.data.totals.sum_expense
    totals.balance_sum = response.data.totals.balance_sum
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить регистр'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    await loadOptions()
    await loadRegister()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  }
})
</script>

<style scoped>
.inner-card {
  background: rgba(255, 255, 255, 0.7);
}

.registrar-link {
  color: var(--primary, #b24c2d);
  text-decoration: none;
  font-weight: 600;
}

.registrar-link:hover {
  text-decoration: underline;
}

.muted {
  color: var(--text-soft, #888);
}
</style>
