<template>
  <div :class="['page-shell', 'document-workspace', { 'document-workspace-compact': isCompactMode }]">
    <section class="panel document-panel">
      <div class="panel-body document-body">
        <div class="form-grid workspace-form-grid doc-header-grid">
          <FormField label="Номер">
            <input v-model="form.number" class="input" placeholder="авто" />
          </FormField>
          <FormField label="Дата">
            <input v-model="form.date" class="input" type="date" />
          </FormField>
          <FormField label="Заказчик">
            <EntityPicker
              :model-value="form.customer_id ?? null"
              :selected-label="form.customer_name ?? null"
              title="Выбор заказчика"
              description="Найдите и выберите контрагента-заказчика."
              placeholder="Выберите заказчика"
              search-placeholder="Поиск по названию…"
              empty-text="Заказчики не найдены"
              size="full"
              edit-kind="counterparties"
              :load-page="loadCounterpartyPage"
              @update:model-value="(value) => { form.customer_id = value }"
              @change="handleCustomerChange"
            />
          </FormField>
          <FormField label="Объект">
            <EntityPicker
              :model-value="form.object_id ?? null"
              :selected-label="form.object_name ?? null"
              title="Выбор объекта"
              description="Найдите и выберите объект строительства."
              placeholder="Выберите объект"
              search-placeholder="Поиск по названию…"
              empty-text="Объекты не найдены"
              size="full"
              edit-kind="objects"
              :load-page="loadObjectPage"
              @update:model-value="(value) => { form.object_id = value }"
              @change="handleObjectChange"
            />
          </FormField>
          <FormField label="Подрядчик">
            <EntityPicker
              :model-value="form.contractor_id ?? null"
              :selected-label="form.contractor_name ?? null"
              title="Выбор подрядчика"
              description="Найдите и выберите организацию-подрядчика."
              placeholder="Выберите подрядчика"
              search-placeholder="Поиск по названию…"
              empty-text="Организации не найдены"
              size="full"
              edit-kind="organizations"
              :load-page="loadOrganizationPage"
              @update:model-value="(value) => { form.contractor_id = value }"
              @change="handleContractorChange"
            />
          </FormField>
          <FormField label="Ответственный">
            <EntityPicker
              :model-value="form.responsible_id ?? null"
              :selected-label="form.responsible_name ?? null"
              title="Выбор ответственного"
              description="Найдите и выберите ответственного сотрудника."
              placeholder="Выберите ответственного"
              search-placeholder="Поиск по ФИО…"
              empty-text="Сотрудники не найдены"
              size="full"
              edit-kind="persons"
              :load-page="loadPersonPage"
              @update:model-value="(value) => { form.responsible_id = value }"
              @change="handleResponsibleChange"
            />
          </FormField>
          <FormField label="Договор">
            <EntityPicker
              :model-value="form.contract_id ?? null"
              :selected-label="form.contract_number ?? null"
              title="Выбор договора"
              description="Найдите и выберите договор."
              placeholder="Выберите договор"
              search-placeholder="Поиск по номеру…"
              empty-text="Договоры не найдены"
              size="full"
              edit-kind="contracts"
              :load-page="loadContractPage"
              @update:model-value="(value) => { form.contract_id = value }"
              @change="handleContractChange"
            />
          </FormField>
        </div>

        <div class="toolbar">
          <button class="button button-secondary" type="button" @click="catalogVisible = !catalogVisible">
            {{ catalogVisible ? 'Скрыть панель' : 'Показать панель' }}
          </button>
          <button class="button button-secondary" type="button" @click="addGroupLine">Добавить группу</button>
          <button class="button button-secondary" type="button" @click="addWorkLine">Добавить пустую работу</button>
          <button v-if="isEdit" class="button button-secondary" type="button" title="Импорт/экспорт строк" @click="dataExchangeOpen = true">⇄ Обмен данными</button>
          <span class="status-pill" :class="form.is_posted ? 'posted' : 'draft'">
            {{ form.is_posted ? 'Проведен' : 'Черновик' }}
          </span>
          <span class="document-inline-summary">
            <span class="document-inline-summary-label">Сумма</span>
            <strong>{{ formatNumber(form.total_sum) }}</strong>
          </span>
          <span class="document-inline-summary">
            <span class="document-inline-summary-label">План</span>
            <strong>{{ formatNumber(form.total_labor) }}</strong>
          </span>
        </div>

        <div
          ref="workspaceRef"
          class="estimate-workspace"
          :class="{ 'estimate-workspace-resizing': resizingCatalog }"
          :style="workspaceLayoutStyle"
        >
          <EstimateWorkCatalog
            v-if="catalogVisible"
            @insert-work="insertWorkFromCatalog"
          />

          <div
            v-if="catalogVisible"
            class="estimate-workspace-divider"
            role="separator"
            aria-orientation="vertical"
            tabindex="0"
            @pointerdown="startCatalogResize"
            @keydown.left.prevent="nudgeCatalogWidth(-2)"
            @keydown.right.prevent="nudgeCatalogWidth(2)"
          >
            <span class="estimate-workspace-divider-grip"></span>
          </div>

          <div class="estimate-workspace-main">
            <div
              ref="linesShellRef"
              :class="[
                'lines-shell',
                'workspace-lines-shell',
                'estimate-lines-shell',
                { 'estimate-lines-shell-column-resizing': Boolean(resizingTableColumn) },
              ]"
              @dragover.prevent
              @drop.prevent="handleWorkDrop($event)"
            >
              <table class="line-table workspace-line-table" :style="estimateTableStyle">
                <colgroup>
                  <col
                    v-for="column in estimateTableColumns"
                    :key="column.key"
                    :style="estimateColumnStyle(column.key)"
                  />
                </colgroup>
                <thead>
                  <tr>
                    <th
                      v-for="column in estimateTableColumns"
                      :key="column.key"
                      :class="[
                        'estimate-header-cell',
                        column.resizable ? 'estimate-header-cell-resizable' : null,
                        column.key === 'actions' ? 'estimate-header-cell-actions' : null,
                      ]"
                    >
                      <span v-if="column.label" class="estimate-header-label">{{ column.label }}</span>
                      <span
                        v-if="column.resizeHandleFor"
                        class="estimate-column-resize-handle"
                        role="separator"
                        aria-orientation="vertical"
                        tabindex="0"
                        :aria-label="`Изменить ширину колонки ${column.label}`"
                        @pointerdown.prevent.stop="startTableColumnResize(column.resizeHandleFor, $event)"
                        @keydown.left.prevent.stop="nudgeTableColumnWidth(column.resizeHandleFor, -1.5)"
                        @keydown.right.prevent.stop="nudgeTableColumnWidth(column.resizeHandleFor, 1.5)"
                      ></span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="line in form.lines" :key="line.line_number">
                    <tr
                      :class="{
                        'estimate-line-group': line.is_group,
                        'estimate-line-selected': selectedLine === line,
                        'estimate-line-drop-target': dragTargetLineNumber === line.line_number,
                      }"
                      @click="selectLine(line)"
                      @dragenter.prevent="setDragTargetLine(line)"
                      @dragover.prevent="setDragTargetLine(line)"
                      @dragleave="clearDragTargetLine(line)"
                      @drop.stop.prevent="handleWorkDrop($event, line)"
                    >
                      <td>{{ line.line_number }}</td>
                      <td>
                        <input v-model="line.is_group" type="checkbox" @change="recomputeLine(line)" />
                      </td>
                      <td>
                        <input v-if="line.is_group" v-model="line.group_name" class="input dense-input" placeholder="Название группы" />
                        <WorkPicker
                          v-else
                          :model-value="line.work_id ?? null"
                          :selected-label="line.work_name ?? null"
                          :compact="isCompactMode"
                          :show-open-button="true"
                          @update:model-value="(val) => { line.work_id = val }"
                          @change="(work) => applyWork(line, work)"
                        />
                      </td>
                      <td>
                        <input v-model.number="line.quantity" class="input dense-input" type="number" step="0.01" @input="recomputeLine(line)" />
                      </td>
                      <td><input v-model="line.unit" class="input dense-input" /></td>
                      <td>
                        <input v-model.number="line.price" class="input dense-input" type="number" step="0.01" @input="recomputeLine(line)" />
                      </td>
                      <td>
                        <input
                          v-model.number="line.labor_rate"
                          class="input dense-input"
                          type="number"
                          step="0.01"
                          @input="recomputeLine(line)"
                        />
                      </td>
                      <td>{{ formatNumber(line.sum) }}</td>
                      <td>{{ formatNumber(line.planned_labor) }}</td>
                      <td>
                        <button class="button button-danger compact-button" type="button" @click.stop="removeLine(line.line_number)">×</button>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="document-summary-bar">
          <article class="document-summary-item">
            <span class="document-summary-label">Итоговая сумма</span>
            <strong class="document-summary-value">{{ formatNumber(form.total_sum) }}</strong>
          </article>
          <article class="document-summary-item">
            <span class="document-summary-label">Плановая трудоемкость</span>
            <strong class="document-summary-value">{{ formatNumber(form.total_labor) }}</strong>
          </article>
        </div>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>
      </div>
    </section>
    <EstimateDataExchangeDialog v-if="isEdit" :open="dataExchangeOpen" :doc-id="Number(props.id)" title="Смета" @close="dataExchangeOpen = false" @imported="loadDocument" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import EntityPicker, { type PickerItem } from '../../components/common/EntityPicker.vue'
