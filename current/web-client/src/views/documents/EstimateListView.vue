<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar search-row">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру, заказчику, объекту" />
        </div>

        <ListCommandBar :state="state" :config="config" @open-settings="settingsOpen = true">
          <template #commands>
            <button
              v-if="state.singleRow.value"
              class="button button-secondary"
              type="button"
              @click="printDocument(state.singleRow.value?.id as number)"
            >
              Печать сметы
            </button>
            <button
              v-if="state.singleRow.value"
              class="button button-secondary"
              type="button"
              @click="printActDocument(state.singleRow.value?.id as number)"
            >
              Печать акта
            </button>
          </template>
        </ListCommandBar>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <DataTable
          :columns="effectiveColumns"
          :rows="rows as Record<string, unknown>[]"
          :loading="loading"
          empty-text="Смет пока нет"
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
            <RouterLink class="document-list-link" :to="`/documents/estimates/${(row as unknown as Estimate).id}`">
              <strong>{{ (row as unknown as Estimate).number }}</strong>
            </RouterLink>
          </template>
          <template #cell-date="{ row }">
            <RouterLink class="document-list-link" :to="`/documents/estimates/${(row as unknown as Estimate).id}`">
              {{ formatDate((row as unknown as Estimate).date) }}
            </RouterLink>
          </template>
          <template #cell-total_sum="{ row }">
            {{ formatNumber((row as unknown as Estimate).total_sum) }}
          </template>
          <template #cell-is_posted="{ row }">
            <span :class="['status-pill', (row as unknown as Estimate).is_posted ? 'posted' : 'draft']">
              {{ (row as unknown as Estimate).is_posted ? 'Проведен' : 'Черновик' }}
            </span>
          </template>
        </DataTable>

        <div class="toolbar pagination-row">
          <span class="muted">
            Страница {{ pagination.page }} из {{ pagination.pages }}. Всего: {{ pagination.total }}
          </span>
          <div class="table-actions">
            <button class="button button-secondary" type="button" :disabled="page <= 1" @click="page -= 1">Назад</button>
            <button class="button button-secondary" type="button" :disabled="page >= pagination.pages" @click="page += 1">
              Вперёд
            </button>
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
    <PrintFormatDialog
      :open="printState !== null"
      :title="printState?.action === 'act' ? 'Печать акта' : 'Печать сметы'"
      @close="printState = null"
      @select="runPrint"
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
import PrintFormatDialog from '../../components/common/PrintFormatDialog.vue'
import ContextMenu from '../../components/common/ContextMenu.vue'
import ListCommandBar from '../../components/documents/ListCommandBar.vue'
import ListSettingsDialog from '../../components/documents/ListSettingsDialog.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { useDocumentList } from '../../composables/useDocumentList'
import { useDocumentListContextMenu } from '../../composables/useDocumentListContextMenu'
import { estimateListConfig } from '../../config/documentLists'
import { printAct, printEstimate } from '../../api/documents'
import type { Estimate } from '../../types/models'
import type { DocListRow } from '../../config/documentListTypes'
import type { ColumnState } from '../../composables/useListSettings'

const props = defineProps<{ tabId?: string }>()
const config = estimateListConfig
const state = useDocumentList(config)
const ctx = useDocumentListContextMenu(config, state)

useHeaderBar(props.tabId, computed(() => config.title), computed(() => []))

const {
  rows, loading, error, search, page, pagination, selectedIds,
  sort, filters, filterRowVisible, effectiveColumns,
  onSortChange, onFilterChange,
} = state

const settingsOpen = ref(false)
const printState = ref<{ action: 'estimate' | 'act'; id: number } | null>(null)

const settingsStates = computed<ColumnState[]>(() => {
  const saved = state.settings.savedColumns.value
  if (saved) return saved
  return config.columns.map((c) => ({ key: c.key, visible: c.defaultVisible !== false }))
})

function onApplyColumns(states: ColumnState[]) {
  void state.settings.saveColumns(states)
}

async function onResetColumns() {
  await state.settings.resetColumns()
}

function handleRowDblClick(row: Record<string, unknown>) {
  state.openItem((row as unknown as Estimate).id as number)
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

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function printDocument(id?: number) {
  if (!id) return
  printState.value = { action: 'estimate', id }
}

function printActDocument(id?: number) {
  if (!id) return
  printState.value = { action: 'act', id }
}

async function runPrint(format: 'excel' | 'pdf') {
  if (!printState.value) return
  const { action, id } = printState.value
  try {
    const blob = action === 'estimate' ? await printEstimate(id, format) : await printAct(id, format)
    downloadBlob(blob, `${action}_${id}.${format === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сформировать печатную форму'
  } finally {
    printState.value = null
  }
}
</script>

<style scoped>
.search-row {
  margin-bottom: 0.75rem;
}
.pagination-row {
  justify-content: space-between;
  margin-top: 1rem;
}
</style>
