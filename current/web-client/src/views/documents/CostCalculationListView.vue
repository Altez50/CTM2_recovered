<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру или периоду" />
          <button class="button button-primary" @click="router.push('/documents/cost-calculations/new')">Расчёт себестоимости</button>
          <button class="button button-secondary" title="Обновить" @click="loadItems">↻</button>
        </div>
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <SelectionActionBar :selected-count="selectedIds.length" @deselect-all="selectedIds = []">
          <button v-if="selectedIds.length === 1" class="button button-secondary" type="button" @click="openItem(Number(selectedIds[0]))">Открыть</button>
          <button v-if="canCalculateSelected" class="button button-secondary" type="button" @click="runCalculateSelected">Рассчитать</button>
          <button v-if="auth.isAdmin && canPostSelected" class="button button-secondary" type="button" title="Провести" @click="runPostSelected">✓</button>
          <button v-if="auth.isAdmin && canUnpostSelected" class="button button-secondary" type="button" title="Отменить проведение" @click="runUnpostSelected">↺</button>
          <button v-if="canDeleteSelected" class="button button-danger" type="button" title="Удалить" @click="removeSelected">✕</button>
        </SelectionActionBar>

        <DataTable :columns="columns" :rows="rows as any[]" :loading="loading" empty-text="Расчётов пока нет" selectable :selected-ids="selectedIds" @update:selected-ids="selectedIds = $event" @row-dblclick="handleRowDblClick">
          <template #cell-number="{ row }"><strong>{{ row.number }}</strong></template>
          <template #cell-date="{ row }">{{ formatDate(row.date) }}</template>
          <template #cell-status="{ row }"><span :class="['status-pill', statusClass(row.status)]">{{ statusLabel(row.status) }}</span></template>
        </DataTable>

        <div class="toolbar pagination-row">
          <span class="muted">Страница {{ pagination.page }} из {{ pagination.pages }}. Всего: {{ pagination.total }}</span>
          <div class="table-actions"><button class="button button-secondary" :disabled="page <= 1" @click="page -= 1">Назад</button><button class="button button-secondary" :disabled="page >= pagination.pages" @click="page += 1">Вперед</button></div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from '../../components/common/DataTable.vue'
import SelectionActionBar from '../../components/common/SelectionActionBar.vue'
import { useAuthStore } from '../../stores/auth'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import type { CostCalculation } from '../../types/costAccounting'
import type { ApiResponse } from '../../types/api'
import { listCostCalculations, deleteCostCalculation, calculateCost, postCostCalculation, unpostCostCalculation } from '../../api/costAccounting'

const props = defineProps<{ tabId?: string }>()
const auth = useAuthStore(); const router = useRouter()
const headerActions = computed<HeaderAction[]>(() => [{ key: 'create', icon: '+', title: 'Расчёт себестоимости', variant: 'primary', to: '/documents/cost-calculations/new' }])
useHeaderBar(props.tabId, computed(() => 'Расчёты себестоимости'), headerActions)

const rows = ref<CostCalculation[]>([]); const loading = ref(false); const error = ref(''); const search = ref(''); const page = ref(1)
const pagination = ref({ page: 1, pages: 1, total: 0 }); const selectedIds = ref<string[]>([]); let searchTimer = 0
const columns = [{ key: 'number', label: 'Номер' }, { key: 'date', label: 'Дата' }, { key: 'period', label: 'Период' }, { key: 'object_name', label: 'Объект' }, { key: 'status', label: 'Статус' }]

const canCalculateSelected = computed(() => selectedIds.value.length > 0 && selectedIds.value.every((id) => { const row = rows.value.find((r) => String(r.id) === id); return row && row.status === 'draft' }))
const canPostSelected = computed(() => selectedIds.value.length > 0 && selectedIds.value.every((id) => { const row = rows.value.find((r) => String(r.id) === id); return row && row.status === 'calculated' }))
const canUnpostSelected = computed(() => selectedIds.value.length > 0 && selectedIds.value.every((id) => { const row = rows.value.find((r) => String(r.id) === id); return row && row.status === 'posted' }))
const canDeleteSelected = computed(() => selectedIds.value.length > 0 && selectedIds.value.every((id) => { const row = rows.value.find((r) => String(r.id) === id); return row && row.status !== 'posted' }))

function formatDate(v: any) { if (!v) return '—'; const [y,m,d] = String(v).split('-').map(Number); return y && m && d ? new Date(y,m-1,d).toLocaleDateString('ru-RU') : v }
function statusClass(s: string) { return s === 'posted' ? 'posted' : s === 'calculated' ? 'success' : 'draft' }
function statusLabel(s: string) { return s === 'posted' ? 'Проведен' : s === 'calculated' ? 'Рассчитан' : 'Черновик' }
function openItem(id: number) { router.push(`/documents/cost-calculations/${id}`) }
function handleRowDblClick(row: Record<string, unknown>) { router.push(`/documents/cost-calculations/${(row as any).id}`) }

async function loadItems() { loading.value = true; error.value = ''; try { const r = await listCostCalculations({ page: page.value, page_size: 20, sort_order: 'desc' }); rows.value = r.data; pagination.value = { page: r.pagination?.page ?? 1, pages: r.pagination?.pages ?? 1, total: r.pagination?.total ?? 0 }; selectedIds.value = [] } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } finally { loading.value = false } }

async function batchAction(action: (id: number) => Promise<ApiResponse<unknown>>, errorLabel: string) {
  if (!selectedIds.value.length) return; error.value = ''; let failed = 0
  for (const id of selectedIds.value) { try { await action(Number(id)) } catch { failed++ } }
  await loadItems(); if (failed) error.value = `Не удалось выполнить для ${failed} расчётов`
}

async function runCalculateSelected() { await batchAction(calculateCost, 'рассчитать') }
async function runPostSelected() { await batchAction(postCostCalculation, 'провести') }

async function runUnpostSelected() {
  if (!selectedIds.value.length) return
  if (!window.confirm(`Отменить проведение для ${selectedIds.value.length} расчётов?`)) return
  await batchAction(unpostCostCalculation, 'отменить проведение')
}

async function removeSelected() {
  if (!selectedIds.value.length) return
  const label = selectedIds.value.length === 1 ? 'расчёт' : `${selectedIds.value.length} расчётов`
  if (!window.confirm(`Пометить ${label} на удаление?`)) return
  await batchAction(deleteCostCalculation, 'удалить')
}

watch(page, loadItems); watch(search, () => { clearTimeout(searchTimer); searchTimer = window.setTimeout(() => { page.value = 1; loadItems() }, 300) }); onMounted(loadItems)
</script>
<style scoped>.pagination-row { justify-content: space-between; margin-top: 1rem; } .status-pill.success { background: rgba(34, 197, 94, 0.12); color: var(--success, #16a34a); }</style>