import FormField from '../../components/common/FormField.vue'
import WorkPicker from '../../components/common/WorkPicker.vue'
import EstimateWorkCatalog from '../../components/documents/EstimateWorkCatalog.vue'
import EstimateDataExchangeDialog from '../../components/documents/EstimateDataExchangeDialog.vue'
import { useDocumentDensity } from '../../composables/useDocumentDensity'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { createEstimate, getEstimate, postEstimate, unpostEstimate, updateEstimate } from '../../api/documents'
import { listReferences } from '../../api/references'
import { useAuthStore } from '../../stores/auth'
import type { HeaderAction } from '../../stores/headerBar'
import type { WorkRecord } from '../../types/models'
import type {
  ContractRecord,
  Counterparty,
  Estimate,
  EstimateLine,
  ObjectRecord,
  OrganizationRecord,
  PersonRecord,
} from '../../types/models'

const props = defineProps<{ id?: string; tabId?: string }>()
const router = useRouter()
const auth = useAuthStore()
const CATALOG_WIDTH_STORAGE_KEY = 'ctm.estimateCatalogWidthPercent'
const TABLE_COLUMN_WIDTHS_STORAGE_KEY = 'ctm.estimateLineColumnWidths'
const DEFAULT_CATALOG_WIDTH_PERCENT = 28
const MIN_CATALOG_WIDTH_PERCENT = 20
const MAX_CATALOG_WIDTH_PERCENT = 55
const ESTIMATE_FIXED_COLUMNS_WIDTH_REM = 8.25

