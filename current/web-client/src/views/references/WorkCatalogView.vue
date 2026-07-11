<template>
  <div class="page-shell work-catalog-page">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar control-strip">
          <input
            v-model="search"
            class="input toolbar-grow"
            type="search"
            placeholder="Поиск по названию или коду работы"
          />
          <select v-if="specificationReviewEnabled" v-model="reviewFilter" class="select review-select">
            <option value="all">Все статусы</option>
            <option value="incorrect">Некорректно</option>
            <option value="corrected">Исправлено</option>
            <option value="ok">ОК</option>
          </select>
          <button class="button button-secondary control-button" type="button" title="Обновить" @click="loadItems">↻</button>
          <button class="button button-primary control-button" type="button" title="Добавить" @click="openCreate">+</button>
          <details v-if="specificationReviewEnabled" ref="commandMenuRef" class="command-menu">
            <summary class="button button-secondary control-button command-menu-trigger">Еще</summary>
            <div class="command-menu-panel">
              <button class="command-menu-item" type="button" @click="exportIncorrectWorks">
                Экспорт некорректных
              </button>
              <button class="command-menu-item" type="button" @click="triggerCorrectionImport">
                Импорт исправлений
              </button>
            </div>
          </details>
        </div>

        <input
          ref="correctionImportRef"
          class="visually-hidden"
          type="file"
          accept=".xls,.xlsx"
          @change="handleCorrectionFile"
        />

        <div v-if="error" class="message-banner message-error">{{ error }}</div>
        <div v-if="successMessage" class="message-banner message-success">{{ successMessage }}</div>

        <SelectionActionBar
          :selected-count="selectedIds.length"
          @deselect-all="selectedIds = []"
        >
          <button
            class="button button-danger compact-action-button"
            type="button"
            title="Удалить"
            @click="removeSelected"
          >
            ✕
          </button>
        </SelectionActionBar>

        <div class="works-table">
          <DataTable
            :columns="displayColumns"
            :rows="rows"
            :loading="loading"
            empty-text="Работы пока не созданы"
            selectable
            :selected-ids="selectedIds"
            @update:selected-ids="selectedIds = $event"
            @row-dblclick="handleRowDblClick"
          >
            <template #cell-kind="{ row }">
              <span class="status-pill" :class="(row as any).is_group ? 'draft' : 'posted'">
                {{ (row as any).is_group ? 'Группа' : 'Работа' }}
              </span>
            </template>

            <template #cell-name="{ row }">
              <div class="name-cell">
                <button
                  class="work-name-button"
                  type="button"
                  :title="`Открыть карточку: ${(row as any).name}`"
                  @click="openEdit(row as any as WorkRecord)"
                >
                  {{ (row as any).name }}
                </button>
                <span v-if="(row as any).code" class="work-code">Код: {{ (row as any).code }}</span>
              </div>
            </template>

            <template #cell-review_status="{ row }">
              <span class="status-pill" :class="reviewPillClass((row as any).specification_review_status)">
                {{ reviewStatusLabel((row as any).specification_review_status) }}
              </span>
            </template>

            <template #cell-unit="{ row }">
              {{ (row as any).is_group ? '—' : (row as any).unit || '—' }}
            </template>

            <template #cell-price="{ row }">
              {{ (row as any).is_group ? '—' : formatMoney((row as any).price) }}
            </template>

            <template #cell-labor_rate="{ row }">
              {{ (row as any).is_group ? '—' : formatNumber((row as any).labor_rate) }}
            </template>
          </DataTable>
        </div>

        <div class="toolbar pagination-row">
          <span class="muted">
            Страница {{ pagination.page }} из {{ pagination.pages }}. Всего записей: {{ pagination.total }}.
          </span>
          <div class="table-actions pagination-actions">
            <button class="button button-secondary compact-page-button" type="button" :disabled="page <= 1" @click="page = 1">
              «
            </button>
            <button
              class="button button-secondary compact-page-button"
              type="button"
              :disabled="page <= 1"
              @click="page -= 1"
            >
              ‹
            </button>
            <span class="page-indicator">{{ pagination.page }} / {{ pagination.pages }}</span>
            <button
              class="button button-secondary compact-page-button"
              type="button"
              :disabled="page >= pagination.pages"
              @click="page += 1"
            >
              ›
            </button>
            <button
              class="button button-secondary compact-page-button"
              type="button"
              :disabled="page >= pagination.pages"
              @click="page = pagination.pages"
            >
              »
            </button>
          </div>
        </div>
      </div>
    </section>

    <WorkForm
      :open="editorOpen"
      :work-id="editorWorkId"
      @close="editorOpen = false"
      @saved="handleSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import SelectionActionBar from '../../components/common/SelectionActionBar.vue'
