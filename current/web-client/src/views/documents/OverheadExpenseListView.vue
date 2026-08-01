<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar search-row">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру или периоду" />
        </div>

        <ListCommandBar :state="state" :config="config" @open-settings="settingsOpen = true" />

        <div v-if="auth.canManageCost" class="toolbar distribution-bar">
          <span class="muted">Распределение за период:</span>
          <input v-model="distPeriod" class="input input-period" type="month" />
          <select v-model="distBaseId" class="select">
            <option :value="0" disabled>База распределения…</option>
            <option v-for="b in allocationBases" :key="b.id" :value="b.id">{{ b.name }}</option>
          </select>
          <button class="button button-success" type="button" :disabled="!distBaseId || distributing" @click="runDistribute">Распределить</button>
          <button class="button button-warning" type="button" :disabled="distributing" @click="runCancelDistribution">Отменить распределение</button>
        </div>

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
            <RouterLink class="document-list-link" :to="`/documents/overhead-expenses/${(row as DocListRow).id}`">
              <strong>{{ (row as DocListRow).number }}</strong>
            </RouterLink>
          </template>
          <template #cell-date="{ row }">{{ formatDate((row as DocListRow).date as string) }}</template>
          <template #cell-is_distributed="{ row }">
            <span :class="['status-pill', (row as DocListRow).is_distributed ? 'posted' : 'draft']">
              {{ (row as DocListRow).is_distributed ? 'Распределены' : 'Не распределены' }}
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
import { computed, onMounted, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import ContextMenu from '../../components/common/ContextMenu.vue'
import ListCommandBar from '../../components/documents/ListCommandBar.vue'
import ListSettingsDialog from '../../components/documents/ListSettingsDialog.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { useDocumentList } from '../../composables/useDocumentList'
import { useDocumentListContextMenu } from '../../composables/useDocumentListContextMenu'
import { overheadExpenseListConfig } from '../../config/documentLists'
import { listAllocationBases, distributeOverhead, cancelOverheadDistribution } from '../../api/costAccounting'
import { useAuthStore } from '../../stores/auth'
import type { DocListRow } from '../../config/documentListTypes'
import type { AllocationBase } from '../../types/costAccounting'
import type { ColumnState } from '../../composables/useListSettings'

const props = defineProps<{ tabId?: string }>()
const config = overheadExpenseListConfig
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

// ── Распределение накладных расходов ───────────────────────────────────
const allocationBases = ref<AllocationBase[]>([])
const distPeriod = ref(new Date().toISOString().slice(0, 7))
const distBaseId = ref(0)
const distributing = ref(false)

async function runDistribute() {
  if (!distPeriod.value || !distBaseId.value) return
  if (!window.confirm(`Распределить накладные расходы за период ${distPeriod.value}?`)) return
  distributing.value = true
  try {
    await distributeOverhead({ period: distPeriod.value, allocation_base_id: distBaseId.value, object_id: 0 })
    await state.loadItems()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка распределения'
  } finally {
    distributing.value = false
  }
}

async function runCancelDistribution() {
  if (!distPeriod.value) return
  if (!window.confirm(`Отменить распределение за период ${distPeriod.value}?`)) return
  distributing.value = true
  try {
    await cancelOverheadDistribution(distPeriod.value)
    await state.loadItems()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка отмены'
  } finally {
    distributing.value = false
  }
}

onMounted(async () => {
  try {
    const r = await listAllocationBases()
    allocationBases.value = r.data ?? []
  } catch {
    /* ignore */
  }
})
</script>

<style scoped>
.search-row { margin-bottom: 0.75rem; }
.distribution-bar { margin: 0.5rem 0 0.75rem; gap: 0.5rem; flex-wrap: wrap; }
.input-period { width: 150px; }
.pagination-row { justify-content: space-between; margin-top: 1rem; }
</style>
