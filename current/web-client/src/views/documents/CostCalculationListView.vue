<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar search-row">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру или периоду" />
        </div>

        <ListCommandBar :state="state" :config="config" @open-settings="settingsOpen = true">
          <template #commands>
            <button
              v-if="canCalculate"
              class="button button-secondary"
              type="button"
              @click="runCalculateSelected"
            >
              Рассчитать
            </button>
          </template>
        </ListCommandBar>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <DataTable
          :columns="effectiveColumns"
          :rows="rows as Record<string, unknown>[]"
          :loading="loading"
          empty-text="Расчётов пока нет"
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
            <strong>{{ (row as DocListRow).number }}</strong>
          </template>
          <template #cell-date="{ row }">{{ formatDate((row as DocListRow).date as string) }}</template>
          <template #cell-status="{ row }">
            <span :class="['status-pill', statusClass((row as DocListRow).status as string)]">
              {{ statusLabel((row as DocListRow).status as string) }}
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
import { computed, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import ContextMenu from '../../components/common/ContextMenu.vue'
import ListCommandBar from '../../components/documents/ListCommandBar.vue'
import ListSettingsDialog from '../../components/documents/ListSettingsDialog.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { useDocumentList } from '../../composables/useDocumentList'
import { useDocumentListContextMenu } from '../../composables/useDocumentListContextMenu'
import { costCalculationListConfig } from '../../config/documentLists'
import { calculateCost } from '../../api/costAccounting'
import { useAuthStore } from '../../stores/auth'
import type { DocListRow } from '../../config/documentListTypes'
import type { ColumnState } from '../../composables/useListSettings'

const props = defineProps<{ tabId?: string }>()
const config = costCalculationListConfig
const state = useDocumentList(config)
const ctx = useDocumentListContextMenu(config, state)
const auth = useAuthStore()

useHeaderBar(props.tabId, computed(() => config.title), computed(() => []))

const {
  rows, loading, error, search, page, pagination, selectedIds,
  sort, filters, filterRowVisible, effectiveColumns,
  onSortChange, onFilterChange,
} = state

const settingsOpen = ref(false)
const settingsStates = computed<ColumnState[]>(() => {
  const saved = state.settings.savedColumns.value
  return saved ?? config.columns.map((c) => ({ key: c.key, visible: c.defaultVisible !== false }))
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

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const [y, m, d] = value.split('-').map(Number)
  if (!y || !m || !d) return value
  return new Date(y, m - 1, d).toLocaleDateString('ru-RU')
}

function statusClass(s: string) {
  return s === 'posted' ? 'posted' : s === 'calculated' ? 'success' : 'draft'
}

function statusLabel(s: string) {
  return s === 'posted' ? 'Проведён' : s === 'calculated' ? 'Рассчитан' : 'Черновик'
}

const canCalculate = computed(() => {
  if (!auth.canManageCost) return false
  if (!selectedIds.value.length) return false
  return selectedIds.value.every((id) => {
    const row = rows.value.find((r) => String(r.id) === String(id))
    return row && row.status === 'draft'
  })
})

async function runCalculateSelected() {
  if (!selectedIds.value.length) return
  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      await calculateCost(Number(id))
    } catch {
      failed++
    }
  }
  await state.loadItems()
  if (failed) error.value = `Не удалось рассчитать ${failed} ${failed === 1 ? 'расчёт' : 'расчётов'}`
}
</script>

<style scoped>
.search-row { margin-bottom: 0.75rem; }
.pagination-row { justify-content: space-between; margin-top: 1rem; }
.status-pill.success { background: rgba(34, 197, 94, 0.12); color: var(--success, #16a34a); }
</style>