type EstimateTableColumnKey =
  | 'line_number'
  | 'group'
  | 'work'
  | 'quantity'
  | 'unit'
  | 'price'
  | 'labor'
  | 'sum'
  | 'plan'
  | 'actions'
type EstimateResizableColumnKey = 'group' | 'work' | 'quantity' | 'unit' | 'price' | 'labor' | 'sum' | 'plan'
type EstimateColumnWidths = Record<EstimateResizableColumnKey, number>
type EstimateTableColumnDefinition = {
  key: EstimateTableColumnKey
  label: string
  resizable?: boolean
  resizeHandleFor?: EstimateResizableColumnKey
}

const ESTIMATE_TABLE_COLUMNS: ReadonlyArray<EstimateTableColumnDefinition> = [
  { key: 'line_number', label: '№' },
  { key: 'group', label: 'Группа', resizable: true, resizeHandleFor: 'group' },
  { key: 'work', label: 'Работа', resizable: true, resizeHandleFor: 'work' },
  { key: 'quantity', label: 'Кол-во', resizable: true, resizeHandleFor: 'quantity' },
  { key: 'unit', label: 'Ед.', resizable: true, resizeHandleFor: 'unit' },
  { key: 'price', label: 'Цена', resizable: true, resizeHandleFor: 'price' },
  { key: 'labor', label: 'Трудоемкость', resizable: true, resizeHandleFor: 'labor' },
  { key: 'sum', label: 'Сумма', resizable: true, resizeHandleFor: 'sum' },
  { key: 'plan', label: 'План', resizable: true },
  { key: 'actions', label: '' },
] as const
const ESTIMATE_RESIZABLE_COLUMN_ORDER = ['group', 'work', 'quantity', 'unit', 'price', 'labor', 'sum', 'plan'] as const
const ESTIMATE_DEFAULT_COLUMN_WIDTHS = {
  group: 9,
  work: 31,
  quantity: 10,
  unit: 8,
  price: 11,
  labor: 11,
  sum: 10,
  plan: 10,
} as const
const ESTIMATE_MIN_COLUMN_WIDTHS = {
  group: 6,
  work: 18,
  quantity: 7,
  unit: 6,
  price: 8,
  labor: 8,
  sum: 8,
  plan: 8,
} as const
const estimateTableColumns = ESTIMATE_TABLE_COLUMNS

const { isCompactMode } = useDocumentDensity()
const saving = ref(false)
const error = ref('')
const catalogVisible = ref(true)
const dataExchangeOpen = ref(false)
const workspaceRef = ref<HTMLElement | null>(null)
const linesShellRef = ref<HTMLElement | null>(null)
const linesShellWidth = ref(0)
const catalogWidthPercent = ref(readCatalogWidthPercent())
const estimateColumnWidths = ref<EstimateColumnWidths>(readEstimateColumnWidths())
const resizingCatalog = ref(false)
const resizingTableColumn = ref<EstimateResizableColumnKey | null>(null)
const selectedLine = ref<EstimateLine | null>(null)
const dragTargetLineNumber = ref<number | null>(null)
let stopCatalogResize: null | (() => void) = null
let stopTableColumnResize: null | (() => void) = null
let linesShellResizeObserver: ResizeObserver | null = null

