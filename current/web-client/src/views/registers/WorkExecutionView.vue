<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body page-shell">
        <!-- Форма-фильтр -->
        <div class="form-grid">
          <FormField label="Период с">
            <input v-model="register.formFilters.period_from" class="input" type="date" />
          </FormField>
          <FormField label="Период по">
            <input v-model="register.formFilters.period_to" class="input" type="date" />
          </FormField>
          <FormField label="Объект">
            <select v-model="register.formFilters.object_id" class="select">
              <option value="">Все</option>
              <option v-for="item in objects" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </FormField>
          <FormField label="Смета">
            <select v-model="register.formFilters.estimate_id" class="select">
              <option value="">Все</option>
              <option v-for="item in estimates" :key="item.id" :value="item.id">{{ item.number }}</option>
            </select>
          </FormField>
          <FormField label="Работа">
            <select v-model="register.formFilters.work_id" class="select">
              <option value="">Все</option>
              <option v-for="item in works" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </FormField>
          <FormField label="Заказчик">
            <select v-model="register.formFilters.customer_id" class="select">
              <option value="">Все</option>
              <option v-for="item in counterparties" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </FormField>
          <FormField label="Договор">
            <select v-model="register.formFilters.contract_id" class="select">
              <option value="">Все</option>
              <option v-for="item in contracts" :key="item.id" :value="item.id">{{ item.number }}</option>
            </select>
          </FormField>
          <FormField label="Группировка">
            <select v-model="register.formFilters.group_by" class="select">
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
          <button class="button button-primary" type="button" @click="register.applyFormFilters()">Показать</button>
        </div>

        <p v-if="register.error.value" class="page-subtitle" style="color: var(--danger)">{{ register.error.value }}</p>

        <!-- Командная панель -->
        <RegisterCommandBar
          :filterable="filterable"
          @refresh="register.loadItems()"
          @toggle-filter="filterable = !filterable"
          @settings="showSettings = true"
          @export="register.exportData($event)"
        />

        <!-- Таблица -->
        <DataTable
          :columns="displayColumns"
          :rows="register.rows.value as Record<string, unknown>[]"
          :loading="register.loading.value"
          :sortable="true"
          :sort="register.sort.value"
          :filterable="filterable"
          :filters="register.quickFilters"
          empty-text="Движений не найдено"
          row-key="id"
          @sort-change="register.onSortChange"
          @filter-change="register.onFilterChange"
          @row-dblclick="openDetail"
          @row-contextmenu="onContextMenu"
        >
          <template #cell-recorder="{ row }">
            <RouterLink
              v-if="(row as WorkExecutionItem).recorder_type === 'estimate'"
              :to="`/documents/estimates/${(row as WorkExecutionItem).recorder_id}`"
              class="registrar-link"
            >
              {{ `Смета ${(row as WorkExecutionItem).recorder_number || `#${(row as WorkExecutionItem).recorder_id}`}` }}
            </RouterLink>
            <RouterLink
              v-else-if="(row as WorkExecutionItem).recorder_type === 'daily_report'"
              :to="`/documents/daily-reports/${(row as WorkExecutionItem).recorder_id}`"
              class="registrar-link"
            >
              {{ `Рапорт ${(row as WorkExecutionItem).recorder_number || `#${(row as WorkExecutionItem).recorder_id}`}` }}
            </RouterLink>
            <span v-else class="muted">—</span>
          </template>
          <template #cell-quantity_income="{ row }">{{ fmt((row as WorkExecutionItem).quantity_income) }}</template>
          <template #cell-quantity_expense="{ row }">{{ fmt((row as WorkExecutionItem).quantity_expense) }}</template>
          <template #cell-sum_income="{ row }">{{ fmt((row as WorkExecutionItem).sum_income) }}</template>
          <template #cell-sum_expense="{ row }">{{ fmt((row as WorkExecutionItem).sum_expense) }}</template>
          <template #cell-balance_sum="{ row }">{{ fmt((row as WorkExecutionItem).balance_sum) }}</template>
        </DataTable>

        <!-- Пагинация -->
        <div v-if="register.pagination.pages > 1" class="pagination-row">
          <button class="button button-secondary" :disabled="register.page.value <= 1" @click="register.goToPage(register.page.value - 1)">←</button>
          <span class="page-info">Стр. {{ register.page.value }} из {{ register.pagination.pages }}</span>
          <button class="button button-secondary" :disabled="register.page.value >= register.pagination.pages" @click="register.goToPage(register.page.value + 1)">→</button>
        </div>

        <!-- Итоги -->
        <div class="metric-grid">
          <article class="panel metric-card inner-card">
            <div class="metric-label">Итого приход</div>
            <div class="metric-value">{{ fmt(register.totals.sum_income) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Итого расход</div>
            <div class="metric-value">{{ fmt(register.totals.sum_expense) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Баланс</div>
            <div class="metric-value">{{ fmt(register.totals.balance_sum) }}</div>
          </article>
        </div>
      </div>
    </section>

    <!-- Диалог настройки колонок -->
    <ListSettingsDialog
      :open="showSettings"
      :columns="defaultColumns"
      :states="columnStates"
      @apply="onApplyColumns"
      @reset="onResetColumns"
      @close="showSettings = false"
    />

    <!-- Контекстное меню -->
    <ContextMenu
      :open="ctxOpen"
      :items="ctxItems"
      :x="ctxX"
      :y="ctxY"
      @select="onCtxSelect"
      @close="ctxOpen = false"
    />

    <!-- Детализация -->
    <WorkExecutionDetailDialog
      :open="detailOpen"
      :parent-row="detailRow"
      :period-from="register.formFilters.period_from"
      :period-to="register.formFilters.period_to"
      @close="detailOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from '../../components/common/DataTable.vue'
import type { Column } from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import ContextMenu from '../../components/common/ContextMenu.vue'
import type { ContextMenuItem } from '../../components/common/ContextMenu.vue'
import RegisterCommandBar from '../../components/registers/RegisterCommandBar.vue'
import ListSettingsDialog from '../../components/documents/ListSettingsDialog.vue'
import WorkExecutionDetailDialog from './WorkExecutionDetailDialog.vue'
import { useWorksRegister, type RegisterColumn } from '../../composables/useWorksRegister'
import type { ColumnState } from '../../composables/useListSettings'
import { listEstimates } from '../../api/documents'
import { listReferences } from '../../api/references'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import type { ContractRecord, Counterparty, Estimate, ObjectRecord, WorkExecutionItem, WorkRecord } from '../../types/models'

const router = useRouter()
const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, computed(() => 'Регистр выполнения работ'), computed<HeaderAction[]>(() => []))

// === Колонки по умолчанию ===
const defaultColumns: RegisterColumn[] = [
  { key: 'period', label: 'Период', sortable: true, defaultVisible: true },
  { key: 'recorder', label: 'Регистратор', sortable: true, defaultVisible: true, filterable: true, filter: { type: 'text', placeholder: '№…' } },
  { key: 'customer_name', label: 'Заказчик', sortable: true, defaultVisible: true, filterable: true, filter: { type: 'select' } },
  { key: 'contract_number', label: 'Договор', sortable: true, defaultVisible: true, filterable: true, filter: { type: 'select' } },
  { key: 'object_name', label: 'Объект', sortable: true, defaultVisible: true, filterable: true, filter: { type: 'select' } },
  { key: 'estimate_number', label: 'Смета', sortable: true, defaultVisible: true, filterable: true, filter: { type: 'select' } },
  { key: 'work_name', label: 'Работа', sortable: true, defaultVisible: true, filterable: true, filter: { type: 'select' } },
  { key: 'quantity_income', label: 'Приход кол-во', sortable: true, defaultVisible: true },
  { key: 'quantity_expense', label: 'Расход кол-во', sortable: true, defaultVisible: true },
  { key: 'sum_income', label: 'Приход сумма', sortable: true, defaultVisible: false },
  { key: 'sum_expense', label: 'Расход сумма', sortable: true, defaultVisible: false },
  { key: 'balance_sum', label: 'Баланс', sortable: false, defaultVisible: true },
]

const register = useWorksRegister('works-register', defaultColumns)

// === UI state ===
const filterable = ref(false)
const showSettings = ref(false)
const ctxOpen = ref(false)
const ctxX = ref(0)
const ctxY = ref(0)
const ctxRow = ref<WorkExecutionItem | null>(null)
const detailOpen = ref(false)
const detailRow = ref<WorkExecutionItem | null>(null)

// === Reference data ===
const objects = ref<ObjectRecord[]>([])
const estimates = ref<Estimate[]>([])
const works = ref<WorkRecord[]>([])
const counterparties = ref<Counterparty[]>([])
const contracts = ref<ContractRecord[]>([])

// === Display columns: merge settings + dynamic filter options ===
const displayColumns = computed<Column[]>(() => {
  return register.effectiveColumns.value.map((col) => {
    const enriched: Column = { ...col }
    if (col.key === 'customer_name' && col.filter?.type === 'select') {
      enriched.filter = { type: 'select', options: counterparties.value.map(c => ({ value: String(c.id), label: c.name })) }
    } else if (col.key === 'contract_number' && col.filter?.type === 'select') {
      enriched.filter = { type: 'select', options: contracts.value.map(c => ({ value: String(c.id), label: c.number })) }
    } else if (col.key === 'object_name' && col.filter?.type === 'select') {
      enriched.filter = { type: 'select', options: objects.value.map(o => ({ value: String(o.id), label: o.name })) }
    } else if (col.key === 'estimate_number' && col.filter?.type === 'select') {
      enriched.filter = { type: 'select', options: estimates.value.map(e => ({ value: String(e.id), label: e.number })) }
    } else if (col.key === 'work_name' && col.filter?.type === 'select') {
      enriched.filter = { type: 'select', options: works.value.map(w => ({ value: String(w.id), label: w.name })) }
    }
    return enriched
  })
})

// === Column states for ListSettingsDialog ===
const columnStates = computed<ColumnState[]>(() => {
  return register.effectiveColumns.value.map(c => ({ key: c.key, visible: c.visible !== false }))
})

function onApplyColumns(states: ColumnState[]) {
  register.settings.saveColumns(states)
}

async function onResetColumns() {
  await register.settings.resetColumns()
}

// === Context menu ===
const ctxItems = computed<ContextMenuItem[]>(() => {
  if (!ctxRow.value) return []
  const items: ContextMenuItem[] = [
    { key: 'detail', label: 'Открыть детализацию', icon: '🔍' },
    { type: 'separator' },
  ]
  if (ctxRow.value.estimate_id) {
    items.push({ key: 'goto_estimate', label: 'Перейти к смете', icon: '→' })
  }
  if (ctxRow.value.recorder_type === 'daily_report') {
    items.push({ key: 'goto_daily_report', label: 'Перейти к дневному отчёту', icon: '→' })
  }
  items.push({ type: 'separator' })
  items.push({ key: 'settings', label: 'Настройка списка…', icon: '⚙' })
  return items
})

function onContextMenu(row: Record<string, unknown>, event: MouseEvent) {
  ctxRow.value = row as unknown as WorkExecutionItem
  ctxX.value = event.clientX
  ctxY.value = event.clientY
  ctxOpen.value = true
}

function onCtxSelect(key: string) {
  ctxOpen.value = false
  const row = ctxRow.value
  if (!row) return
  switch (key) {
    case 'detail':
      openDetail(row as unknown as Record<string, unknown>)
      break
    case 'goto_estimate':
      if (row.estimate_id) router.push(`/documents/estimates/${row.estimate_id}`)
      break
    case 'goto_daily_report':
      if (row.recorder_type === 'daily_report') router.push(`/documents/daily-reports/${row.recorder_id}`)
      break
    case 'settings':
      showSettings.value = true
      break
  }
}

function openDetail(row: Record<string, unknown>) {
  detailRow.value = row as unknown as WorkExecutionItem
  detailOpen.value = true
}

// === Helpers ===
function fmt(v: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v || 0)
}

// === Init ===
onMounted(async () => {
  try {
    const [objectResult, estimateResult, workResult, counterpartyResult, contractResult] = await Promise.all([
      listReferences('objects', { page_size: 100 }),
      listEstimates({ page_size: 100 }),
      listReferences('works', { page_size: 100 }),
      listReferences('counterparties', { page_size: 100 }),
      listReferences('contracts', { page_size: 100 }),
    ])
    objects.value = objectResult.data as ObjectRecord[]
    estimates.value = estimateResult.data as Estimate[]
    works.value = workResult.data as WorkRecord[]
    counterparties.value = counterpartyResult.data as Counterparty[]
    contracts.value = contractResult.data as ContractRecord[]
  } catch {
    // Не критично — фильтр-селекты будут пустые
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

.pagination-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
}

.page-info {
  font-size: 0.85rem;
  color: var(--text-soft, #666);
}
</style>
