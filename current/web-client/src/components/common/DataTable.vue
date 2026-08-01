<template>
  <div class="table-shell">
    <div v-if="loading" class="empty-state">Загрузка данных…</div>
    <template v-else-if="rows.length">
      <div class="desktop-table">
        <table>
          <thead>
            <tr>
              <th
                v-for="column in visibleColumns"
                :key="column.key"
                :class="['th-head', { sortable: column.sortable, sorted: sort?.key === column.key }]"
                :title="column.sortable ? 'Сортировка по колонке' : undefined"
                @click="column.sortable ? onHeaderClick(column.key) : undefined"
              >
                <span class="th-label">{{ column.label }}</span>
                <span v-if="column.sortable" class="th-arrow">
                  {{ sort?.key === column.key ? (sort.order === 'asc' ? '▲' : sort.order === 'desc' ? '▼' : '↕') : '↕' }}
                </span>
              </th>
            </tr>
            <tr v-if="filterable" class="filter-row">
              <th v-for="column in visibleColumns" :key="column.key">
                <template v-if="column.filter">
                  <select
                    v-if="column.filter.type === 'select'"
                    class="filter-input"
                    :value="filterValues[column.key] ?? ''"
                    @change="onFilterChange(column.key, ($event.target as HTMLSelectElement).value)"
                  >
                    <option value="">{{ column.filter.placeholder ?? '—' }}</option>
                    <option v-for="opt in column.filter.options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  </select>
                  <input
                    v-else
                    class="filter-input"
                    :type="column.filter.type"
                    :placeholder="column.filter.placeholder ?? '…'"
                    :value="filterValues[column.key] ?? ''"
                    @input="onFilterChange(column.key, ($event.target as HTMLInputElement).value)"
                  />
                </template>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in rows"
              :key="getRowKey(row)"
              :class="{
                'row-selected': selectable && isSelected(row),
                'row-marked': isMarked(row),
              }"
              :style="selectable ? 'cursor: pointer' : undefined"
              @click="handleRowClick($event, row, index)"
              @dblclick="handleRowDblClick($event, row)"
              @contextmenu.prevent="handleRowContextMenu($event, row)"
            >
              <td v-for="column in visibleColumns" :key="column.key">
                <slot :name="`cell-${column.key}`" :row="row">
                  {{ row[column.key] }}
                </slot>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mobile-cards">
        <article
          v-for="(row, index) in rows"
          :key="getRowKey(row)"
          class="panel mobile-card"
          :class="{ 'row-selected': selectable && isSelected(row), 'row-marked': isMarked(row) }"
          @click="handleRowClick($event, row, index)"
          @dblclick="handleRowDblClick($event, row)"
          @contextmenu.prevent="handleRowContextMenu($event, row)"
        >
          <div v-for="column in visibleColumns" :key="column.key" class="card-row">
            <span class="card-label">{{ column.label }}</span>
            <div class="card-value">
              <slot :name="`cell-${column.key}`" :row="row">
                {{ row[column.key] }}
              </slot>
            </div>
          </div>
        </article>
      </div>
    </template>
    <div v-else class="empty-state">{{ emptyText }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

export interface FilterOption {
  value: string
  label: string
}

export interface ColumnFilter {
  type: 'text' | 'number' | 'date' | 'month' | 'select'
  placeholder?: string
  options?: FilterOption[]
}

export interface Column {
  key: string
  label: string
  sortable?: boolean
  visible?: boolean
  filter?: ColumnFilter
}

export interface SortState {
  key: string | null
  order: 'asc' | 'desc' | null
}

const props = withDefaults(
  defineProps<{
    columns: Column[]
    rows: any[]
    loading?: boolean
    emptyText?: string
    rowKey?: string
    selectable?: boolean
    selectedIds?: string[]
    sortable?: boolean
    sort?: SortState
    filterable?: boolean
    filters?: Record<string, string>
  }>(),
  {
    loading: false,
    emptyText: 'Записей пока нет',
    rowKey: 'id',
    selectable: false,
    selectedIds: () => [],
    sortable: false,
    filterable: false,
  },
)

const emit = defineEmits<{
  'update:selectedIds': [ids: string[]]
  'row-dblclick': [row: Record<string, unknown>]
  'row-contextmenu': [row: Record<string, unknown>, event: MouseEvent]
  'sort-change': [key: string]
  'filter-change': [key: string, value: string]
}>()

const visibleColumns = computed(() => props.columns.filter((c) => c.visible !== false))

// Локальное зеркало значений строки отбора (управляемое, чтобы input оставался
// контролируемым при сбросе снаружи через пропс filters).
const filterValues = computed<Record<string, string>>(() => ({ ...(props.filters ?? {}) }))

const lastClickedIndex = ref<number | null>(null)

function getRowKey(row: Record<string, unknown>) {
  return String(row[props.rowKey] ?? Math.random())
}

function isSelected(row: Record<string, unknown>) {
  return props.selectedIds.includes(getRowKey(row))
}

function isMarked(row: Record<string, unknown>) {
  return !!(row as Record<string, unknown>).marked_for_deletion
}

function onHeaderClick(key: string) {
  emit('sort-change', key)
}

function onFilterChange(key: string, value: string) {
  emit('filter-change', key, value)
}

function isInteractiveElement(target: HTMLElement): boolean {
  return target.closest('a, button, input, select, label, [role="button"]') !== null
}

function handleRowClick(event: MouseEvent, row: Record<string, unknown>, index: number) {
  if (!props.selectable) return
  if (isInteractiveElement(event.target as HTMLElement)) return

  const rowId = getRowKey(row)

  if (event.ctrlKey || event.metaKey) {
    // Ctrl+click: toggle selection of this row
    const newIds = [...props.selectedIds]
    const idx = newIds.indexOf(rowId)
    if (idx >= 0) {
      newIds.splice(idx, 1)
    } else {
      newIds.push(rowId)
    }
    emit('update:selectedIds', newIds)
    lastClickedIndex.value = index
  } else if (event.shiftKey && lastClickedIndex.value !== null) {
    // Shift+click: extend selection from last clicked to current
    const start = Math.min(lastClickedIndex.value, index)
    const end = Math.max(lastClickedIndex.value, index)
    const rangeIds = new Set(props.selectedIds)
    for (let i = start; i <= end; i++) {
      rangeIds.add(getRowKey(props.rows[i]))
    }
    emit('update:selectedIds', [...rangeIds])
  } else {
    // Plain click: select only this row
    emit('update:selectedIds', [rowId])
    lastClickedIndex.value = index
  }
}

function handleRowDblClick(event: MouseEvent, row: Record<string, unknown>) {
  if (!props.selectable) return
  if (isInteractiveElement(event.target as HTMLElement)) return
  emit('row-dblclick', row)
}

function handleRowContextMenu(event: MouseEvent, row: Record<string, unknown>) {
  emit('row-contextmenu', row, event)
}
</script>

<style scoped>
.table-shell {
  display: grid;
  gap: 1rem;
}

.desktop-table {
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  text-align: left;
  padding: 0.9rem 0.85rem;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

th {
  color: var(--text-soft);
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.th-head.sortable {
  cursor: pointer;
  user-select: none;
}

.th-head.sortable:hover {
  color: var(--accent);
}

.th-head.sorted {
  color: var(--accent);
}

.th-label {
  vertical-align: middle;
}

.th-arrow {
  margin-left: 0.35rem;
  font-size: 0.75rem;
  opacity: 0.85;
}

.filter-row th {
  padding-top: 0;
  padding-bottom: 0.6rem;
  text-transform: none;
  letter-spacing: 0;
}

.filter-input {
  width: 100%;
  min-width: 5rem;
  padding: 0.3rem 0.45rem;
  font-size: 0.82rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-panel, #fff);
  color: var(--text);
}

tr.row-selected {
  background: rgba(178, 76, 45, 0.09);
}

tr.row-selected:hover {
  background: rgba(178, 76, 45, 0.15);
}

tr.row-marked td,
.mobile-card.row-marked {
  opacity: 0.6;
}

tr.row-marked td {
  text-decoration: line-through;
}

.empty-state {
  padding: 1.5rem;
  text-align: center;
  color: var(--text-soft);
}

.mobile-cards {
  display: none;
  gap: 0.85rem;
}

.mobile-card {
  padding: 1rem;
}

.mobile-card.row-selected {
  border-color: rgba(178, 76, 45, 0.32);
  background: rgba(178, 76, 45, 0.06);
  box-shadow: 0 0 0 1px rgba(178, 76, 45, 0.18);
}

.card-row {
  display: grid;
  gap: 0.3rem;
  padding: 0.4rem 0;
}

.card-label {
  color: var(--text-soft);
  font-size: 0.82rem;
}

.card-value {
  font-weight: 600;
}

@media (max-width: 767px) {
  .desktop-table {
    display: none;
  }

  .mobile-cards {
    display: grid;
  }
}
</style>
