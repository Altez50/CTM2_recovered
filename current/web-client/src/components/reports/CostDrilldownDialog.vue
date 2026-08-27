<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @click="$emit('close')">
      <div class="modal panel drilldown-modal" role="dialog" aria-modal="true" @click.stop>
        <header class="modal-header">
          <h2 class="modal-title">{{ title }}</h2>
          <button class="button button-secondary" type="button" @click="$emit('close')">✕</button>
        </header>

        <div class="modal-body">
          <div v-if="loading" class="loading-state">Загрузка…</div>
          <template v-else>
            <table v-if="items.length" class="drilldown-table">
              <thead>
                <tr>
                  <th>Период</th>
                  <th>Дата</th>
                  <th>Регистратор</th>
                  <th>Элемент затрат</th>
                  <th>Объект</th>
                  <th>Работа</th>
                  <th class="num">Количество</th>
                  <th class="num">Сумма</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in items"
                  :key="item.id"
                  class="drilldown-row"
                  @dblclick="openRegistrar(item)"
                >
                  <td>{{ item.period }}</td>
                  <td>{{ item.date || '—' }}</td>
                  <td>
                    <RouterLink
                      v-if="item.registrar_type && item.registrar_id"
                      :to="registrarRoute(item.registrar_type, item.registrar_id)"
                      class="registrar-link"
                    >
                      {{ registrarLabel(item.registrar_type) }} {{ item.registrar_number || `#${item.registrar_id}` }}
                    </RouterLink>
                    <span v-else class="muted">—</span>
                  </td>
                  <td>{{ item.cost_element_name || '—' }}</td>
                  <td>{{ item.object_name || '—' }}</td>
                  <td>{{ item.work_name || '—' }}</td>
                  <td class="num">{{ fmt(item.quantity) }}</td>
                  <td class="num" :class="{ negative: item.amount < 0 }">{{ fmt(item.amount) }}</td>
                </tr>
              </tbody>
              <tfoot>
                <tr>
                  <td colspan="6"><strong>Итого</strong></td>
                  <td class="num"><strong>{{ fmt(totals.quantity) }}</strong></td>
                  <td class="num"><strong>{{ fmt(totals.amount) }}</strong></td>
                </tr>
              </tfoot>
            </table>
            <div v-else class="empty-state">Нет данных</div>
          </template>
        </div>

        <footer v-if="pages > 1 || items.length" class="modal-footer">
          <div class="pager">
            <button class="button button-secondary" :disabled="page <= 1" @click="goPage(page - 1)">←</button>
            <span v-if="pages > 1" class="page-info">Стр. {{ page }} из {{ pages }}</span>
            <button class="button button-secondary" :disabled="page >= pages" @click="goPage(page + 1)">→</button>
          </div>
          <button class="button button-secondary" type="button" @click="$emit('close')">Закрыть</button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  getActualCostsDrilldown,
  getPlannedCostsDrilldown,
  getOverheadDrilldown,
} from '../../api/costAccounting'
import type { DrilldownItem, DrilldownQuery } from '../../types/costAccounting'

const props = defineProps<{
  open: boolean
  title: string
  register: 'actual' | 'planned' | 'overhead'
  filters: DrilldownQuery
}>()

const emit = defineEmits<{ close: [] }>()

const items = ref<DrilldownItem[]>([])
const totals = ref({ quantity: 0, amount: 0 })
const loading = ref(false)
const page = ref(1)
const pages = ref(1)

function fmt(v: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v || 0)
}

const REGISTRAR_ROUTES: Record<string, string> = {
  MaterialConsumption: '/documents/material-consumptions/',
  MachineryUsageReport: '/documents/machinery-usage/',
  SubcontractAcceptance: '/documents/subcontract-acceptances/',
  Timesheet: '/documents/timesheets/',
  DailyReport: '/documents/daily-reports/',
  Estimate: '/documents/estimates/',
}

const REGISTRAR_LABELS: Record<string, string> = {
  MaterialConsumption: 'Акт расхода',
  MachineryUsageReport: 'Рапорт',
  SubcontractAcceptance: 'Субподряд',
  Timesheet: 'Табель',
  DailyReport: 'Наряд',
  Estimate: 'Смета',
}

function registrarRoute(type: string, id: number): string {
  return (REGISTRAR_ROUTES[type] || '/documents/') + id
}

function registrarLabel(type: string): string {
  return REGISTRAR_LABELS[type] || type
}

function openRegistrar(item: DrilldownItem) {
  if (item.registrar_type && item.registrar_id) {
    window.location.hash = '#' + registrarRoute(item.registrar_type, item.registrar_id)
  }
}

async function load() {
  loading.value = true
  try {
    const params: DrilldownQuery = { ...props.filters, page: page.value, page_size: 50 }
    let resp
    if (props.register === 'actual') resp = await getActualCostsDrilldown(params)
    else if (props.register === 'planned') resp = await getPlannedCostsDrilldown(params)
    else resp = await getOverheadDrilldown(params)
    items.value = resp.data.items
    totals.value = resp.data.totals
    if (resp.pagination) {
      pages.value = resp.pagination.pages
    }
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

function goPage(p: number) {
  if (p < 1 || p > pages.value) return
  page.value = p
  load()
}

// Сброс страницы и загрузка при открытии
watch(() => props.open, (val) => {
  if (val) {
    page.value = 1
    load()
  }
})
</script>

<style scoped>
.drilldown-modal {
  max-width: 1100px;
  width: 95vw;
}

.modal-body {
  max-height: 65vh;
  overflow: auto;
  padding: 0;
}

.drilldown-table {
  width: 100%;
  border-collapse: collapse;
}

.drilldown-table th {
  position: sticky;
  top: 0;
  background: var(--panel-bg, #f5f0eb);
  padding: 0.4rem 0.6rem;
  text-align: left;
  font-size: 0.8rem;
  font-weight: 600;
  border-bottom: 1px solid var(--border, #e0d6cc);
  white-space: nowrap;
}

.drilldown-table td {
  padding: 0.35rem 0.6rem;
  font-size: 0.85rem;
  border-bottom: 1px solid var(--border-light, #eee);
}

.drilldown-table tfoot td {
  border-top: 2px solid var(--border, #e0d6cc);
  background: var(--panel-bg, #f5f0eb);
}

.drilldown-row {
  cursor: pointer;
}

.drilldown-row:hover {
  background: var(--hover-bg, rgba(0, 0, 0, 0.03));
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.negative {
  color: #c0392b;
}

.registrar-link {
  color: var(--primary, #b24c2d);
  text-decoration: none;
  font-weight: 600;
}

.registrar-link:hover {
  text-decoration: underline;
}

.muted {
  color: var(--text-soft, #888);
}

.loading-state,
.empty-state {
  padding: 2rem;
  text-align: center;
  color: var(--text-soft, #888);
}

.modal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  border-top: 1px solid var(--border, #e0d6cc);
}

.pager {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.page-info {
  font-size: 0.85rem;
  color: var(--text-soft, #666);
}
</style>
