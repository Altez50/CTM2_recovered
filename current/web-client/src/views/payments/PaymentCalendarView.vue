<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body page-shell">
        <div class="form-grid">
          <FormField label="Период с">
            <input v-model="filters.date_from" class="input" type="date" />
          </FormField>
          <FormField label="Период по">
            <input v-model="filters.date_to" class="input" type="date" />
          </FormField>
          <FormField label="Объект">
            <select v-model="filters.object_id" class="select">
              <option value="">Все</option>
              <option v-for="item in objects" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </FormField>
          <FormField label="Контрагент">
            <select v-model="filters.counterparty_id" class="select">
              <option value="">Все</option>
              <option v-for="item in counterparties" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </FormField>
          <FormField label="Направление">
            <select v-model="filters.direction" class="select">
              <option value="">Все</option>
              <option value="incoming">Поступления</option>
              <option value="outgoing">Платежи</option>
            </select>
          </FormField>
          <FormField label="Категория">
            <select v-model="filters.category" class="select">
              <option value="">Все</option>
              <option value="customer_stage">Этап заказчика</option>
              <option value="payroll">Зарплата</option>
              <option value="supplier">Поставщик</option>
              <option value="tax">Налоги</option>
              <option value="other">Прочее</option>
            </select>
          </FormField>
          <FormField label="Группировка">
            <select v-model="filters.group_by" class="select">
              <option value="">Без группировки</option>
              <option value="counterparty">По контрагенту</option>
              <option value="object">По объекту</option>
              <option value="contract">По договору</option>
              <option value="category">По категории</option>
              <option value="direction">По направлению</option>
            </select>
          </FormField>
        </div>

        <div class="toolbar">
          <button class="button button-primary" type="button" @click="loadAll">Показать</button>
        </div>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <DataTable :columns="columns" :rows="registerRows as Record<string, unknown>[]" :loading="loading" empty-text="Движений не найдено">
          <template #cell-planned_amount="{ row }">{{ formatNumber((row as unknown as PaymentRegisterItem).planned_amount) }}</template>
          <template #cell-fact_amount="{ row }">{{ formatNumber((row as unknown as PaymentRegisterItem).fact_amount) }}</template>
          <template #cell-balance="{ row }">{{ formatNumber((row as unknown as PaymentRegisterItem).balance) }}</template>
          <template #cell-is_overdue="{ row }">
            <span v-if="(row as unknown as PaymentRegisterItem).is_overdue" class="status-pill" style="background: var(--danger); color: white">Просрочен</span>
            <span v-else-if="(row as unknown as PaymentRegisterItem).is_paid" class="status-pill posted">Оплачен</span>
          </template>
        </DataTable>

        <div class="metric-grid">
          <article class="panel metric-card inner-card">
            <div class="metric-label">Поступления (план)</div>
            <div class="metric-value">{{ formatNumber(totals.incoming_planned) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Платежи (план)</div>
            <div class="metric-value">{{ formatNumber(totals.outgoing_planned) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Чистый поток</div>
            <div class="metric-value" :style="{ color: totals.net_flow >= 0 ? 'var(--success)' : 'var(--danger)' }">{{ formatNumber(totals.net_flow) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Поступления (факт)</div>
            <div class="metric-value">{{ formatNumber(totals.incoming_fact) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Платежи (факт)</div>
            <div class="metric-value">{{ formatNumber(totals.outgoing_fact) }}</div>
          </article>
        </div>

        <h3>Кассовый поток по дням</h3>
        <div v-if="cashflow.length" class="cashflow-grid">
          <div
            v-for="day in cashflow"
            :key="day.date"
            :class="['cashflow-day', { deficit: day.is_deficit, surplus: !day.is_deficit && day.cumulative_balance > 0 }]"
          >
            <div class="cashflow-date">{{ formatDate(day.date) }}</div>
            <div class="cashflow-row"><span class="muted">+{{ formatNumber(day.incoming_planned) }}</span></div>
            <div class="cashflow-row"><span class="muted">-{{ formatNumber(day.outgoing_planned) }}</span></div>
            <div class="cashflow-balance" :style="{ color: day.cumulative_balance < 0 ? 'var(--danger)' : 'var(--success)' }">
              {{ formatNumber(day.cumulative_balance) }}
            </div>
          </div>
        </div>
        <p v-else class="muted">Нет данных по дням. Выберите период и нажмите «Показать».</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import { queryCashflow, queryPaymentRegister } from '../../api/payments'
import { listReferences } from '../../api/references'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import type { CashflowDayItem, Counterparty, ObjectRecord, PaymentRegisterItem, PaymentRegisterTotals } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, computed(() => 'Платёжный календарь'), computed<HeaderAction[]>(() => []))

const registerRows = ref<PaymentRegisterItem[]>([])
const cashflow = ref<CashflowDayItem[]>([])
const loading = ref(false)
const error = ref('')
const objects = ref<ObjectRecord[]>([])
const counterparties = ref<Counterparty[]>([])

const totals = reactive<PaymentRegisterTotals>({
  incoming_planned: 0,
  outgoing_planned: 0,
  incoming_fact: 0,
  outgoing_fact: 0,
  net_flow: 0,
})

const today = new Date().toISOString().slice(0, 10)
const monthStart = today.slice(0, 8) + '01'

const filters = reactive({
  date_from: monthStart,
  date_to: today,
  object_id: '' as number | '',
  counterparty_id: '' as number | '',
  direction: '',
  category: '',
  group_by: '',
})

const columns = [
  { key: 'planned_date', label: 'Дата план' },
  { key: 'direction', label: 'Направление' },
  { key: 'category', label: 'Категория' },
  { key: 'counterparty_name', label: 'Контрагент' },
  { key: 'object_name', label: 'Объект' },
  { key: 'contract_number', label: 'Договор' },
  { key: 'planned_amount', label: 'План' },
  { key: 'fact_amount', label: 'Факт' },
  { key: 'balance', label: 'Остаток' },
  { key: 'is_overdue', label: 'Статус' },
]

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value || 0)
}

function formatDate(value: string) {
  const [y, m, d] = value.split('-').map(Number)
  if (!y || !m || !d) return value
  return new Date(y, m - 1, d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
}

async function loadOptions() {
  const [objRes, cpRes] = await Promise.all([
    listReferences('objects', { page_size: 100 }),
    listReferences('counterparties', { page_size: 100 }),
  ])
  objects.value = objRes.data as ObjectRecord[]
  counterparties.value = cpRes.data as Counterparty[]
}

async function loadRegister() {
  const res = await queryPaymentRegister({
    page: 1,
    page_size: 100,
    period_from: filters.date_from,
    period_to: filters.date_to,
    object_id: filters.object_id,
    counterparty_id: filters.counterparty_id,
    direction: filters.direction,
    category: filters.category,
    group_by: filters.group_by,
  })
  registerRows.value = res.data.items
  totals.incoming_planned = res.data.totals.incoming_planned
  totals.outgoing_planned = res.data.totals.outgoing_planned
  totals.incoming_fact = res.data.totals.incoming_fact
  totals.outgoing_fact = res.data.totals.outgoing_fact
  totals.net_flow = res.data.totals.net_flow
}

async function loadCashflow() {
  const res = await queryCashflow({
    date_from: filters.date_from,
    date_to: filters.date_to,
    object_id: filters.object_id || null,
    counterparty_id: filters.counterparty_id || null,
  })
  cashflow.value = res.data
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadRegister(), loadCashflow()])
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    await loadOptions()
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  }
})
</script>

<style scoped>
.inner-card {
  background: rgba(255, 255, 255, 0.7);
}
.cashflow-grid {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
}
.cashflow-day {
  min-width: 110px;
  padding: 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border, #ddd);
  background: var(--panel-bg, #fff);
  text-align: center;
}
.cashflow-day.deficit {
  border-color: var(--danger, #e53e3e);
  background: rgba(229, 62, 62, 0.08);
}
.cashflow-day.surplus {
  border-color: var(--success, #38a169);
  background: rgba(56, 161, 105, 0.06);
}
.cashflow-date {
  font-weight: 600;
  font-size: 0.85rem;
  margin-bottom: 0.25rem;
}
.cashflow-row {
  font-size: 0.8rem;
}
.cashflow-balance {
  font-weight: 700;
  font-size: 0.9rem;
  margin-top: 0.25rem;
}
</style>
