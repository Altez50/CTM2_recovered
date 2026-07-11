<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar timesheet-filters-row">
          <input
            v-model="search"
            class="input toolbar-grow timesheet-filter-search"
            type="search"
            placeholder="Поиск по номеру, объекту, смете или бригадиру"
          />
          <select v-model="objectId" class="select timesheet-filter-control timesheet-filter-object">
            <option :value="null">Все объекты</option>
            <option v-for="item in objects" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
          <input v-model="monthYear" class="input timesheet-filter-control timesheet-filter-month" type="month" />
          <select v-model="postingFilter" class="select timesheet-filter-control timesheet-filter-status">
            <option value="">Все статусы</option>
            <option value="draft">Черновики</option>
            <option value="posted">Проведенные</option>
          </select>
          <button class="button button-secondary timesheet-filter-action" type="button" title="Обновить" @click="loadItems">↻</button>
          <button class="button button-primary timesheet-filter-action" type="button" @click="router.push('/documents/timesheets/new')">Создать табель</button>
        </div>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <SelectionActionBar
          :selected-count="selectedIds.length"
          @deselect-all="selectedIds = []"
        >
          <button
            v-if="selectedIds.length === 1"
            class="button button-secondary"
            type="button"
            @click="openItem(Number(selectedIds[0]))"
          >
            Открыть
          </button>
          <button
            v-if="selectedIds.length === 1"
            class="button button-secondary"
            type="button"
            title="Копировать"
            @click="copyItem(Number(selectedIds[0]))"
          >
            ⎘
          </button>
          <button
            v-if="canManagePostingSelected && canPostSelected"
            class="button button-secondary"
            type="button"
            title="Провести"
            @click="changePostingSelected('post')"
          >
            ✓
          </button>
          <button
            v-if="canManagePostingSelected && canUnpostSelected"
            class="button button-secondary"
            type="button"
            title="Отменить проведение"
            @click="changePostingSelected('unpost')"
          >
            ↺
          </button>
          <button
            v-if="selectedIds.length === 1"
            class="button button-secondary"
            type="button"
            @click="printItem(Number(selectedIds[0]))"
          >
            Печать
          </button>
          <button
            v-if="canDeleteSelected"
            class="button button-danger"
            type="button"
            title="Удалить"
            @click="removeSelected"
          >
            ✕
          </button>
        </SelectionActionBar>

        <DataTable
          :columns="columns"
          :rows="rows as Record<string, unknown>[]"
          :loading="loading"
          empty-text="Табелей пока нет"
          selectable
          :selected-ids="selectedIds"
          @update:selected-ids="selectedIds = $event"
          @row-dblclick="handleRowDblClick"
        >
          <template #cell-number="{ row }">
            <RouterLink class="document-list-link" :to="`/documents/timesheets/${(row as unknown as Timesheet).id}`">
              <strong>{{ (row as unknown as Timesheet).number }}</strong>
            </RouterLink>
          </template>
          <template #cell-date="{ row }">
            <RouterLink class="document-list-link" :to="`/documents/timesheets/${(row as unknown as Timesheet).id}`">
              {{ formatDate((row as unknown as Timesheet).date) }}
            </RouterLink>
          </template>
          <template #cell-month_year="{ row }">
            {{ formatMonthYear((row as unknown as Timesheet).month_year) }}
          </template>
          <template #cell-total_hours="{ row }">
            {{ formatNumber((row as unknown as Timesheet).total_hours) }}
          </template>
          <template #cell-total_amount="{ row }">
            {{ formatNumber((row as unknown as Timesheet).total_amount) }}
          </template>
          <template #cell-is_posted="{ row }">
            <span :class="['status-pill', (row as unknown as Timesheet).is_posted ? 'posted' : 'draft']">
              {{ (row as unknown as Timesheet).is_posted ? 'Проведен' : 'Черновик' }}
            </span>
          </template>
        </DataTable>

        <div class="toolbar pagination-row">
          <span class="muted">Страница {{ pagination.page }} из {{ pagination.pages }}. Всего: {{ pagination.total }}</span>
          <div class="table-actions">
            <button class="button button-secondary" type="button" :disabled="page <= 1" @click="page -= 1">Назад</button>
            <button class="button button-secondary" type="button" :disabled="page >= pagination.pages" @click="page += 1">Вперед</button>
          </div>
        </div>
      </div>
    </section>
    <PrintFormatDialog
      :open="printId !== null"
      title="Печать табеля"
      @close="printId = null"
      @select="runPrint"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from '../../components/common/DataTable.vue'
import PrintFormatDialog from '../../components/common/PrintFormatDialog.vue'
import SelectionActionBar from '../../components/common/SelectionActionBar.vue'
import {
  copyTimesheet,
  deleteTimesheet,
  listTimesheets,
  postTimesheet,
  printTimesheet,
  unpostTimesheet,
} from '../../api/documents'
import { listReferences } from '../../api/references'
import { useAuthStore } from '../../stores/auth'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import type { ObjectRecord, Timesheet } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
const auth = useAuthStore()
const router = useRouter()

const headerActions = computed<HeaderAction[]>(() => [
  { key: 'create', icon: '+', title: 'Создать табель', variant: 'primary', to: '/documents/timesheets/new' },
])
useHeaderBar(props.tabId, computed(() => 'Табели'), headerActions)

