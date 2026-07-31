<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру отчета или сметы" />
          <button class="button button-primary" type="button" @click="router.push('/documents/daily-reports/new')">Создать отчет</button>
          <button class="button button-secondary" type="button" title="Обновить" @click="loadItems">↻</button>
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
            v-if="auth.isAdmin && canPostSelected"
            class="button button-secondary"
            type="button"
            title="Провести"
            @click="changePostingSelected('post')"
          >
            ✓
          </button>
          <button
            v-if="auth.isAdmin && canUnpostSelected"
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
            @click="printDocument(Number(selectedIds[0]))"
          >
            Печать
          </button>
          <button
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
          empty-text="Отчетов пока нет"
          selectable
          :selected-ids="selectedIds"
          @update:selected-ids="selectedIds = $event"
          @row-dblclick="handleRowDblClick"
          @row-contextmenu="onContextMenu as any"
        >
          <template #cell-number="{ row }">
            <RouterLink class="document-list-link" :to="`/documents/daily-reports/${(row as unknown as DailyReport).id}`">
              <strong>{{ (row as unknown as DailyReport).number }}</strong>
            </RouterLink>
          </template>
          <template #cell-date="{ row }">
            <RouterLink class="document-list-link" :to="`/documents/daily-reports/${(row as unknown as DailyReport).id}`">
              {{ formatDate((row as unknown as DailyReport).date) }}
            </RouterLink>
          </template>
          <template #cell-is_posted="{ row }">
            <span :class="['status-pill', (row as unknown as DailyReport).is_posted ? 'posted' : 'draft']">
              {{ (row as unknown as DailyReport).is_posted ? 'Проведен' : 'Черновик' }}
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
              Вперед
            </button>
          </div>
        </div>
      </div>
    </section>
    <PrintFormatDialog
      :open="printId !== null"
      title="Печать отчёта"
      @close="printId = null"
      @select="runPrint"
    />
    <ContextMenu :open="menuOpen" :items="menuItems" :x="menuX" :y="menuY" @close="closeMenu" @select="onMenuSelect" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import PrintFormatDialog from '../../components/common/PrintFormatDialog.vue'
import SelectionActionBar from '../../components/common/SelectionActionBar.vue'
import {
  copyDailyReport,
  deleteDailyReport,
  listDailyReports,
  postDailyReport,
  printDailyReport,
  restoreDailyReport,
  unpostDailyReport,
} from '../../api/documents'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import ContextMenu from '../../components/common/ContextMenu.vue'
import { useDocumentContextMenu } from '../../composables/useDocumentContextMenu'
import type { DailyReport } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
const auth = useAuthStore()
const router = useRouter()

const headerActions = computed<HeaderAction[]>(() => [
  { key: 'create', icon: '+', title: 'Создать отчет', variant: 'primary', to: '/documents/daily-reports/new' },
])
useHeaderBar(props.tabId, computed(() => 'Ежедневные отчеты'), headerActions)
const rows = ref<DailyReport[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const page = ref(1)
const pagination = ref({ page: 1, pages: 1, total: 0 })
const selectedIds = ref<string[]>([])
let searchTimer = 0

const columns = [
  { key: 'number', label: 'Номер' },
  { key: 'date', label: 'Дата' },
  { key: 'estimate_number', label: 'Смета' },
  { key: 'foreman_name', label: 'Прораб' },
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

const { menuOpen, menuX, menuY, menuItems, onContextMenu, closeMenu, onMenuSelect } = useDocumentContextMenu<DailyReport>({
  onPost: async (row) => { await postDailyReport(Number(row.id)); await loadItems() },
  onUnpost: async (row) => { await unpostDailyReport(Number(row.id)); await loadItems() },
  onDelete: async (row) => { await deleteDailyReport(Number(row.id)); await loadItems() },
  onRestore: async (row) => { await restoreDailyReport(Number(row.id)); await loadItems() },
})

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const [yearValue, monthValue, dayValue] = value.split('-').map(Number)
  if (!yearValue || !monthValue || !dayValue) return value
  return new Date(yearValue, monthValue - 1, dayValue).toLocaleDateString('ru-RU')
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
  router.push(`/documents/daily-reports/${id}`)
}

function handleRowDblClick(row: Record<string, unknown>) {
  router.push(`/documents/daily-reports/${(row as unknown as DailyReport).id}`)
}

async function loadItems() {
  loading.value = true
  error.value = ''
  try {
    const response = await listDailyReports({
      page: page.value,
      page_size: 20,
      search: search.value,
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
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
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
        await postDailyReport(Number(id))
      } else {
        await unpostDailyReport(Number(id))
      }
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось изменить статус для ${failed} из ${selectedIds.value.length + failed} отчётов`
  }
}

async function printDocument(id?: number) {
  if (!id) return
  printId.value = id
}

const printId = ref<number | null>(null)

async function runPrint(format: 'excel' | 'pdf') {
  if (!printId.value) return
  const id = printId.value
  try {
    const blob = await printDailyReport(id, format)
    downloadBlob(blob, `daily_report_${id}.${format === 'pdf' ? 'pdf' : 'xls'}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сформировать печатную форму'
  }
}

async function copyItem(id?: number) {
  if (!id) return
  try {
    const response = await copyDailyReport(id)
    await router.push(`/documents/daily-reports/${response.data.id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось скопировать отчет'
  }
}

async function removeSelected() {
  if (!selectedIds.value.length) return
  const label = selectedIds.value.length === 1 ? 'отчет' : `${selectedIds.value.length} отчетов`
  if (!window.confirm(`Пометить ${label} на удаление?`)) return

  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      await deleteDailyReport(Number(id))
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось удалить ${failed} из ${selectedIds.value.length + failed} отчетов`
  }
}

watch(page, loadItems)
watch(search, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    loadItems()
  }, 300)
})

onMounted(loadItems)
</script>

<style scoped>
.pagination-row {
  justify-content: space-between;
  margin-top: 1rem;
}
</style>