import WorkForm from '../../components/work/WorkForm.vue'
import { listReferences } from '../../api/references'
import { clearWorkCatalogCache } from '../../api/workCatalog'
import { deleteWork, exportFlaggedSpecifications, importSpecificationCorrections } from '../../api/works'
import { useSpecificationReview } from '../../composables/useSpecificationReview'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import type { WorkRecord } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
useHeaderBar(props.tabId, computed(() => 'Работы'), computed<HeaderAction[]>(() => []))

const rows = ref<WorkRecord[]>([])
const loading = ref(false)
const error = ref('')
const successMessage = ref('')
const search = ref('')
const reviewFilter = ref<'all' | 'ok' | 'incorrect' | 'corrected'>('all')
const page = ref(1)
const editorOpen = ref(false)
const editorWorkId = ref<number | null>(null)
const correctionImportRef = ref<HTMLInputElement | null>(null)
const commandMenuRef = ref<HTMLDetailsElement | null>(null)
const pagination = reactive({ page: 1, pages: 1, total: 0 })
const pageSize = 50
const selectedIds = ref<string[]>([])

const { specificationReviewEnabled } = useSpecificationReview()

const columns = computed(() => {
  const result = [
    { key: 'kind', label: 'Тип' },
    { key: 'name', label: 'Наименование' },
  ]

  if (specificationReviewEnabled.value) {
    result.push({ key: 'review_status', label: 'Проверка' })
  }

  result.push(
    { key: 'unit', label: 'Ед. изм.' },
    { key: 'price', label: 'Цена' },
    { key: 'labor_rate', label: 'Норма труда' },
  )

  return result
})

const displayColumns = computed(() => columns.value.filter((c) => c.key !== 'actions'))

let searchTimer = 0

function formatMoney(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value ?? 0)
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 4,
  }).format(value ?? 0)
}

async function loadItems() {
  loading.value = true
  error.value = ''

  try {
    const response = await listReferences('works', {
      page: page.value,
      page_size: pageSize,
      search: search.value,
      review_status: specificationReviewEnabled.value ? reviewFilter.value : undefined,
    })

    rows.value = (response.data as WorkRecord[]).filter((item) => !item.marked_for_deletion)
    pagination.page = response.pagination?.page ?? 1
    pagination.pages = response.pagination?.pages ?? 1
    pagination.total = response.pagination?.total ?? 0
    selectedIds.value = []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить список работ'
  } finally {
    loading.value = false
  }
}

function reviewStatusLabel(value?: WorkRecord['specification_review_status']) {
  if (value === 'incorrect') {
    return 'Некорректно'
  }
  if (value === 'corrected') {
    return 'Исправлено'
  }
  return 'ОК'
}

function reviewPillClass(value?: WorkRecord['specification_review_status']) {
  if (value === 'incorrect') {
    return 'draft'
  }
  if (value === 'corrected') {
    return 'pending'
  }
  return 'posted'
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function openCreate() {
  closeCommandMenu()
  editorWorkId.value = null
  editorOpen.value = true
}

function openEdit(work: WorkRecord) {
  editorWorkId.value = work.id
  editorOpen.value = true
}

function handleRowDblClick(row: Record<string, unknown>) {
  openEdit(row as unknown as WorkRecord)
}

async function handleSaved() {
  clearWorkCatalogCache()
  successMessage.value = 'Карточка работы сохранена'
  await loadItems()
}

async function exportIncorrectWorks() {
  closeCommandMenu()
  error.value = ''
  successMessage.value = ''
  try {
    const blob = await exportFlaggedSpecifications('incorrect')
    downloadBlob(blob, 'work_specifications_incorrect.xls')
    successMessage.value = 'Файл с некорректными спецификациями сформирован'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось выгрузить некорректные спецификации'
  }
}

function triggerCorrectionImport() {
  closeCommandMenu()
  correctionImportRef.value?.click()
}

function closeCommandMenu() {
  if (commandMenuRef.value) {
    commandMenuRef.value.open = false
  }
}

async function handleCorrectionFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }

  error.value = ''
  successMessage.value = ''
  try {
    const response = await importSpecificationCorrections(file)
    clearWorkCatalogCache()
    await loadItems()
    successMessage.value = `Исправления импортированы: работ ${response.data.updated_work_count}, строк ${response.data.updated_specification_count}`
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось импортировать исправления'
  }
}

async function removeSelected() {
  if (!selectedIds.value.length) return
  const label = selectedIds.value.length === 1 ? 'работу' : `${selectedIds.value.length} работ`
  if (!window.confirm(`Удалить ${label} вместе со строками спецификации?`)) return

  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      await deleteWork(Number(id))
    } catch {
      failed++
    }
  }
  clearWorkCatalogCache()
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось удалить ${failed} из ${selectedIds.value.length + failed} работ`
  }
}

watch(page, loadItems)
watch(reviewFilter, () => {
  page.value = 1
  loadItems()
})
watch(search, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    loadItems()
  }, 250)
})

onMounted(loadItems)
</script>
