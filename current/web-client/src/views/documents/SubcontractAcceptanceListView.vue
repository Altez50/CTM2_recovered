<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру" />
          <button class="button button-primary" @click="router.push('/documents/subcontract-acceptances/new')">Акт субподряда</button>
          <button class="button button-secondary" title="Обновить" @click="loadItems">↻</button>
        </div>
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <SelectionActionBar :selected-count="selectedIds.length" @deselect-all="selectedIds = []">
          <button v-if="selectedIds.length === 1" class="button button-secondary" type="button" @click="openItem(Number(selectedIds[0]))">Открыть</button>
          <button v-if="auth.isAdmin && canPostSelected" class="button button-secondary" type="button" title="Провести" @click="changePostingSelected('post')">✓</button>
          <button v-if="auth.isAdmin && canUnpostSelected" class="button button-secondary" type="button" title="Отменить проведение" @click="changePostingSelected('unpost')">↺</button>
          <button class="button button-danger" type="button" title="Удалить" @click="removeSelected">✕</button>
        </SelectionActionBar>

        <DataTable :columns="columns" :rows="rows as any[]" :loading="loading" empty-text="Актов пока нет" selectable :selected-ids="selectedIds" @update:selected-ids="selectedIds = $event" @row-dblclick="handleRowDblClick" @row-contextmenu="onContextMenu as any">
          <template #cell-number="{ row }"><RouterLink class="document-list-link" :to="`/documents/subcontract-acceptances/${row.id}`"><strong>{{ row.number }}</strong></RouterLink></template>
          <template #cell-date="{ row }">{{ formatDate(row.date) }}</template>
          <template #cell-is_posted="{ row }"><span :class="['status-pill', row.is_posted ? 'posted' : 'draft']">{{ row.is_posted ? 'Проведен' : 'Черновик' }}</span></template>
        </DataTable>

        <div class="toolbar pagination-row">
          <span class="muted">Страница {{ pagination.page }} из {{ pagination.pages }}. Всего: {{ pagination.total }}</span>
          <div class="table-actions"><button class="button button-secondary" :disabled="page <= 1" @click="page -= 1">Назад</button><button class="button button-secondary" :disabled="page >= pagination.pages" @click="page += 1">Вперед</button></div>
        </div>
      </div>
    </section>
    <ContextMenu :open="menuOpen" :items="menuItems" :x="menuX" :y="menuY" @close="closeMenu" @select="onMenuSelect" />
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
import ContextMenu from '../../components/common/ContextMenu.vue'
import { useDocumentContextMenu } from '../../composables/useDocumentContextMenu'
import type { SubcontractAcceptance } from '../../types/costAccounting'
import { listSubcontractAcceptances, deleteSubcontractAcceptance, postSubcontractAcceptance, restoreSubcontractAcceptance, unpostSubcontractAcceptance } from '../../api/costAccounting'

const props = defineProps<{ tabId?: string }>()
const auth = useAuthStore(); const router = useRouter()
const headerActions = computed<HeaderAction[]>(() => [{ key: 'create', icon: '+', title: 'Акт субподряда', variant: 'primary', to: '/documents/subcontract-acceptances/new' }])
useHeaderBar(props.tabId, computed(() => 'Акты приёмки субподрядных работ'), headerActions)

const rows = ref<SubcontractAcceptance[]>([]); const loading = ref(false); const error = ref(''); const search = ref(''); const page = ref(1)
const pagination = ref({ page: 1, pages: 1, total: 0 }); const selectedIds = ref<string[]>([]); let searchTimer = 0
const columns = [{ key: 'number', label: 'Номер' }, { key: 'date', label: 'Дата' }, { key: 'object_name', label: 'Объект' }, { key: 'estimate_number', label: 'Смета' }, { key: 'is_posted', label: 'Статус' }]

const canPostSelected = computed(() => selectedIds.value.length > 0 && selectedIds.value.every((id) => { const row = rows.value.find((r) => String(r.id) === id); return row && !row.is_posted }))
const canUnpostSelected = computed(() => selectedIds.value.length > 0 && selectedIds.value.every((id) => { const row = rows.value.find((r) => String(r.id) === id); return row && row.is_posted }))

const { menuOpen, menuX, menuY, menuItems, onContextMenu, closeMenu, onMenuSelect } = useDocumentContextMenu<SubcontractAcceptance>({
  onPost: async (row) => { await postSubcontractAcceptance(Number(row.id)); await loadItems() },
  onUnpost: async (row) => { await unpostSubcontractAcceptance(Number(row.id)); await loadItems() },
  onDelete: async (row) => { await deleteSubcontractAcceptance(Number(row.id)); await loadItems() },
  onRestore: async (row) => { await restoreSubcontractAcceptance(Number(row.id)); await loadItems() },
})

function formatDate(v: any) { if (!v) return '—'; const [y,m,d] = String(v).split('-').map(Number); return y && m && d ? new Date(y,m-1,d).toLocaleDateString('ru-RU') : v }
function openItem(id: number) { router.push(`/documents/subcontract-acceptances/${id}`) }
function handleRowDblClick(row: Record<string, unknown>) { router.push(`/documents/subcontract-acceptances/${(row as any).id}`) }

async function loadItems() { loading.value = true; error.value = ''; try { const r = await listSubcontractAcceptances({ page: page.value, page_size: 20, search: search.value, sort_order: 'desc' }); rows.value = r.data; pagination.value = { page: r.pagination?.page ?? 1, pages: r.pagination?.pages ?? 1, total: r.pagination?.total ?? 0 }; selectedIds.value = [] } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } finally { loading.value = false } }
async function changePostingSelected(mode: string) { if (!selectedIds.value.length) return; error.value = ''; let failed = 0; for (const id of selectedIds.value) { try { mode === 'post' ? await postSubcontractAcceptance(Number(id)) : await unpostSubcontractAcceptance(Number(id)) } catch { failed++ } }; await loadItems(); if (failed) error.value = `Не удалось изменить статус для ${failed} актов` }
async function removeSelected() { if (!selectedIds.value.length) return; const label = selectedIds.value.length === 1 ? 'акт' : `${selectedIds.value.length} актов`; if (!window.confirm(`Пометить ${label} на удаление?`)) return; error.value = ''; let failed = 0; for (const id of selectedIds.value) { try { await deleteSubcontractAcceptance(Number(id)) } catch { failed++ } }; await loadItems(); if (failed) error.value = `Не удалось удалить ${failed} актов` }

watch(page, loadItems); watch(search, () => { clearTimeout(searchTimer); searchTimer = window.setTimeout(() => { page.value = 1; loadItems() }, 300) }); onMounted(loadItems)
</script>
<style scoped>.pagination-row { justify-content: space-between; margin-top: 1rem; }</style>
