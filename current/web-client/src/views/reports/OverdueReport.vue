<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="form-grid">
          <FormField label="На дату">
            <input v-model="filters.date" class="input" type="date" />
          </FormField>
          <FormField label="Организация">
            <select v-model="filters.organization_id" class="select">
              <option :value="''">Все</option>
              <option v-for="o in organizations" :key="o.id" :value="o.id">{{ o.name }}</option>
            </select>
          </FormField>
        </div>

        <div class="toolbar">
          <button class="button button-primary" type="button" :disabled="loading" @click="load">Сформировать</button>
          <button class="button button-secondary" type="button" :disabled="!rows.length" @click="exportCsv">Выгрузить в CSV</button>
          <div class="toolbar-grow"></div>
          <span class="metric-card" v-if="rows.length">
            Просроч. дебиторка: <strong>{{ formatMoney(totals.rec) }}</strong> • кредиторка: <strong>{{ formatMoney(totals.pay) }}</strong>
          </span>
        </div>

        <p v-if="error" class="message-banner message-error">{{ error }}</p>

        <DataTable :columns="columns" :rows="rows as Record<string, unknown>[]" :loading="loading" empty-text="Нет просроченной задолженности.">
          <template #cell-direction="{ row }">
            <span :class="['status-pill', (row as unknown as OverdueItem).direction === 'receivable' ? 'posted' : 'draft']">
              {{ (row as unknown as OverdueItem).direction === 'receivable' ? 'Дебиторка (нам должны)' : 'Кредиторка (мы должны)' }}
            </span>
          </template>
          <template #cell-days_overdue="{ row }">{{ (row as unknown as OverdueItem).days_overdue }}</template>
          <template #cell-overdue_amount="{ row }">
            <strong>{{ formatMoney((row as unknown as OverdueItem).overdue_amount) }}</strong>
          </template>
        </DataTable>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import { listReferences } from '../../api/references'
import { getOverdue } from '../../api/settlements'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { downloadCsv } from '../../utils/reportExport'
import type { OrganizationRecord, OverdueItem } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, computed(() => 'Отчёт: Просроченная задолженность'), computed(() => []))

const rows = ref<OverdueItem[]>([])
const loading = ref(false)
const error = ref('')
const organizations = ref<OrganizationRecord[]>([])

const filters = reactive({ date: new Date().toISOString().slice(0, 10), organization_id: '' as number | '' })

const columns = [
  { key: 'organization_name', label: 'Организация' },
  { key: 'counterparty_name', label: 'Контрагент' },
  { key: 'contract_number', label: 'Договор' },
  { key: 'direction', label: 'Тип долга' },
  { key: 'period', label: 'Срок (от)' },
  { key: 'days_overdue', label: 'Дней просрочки' },
  { key: 'overdue_amount', label: 'Сумма просрочки' },
]

const totals = computed(() => rows.value.reduce(
  (acc, r) => {
    if (r.direction === 'receivable') acc.rec += r.overdue_amount
    else acc.pay += r.overdue_amount
    return acc
  },
  { rec: 0, pay: 0 },
))

function formatMoney(value: number) {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getOverdue({ date: filters.date || null })
    const all = res.data
    const orgFilter = filters.organization_id === '' ? null : Number(filters.organization_id)
    rows.value = orgFilter === null ? all : all.filter((r) => r.organization_id === orgFilter)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  downloadCsv(
    `Просрочка_${filters.date}`,
    ['Организация', 'Контрагент', 'Договор', 'Тип долга', 'Срок (от)', 'Дней просрочки', 'Сумма просрочки'],
    rows.value.map((r) => [
      r.organization_name,
      r.counterparty_name,
      r.contract_number,
      r.direction === 'receivable' ? 'Дебиторка' : 'Кредиторка',
      r.period,
      r.days_overdue,
      r.overdue_amount,
    ]),
  )
}

onMounted(async () => {
  try {
    const orgRes = await listReferences('organizations', { page_size: 200 })
    organizations.value = orgRes.data as OrganizationRecord[]
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки справочников'
  }
})
</script>

<style scoped>
.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem 1rem; margin-bottom: 1rem; }
.toolbar { align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
.message-error { background: var(--danger-bg, #fde8e8); color: var(--danger, #b00020); padding: 0.5rem 0.75rem; border-radius: 4px; }
</style>
