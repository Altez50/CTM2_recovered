<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <label class="input-label">Период</label>
          <input v-model="period" class="input" type="month" style="width: 160px" />
          <button class="button button-primary" @click="loadData">Сформировать</button>
          <button class="button button-secondary" @click="loadAll">Все периоды</button>
        </div>
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>
        <DataTable :columns="columns" :rows="rows as any[]" :loading="loading" empty-text="Нет данных">
          <template #cell-profit="{ row }"><span :class="{ positive: row.profit > 0, negative: row.profit < 0 }">{{ fmt(row.profit) }}</span></template>
          <template #cell-profitability_pct="{ row }"><span :class="{ positive: row.profitability_pct > 0, negative: row.profitability_pct < 0 }">{{ row.profitability_pct.toFixed(1) }}%</span></template>
        </DataTable>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { getCostProfitability } from '../../api/costAccounting'
import type { ProfitabilityRow } from '../../types/costAccounting'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, ref('Рентабельность по объектам'), ref([]))

const rows = ref<ProfitabilityRow[]>([]); const loading = ref(false); const error = ref(''); const period = ref('')

const columns = [{ key: 'object_name', label: 'Объект' }, { key: 'planned_cost', label: 'План. себест.' }, { key: 'actual_cost', label: 'Факт. себест.' }, { key: 'contract_value', label: 'Выручка' }, { key: 'profit', label: 'Прибыль' }, { key: 'profitability_pct', label: 'Рент.%' }]

function fmt(v: number) { return v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

async function loadData() {
  if (!period.value) { error.value = 'Укажите период'; return }
  loading.value = true; error.value = ''
  try { const r = await getCostProfitability(period.value); rows.value = r.data.rows } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } finally { loading.value = false }
}
async function loadAll() {
  loading.value = true; error.value = ''
  try { const r = await getCostProfitability(null); rows.value = r.data.rows } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } finally { loading.value = false }
}
onMounted(() => { period.value = new Date().toISOString().slice(0, 7) })
</script>
<style scoped>.negative { color: var(--danger, #dc2626); } .positive { color: var(--success, #16a34a); }</style>
