<template>
  <div class="page-shell">
    <section class="panel">
      <header class="panel-header">
        <h1 class="panel-title">Рентабельность по объектам</h1>
      </header>
      <div class="panel-body page-shell">
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <div class="form-grid">
          <FormField label="Период">
            <input v-model="period" class="input" type="month" />
          </FormField>
          <FormField label="Группировка">
            <select v-model="groupBy" class="select">
              <option value="object">По объектам</option>
              <option value="contract">По договорам</option>
              <option value="object_contract">Объект + договор</option>
            </select>
          </FormField>
          <div class="form-actions">
            <button class="button button-primary" type="button" @click="loadReport">Показать</button>
          </div>
        </div>

        <div v-if="loading" class="page-subtitle">Загрузка…</div>

        <table v-else-if="rows.length" class="data-table">
          <thead>
            <tr>
              <template v-if="groupBy === 'object'">
                <th>Объект</th>
                <th>Договор</th>
              </template>
              <template v-else-if="groupBy === 'contract'">
                <th>Договор</th>
                <th>Контрагент</th>
              </template>
              <template v-else>
                <th>Объект</th>
                <th>Договор</th>
              </template>
              <th class="num">Плановая себестоимость</th>
              <th class="num">Фактическая себестоимость</th>
              <th class="num">Стоимость по договору</th>
              <th class="num">Прибыль</th>
              <th class="num">Рентабельность, %</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in rows" :key="i">
              <template v-if="groupBy === 'object'">
                <td>{{ row.object_name || '—' }}</td>
                <td class="muted">{{ row.contract_number || '—' }}</td>
              </template>
              <template v-else-if="groupBy === 'contract'">
                <td>{{ row.contract_number || '—' }}</td>
                <td class="muted">{{ row.counterparty_name || '—' }}</td>
              </template>
              <template v-else>
                <td>{{ row.object_name || '—' }}</td>
                <td class="muted">{{ row.contract_number || '—' }}</td>
              </template>
              <td class="num drilldown-cell" @click="openDrilldown('planned', drillTitle(row), drillFilters(row))">{{ fmt(row.planned_cost) }}</td>
              <td class="num drilldown-cell" @click="openDrilldown('actual', drillTitle(row), drillFilters(row))">{{ fmt(row.actual_cost) }}</td>
              <td class="num">{{ fmt(row.contract_value) }}</td>
              <td class="num" :class="{ profit: row.profit > 0, loss: row.profit < 0 }">{{ fmt(row.profit) }}</td>
              <td class="num" :class="{ profit: row.profitability_pct > 0, loss: row.profitability_pct < 0 }">{{ row.profitability_pct.toFixed(1) }}</td>
            </tr>
          </tbody>
          <tfoot v-if="totals">
            <tr>
              <td :colspan="groupBy === 'contract' ? 2 : 2"><strong>Итого</strong></td>
              <td class="num"><strong>{{ fmt(totals.planned_cost) }}</strong></td>
              <td class="num"><strong>{{ fmt(totals.actual_cost) }}</strong></td>
              <td class="num"><strong>{{ fmt(totals.contract_value) }}</strong></td>
              <td class="num"><strong>{{ fmt(totals.profit) }}</strong></td>
              <td class="num"><strong>{{ totals.profitability_pct.toFixed(1) }}</strong></td>
            </tr>
          </tfoot>
        </table>

        <div v-else class="empty-state">
          <p class="page-subtitle">Нет данных. Выполните расчёт себестоимости за выбранный период.</p>
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
import { computed, onMounted, reactive, ref } from 'vue'
import FormField from '../../components/common/FormField.vue'
import CostDrilldownDialog from '../../components/reports/CostDrilldownDialog.vue'
import { getCostProfitability } from '../../api/costAccounting'
import type { DrilldownQuery, ProfitabilityRow } from '../../types/costAccounting'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, computed(() => 'Рентабельность по объектам'), computed<HeaderAction[]>(() => []))

const period = ref('')
const groupBy = ref<'object' | 'contract' | 'object_contract'>('object')
const rows = ref<ProfitabilityRow[]>([])
const loading = ref(false)
const error = ref('')

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

function drillTitle(row: ProfitabilityRow): string {
  return row.object_name || row.contract_number || '—'
}

function drillFilters(row: ProfitabilityRow): DrilldownQuery {
  const includeObject = groupBy.value === 'object' || groupBy.value === 'object_contract'
  return {
    period_from: period.value || undefined,
    period_to: period.value || undefined,
    object_id: includeObject ? row.object_id : undefined,
  }
}

const totals = computed(() => {
  if (!rows.value.length) return null
  const sum = rows.value.reduce(
    (acc, r) => ({
      planned_cost: acc.planned_cost + r.planned_cost,
      actual_cost: acc.actual_cost + r.actual_cost,
      contract_value: acc.contract_value + r.contract_value,
      profit: acc.profit + r.profit,
    }),
    { planned_cost: 0, actual_cost: 0, contract_value: 0, profit: 0 },
  )
  return {
    ...sum,
    profitability_pct: sum.actual_cost ? (sum.profit / sum.actual_cost) * 100 : 0,
  }
})

function fmt(v: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v || 0)
}

async function loadReport() {
  loading.value = true
  error.value = ''
  try {
    const response = await getCostProfitability(period.value || null, groupBy.value)
    rows.value = response.data.rows
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки отчёта'
  } finally {
    loading.value = false
  }
}

onMounted(() => loadReport())
</script>

<style scoped>
.drilldown-cell { cursor: pointer; text-decoration: underline dotted; }

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 0.45rem 0.6rem;
  border-bottom: 1px solid var(--border-light, #eee);
  font-size: 0.85rem;
  text-align: left;
}

.data-table th {
  background: var(--panel-bg, #f5f0eb);
  font-weight: 600;
  position: sticky;
  top: 0;
}

.data-table tfoot td {
  border-top: 2px solid var(--border, #e0d6cc);
  background: var(--panel-bg, #f5f0eb);
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.muted {
  color: var(--text-soft, #888);
}

.profit {
  color: #2d7a4e;
}

.loss {
  color: #c0392b;
}

.form-actions {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
}

.empty-state {
  padding: 2rem;
  text-align: center;
}
</style>