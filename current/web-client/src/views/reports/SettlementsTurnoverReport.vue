<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="form-grid">
          <FormField label="Период с">
            <input v-model="filters.date_from" class="input" type="date" />
          </FormField>
          <FormField label="Период по">
            <input v-model="filters.date_to" class="input" type="date" />
          </FormField>
          <FormField label="Организация">
            <select v-model="filters.organization_id" class="select">
              <option :value="''">Все</option>
              <option v-for="o in organizations" :key="o.id" :value="o.id">{{ o.name }}</option>
            </select>
          </FormField>
          <FormField label="Контрагент">
            <select v-model="filters.counterparty_id" class="select">
              <option :value="''">Все</option>
              <option v-for="c in counterparties" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </FormField>
          <FormField label="Договор">
            <select v-model="filters.contract_id" class="select">
              <option :value="''">Все</option>
              <option v-for="c in contracts" :key="c.id" :value="c.id">{{ c.number }}</option>
            </select>
          </FormField>
        </div>

        <div class="toolbar">
          <button class="button button-primary" type="button" :disabled="loading" @click="load">Сформировать</button>
          <button class="button button-secondary" type="button" :disabled="!rows.length" @click="exportCsv">Выгрузить в CSV</button>
          <div class="toolbar-grow"></div>
          <span class="metric-card" v-if="rows.length">
            Долг покупателей: <strong>{{ formatMoney(totals.recClosing) }}</strong> • Долг поставщикам: <strong>{{ formatMoney(totals.payClosing) }}</strong>
            • Авансы покупателей: <strong>{{ formatMoney(totals.customerAdvance) }}</strong> • Авансы поставщикам: <strong>{{ formatMoney(totals.supplierAdvance) }}</strong>
          </span>
        </div>

        <p v-if="error" class="message-banner message-error">{{ error }}</p>
        <p class="muted">Долг и аванс показаны отдельно по организации, контрагенту, договору и объекту. Зачет выполняется в том же разрезе при проведении поставки.</p>

        <DataTable :columns="columns" :rows="rows as Record<string, unknown>[]" :loading="loading" empty-text="Нет данных. Задайте период и нажмите «Сформировать».">
          <template #cell-receivable_opening="{ row }">{{ formatMoney((row as unknown as SettlementTurnoverRow).receivable_opening) }}</template>
          <template #cell-receivable_accrual_turnover="{ row }">{{ formatMoney((row as unknown as SettlementTurnoverRow).receivable_accrual_turnover) }}</template>
          <template #cell-receivable_payment_turnover="{ row }">{{ formatMoney((row as unknown as SettlementTurnoverRow).receivable_payment_turnover) }}</template>
          <template #cell-receivable_closing="{ row }">
            <strong>{{ formatMoney((row as unknown as SettlementTurnoverRow).receivable_closing) }}</strong>
          </template>
          <template #cell-payable_opening="{ row }">{{ formatMoney((row as unknown as SettlementTurnoverRow).payable_opening) }}</template>
          <template #cell-payable_accrual_turnover="{ row }">{{ formatMoney((row as unknown as SettlementTurnoverRow).payable_accrual_turnover) }}</template>
          <template #cell-payable_payment_turnover="{ row }">{{ formatMoney((row as unknown as SettlementTurnoverRow).payable_payment_turnover) }}</template>
          <template #cell-payable_closing="{ row }">
            <strong>{{ formatMoney((row as unknown as SettlementTurnoverRow).payable_closing) }}</strong>
          </template>
          <template #cell-customer_advance_opening="{ row }">{{ formatMoney(Number(row.customer_advance_opening)) }}</template>
          <template #cell-customer_advance_closing="{ row }">{{ formatMoney(Number(row.customer_advance_closing)) }}</template>
          <template #cell-supplier_advance_opening="{ row }">{{ formatMoney(Number(row.supplier_advance_opening)) }}</template>
          <template #cell-supplier_advance_closing="{ row }">{{ formatMoney(Number(row.supplier_advance_closing)) }}</template>
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
import { getSettlementsTurnover } from '../../api/settlements'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { downloadCsv } from '../../utils/reportExport'
import type { ContractRecord, Counterparty, OrganizationRecord, SettlementTurnoverRow } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, computed(() => 'Отчёт: Оборотно-сальдовая ведомость'), computed(() => []))

const rows = ref<SettlementTurnoverRow[]>([])
const loading = ref(false)
const error = ref('')
const organizations = ref<OrganizationRecord[]>([])
const counterparties = ref<Counterparty[]>([])
const contracts = ref<ContractRecord[]>([])

const filters = reactive({
  date_from: new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10),
  date_to: new Date().toISOString().slice(0, 10),
  organization_id: '' as number | '',
  counterparty_id: '' as number | '',
  contract_id: '' as number | '',
})

const columns = [
  { key: 'organization_name', label: 'Организация' },
  { key: 'counterparty_name', label: 'Контрагент' },
  { key: 'contract_number', label: 'Договор' },
  { key: 'object_name', label: 'Объект' },
  { key: 'receivable_opening', label: 'Дт сальдо нач.' },
  { key: 'receivable_accrual_turnover', label: 'Дт оборот (начисл.)' },
  { key: 'receivable_payment_turnover', label: 'Дт оборот (оплата)' },
  { key: 'receivable_closing', label: 'Дт сальдо кон.' },
  { key: 'payable_opening', label: 'Кт сальдо нач.' },
  { key: 'payable_accrual_turnover', label: 'Кт оборот (начисл.)' },
  { key: 'payable_payment_turnover', label: 'Кт оборот (оплата)' },
  { key: 'payable_closing', label: 'Кт сальдо кон.' },
  { key: 'customer_advance_opening', label: 'Аванс покупателя нач.' },
  { key: 'customer_advance_closing', label: 'Аванс покупателя кон.' },
  { key: 'supplier_advance_opening', label: 'Аванс поставщику нач.' },
  { key: 'supplier_advance_closing', label: 'Аванс поставщику кон.' },
]

const totals = computed(() => rows.value.reduce(
  (acc, r) => {
    acc.recClosing += r.receivable_closing
    acc.payClosing += r.payable_closing
    acc.customerAdvance += r.customer_advance_closing
    acc.supplierAdvance += r.supplier_advance_closing
    return acc
  },
  { recClosing: 0, payClosing: 0, customerAdvance: 0, supplierAdvance: 0 },
))

function formatMoney(value: number) {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getSettlementsTurnover({
      date_from: filters.date_from,
      date_to: filters.date_to,
      organization_id: filters.organization_id === '' ? null : Number(filters.organization_id),
      counterparty_id: filters.counterparty_id === '' ? null : Number(filters.counterparty_id),
      contract_id: filters.contract_id === '' ? null : Number(filters.contract_id),
    })
    rows.value = res.data
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  downloadCsv(
    `ОСВ_взаиморасчеты_${filters.date_from}_${filters.date_to}`,
    columns.map(c => c.label),
    rows.value.map(r => columns.map(c => r[c.key as keyof SettlementTurnoverRow])),
  )
}

onMounted(async () => {
  try {
    const [orgRes, cpRes, ctRes] = await Promise.all([
      listReferences('organizations', { page_size: 200 }),
      listReferences('counterparties', { page_size: 200 }),
      listReferences('contracts', { page_size: 500 }),
    ])
    organizations.value = orgRes.data as OrganizationRecord[]
    counterparties.value = cpRes.data as Counterparty[]
    contracts.value = ctRes.data as ContractRecord[]
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