const form = ref<Estimate>({
  number: '',
  date: new Date().toISOString().slice(0, 10),
  customer_id: null,
  object_id: null,
  contractor_id: null,
  responsible_id: null,
  contract_id: null,
  total_sum: 0,
  total_labor: 0,
  is_posted: false,
  lines: [],
})

const isEdit = Boolean(props.id)
const canChangePosting = computed(() => auth.isAdmin && isEdit)

const headerTitle = computed(() => (isEdit ? `Смета ${form.value.number}` : 'Новая смета'))
const headerActions = computed<HeaderAction[]>(() => [
  { key: 'list', icon: '←', title: 'К списку', to: '/documents/estimates' },
  {
    key: 'save',
    icon: '💾',
    title: saving.value ? 'Сохранение…' : 'Сохранить',
    variant: 'primary',
    disabled: saving.value,
    onClick: save,
  },
  ...(canChangePosting.value && !form.value.is_posted
    ? [{ key: 'post', icon: '✓', title: 'Провести', variant: 'success' as const, disabled: saving.value, onClick: postDocument }]
    : []),
  ...(canChangePosting.value && form.value.is_posted
    ? [{ key: 'unpost', icon: '↺', title: 'Отменить проведение', variant: 'warning' as const, disabled: saving.value, onClick: unpostDocument }]
    : []),
])
useHeaderBar(props.tabId, headerTitle, headerActions)

const workspaceLayoutStyle = computed(() => {
  if (!catalogVisible.value) {
    return {
      gridTemplateColumns: 'minmax(0, 1fr)',
    }
  }

  return {
    gridTemplateColumns: `minmax(18rem, ${catalogWidthPercent.value}%) 0.75rem minmax(0, 1fr)`,
  }
})

const estimateFlexibleWidthPx = computed(() => {
  return Math.max(linesShellWidth.value - remToPx(ESTIMATE_FIXED_COLUMNS_WIDTH_REM), 480)
})

const estimateTableStyle = computed(() => ({
  width: `${estimateFlexibleWidthPx.value + remToPx(ESTIMATE_FIXED_COLUMNS_WIDTH_REM)}px`,
  minWidth: `${estimateFlexibleWidthPx.value + remToPx(ESTIMATE_FIXED_COLUMNS_WIDTH_REM)}px`,
}))

function estimateColumnStyle(key: EstimateTableColumnKey) {
  if (key === 'line_number') {
    return { width: `${remToPx(4.5)}px`, minWidth: `${remToPx(4.5)}px` }
  }

  if (key === 'actions') {
    return { width: `${remToPx(3.75)}px`, minWidth: `${remToPx(3.75)}px` }
  }

  const width = estimateColumnWidths.value[key]
  const widthPx = Math.max((estimateFlexibleWidthPx.value * width) / 100, 0)
  return {
    width: `${widthPx}px`,
    minWidth: `${widthPx}px`,
  }
}

function createLine(isGroup = false): EstimateLine {
  return {
    line_number: 0,
    work_id: null,
    work_name: null,
    quantity: 0,
    unit: '',
    price: 0,
    labor_rate: 0,
    sum: 0,
    planned_labor: 0,
    is_group: isGroup,
    group_name: isGroup ? 'Новая группа' : '',
    parent_group_id: null,
    is_collapsed: false,
  }
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value || 0)
}

function applyWork(line: EstimateLine, work: { name: string; unit?: string | null; price: number; labor_rate: number } | null) {
  line.work_name = work?.name ?? null

  if (work && !line.is_group) {
    line.unit = work.unit ?? ''
    line.price = Number(work.price ?? 0)
    line.labor_rate = Number(work.labor_rate ?? 0)
  } else if (!work) {
    line.unit = ''
    line.price = 0
    line.labor_rate = 0
  }

  recomputeLine(line)
}

function recomputeLine(line: EstimateLine) {
  if (line.is_group) {
    line.sum = 0
    line.planned_labor = 0
  } else {
    line.sum = Number((line.quantity * line.price).toFixed(2))
    line.planned_labor = Number((line.quantity * line.labor_rate).toFixed(2))
  }
  recomputeAll()
}

function recomputeAll() {
  form.value.lines.forEach((line, index) => {
    line.line_number = index + 1
  })
  form.value.total_sum = form.value.lines.reduce((acc, line) => acc + (line.is_group ? 0 : line.sum), 0)
  form.value.total_labor = form.value.lines.reduce((acc, line) => acc + (line.is_group ? 0 : line.planned_labor), 0)
  ensureSelectedLine()
}

function addWorkLine() {
  insertLine(createLine(false))
}

