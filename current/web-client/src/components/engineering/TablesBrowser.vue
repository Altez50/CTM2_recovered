<template>
  <div class="eng-split">
    <aside class="panel eng-side">
      <EngineeringTableTree
        :catalog="catalog"
        :selected-table="table"
        compact
        @select-table="onSelectTable"
      />
    </aside>

    <section class="panel eng-main">
      <div class="panel-body">
        <template v-if="table">
          <div class="toolbar eng-toolbar">
            <div class="eng-table-title">
              <strong>{{ currentSynonym }}</strong>
              <span class="muted eng-phys">{{ table }}</span>
            </div>
            <input
              v-model="search"
              class="input"
              type="search"
              placeholder="Поиск…"
              style="max-width: 16rem"
            />
            <button class="button button-secondary" type="button" title="Отбор по колонкам" @click="filterable = !filterable">
              Отбор
            </button>
            <button class="button button-secondary" type="button" title="Настройка списка" @click="settingsOpen = true">
              Настройка
            </button>
            <button class="button button-secondary" type="button" title="Экспорт CSV" @click="exportCsv">CSV</button>
            <button class="button button-secondary" type="button" title="Обновить" @click="loadData">↻</button>
          </div>

          <p v-if="error" class="muted" style="color: var(--danger)">{{ error }}</p>

          <DataTable
            :columns="columns"
            :rows="rows"
            :loading="loading"
            :sortable="true"
            :sort="sort"
            :filterable="filterable"
            :filters="filterValues"
            empty-text="Записей нет"
            @sort-change="onSortChange"
            @filter-change="onFilterChange"
          />

          <div class="toolbar pagination-row">
            <span class="muted">
              Стр. {{ pagination.page }} из {{ pagination.pages }} · Всего: {{ pagination.total }}
            </span>
            <div class="table-actions">
              <button class="button button-secondary" type="button" :disabled="pagination.page <= 1" @click="pagination.page--">Назад</button>
              <button class="button button-secondary" type="button" :disabled="pagination.page >= pagination.pages" @click="pagination.page++">Вперёд</button>
            </div>
          </div>
        </template>
        <div v-else class="empty-state">Выберите таблицу слева</div>
      </div>
    </section>

    <ListSettingsDialog
      :open="settingsOpen"
      :columns="settingsColumns"
      :states="settingsStates"
      @apply="onApplySettings"
      @reset="resetSettings"
      @close="settingsOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import DataTable from '../common/DataTable.vue'
import type { Column } from '../common/DataTable.vue'
import EngineeringTableTree from './EngineeringTableTree.vue'
import ListSettingsDialog from '../documents/ListSettingsDialog.vue'
import { getTableData, type EngineeringCatalog, type EngineeringField } from '../../api/engineering'
import { getUserSettings, putUserSettings } from '../../api/system'
import { downloadCsv } from '../../utils/reportExport'

const props = defineProps<{ catalog: EngineeringCatalog | null }>()

