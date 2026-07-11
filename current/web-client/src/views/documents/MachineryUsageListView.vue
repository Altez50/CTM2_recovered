<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру" />
          <button class="button button-primary" @click="router.push('/documents/machinery-usage/new')">Рапорт машин</button>
          <button class="button button-secondary" title="Обновить" @click="loadItems">↻</button>
        </div>
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <SelectionActionBar :selected-count="selectedIds.length" @deselect-all="selectedIds = []">
          <button v-if="selectedIds.length === 1" class="button button-secondary" type="button" @click="openItem(Number(selectedIds[0]))">Открыть</button>
          <button v-if="auth.isAdmin && canPostSelected" class="button button-secondary" type="button" title="Провести" @click="changePostingSelected('post')">✓</button>
          <button v-if="auth.isAdmin && canUnpostSelected" class="button button-secondary" type="button" title="Отменить проведение" @click="changePostingSelected('unpost')">↺</button>
          <button class="button button-danger" type="button" title="Удалить" @click="removeSelected">✕</button>
        </SelectionActionBar>

        <DataTable :columns="columns" :rows="rows as any[]" :loading="loading" empty-text="Рапортов пока нет" selectable :selected-ids="selectedIds" @update:selected-ids="selectedIds = $event" @row-dblclick="handleRowDblClick">
          <template #cell-number="{ row }"><RouterLink class="document-list-link" :to="`/documents/machinery-usage/${row.id}`"><strong>{{ row.number }}</strong></RouterLink></template>
          <template #cell-date="{ row }">{{ formatDate(row.date) }}</template>
          <template #cell-is_posted="{ row }"><span :class="['status-pill', row.is_posted ? 'posted' : 'draft']">{{ row.is_posted ? 'Проведен' : 'Черновик' }}</span></template>
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
import type { MachineryUsageReport } from '../../types/costAccounting'
import { listMachineryUsageReports, deleteMachineryUsageReport, postMachineryUsageReport, unpostMachineryUsageReport } from '../../api/costAccounting'

const props = defineProps<{ tabId?: string }>()
const auth = useAuthStore(); const router = useRouter()
const headerActions = computed<HeaderAction[]>(() => [{ key: 'create', icon: '+', title: 'Рапорт машин', variant: 'primary', to: '/documents/machinery-usage/new' }])
useHeaderBar(props.tabId, computed(() => 'Рапорты о работе машин'), headerActions)

const rows = ref<MachineryUsageReport[]>([]); const loading = ref(false); const error = ref(''); const search = ref(''); const page = ref(1)
const pagination = ref({ page: 1, pages: 1, total: 0 }); const selectedIds = ref<string[]>([]); let searchTimer = 0

const columns = [{ key: 'number', label: 'Номер' }, { key: 'date', label: 'Дата' }, { key: 'object_name', label: 'Объект' }, { key: 'estimate_number', label: 'Смета' }, { key: 'is_posted', label: 'Статус' }]

const canPostSelected = computed(() => selectedIds.value.length > 0 && selectedIds.value.every((id) => { const row = rows.value.find((r) => String(r.id) === id); return row && !row.is_posted }))
const canUnpostSelected = computed(() => selectedIds.value.length > 0 && selectedIds.value.every((id) => { const row = rows.value.find((r) => String(r.id) === id); return row && row.is_posted }))

function formatDate(v: any) { if (!v) return '—'; const [y,m,d] = String(v).split('-').map(Number); return y && m && d ? new Date(y,m-1,d).toLocaleDateString('ru-RU') : v }
function openItem(id: number) { router.push(`/documents/machinery-usage/${id}`) }
function handleRowDblClick(row: Record<string, unknown>) { router.push(`/documents/machinery-usage/${(row as any).id}`) }

async function loadItems() {
  loading.value = true; error.value = ''
  try { const r = await listMachineryUsageReports({ page: page.value, page_size: 20, search: search.value, sort_order: 'desc' }); rows.value = r.data; pagination.value = { page: r.pagination?.page ?? 1, pages: r.pagination?.pages ?? 1, total: r.pagination?.total ?? 0 }; selectedIds.value = [] } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } finally { loading.value = false }
}

async function changePostingSelected(mode: string) {
  if (!selectedIds.value.length) return; error.value = ''; let failed = 0
  for (const id of selectedIds.value) { try { mode === 'post' ? await postMachineryUsageReport(Number(id)) : await unpostMachineryUsageReport(Number(id)) } catch { failed++ } }
  await loadItems(); if (failed) error.value = `Не удалось изменить статус для ${failed} рапортов`
}

async function removeSelected() {
  if (!selectedIds.value.length) return
  const label = selectedIds.value.length === 1 ? 'рапорт' : `${selectedIds.value.length} рапортов`
  if (!window.confirm(`Пометить ${label} на удаление?`)) return
  error.value = ''; let failed = 0
  for (const id of selectedIds.value) { try { await deleteMachineryUsageReport(Number(id)) } catch { failed++ } }
  await loadItems(); if (failed) error.value = `Не удалось удалить ${failed} рапортов`
}

watch(page, loadItems); watch(search, () => { clearTimeout(searchTimer); searchTimer = window.setTimeout(() => { page.value = 1; loadItems() }, 300) }); onMounted(loadItems)
</script>
<style scoped>.pagination-row { justify-content: space-between; margin-top: 1rem; }</style>
