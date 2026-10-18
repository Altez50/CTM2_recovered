<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar search-row">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру, контрагенту, складу" />
        </div>

        <ListCommandBar :state="state" :config="config" @open-settings="settingsOpen = true" />

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <DataTable
          :columns="effectiveColumns"
          :rows="rows as Record<string, unknown>[]"
          :loading="loading"
          empty-text="Документов пока нет"
          selectable
          :selected-ids="selectedIds"
          sortable
          :sort="sort"
          :filterable="filterRowVisible"
          :filters="filters"
          @update:selected-ids="selectedIds = $event"
          @row-dblclick="handleRowDblClick"
          @row-contextmenu="(row, ev) => ctx.onContextMenu(row as DocListRow, ev)"
          @sort-change="onSortChange"
          @filter-change="onFilterChange"
        >
          <template #cell-number="{ row }">
            <RouterLink class="document-list-link" :to="config.itemRoute((row as DocListRow).id as number)">
              <strong>{{ (row as DocListRow).number }}</strong>
            </RouterLink>
          </template>
          <template #cell-date="{ row }">{{ formatDate((row as DocListRow).date as string) }}</template>
          <template #cell-sum_without_vat="{ row }">{{ formatNumber((row as DocListRow).sum_without_vat as number) }}</template>
          <template #cell-sum_with_vat="{ row }">{{ formatNumber((row as DocListRow).sum_with_vat as number) }}</template>
          <template #cell-is_posted="{ row }">
            <span :class="['status-pill', (row as DocListRow).is_posted ? 'posted' : 'draft']">
              {{ (row as DocListRow).is_posted ? 'Проведён' : 'Черновик' }}
            </span>
          </template>
        </DataTable>

        <div class="toolbar pagination-row">
          <span class="muted">Страница {{ pagination.page }} из {{ pagination.pages }}. Всего: {{ pagination.total }}</span>
          <div class="table-actions">
            <button class="button button-secondary" type="button" :disabled="page <= 1" @click="page -= 1">Назад</button>
            <button class="button button-secondary" type="button" :disabled="page >= pagination.pages" @click="page += 1">Вперёд</button>
          </div>
        </div>
      </div>
    </section>

    <ListSettingsDialog
      :open="settingsOpen"
      :columns="config.columns"
      :states="settingsStates"
      @close="settingsOpen = false"
      @apply="onApplyColumns"
      @reset="onResetColumns"
    />
    <ContextMenu
      :open="ctx.menuOpen.value"
      :items="ctx.menuItems.value"
      :x="ctx.menuX.value"
      :y="ctx.menuY.value"
      @close="ctx.closeMenu()"
      @select="ctx.onSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import ContextMenu from '../../components/common/ContextMenu.vue'
import ListCommandBar from '../../components/documents/ListCommandBar.vue'
import ListSettingsDialog from '../../components/documents/ListSettingsDialog.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { useDocumentList } from '../../composables/useDocumentList'
import { useDocumentListContextMenu } from '../../composables/useDocumentListContextMenu'
import { goodsDocumentListConfig } from '../../config/documentLists'
import { useWorkspaceStore } from '../../stores/workspace'
import type { DocListRow } from '../../config/documentListTypes'
import type { ColumnState } from '../../composables/useListSettings'

const props = withDefaults(defineProps<{ tabId?: string; kind?: 'receipt' | 'issue' }>(), { kind: 'receipt' })
const workspace = useWorkspaceStore()
const config = computed(() => goodsDocumentListConfig(props.kind ?? 'receipt'))
const state = useDocumentList(config.value)
const ctx = useDocumentListContextMenu(config.value, state)

// Workspace panes stay mounted while hidden. Refresh when the user returns so
// documents created or changed in another tab are immediately visible.
watch(
  () => workspace.activeId,
  (activeId, previousId) => {
    if (activeId === props.tabId && previousId !== activeId) {
      void state.loadItems()
    }
  },
)

useHeaderBar(props.tabId, computed(() => config.value.title), computed(() => []))

const {
  rows, loading, error, search, page, pagination, selectedIds,
  sort, filters, filterRowVisible, effectiveColumns,
  onSortChange, onFilterChange,
} = state

const settingsOpen = ref(false)
const settingsStates = computed<ColumnState[]>(() => {
  const saved = state.settings.savedColumns.value
  return saved ?? config.value.columns.map((c) => ({ key: c.key, visible: c.defaultVisible !== false }))
})

function onApplyColumns(states: ColumnState[]) {
  void state.settings.saveColumns(states)
}
function onResetColumns() {
  void state.settings.resetColumns()
}

function handleRowDblClick(row: Record<string, unknown>) {
  state.openItem((row as DocListRow).id as number)
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value ?? 0)
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const [y, m, d] = value.split('-').map(Number)
  if (!y || !m || !d) return value
  return new Date(y, m - 1, d).toLocaleDateString('ru-RU')
}
</script>

<style scoped>
.search-row { margin-bottom: 0.75rem; }
.pagination-row { justify-content: space-between; margin-top: 1rem; }
</style>