function addGroupLine() {
  insertLine(createLine(true))
}

function removeLine(lineNumber: number) {
  const removedIndex = form.value.lines.findIndex((line) => line.line_number === lineNumber)
  if (removedIndex < 0) {
    return
  }

  const removedLine = form.value.lines[removedIndex]
  form.value.lines.splice(removedIndex, 1)

  if (selectedLine.value === removedLine) {
    selectedLine.value = form.value.lines[Math.max(0, removedIndex - 1)] ?? form.value.lines[removedIndex] ?? null
  }

  recomputeAll()
}

async function loadCounterpartyPage(params: { search: string; page: number; pageSize: number }) {
  const response = await listReferences('counterparties', {
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
  })
  return {
    items: (response.data as Counterparty[]).map((item) => ({
      id: item.id,
      label: item.name,
    })),
    pages: response.pagination?.pages ?? 1,
  }
}

function handleCustomerChange(item: PickerItem | null) {
  form.value.customer_name = item?.label ?? null
  if (!item) form.value.customer_id = null
}

async function loadObjectPage(params: { search: string; page: number; pageSize: number }) {
  const response = await listReferences('objects', {
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
  })
  return {
    items: (response.data as ObjectRecord[]).map((item) => ({
      id: item.id,
      label: item.name,
      caption: item.address ?? null,
    })),
    pages: response.pagination?.pages ?? 1,
  }
}

function handleObjectChange(item: PickerItem | null) {
  form.value.object_name = item?.label ?? null
  if (!item) form.value.object_id = null
}

async function loadOrganizationPage(params: { search: string; page: number; pageSize: number }) {
  const response = await listReferences('organizations', {
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
  })
  return {
    items: (response.data as OrganizationRecord[]).map((item) => ({
      id: item.id,
      label: item.name,
    })),
    pages: response.pagination?.pages ?? 1,
  }
}

function handleContractorChange(item: PickerItem | null) {
  form.value.contractor_name = item?.label ?? null
  if (!item) form.value.contractor_id = null
}

async function loadPersonPage(params: { search: string; page: number; pageSize: number }) {
  const response = await listReferences('persons', {
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
  })
  return {
    items: (response.data as PersonRecord[]).map((item) => ({
      id: item.id,
      label: item.full_name,
      caption: item.position ?? null,
    })),
    pages: response.pagination?.pages ?? 1,
  }
}

function handleResponsibleChange(item: PickerItem | null) {
  form.value.responsible_name = item?.label ?? null
  if (!item) form.value.responsible_id = null
}

async function loadContractPage(params: { search: string; page: number; pageSize: number }) {
  const response = await listReferences('contracts', {
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
  })
  return {
    items: (response.data as ContractRecord[]).map((item) => ({
      id: item.id,
      label: item.number,
      caption: item.counterparty_name ?? null,
    })),
    pages: response.pagination?.pages ?? 1,
  }
}

function handleContractChange(item: PickerItem | null) {
  form.value.contract_number = item?.label ?? null
  if (!item) form.value.contract_id = null
}

async function loadDocument() {
  if (!props.id) return
  const response = await getEstimate(Number(props.id))
  form.value = response.data
  recomputeAll()
  ensureSelectedLine('last')
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const payload: Estimate = {
      ...form.value,
      lines: form.value.lines.map((line, index) => ({
        ...line,
        line_number: index + 1,
      })),
    }
    if (props.id) {
      await updateEstimate(Number(props.id), payload)
    } else {
      const response = await createEstimate(payload)
      await router.replace(`/documents/estimates/${response.data.id}`)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сохранить смету'
  } finally {
    saving.value = false
  }
}

async function postDocument() {
  if (!props.id) return
  saving.value = true
  error.value = ''
  try {
    // 1С-поведение: перед проведением записать форму, иначе несохранённые правки теряются
    const payload: Estimate = {
      ...form.value,
      lines: form.value.lines.map((line, index) => ({
        ...line,
        line_number: index + 1,
      })),
    }
    await updateEstimate(Number(props.id), payload)
    await postEstimate(Number(props.id))
    await loadDocument()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось провести смету'
  } finally {
    saving.value = false
  }
}

async function unpostDocument() {
  if (!props.id) return
  saving.value = true
  error.value = ''
  try {
    await unpostEstimate(Number(props.id))
    await loadDocument()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось отменить проведение'
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    syncLinesShellWidth()
    observeLinesShellWidth()
    await loadDocument()
    if (!form.value.lines.length) {
      addWorkLine()
    } else {
      ensureSelectedLine('last')
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  }
})

onBeforeUnmount(() => {
  stopCatalogResize?.()
  stopTableColumnResize?.()
  linesShellResizeObserver?.disconnect()
})

