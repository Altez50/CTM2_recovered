<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <label class="input-label">Период</label>
          <span class="input-label">С</span>
          <input v-model="periodFrom" class="input" type="month" style="width: 150px" />
          <span class="input-label">По</span>
          <input v-model="periodTo" class="input" type="month" style="width: 150px" />
          <span class="input-label">Объект</span>
          <EntityPicker
            :model-value="objectId || null"
            :selected-label="objectName"
            title="Выбор объекта" description="Найдите и выберите объект строительства. Очистите — для всех объектов."
            placeholder="Все объекты" search-placeholder="Поиск по названию…"
            empty-text="Объекты не найдены" size="full" style="width: 280px"
            :load-page="loadObjectPage"
            @update:model-value="onObjectChange"
            @change="(item) => { objectName = item?.label ?? null }"
          />
          <button class="button button-primary" @click="loadData">Сформировать</button>
        </div>
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <div v-if="objectName && rows.length" class="object-title">{{ objectName }}</div>
        <DataTable :columns="columns" :rows="rows as any[]" :loading="loading" empty-text="Нет данных за период">
          <template #cell-opening_balance="{ row }">{{ fmt(row.opening_balance) }}</template>
          <template #cell-inflow="{ row }">{{ fmt(row.inflow) }}</template>
          <template #cell-outflow="{ row }">{{ fmt(row.outflow) }}</template>
          <template #cell-closing_balance="{ row }"><strong>{{ fmt(row.closing_balance) }}</strong></template>
        </DataTable>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import EntityPicker from '../../components/common/EntityPicker.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { getCostTurnover } from '../../api/costAccounting'
import { listReferences } from '../../api/references'
import type { TurnoverRow } from '../../types/costAccounting'
import type { ObjectRecord } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, ref('Оборотно-сальдовая ведомость по затратам'), ref([]))

const rows = ref<TurnoverRow[]>([])
const loading = ref(false)
const error = ref('')
const periodFrom = ref('')
const periodTo = ref('')
const objectId = ref(0)
const objectName = ref<string | null>(null)

const columns = [{ key: 'cost_element_name', label: 'Элемент затрат' }, { key: 'opening_balance', label: 'Начальное сальдо' }, { key: 'inflow', label: 'Приход' }, { key: 'outflow', label: 'Расход' }, { key: 'closing_balance', label: 'Конечное сальдо' }]

function fmt(v: number) { return v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

function onObjectChange(v: number | null) {
  objectId.value = v ?? 0
}

async function loadObjectPage(params: { search: string; page: number; pageSize: number }) {
  const resp = await listReferences('objects', { page: params.page, page_size: Math.min(params.pageSize, 50), search: params.search })
  return { items: (resp.data as ObjectRecord[]).map(o => ({ id: o.id, label: o.name, caption: o.address ?? null })), pages: resp.pagination?.pages ?? 1 }
}

async function loadData() {
  if (!periodFrom.value) { error.value = 'Укажите период «С»'; return }
  if (!periodTo.value) { error.value = 'Укажите период «По»'; return }
  if (periodFrom.value > periodTo.value) { error.value = 'Период «С» не может быть позже «По»'; return }
  loading.value = true; error.value = ''
  try {
    const r = await getCostTurnover(periodFrom.value, periodTo.value, objectId.value)
    rows.value = r.data.rows
    objectName.value = r.data.object_name
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const cur = new Date().toISOString().slice(0, 7)
  periodFrom.value = cur
  periodTo.value = cur
})
</script>

<style scoped>
.object-title { font-size: 1.15rem; font-weight: 600; margin: 1rem 0; }
</style>
