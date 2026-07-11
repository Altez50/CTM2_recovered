<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <label class="input-label">Период</label>
          <input v-model="period" class="input" type="month" style="width: 160px" />
          <label class="input-label">Порог откл. %</label>
          <input v-model.number="threshold" class="input" type="number" min="0" step="1" style="width: 80px" />
          <label class="input-label">Объект</label>
          <input v-model.number="objectId" class="input" type="number" min="0" placeholder="0" style="width: 80px" />
          <button class="button button-primary" @click="loadData">Сформировать</button>
        </div>
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>
        <DataTable :columns="columns" :rows="rows as any[]" :loading="loading" empty-text="Нет отклонений">
          <template #cell-deviation="{ row }"><span :class="{ negative: row.deviation > 0, positive: row.deviation < 0 }">{{ fmt(row.deviation) }}</span></template>
          <template #cell-deviation_pct="{ row }"><span :class="{ negative: row.deviation > 0 }">{{ row.deviation_pct.toFixed(1) }}%</span></template>
        </DataTable>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { getCostDeviations } from '../../api/costAccounting'
import type { DeviationRow } from '../../types/costAccounting'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, ref('Отчёт по отклонениям'), ref([]))

const rows = ref<DeviationRow[]>([]); const loading = ref(false); const error = ref('')
const period = ref(''); const threshold = ref(0); const objectId = ref(0)

const columns = [{ key: 'work_name', label: 'Работа' }, { key: 'cost_element_name', label: 'Элемент' }, { key: 'planned_amount', label: 'План' }, { key: 'actual_amount', label: 'Факт' }, { key: 'deviation', label: 'Отклонение' }, { key: 'deviation_pct', label: '%' }]

function fmt(v: number) { return v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

async function loadData() {
  if (!period.value) { error.value = 'Укажите период'; return }
  loading.value = true; error.value = ''
  try { const r = await getCostDeviations(period.value, threshold.value, objectId.value); rows.value = r.data.rows } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } finally { loading.value = false }
}
onMounted(() => { period.value = new Date().toISOString().slice(0, 7) })
</script>
<style scoped>.negative { color: var(--danger, #dc2626); } .positive { color: var(--success, #16a34a); }</style>