watch(
  () => form.value.lines.length,
  (length) => {
    if (length === 0) {
      selectedLine.value = null
      return
    }

    ensureSelectedLine()
  },
)

watch(catalogWidthPercent, (value) => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(CATALOG_WIDTH_STORAGE_KEY, String(clampCatalogWidthPercent(value)))
  }
})

watch(
  estimateColumnWidths,
  (value) => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(TABLE_COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(value))
    }
  },
  { deep: true },
)

function clampCatalogWidthPercent(value: number) {
  if (!Number.isFinite(value)) {
    return DEFAULT_CATALOG_WIDTH_PERCENT
  }

  return Math.min(Math.max(value, MIN_CATALOG_WIDTH_PERCENT), MAX_CATALOG_WIDTH_PERCENT)
}

function nudgeCatalogWidth(delta: number) {
  if (!catalogVisible.value) {
    return
  }

  catalogWidthPercent.value = clampCatalogWidthPercent(catalogWidthPercent.value + delta)
}

function nudgeTableColumnWidth(columnKey: EstimateResizableColumnKey, delta: number) {
  const index = ESTIMATE_RESIZABLE_COLUMN_ORDER.indexOf(columnKey)
  const nextKey = ESTIMATE_RESIZABLE_COLUMN_ORDER[index + 1]
  if (index < 0 || !nextKey) {
    return
  }

  const pairTotal = estimateColumnWidths.value[columnKey] + estimateColumnWidths.value[nextKey]
  const minCurrent = ESTIMATE_MIN_COLUMN_WIDTHS[columnKey]
  const minNext = ESTIMATE_MIN_COLUMN_WIDTHS[nextKey]
  const nextCurrentWidth = clampNumber(
    estimateColumnWidths.value[columnKey] + delta,
    minCurrent,
    pairTotal - minNext,
  )

  estimateColumnWidths.value = {
    ...estimateColumnWidths.value,
    [columnKey]: nextCurrentWidth,
    [nextKey]: pairTotal - nextCurrentWidth,
  }
}

function ensureSelectedLine(fallback: 'first' | 'last' = 'last') {
  if (!form.value.lines.length) {
    selectedLine.value = null
    return
  }

  if (selectedLine.value && form.value.lines.includes(selectedLine.value)) {
    return
  }

  selectedLine.value = fallback === 'first' ? form.value.lines[0] ?? null : form.value.lines[form.value.lines.length - 1] ?? null
}

function currentInsertIndex(referenceLine: EstimateLine | null = selectedLine.value) {
  if (!form.value.lines.length) {
    return 0
  }

  if (!referenceLine) {
    return form.value.lines.length
  }

  const index = form.value.lines.indexOf(referenceLine)
  return index >= 0 ? index + 1 : form.value.lines.length
}

function selectLine(line: EstimateLine) {
  selectedLine.value = line
}

function insertLine(line: EstimateLine, index = currentInsertIndex()) {
  const safeIndex = Math.min(Math.max(index, 0), form.value.lines.length)
  form.value.lines.splice(safeIndex, 0, line)
  selectedLine.value = line
  recomputeAll()
}

function buildLineFromCatalog(work: WorkRecord): EstimateLine {
  const line = createLine(false)
  line.work_id = work.id
  line.work_name = work.name
  line.unit = work.unit ?? ''
  line.price = Number(work.price ?? 0)
  line.labor_rate = Number(work.labor_rate ?? 0)
  return line
}

function insertWorkFromCatalog(work: WorkRecord) {
  insertLine(buildLineFromCatalog(work))
}

function setDragTargetLine(line: EstimateLine) {
  dragTargetLineNumber.value = line.line_number
}

function clearDragTargetLine(line: EstimateLine) {
  if (dragTargetLineNumber.value === line.line_number) {
    dragTargetLineNumber.value = null
  }
}

function handleWorkDrop(event: DragEvent, referenceLine: EstimateLine | null = selectedLine.value) {
  const payload = event.dataTransfer?.getData('application/x-ctm-work')
  dragTargetLineNumber.value = null

  if (!payload) {
    return
  }

  try {
    insertLine(buildLineFromCatalog(JSON.parse(payload) as WorkRecord), currentInsertIndex(referenceLine))
  } catch {
    error.value = 'Не удалось добавить работу из каталога'
  }
}

