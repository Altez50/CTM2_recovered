<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="form-grid">
          <FormField label="На дату">
            <input v-model="filters.date" class="input" type="date" />
          </FormField>
          <FormField label="Объект">
            <select v-model="filters.object_id" class="select">
              <option :value="''">Все объекты</option>
              <option v-for="o in objects" :key="o.id" :value="o.id">{{ o.name }}</option>
            </select>
          </FormField>
          <FormField label="Материал">
            <select v-model="filters.material_id" class="select">
              <option :value="''">Все материалы</option>
              <option v-for="m in materials" :key="m.id" :value="m.id">{{ m.code }} {{ m.name }}</option>
            </select>
          </FormField>
        </div>

        <div class="toolbar">
          <button class="button button-primary" type="button" :disabled="loading" @click="load">Показать</button>
          <button class="button button-secondary" type="button" :disabled="!rows.length" @click="exportCsv">Выгрузить в CSV</button>
          <div class="toolbar-grow"></div>
          <span class="metric-card" v-if="rows.length">
            Строк: <strong>{{ rows.length }}</strong> • Сумма прихода: <strong>{{ formatMoney(totalSum) }}</strong>
          </span>
        </div>

        <p v-if="error" class="message-banner message-error">{{ error }}</p>

        <DataTable :columns="columns" :rows="rows as Record<string, unknown>[]" :loading="loading" empty-text="Нет данных. Задайте параметры и нажмите «Показать».">
          <template #cell-quantity_balance="{ row }">
            <span :class="{ 'balance-negative': (row as unknown as InventoryBalanceItem).quantity_balance < 0 }">
              {{ formatQty((row as unknown as InventoryBalanceItem).quantity_balance) }}
            </span>
          </template>
          <template #cell-sum_income="{ row }">{{ formatMoney((row as unknown as InventoryBalanceItem).sum_income) }}</template>
          <template #cell-average_price="{ row }">{{ formatMoney((row as unknown as InventoryBalanceItem).average_price) }}</template>
          <template #cell-quantity_income="{ row }">{{ formatQty((row as unknown as InventoryBalanceItem).quantity_income) }}</template>
          <template #cell-quantity_expense="{ row }">{{ formatQty((row as unknown as InventoryBalanceItem).quantity_expense) }}</template>
        </DataTable>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import { getInventoryBalances } from '../../api/goods'
import { listReferences } from '../../api/references'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { downloadCsv } from '../../utils/reportExport'
import type { InventoryBalanceItem, MaterialRecord, ObjectRecord } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, computed(() => 'Отчёт: Остатки ТМЦ'), computed(() => []))

const rows = ref<InventoryBalanceItem[]>([])
const loading = ref(false)
const error = ref('')
const objects = ref<ObjectRecord[]>([])
const materials = ref<MaterialRecord[]>([])

const filters = reactive({ date: new Date().toISOString().slice(0, 10), object_id: '' as number | '', material_id: '' as number | '' })

const columns = [
  { key: 'material_code', label: 'Код' },
  { key: 'material_name', label: 'Наименование' },
  { key: 'object_name', label: 'Объект' },
  { key: 'unit_name', label: 'Ед.' },
  { key: 'quantity_income', label: 'Приход' },
  { key: 'quantity_expense', label: 'Расход' },
  { key: 'quantity_balance', label: 'Остаток' },
  { key: 'sum_income', label: 'Сумма прихода' },
  { key: 'average_price', label: 'Ср. цена' },
]

const totalSum = computed(() => rows.value.reduce((s, r) => s + (r.sum_income || 0), 0))

function formatMoney(value: number) {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0))
}
function formatQty(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 4 }).format(Number(value || 0))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getInventoryBalances({
      date: filters.date || undefined,
      object_id: filters.object_id === '' ? null : Number(filters.object_id),
      material_id: filters.material_id === '' ? null : Number(filters.material_id),
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
    `Остатки_ТМЦ_${filters.date}`,
    ['Код', 'Наименование', 'Объект', 'Ед.', 'Приход', 'Расход', 'Остаток', 'Сумма прихода', 'Ср. цена'],
    rows.value.map((r) => [r.material_code, r.material_name, r.object_name, r.unit_name, r.quantity_income, r.quantity_expense, r.quantity_balance, r.sum_income, r.average_price]),
  )
}

onMounted(async () => {
  try {
    const [objRes, matRes] = await Promise.all([listReferences('objects', { page_size: 200 }), listReferences('materials', { page_size: 500 })])
    objects.value = objRes.data as ObjectRecord[]
    materials.value = matRes.data as MaterialRecord[]
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки справочников'
  }
})
</script>

<style scoped>
.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem 1rem; margin-bottom: 1rem; }
.toolbar { align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
.balance-negative { color: var(--danger, #b00020); font-weight: 600; }
.message-error { background: var(--danger-bg, #fde8e8); color: var(--danger, #b00020); padding: 0.5rem 0.75rem; border-radius: 4px; }
</style>
