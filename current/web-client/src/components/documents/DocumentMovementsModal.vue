<template>
  <Modal :open="open" size="full" title="Движения документа по регистрам" @close="$emit('close')">
    <div class="modal-stack">
      <div v-if="loading" class="picker-state">Загрузка…</div>
      <div v-else-if="error" class="message-banner message-error">{{ error }}</div>
      <template v-else-if="data">
        <div class="mov-header">
          <strong>Документ №{{ data.document.number || data.document.id }}</strong>
          от {{ data.document.date || '—' }} •
          <span :class="['status-pill', data.document.is_posted ? 'posted' : 'draft']">
            {{ data.document.is_posted ? 'Проведён' : 'Не проведён' }}
          </span>
          • Сумма с НДС: {{ formatMoney(data.document.sum_with_vat) }}
        </div>

        <div class="mov-section">
          <h4>Склад — inventory_register</h4>
          <div v-if="!data.inventory.length" class="empty">Движений по складу нет.</div>
          <DataTable v-else :columns="invColumns" :rows="data.inventory as Record<string, unknown>[]" empty-text="">
            <template #cell-quantity_income="{ row }">{{ formatQty((row as unknown as InventoryMovementDocRow).quantity_income) }}</template>
            <template #cell-quantity_expense="{ row }">{{ formatQty((row as unknown as InventoryMovementDocRow).quantity_expense) }}</template>
            <template #cell-sum_income="{ row }">{{ formatMoney((row as unknown as InventoryMovementDocRow).sum_income) }}</template>
            <template #cell-sum_expense="{ row }">{{ formatMoney((row as unknown as InventoryMovementDocRow).sum_expense) }}</template>
          </DataTable>
        </div>

        <div class="mov-section">
          <h4>Взаиморасчеты — mutual_settlements_register</h4>
          <div v-if="!data.settlements.length" class="empty">Движений по взаиморасчетам нет.</div>
          <DataTable v-else :columns="setColumns" :rows="data.settlements as Record<string, unknown>[]" empty-text="">
            <template #cell-direction="{ row }">
              <span :class="['status-pill', (row as unknown as SettlementMovementDocRow).direction === 'receivable' ? 'posted' : 'draft']">
                {{ (row as unknown as SettlementMovementDocRow).direction === 'receivable' ? 'Дебиторка' : 'Кредиторка' }}
              </span>
            </template>
            <template #cell-accrual_amount="{ row }">{{ formatMoney((row as unknown as SettlementMovementDocRow).accrual_amount) }}</template>
            <template #cell-payment_amount="{ row }">{{ formatMoney((row as unknown as SettlementMovementDocRow).payment_amount) }}</template>
            <template #cell-planned_amount="{ row }">{{ formatMoney((row as unknown as SettlementMovementDocRow).planned_amount) }}</template>
          </DataTable>
        </div>

        <div class="mov-totals">
          <strong>ИТОГИ:</strong>
          Склад — приход {{ formatMoney(data.totals.sum_income) }} / расход {{ formatMoney(data.totals.sum_expense) }} •
          Взаиморасчеты — начислено {{ formatMoney(data.totals.accrual_amount) }} / оплачено {{ formatMoney(data.totals.payment_amount) }}
        </div>

        <div class="toolbar">
          <button class="button button-secondary" type="button" :disabled="!hasRows" @click="exportCsv">Выгрузить в CSV</button>
        </div>
      </template>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DataTable from '../common/DataTable.vue'
import Modal from '../common/Modal.vue'
import { getDocumentMovements } from '../../api/goods'
import { downloadCsv } from '../../utils/reportExport'
import type { DocumentMovements, GoodsKind, InventoryMovementDocRow, SettlementMovementDocRow } from '../../types/models'

const props = defineProps<{ open: boolean; kind: GoodsKind; documentId: number | null }>()
defineEmits<{ close: [] }>()

const data = ref<DocumentMovements | null>(null)
const loading = ref(false)
const error = ref('')

const invColumns = [
  { key: 'line_number', label: '№' },
  { key: 'period', label: 'Период' },
  { key: 'material_code', label: 'Код' },
  { key: 'material_name', label: 'Материал' },
  { key: 'object_name', label: 'Объект' },
  { key: 'unit_name', label: 'Ед.' },
  { key: 'quantity_income', label: 'Приход (кол-во)' },
  { key: 'quantity_expense', label: 'Расход (кол-во)' },
  { key: 'sum_income', label: 'Сумма прихода' },
  { key: 'sum_expense', label: 'Сумма расхода' },
]

const setColumns = [
  { key: 'line_number', label: '№' },
  { key: 'period', label: 'Период' },
  { key: 'direction', label: 'Направление' },
  { key: 'accrual_amount', label: 'Начислено' },
  { key: 'payment_amount', label: 'Оплачено' },
  { key: 'planned_amount', label: 'Планово' },
  { key: 'organization_name', label: 'Организация' },
  { key: 'counterparty_name', label: 'Контрагент' },
  { key: 'contract_number', label: 'Договор' },
]

const hasRows = computed(() => Boolean(data.value && (data.value.inventory.length || data.value.settlements.length)))

function formatMoney(value: number) {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0))
}
function formatQty(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 4 }).format(Number(value || 0))
}

async function load() {
  if (props.documentId == null) return
  loading.value = true
  error.value = ''
  try {
    const res = await getDocumentMovements(props.kind, props.documentId)
    data.value = res.data
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  if (!data.value) return
  downloadCsv(
    `movements_${data.value.document.kind}_${data.value.document.id}`,
    ['Секция', '№', 'Период', 'Материал/Направление', 'Приход кол-во', 'Расход кол-во', 'Сумма прихода', 'Сумма расхода', 'Начислено', 'Оплачено'],
    [
      ...data.value.inventory.map((r) => ['Склад', r.line_number, r.period, r.material_name, r.quantity_income, r.quantity_expense, r.sum_income, r.sum_expense, '', '']),
      ...data.value.settlements.map((r) => ['Взаиморасчеты', r.line_number, r.period, r.direction, '', '', '', '', r.accrual_amount, r.payment_amount]),
    ],
  )
}

watch(() => [props.open, props.documentId], ([open]) => {
  if (open) load()
})
</script>

<style scoped>
.mov-header { margin-bottom: 0.75rem; }
.mov-section { margin-bottom: 1rem; }
.mov-section h4 { margin: 0 0 0.4rem; }
.mov-totals { padding: 0.5rem 0.75rem; background: var(--panel-bg, #f5f5f5); border-radius: 4px; margin-top: 0.5rem; }
.empty { color: var(--muted, #888); padding: 0.5rem 0; }
.message-error { background: var(--danger-bg, #fde8e8); color: var(--danger, #b00020); padding: 0.5rem 0.75rem; border-radius: 4px; }
.picker-state { padding: 1rem; color: var(--muted, #888); }
</style>
