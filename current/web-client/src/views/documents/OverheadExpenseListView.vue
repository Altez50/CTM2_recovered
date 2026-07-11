<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру или периоду" />
          <button class="button button-primary" @click="router.push('/documents/overhead-expenses/new')">Накладные расходы</button>
          <button class="button button-secondary" title="Обновить" @click="loadItems">↻</button>
        </div>
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <SelectionActionBar :selected-count="selectedIds.length" @deselect-all="selectedIds = []">
          <button v-if="selectedIds.length === 1" class="button button-secondary" type="button" @click="openItem(Number(selectedIds[0]))">Открыть</button>
          <button class="button button-danger" type="button" title="Удалить" @click="removeSelected">✕</button>
        </SelectionActionBar>

        <DataTable :columns="columns" :rows="rows as any[]" :loading="loading" empty-text="Документов пока нет" selectable :selected-ids="selectedIds" @update:selected-ids="selectedIds = $event" @row-dblclick="handleRowDblClick">
          <template #cell-number="{ row }"><RouterLink class="document-list-link" :to="`/documents/overhead-expenses/${row.id}`"><strong>{{ row.number }}</strong></RouterLink></template>
          <template #cell-date="{ row }">{{ formatDate(row.date) }}</template>
          <template #cell-is_distributed="{ row }"><span :class="['status-pill', row.is_distributed ? 'posted' : 'draft']">{{ row.is_distributed ? 'Распределены' : 'Не распределены' }}</span></template>
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
import type { OverheadExpense } from '../../types/costAccounting'
import { listOverheadExpenses, deleteOverheadExpense } from '../../api/costAccounting'

const props = defineProps<{ tabId?: string }>()
const auth = useAuthStore(); const router = useRouter()
const headerActions = computed<HeaderAction[]>(() => [{ key: 'create', icon: '+', title: 'Накладные расходы', variant: 'primary', to: '/documents/overhead-expenses/new' }])
useHeaderBar(props.tabId, computed(() => 'Накладные расходы'), headerActions)

const rows = ref<OverheadExpense[]>([]); const loading = ref(false); const error = ref(''); const search = ref(''); const page = ref(1)
const pagination = ref({ page: 1, pages: 1, total: 0 }); const selectedIds = ref<string[]>([]); let searchTimer = 0
const columns = [{ key: 'number', label: 'Номер' }, { key: 'date', label: 'Дата' }, { key: 'period', label: 'Период' }, { key: 'is_distributed', label: 'Статус' }]

function formatDate(v: any) { if (!v) return '—'; const [y,m,d] = String(v).split('-').map(Number); return y && m && d ? new Date(y,m-1,d).toLocaleDateString('ru-RU') : v }
function openItem(id: number) { router.push(`/documents/overhead-expenses/${id}`) }
function handleRowDblClick(row: Record<string, unknown>) { router.push(`/documents/overhead-expenses/${(row as any).id}`) }

async function loadItems() { loading.value = true; error.value = ''; try { const r = await listOverheadExpenses({ page: page.value, page_size: 20, search: search.value, sort_order: 'desc' }); rows.value = r.data; pagination.value = { page: r.pagination?.page ?? 1, pages: r.pagination?.pages ?? 1, total: r.pagination?.total ?? 0 }; selectedIds.value = [] } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } finally { loading.value = false } }
async function removeSelected() { if (!selectedIds.value.length) return; const label = selectedIds.value.length === 1 ? 'документ' : `${selectedIds.value.length} документов`; if (!window.confirm(`Пометить ${label} на удаление?`)) return; error.value = ''; let failed = 0; for (const id of selectedIds.value) { try { await deleteOverheadExpense(Number(id)) } catch { failed++ } }; await loadItems(); if (failed) error.value = `Не удалось удалить ${failed} документов` }

watch(page, loadItems); watch(search, () => { clearTimeout(searchTimer); searchTimer = window.setTimeout(() => { page.value = 1; loadItems() }, 300) }); onMounted(loadItems)
</script>
<style scoped>.pagination-row { justify-content: space-between; margin-top: 1rem; }</style>
