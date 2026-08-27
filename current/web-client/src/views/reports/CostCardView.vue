<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <span class="input-label">Объект</span>
          <EntityPicker
            :model-value="objectId"
            :selected-label="objectName"
            title="Выбор объекта" description="Найдите и выберите объект строительства."
            placeholder="Выберите объект" search-placeholder="Поиск по названию…"
            empty-text="Объекты не найдены" size="full" style="width: 280px"
            :clearable="false"
            :load-page="loadObjectPage"
            @update:model-value="onObjectChange"
            @change="(item) => { objectName = item?.label ?? null }"
          />
          <label class="input-label">Период</label>
          <span class="input-label">С</span>
          <input v-model="periodFrom" class="input" type="month" style="width: 150px" />
          <span class="input-label">По</span>
          <input v-model="periodTo" class="input" type="month" style="width: 150px" />
          <button class="button button-primary" @click="loadData">Сформировать</button>
        </div>
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <div v-if="data" style="margin-top: 1rem">
          <h2 v-if="data.object_name" class="object-title">{{ data.object_name }}</h2>
          <div class="summary-grid">
            <div class="summary-card"><div class="summary-label">Плановая себестоимость</div><div class="summary-value">{{ fmt(data.total_planned) }}</div></div>
            <div class="summary-card"><div class="summary-label">Фактическая себестоимость</div><div class="summary-value">{{ fmt(data.total_actual) }}</div></div>
            <div class="summary-card"><div class="summary-label">Отклонение</div><div class="summary-value" :class="{ negative: data.total_deviation > 0, positive: data.total_deviation < 0 }">{{ fmt(data.total_deviation) }}</div></div>
            <div class="summary-card"><div class="summary-label">Выручка</div><div class="summary-value">{{ fmt(data.total_contract_value) }}</div></div>
            <div class="summary-card"><div class="summary-label">Прибыль</div><div class="summary-value" :class="{ positive: data.total_profit > 0, negative: data.total_profit < 0 }">{{ fmt(data.total_profit) }}</div></div>
            <div class="summary-card"><div class="summary-label">Рентабельность</div><div class="summary-value">{{ data.profitability_pct.toFixed(1) }}%</div></div>
          </div>

          <h3 style="margin-top: 1.5rem">По элементам затрат</h3>
          <DataTable :columns="elementCols" :rows="data.elements as any[]" :loading="loading" empty-text="Нет данных">
            <template #cell-planned_amount="{ row }"><span class="drilldown-cell" @click="openDrilldown('planned', `План: ${row.cost_element_name}`, { period_from: periodFrom || undefined, period_to: periodTo || undefined, object_id: objectId ?? undefined, cost_element_id: row.cost_element_id })">{{ fmt(row.planned_amount) }}</span></template>
            <template #cell-actual_amount="{ row }"><span class="drilldown-cell" @click="openDrilldown('actual', `Факт: ${row.cost_element_name}`, { period_from: periodFrom || undefined, period_to: periodTo || undefined, object_id: objectId ?? undefined, cost_element_id: row.cost_element_id })">{{ fmt(row.actual_amount) }}</span></template>
            <template #cell-deviation="{ row }"><span :class="{ negative: row.deviation > 0, positive: row.deviation < 0 }">{{ fmt(row.deviation) }}</span></template>
          </DataTable>

          <h3 style="margin-top: 1.5rem" v-if="data.works.length">Детализация по работам</h3>
          <DataTable :columns="workCols" :rows="data.works as any[]" :loading="loading" empty-text="Нет данных" v-if="data.works.length">
            <template #cell-completed_quantity="{ row }">{{ fmt(row.completed_quantity) }}</template>
            <template #cell-planned_cost="{ row }">{{ fmt(row.planned_cost) }}</template>
            <template #cell-actual_cost="{ row }"><span class="drilldown-cell" @click="openDrilldown('actual', `Факт по работе: ${row.work_name || '—'}`, { period_from: periodFrom || undefined, period_to: periodTo || undefined, object_id: objectId ?? undefined, work_id: row.work_id })">{{ fmt(row.actual_cost) }}</span></template>
            <template #cell-deviation="{ row }"><span :class="{ negative: row.deviation > 0, positive: row.deviation < 0 }">{{ fmt(row.deviation) }}</span></template>
            <template #cell-contract_value="{ row }">{{ fmt(row.contract_value) }}</template>
            <template #cell-profit="{ row }"><span :class="{ positive: row.profit > 0, negative: row.profit < 0 }">{{ fmt(row.profit) }}</span></template>
            <template #cell-profitability_pct="{ row }">{{ row.profitability_pct }}%</template>
          </DataTable>
        </div>
      </div>
    </section>
    <CostDrilldownDialog
      :open="drilldown.open"
      :title="drilldown.title"
      :register="drilldown.register"
      :filters="drilldown.filters"
      @close="drilldown.open = false"
    />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import CostDrilldownDialog from '../../components/reports/CostDrilldownDialog.vue'