const table = ref('')
const rows = ref<Record<string, unknown>[]>([])
const fieldDefs = ref<EngineeringField[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const filterable = ref(false)
const filterValues = ref<Record<string, string>>({})
const sort = reactive<{ key: string | null; order: 'asc' | 'desc' | null }>({ key: null, order: null })
const pagination = reactive({ page: 1, pages: 1, total: 0 })
const settingsOpen = ref(false)
const hiddenColumns = ref<Set<string>>(new Set())

let searchTimer = 0

const currentSynonym = computed(() => {
  const cat = props.catalog
  if (!cat) return table.value
  for (const c of cat.categories) {
    const t = c.tables.find((x) => x.name === table.value)
    if (t) return t.synonym
  }
  return table.value
})

const settingsColumns = computed(() =>
  fieldDefs.value.map((f) => ({ key: f.name, label: `${f.synonym} (${f.name})` })),
)

const settingsStates = computed(() =>
  fieldDefs.value.map((f) => ({ key: f.name, visible: !hiddenColumns.value.has(f.name) })),
)

const columns = computed<Column[]>(() =>
  fieldDefs.value
    .filter((f) => !hiddenColumns.value.has(f.name))
    .map((f) => ({
      key: f.name,
      label: f.synonym,
      sortable: true,
      visible: true,
      filter: f.type === 'text' ? { type: 'text' as const, placeholder: '…' }
        : f.type === 'number' ? { type: 'number' as const, placeholder: '…' }
        : f.type === 'date' ? { type: 'date' as const }
        : undefined,
    })),
)

function onSelectTable(name: string) {
  if (table.value !== name) {
    table.value = name
    pagination.page = 1
    search.value = ''
    filterValues.value = {}
    sort.key = null
    sort.order = null
    void loadData()
  }
}

function onSortChange(key: string) {
  if (sort.key !== key) {
    sort.key = key
    sort.order = 'asc'
  } else if (sort.order === 'asc') {
    sort.order = 'desc'
  } else if (sort.order === 'desc') {
    sort.key = null
    sort.order = null
  } else {
    sort.order = 'asc'
  }
  pagination.page = 1
  void loadData()
}

function onFilterChange(key: string, value: string) {
  filterValues.value = { ...filterValues.value, [key]: value }
  pagination.page = 1
  void loadData()
}

async function loadData() {
  if (!table.value) return
  loading.value = true
  error.value = ''
  try {
    const resp = await getTableData(table.value, {
      page: pagination.page,
      page_size: 50,
      search: search.value.trim() || undefined,
      sort_by: sort.key ?? undefined,
      sort_order: sort.order ?? undefined,
      filters: filterValues.value,
    })
    const data = resp.data
    rows.value = data.rows
    fieldDefs.value = data.columns
    if (data.columns.length && pagination.page === 1 && !sort.key) {
      // доверяем серверной сортировке по умолчанию
    }
    pagination.page = resp.pagination?.page ?? 1
    pagination.pages = resp.pagination?.pages ?? 1
    pagination.total = resp.pagination?.total ?? 0
    await loadSettings()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

async function loadSettings() {
  try {
    const resp = await getUserSettings(`tables:${table.value}`)
    const raw = resp.data?.columns
    if (raw) {
      const parsed = JSON.parse(raw)
      hiddenColumns.value = new Set(
        fieldDefs.value.filter((f) => !parsed.includes(f.name)).map((f) => f.name),
      )
    }
  } catch {
    // нет сохранённых настроек — используем скрытие по умолчанию
    hiddenColumns.value = new Set(fieldDefs.value.filter((f) => f.hidden_default).map((f) => f.name))
  }
}

async function saveSettings(active: string[]) {
  try {
    await putUserSettings(`tables:${table.value}`, { columns: JSON.stringify(active) })
  } catch {
    /* настройки опциональны */
  }
}

function onApplySettings(states: { key: string; visible: boolean }[]) {
  const active = states.filter((s) => s.visible).map((s) => s.key)
  const activeSet = new Set(active)
  hiddenColumns.value = new Set(fieldDefs.value.filter((f) => !activeSet.has(f.name)).map((f) => f.name))
  void saveSettings(active)
  settingsOpen.value = false
}

function resetSettings() {
  hiddenColumns.value = new Set(fieldDefs.value.filter((f) => f.hidden_default).map((f) => f.name))
  void saveSettings(fieldDefs.value.filter((f) => !f.hidden_default).map((f) => f.name))
}

function exportCsv() {
  const cols = columns.value
  const headers = cols.map((c) => c.label)
  const data = rows.value.map((r) => cols.map((c) => (r[c.key] as string | number | null) ?? ''))
  downloadCsv(`${table.value}`, headers, data)
}

watch(search, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    pagination.page = 1
    void loadData()
  }, 350)
})
</script>

<style scoped>
.eng-split {
  display: grid;
  grid-template-columns: 17rem 1fr;
  gap: 1rem;
  height: 100%;
  min-height: 0;
}
.eng-side {
  padding: 0.6rem;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.eng-main {
  min-width: 0;
  overflow: auto;
}
.eng-toolbar {
  justify-content: flex-start;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}
.eng-table-title {
  display: flex;
  flex-direction: column;
  margin-right: auto;
}
.eng-phys {
  font-size: 0.75rem;
  font-family: ui-monospace, monospace;
}
.pagination-row {
  justify-content: space-between;
  margin-top: 0.75rem;
}
@media (max-width: 900px) {
  .eng-split {
    grid-template-columns: 1fr;
  }
  .eng-side {
    max-height: 14rem;
  }
}
</style>