const rows = ref<Timesheet[]>([])
const objects = ref<ObjectRecord[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const objectId = ref<number | null>(null)
const monthYear = ref('')
const postingFilter = ref('')
const page = ref(1)
const pagination = ref({ page: 1, pages: 1, total: 0 })
const selectedIds = ref<string[]>([])
let searchTimer = 0

const columns = [
  { key: 'number', label: 'Номер' },
  { key: 'date', label: 'Дата' },
  { key: 'month_year', label: 'Период' },
  { key: 'object_name', label: 'Объект' },
  { key: 'estimate_number', label: 'Смета' },
  { key: 'foreman_name', label: 'Бригадир' },
  { key: 'total_hours', label: 'Часы' },
  { key: 'total_amount', label: 'Сумма' },
  { key: 'is_posted', label: 'Статус' },
]

const canPostSelected = computed(() => {
  if (!selectedIds.value.length) return false
  return selectedIds.value.every((id) => {
    const row = rows.value.find((r) => String(r.id) === id)
    return row && !row.is_posted
  })
})

const canUnpostSelected = computed(() => {
  if (!selectedIds.value.length) return false
  return selectedIds.value.every((id) => {
    const row = rows.value.find((r) => String(r.id) === id)
    return row && row.is_posted
  })
})

const canManagePostingSelected = computed(() => {
  if (auth.user?.role === 'admin') return true
  if (auth.user?.role !== 'foreman') return false
  return selectedIds.value.every((id) => {
    const row = rows.value.find((r) => String(r.id) === id)
    return row && row.foreman_id === auth.user?.person_id
  })
})

const canDeleteSelected = computed(() => {
  return selectedIds.value.every((id) => {
    const row = rows.value.find((r) => String(r.id) === id)
    return row && !row.is_posted
  })
})

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value || 0)
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const [yearValue, monthValue, dayValue] = value.split('-').map(Number)
  if (!yearValue || !monthValue || !dayValue) return value
  return new Date(yearValue, monthValue - 1, dayValue).toLocaleDateString('ru-RU')
}

function formatMonthYear(value: string) {
  if (!value) return '—'
  const [yearValue, monthValue] = value.split('-').map(Number)
  if (!yearValue || !monthValue) return value
  return new Date(yearValue, monthValue - 1, 1).toLocaleDateString('ru-RU', { year: 'numeric', month: 'long' })
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function openItem(id: number) {
  router.push(`/documents/timesheets/${id}`)
}

function handleRowDblClick(row: Record<string, unknown>) {
  router.push(`/documents/timesheets/${(row as unknown as Timesheet).id}`)
}

async function loadOptions() {
  const response = await listReferences('objects', { page_size: 50 })
  objects.value = response.data as ObjectRecord[]
}

async function loadItems() {
  loading.value = true
  error.value = ''
  try {
    const response = await listTimesheets({
      page: page.value,
      page_size: 20,
      search: search.value,
      object_id: objectId.value ?? undefined,
      month_year: monthYear.value || undefined,
      is_posted: postingFilter.value === '' ? undefined : postingFilter.value === 'posted' ? 1 : 0,
      sort_order: 'desc',
    })
    rows.value = response.data
    pagination.value = {
      page: response.pagination?.page ?? 1,
      pages: response.pagination?.pages ?? 1,
      total: response.pagination?.total ?? 0,
    }
    selectedIds.value = []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить табели'
  } finally {
    loading.value = false
  }
}

async function changePostingSelected(mode: 'post' | 'unpost') {
  if (!selectedIds.value.length) return
  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      if (mode === 'post') {
        await postTimesheet(Number(id))
      } else {
        await unpostTimesheet(Number(id))
      }
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось изменить статус для ${failed} из ${selectedIds.value.length + failed} табелей`
  }
}

async function printItem(id?: number) {
  if (!id) return
  printId.value = id
}

const printId = ref<number | null>(null)

async function runPrint(format: 'excel' | 'pdf') {
  if (!printId.value) return
  const id = printId.value
  try {
    const blob = await printTimesheet(id, format)
    downloadBlob(blob, `timesheet_${id}.${format === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сформировать печатную форму'
  }
}

async function copyItem(id?: number) {
  if (!id) return
  try {
    const response = await copyTimesheet(id)
    await router.push(`/documents/timesheets/${response.data.id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось скопировать табель'
  }
}

async function removeSelected() {
  if (!selectedIds.value.length) return
  const label = selectedIds.value.length === 1 ? 'табель' : `${selectedIds.value.length} табелей`
  if (!window.confirm(`Пометить ${label} на удаление?`)) return

  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      await deleteTimesheet(Number(id))
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось удалить ${failed} из ${selectedIds.value.length + failed} табелей`
  }
}

watch(page, loadItems)
watch([objectId, monthYear, postingFilter], () => {
  page.value = 1
  loadItems()
})
watch(search, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    loadItems()
  }, 300)
})

onMounted(async () => {
  await auth.initialize()
  await loadOptions()
  await loadItems()
})
</script>

<style scoped>
.timesheet-filters-row {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.65rem;
}

.timesheet-filter-search {
  min-width: 18rem;
}

.timesheet-filter-control {
  flex: 0 0 auto;
}

.timesheet-filter-object {
  width: min(18rem, 24vw);
}

.timesheet-filter-month {
  width: 10.5rem;
}

.timesheet-filter-status {
  width: 12rem;
}

.timesheet-filter-action {
  flex: 0 0 auto;
}

.pagination-row {
  justify-content: space-between;
  margin-top: 1rem;
}

@media (max-width: 980px) {
  .timesheet-filters-row {
    flex-wrap: wrap;
    align-items: stretch;
  }

  .timesheet-filter-search,
  .timesheet-filter-object,
  .timesheet-filter-month,
  .timesheet-filter-status {
    width: 100%;
    min-width: 0;
  }
}
</style>