import EntityPicker from '../../components/common/EntityPicker.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { getCostCard } from '../../api/costAccounting'
import { listReferences } from '../../api/references'
import type { CostCardResponse, DrilldownQuery } from '../../types/costAccounting'
import type { ObjectRecord } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, ref('Карточка себестоимости'), ref([]))

const data = ref<CostCardResponse | null>(null)
const loading = ref(false)
const error = ref('')
const objectId = ref<number | null>(null)
const objectName = ref<string | null>(null)
const periodFrom = ref('')
const periodTo = ref('')

const drilldown = reactive({
  open: false,
  title: '',
  register: 'actual' as 'actual' | 'planned' | 'overhead',
  filters: {} as DrilldownQuery,
})

function openDrilldown(register: 'actual' | 'planned' | 'overhead', title: string, filters: DrilldownQuery) {
  drilldown.register = register
  drilldown.title = title
  drilldown.filters = filters
  drilldown.open = true
}

const elementCols = [{ key: 'cost_element_name', label: 'Элемент' }, { key: 'planned_amount', label: 'План' }, { key: 'actual_amount', label: 'Факт' }, { key: 'deviation', label: 'Отклонение' }]
const workCols = [{ key: 'work_name', label: 'Работа' }, { key: 'completed_quantity', label: 'Объём' }, { key: 'planned_cost', label: 'План' }, { key: 'actual_cost', label: 'Факт' }, { key: 'deviation', label: 'Отклонение' }, { key: 'contract_value', label: 'Выручка' }, { key: 'profit', label: 'Прибыль' }, { key: 'profitability_pct', label: 'Рент.%' }]

function fmt(v: number) { return v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

function onObjectChange(v: number | null) {
  objectId.value = v
}

async function loadObjectPage(params: { search: string; page: number; pageSize: number }) {
  const resp = await listReferences('objects', { page: params.page, page_size: Math.min(params.pageSize, 50), search: params.search })
  return { items: (resp.data as ObjectRecord[]).map(o => ({ id: o.id, label: o.name, caption: o.address ?? null })), pages: resp.pagination?.pages ?? 1 }
}

async function loadData() {
  if (!objectId.value) { error.value = 'Укажите объект'; return }
  if (periodFrom.value && periodTo.value && periodFrom.value > periodTo.value) {
    error.value = 'Период «С» не может быть позже «По»'; return
  }
  loading.value = true; error.value = ''
  try {
    const r = await getCostCard(objectId.value, periodFrom.value || null, periodTo.value || null)
    data.value = r.data
    if (r.data.object_name) objectName.value = r.data.object_name
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.drilldown-cell { cursor: pointer; text-decoration: underline dotted; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; }
.summary-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1rem; }
.summary-label { font-size: 0.78rem; color: var(--text-soft); margin-bottom: 0.3rem; }
.summary-value { font-size: 1.2rem; font-weight: 700; }
.object-title { font-size: 1.15rem; font-weight: 600; margin-bottom: 1rem; }
.negative { color: var(--danger, #dc2626); } .positive { color: var(--success, #16a34a); }
</style>
