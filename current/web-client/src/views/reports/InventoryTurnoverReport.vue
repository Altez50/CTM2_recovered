<template>
  <section class="card"><h1>Обороты и входящие остатки ТМЦ</h1>
    <div class="toolbar"><label>Начало периода <input v-model="from" type="date" /></label><label>Окончание периода <input v-model="to" type="date" /></label>
      <button class="button button-primary" :disabled="busy" @click="load">Показать</button><button class="button" :disabled="!rows.length" @click="exportCsv">Выгрузить CSV</button></div>
    <div class="toolbar"><EntityPicker v-for="filter in filterKinds" :key="filter.key" :model-value="filters[filter.key] ?? null" :title="filter.label"
      :placeholder="filter.label" :load-page="loader(filter.kind)" @update:model-value="value => filters[filter.key] = value" /></div>
    <p v-if="error" role="alert">{{ error }}</p>
    <p>Входящие остатки включают движения до начала периода. Количество показано в базовых единицах.</p>
    <DataTable :columns="columns" :rows="rows" :loading="busy" empty-text="Нет остатков или оборотов" />
  </section>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import EntityPicker from '../../components/common/EntityPicker.vue'
import { listReferences } from '../../api/references'
import { inventoryTurnover } from '../../api/openingBalances'
import { downloadCsv } from '../../utils/reportExport'
import type { ReferenceKind } from '../../types/models'
const today = new Date().toISOString().slice(0, 10)
const from = ref(today), to = ref(today), busy = ref(false), error = ref(''), rows = ref<Record<string, unknown>[]>([])
const filters = reactive<Record<string, number | null>>({})
const filterKinds: { key: string; kind: ReferenceKind; label: string }[] = [
  { key: 'organization_id', kind: 'organizations', label: 'Организация' }, { key: 'warehouse_id', kind: 'warehouses', label: 'Склад' },
  { key: 'material_id', kind: 'materials', label: 'Товар' }, { key: 'object_id', kind: 'objects', label: 'Объект' },
  { key: 'characteristic_id', kind: 'material-characteristics', label: 'Характеристика' }, { key: 'series_id', kind: 'material-series', label: 'Серия' },
]
const columns = [
  { key: 'warehouse_name', label: 'Склад' }, { key: 'material_name', label: 'Товар' }, { key: 'object_name', label: 'Объект' },
  { key: 'characteristic_name', label: 'Характеристика' }, { key: 'series_name', label: 'Серия' }, { key: 'unit_name', label: 'Базовая ед.' },
  { key: 'quantity_opening', label: 'Входящее количество' }, { key: 'cost_opening', label: 'Входящая стоимость' },
  { key: 'quantity_income', label: 'Приход' }, { key: 'cost_income', label: 'Стоимость прихода' },
  { key: 'quantity_expense', label: 'Расход' }, { key: 'cost_expense', label: 'Стоимость расхода' },
  { key: 'quantity_closing', label: 'Исходящее количество' }, { key: 'cost_closing', label: 'Исходящая стоимость' },
]
function loader(kind: ReferenceKind) {
  return async (params: { search: string; page: number; pageSize: number }) => {
    const response = await listReferences(kind, { search: params.search, page: params.page, page_size: params.pageSize })
    return { items: response.data.map(item => ({ id: item.id, label: String('name' in item ? item.name : item.id) })), pages: response.pagination?.pages ?? 1 }
  }
}
async function load() {
  busy.value = true; error.value = ''
  try { rows.value = (await inventoryTurnover({ date_from: from.value, date_to: to.value,
    ...Object.fromEntries(Object.entries(filters).map(([key, value]) => [key, value ?? undefined])) })).data }
  catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка отчета' }
  finally { busy.value = false }
}
function exportCsv() { downloadCsv(`Обороты_ТМЦ_${from.value}_${to.value}`, columns.map(c => c.label), rows.value.map(row => columns.map(c => row[c.key] as string | number | null))) }
onMounted(load)
</script>