function startCatalogResize(event: PointerEvent) {
  if (!catalogVisible.value || !workspaceRef.value) {
    return
  }

  event.preventDefault()
  stopCatalogResize?.()
  resizingCatalog.value = true

  const workspaceRect = workspaceRef.value.getBoundingClientRect()
  const previousCursor = typeof document !== 'undefined' ? document.body.style.cursor : ''
  const previousUserSelect = typeof document !== 'undefined' ? document.body.style.userSelect : ''

  if (typeof document !== 'undefined') {
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const handlePointerMove = (moveEvent: PointerEvent) => {
    const nextPercent = ((moveEvent.clientX - workspaceRect.left) / workspaceRect.width) * 100
    catalogWidthPercent.value = clampCatalogWidthPercent(nextPercent)
  }

  const handlePointerUp = () => {
    if (typeof document !== 'undefined') {
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
    }

    resizingCatalog.value = false
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', handlePointerUp)
    stopCatalogResize = null
  }

  stopCatalogResize = handlePointerUp
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp)
}

function startTableColumnResize(columnKey: EstimateResizableColumnKey, event: PointerEvent) {
  const index = ESTIMATE_RESIZABLE_COLUMN_ORDER.indexOf(columnKey)
  const nextKey = ESTIMATE_RESIZABLE_COLUMN_ORDER[index + 1]
  if (index < 0 || !nextKey || !linesShellRef.value) {
    return
  }

  event.preventDefault()
  stopTableColumnResize?.()
  resizingTableColumn.value = columnKey

  const shellRect = linesShellRef.value.getBoundingClientRect()
  const flexibleWidth = shellRect.width - remToPx(ESTIMATE_FIXED_COLUMNS_WIDTH_REM)
  if (flexibleWidth <= 0) {
    resizingTableColumn.value = null
    return
  }

  const startX = event.clientX
  const startCurrentWidth = estimateColumnWidths.value[columnKey]
  const startNextWidth = estimateColumnWidths.value[nextKey]
  const pairTotal = startCurrentWidth + startNextWidth
  const previousCursor = typeof document !== 'undefined' ? document.body.style.cursor : ''
  const previousUserSelect = typeof document !== 'undefined' ? document.body.style.userSelect : ''

  if (typeof document !== 'undefined') {
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const handlePointerMove = (moveEvent: PointerEvent) => {
    const deltaPercent = ((moveEvent.clientX - startX) / flexibleWidth) * 100
    const nextCurrentWidth = clampNumber(
      startCurrentWidth + deltaPercent,
      ESTIMATE_MIN_COLUMN_WIDTHS[columnKey],
      pairTotal - ESTIMATE_MIN_COLUMN_WIDTHS[nextKey],
    )

    estimateColumnWidths.value = {
      ...estimateColumnWidths.value,
      [columnKey]: nextCurrentWidth,
      [nextKey]: pairTotal - nextCurrentWidth,
    }
  }

  const handlePointerUp = () => {
    if (typeof document !== 'undefined') {
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
    }

    resizingTableColumn.value = null
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', handlePointerUp)
    stopTableColumnResize = null
  }

  stopTableColumnResize = handlePointerUp
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp)
}

function readCatalogWidthPercent() {
  if (typeof window === 'undefined') {
    return DEFAULT_CATALOG_WIDTH_PERCENT
  }

  return clampCatalogWidthPercent(Number(window.localStorage.getItem(CATALOG_WIDTH_STORAGE_KEY)))
}

function readEstimateColumnWidths(): EstimateColumnWidths {
  if (typeof window === 'undefined') {
    return cloneEstimateColumnWidths(ESTIMATE_DEFAULT_COLUMN_WIDTHS)
  }

  try {
    const parsed = JSON.parse(window.localStorage.getItem(TABLE_COLUMN_WIDTHS_STORAGE_KEY) ?? 'null') as Partial<
      Record<EstimateResizableColumnKey, unknown>
    > | null

    if (!parsed || !isEstimateColumnWidths(parsed)) {
      return cloneEstimateColumnWidths(ESTIMATE_DEFAULT_COLUMN_WIDTHS)
    }

    return cloneEstimateColumnWidths({
      group: Number(parsed.group),
      work: Number(parsed.work),
      quantity: Number(parsed.quantity),
      unit: Number(parsed.unit),
      price: Number(parsed.price),
      labor: Number(parsed.labor),
      sum: Number(parsed.sum),
      plan: Number(parsed.plan),
    })
  } catch {
    return cloneEstimateColumnWidths(ESTIMATE_DEFAULT_COLUMN_WIDTHS)
  }
}

function isEstimateColumnWidths(value: Partial<Record<EstimateResizableColumnKey, unknown>>) {
  let total = 0

  for (const key of ESTIMATE_RESIZABLE_COLUMN_ORDER) {
    const width = Number(value[key])
    if (!Number.isFinite(width) || width < ESTIMATE_MIN_COLUMN_WIDTHS[key]) {
      return false
    }
    total += width
  }

  return Math.abs(total - 100) < 0.5
}

function cloneEstimateColumnWidths(
  source: Readonly<Record<EstimateResizableColumnKey, number>>,
): EstimateColumnWidths {
  return {
    group: source.group,
    work: source.work,
    quantity: source.quantity,
    unit: source.unit,
    price: source.price,
    labor: source.labor,
    sum: source.sum,
    plan: source.plan,
  }
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function remToPx(value: number) {
  if (typeof window === 'undefined') {
    return value * 16
  }

  const fontSize = Number.parseFloat(window.getComputedStyle(document.documentElement).fontSize || '16')
  return value * (Number.isFinite(fontSize) ? fontSize : 16)
}

function syncLinesShellWidth() {
  linesShellWidth.value = linesShellRef.value?.clientWidth ?? 0
}

function observeLinesShellWidth() {
  if (typeof ResizeObserver === 'undefined' || !linesShellRef.value) {
    syncLinesShellWidth()
    return
  }

  linesShellResizeObserver?.disconnect()
  linesShellResizeObserver = new ResizeObserver(() => {
    syncLinesShellWidth()
  })
  linesShellResizeObserver.observe(linesShellRef.value)
}
</script>

<style scoped>
.doc-header-grid {
  grid-template-columns: minmax(6rem, 7rem) minmax(8rem, 9rem) repeat(auto-fit, minmax(180px, 1fr));
}

.estimate-workspace {
  display: grid;
  flex: 1 1 auto;
  align-items: stretch;
  height: clamp(28rem, calc(100vh - 19rem), 52rem);
  min-height: 0;
  overflow: hidden;
}

.estimate-workspace-resizing {
  user-select: none;
}

.estimate-workspace-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: col-resize;
  border-radius: 999px;
  background: linear-gradient(
    180deg,
    rgba(178, 76, 45, 0.06),
    rgba(47, 36, 28, 0.12),
    rgba(178, 76, 45, 0.06)
  );
  transition: background-color 140ms ease, box-shadow 140ms ease;
}

.estimate-workspace-divider:hover,
.estimate-workspace-divider:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(178, 76, 45, 0.12);
  background: linear-gradient(
    180deg,
    rgba(178, 76, 45, 0.16),
    rgba(47, 36, 28, 0.18),
    rgba(178, 76, 45, 0.16)
  );
}

.estimate-workspace-divider-grip {
  width: 0.3rem;
  height: 4.6rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 0 0 1px rgba(78, 52, 36, 0.1);
}

.estimate-workspace-main {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.estimate-lines-shell {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.estimate-line-group {
  background: rgba(245, 241, 230, 0.56);
}

.estimate-line-selected td {
  background: rgba(178, 76, 45, 0.12);
}

.estimate-line-selected td:first-child {
  box-shadow: inset 3px 0 0 var(--accent);
}

.estimate-line-drop-target td {
  background: rgba(178, 76, 45, 0.16);
}

.lines-shell {
  overflow: auto;
}

.line-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.line-table th,
.line-table td {
  border-bottom: 1px solid var(--border);
  padding: 0.55rem;
  vertical-align: top;
}

.line-table tbody tr {
  cursor: pointer;
  transition: background-color 120ms ease, box-shadow 120ms ease;
}

.line-table tbody tr:hover td {
  background: rgba(178, 76, 45, 0.06);
}

.estimate-header-cell {
  position: relative;
  user-select: none;
}

.estimate-header-cell-actions {
  width: 3.75rem;
}

.estimate-header-cell-resizable {
  padding-right: 0.85rem;
}

.estimate-header-label {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.estimate-column-resize-handle {
  position: absolute;
  top: 0.18rem;
  right: -0.35rem;
  width: 0.85rem;
  height: calc(100% - 0.36rem);
  border-radius: 999px;
  cursor: col-resize;
  touch-action: none;
  background: linear-gradient(
    180deg,
    rgba(178, 76, 45, 0),
    rgba(178, 76, 45, 0.18) 20%,
    rgba(178, 76, 45, 0.22) 80%,
    rgba(178, 76, 45, 0)
  );
  opacity: 0.28;
  transition: opacity 120ms ease, background-color 120ms ease, box-shadow 120ms ease;
  z-index: 2;
}

.estimate-column-resize-handle:hover,
.estimate-column-resize-handle:focus-visible {
  opacity: 1;
  outline: none;
  box-shadow: 0 0 0 2px rgba(178, 76, 45, 0.14);
}

.estimate-lines-shell-column-resizing .estimate-column-resize-handle,
.estimate-column-resize-handle:focus-visible {
  opacity: 1;
}

.dense-input {
  min-width: 0;
}

.compact-button {
  min-width: 44px;
}

@media (max-width: 1100px) {
  .estimate-workspace {
    height: auto;
    grid-template-columns: minmax(0, 1fr) !important;
    overflow: visible;
  }

  .estimate-workspace-divider {
    display: none;
  }
}

</style>
