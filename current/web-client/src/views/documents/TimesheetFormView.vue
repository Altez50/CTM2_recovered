<template>
  <div :class="['page-shell', 'document-workspace', { 'document-workspace-compact': isCompactMode }]">
    <section class="panel document-panel">
      <div class="panel-body document-body">
        <div class="form-grid workspace-form-grid doc-header-grid">
          <FormField label="Номер">
            <input v-model="form.number" class="input" :disabled="form.is_posted" placeholder="авто" />
          </FormField>
          <FormField label="Дата">
            <input v-model="form.date" class="input" type="date" :disabled="form.is_posted" />
          </FormField>
          <FormField label="Объект">
            <EntityPicker
              :model-value="form.object_id ?? null"
              :selected-label="form.object_name ?? null"
              title="Выбор объекта"
              description="Найдите и выберите объект строительства."
              placeholder="Выберите объект"
              search-placeholder="Поиск по названию или адресу…"
              empty-text="Объекты не найдены"
              size="full"
              :disabled="form.is_posted"
              :load-page="loadObjectPage"
              @update:model-value="(value) => { form.object_id = value }"
              @change="handleObjectChange"
            />
          </FormField>
          <FormField label="Смета">
            <EntityPicker
              :model-value="form.estimate_id ?? null"
              :selected-label="form.estimate_number ?? null"
              title="Выбор сметы"
              description="Найдите и выберите смету. Поиск ограничен выбранным объектом, если он указан."
              placeholder="Выберите смету"
              search-placeholder="Поиск по номеру или объекту…"
              empty-text="Сметы не найдены"
              size="full"
              :disabled="form.is_posted"
              :load-page="loadEstimatePage"
              @update:model-value="(value) => { form.estimate_id = value }"
              @change="handleEstimateChange"
            />
          </FormField>
          <FormField label="Бригадир">
            <EntityPicker
              :model-value="form.foreman_id ?? null"
              :selected-label="form.foreman_name ?? null"
              title="Выбор бригадира"
              description="Найдите и выберите сотрудника, который будет указан как бригадир."
              placeholder="Выберите бригадира"
              search-placeholder="Поиск по ФИО или должности…"
              empty-text="Сотрудники не найдены"
              size="full"
              :disabled="form.is_posted || isForemanUser"
              :load-page="loadPersonPage"
              @update:model-value="(value) => { form.foreman_id = value }"
              @change="handleForemanChange"
            />
          </FormField>
          <FormField label="Период">
            <input v-model="form.month_year" class="input" type="month" :disabled="form.is_posted" />
          </FormField>
        </div>

        <div class="toolbar">
          <span class="status-pill" :class="form.is_posted ? 'posted' : 'draft'">
            {{ form.is_posted ? 'Проведен' : 'Черновик' }}
          </span>
          <span class="document-inline-summary">
            <span class="document-inline-summary-label">Часы</span>
            <strong>{{ formatNumber(form.total_hours) }}</strong>
          </span>
          <span class="document-inline-summary">
            <span class="document-inline-summary-label">Сумма</span>
            <strong>{{ formatNumber(form.total_amount) }}</strong>
          </span>
        </div>

        <div v-if="!form.estimate_id" class="notice notice-warning">
          Смета не выбрана. Это не блокирует сохранение и проведение, но система покажет табель как заполненный без сметы.
        </div>

        <div v-if="message" class="notice notice-info">{{ message }}</div>
        <div v-if="error" class="notice notice-error">{{ error }}</div>

        <div class="toolbar">
          <button class="button button-secondary" type="button" :disabled="form.is_posted" @click="triggerImport">
            Импорт
          </button>
          <button
            class="button button-secondary"
            type="button"
            :disabled="form.is_posted || !form.object_id || autofilling"
            @click="autofill"
          >
            {{ autofilling ? 'Заполнение…' : 'Заполнить по отчетам' }}
          </button>
        </div>

        <input ref="importInput" type="file" hidden accept=".xlsx,.json" @change="handleImport" />
      </div>
    </section>

    <TimesheetLinesEditor v-model="form.lines" :month-year="form.month_year" :disabled="form.is_posted" />

    <Modal
      :open="showImportReviewModal"
      size="full"
      title="Подтверждение импорта табеля"
      description="Проверьте, как строки файла сопоставились с физлицами, при необходимости поменяйте ключи автоподбора или выберите сотрудников вручную."
      @close="closeImportReviewModal"
    >
      <div class="import-review-dialog">
        <div class="import-review-toolbar">
          <div class="import-review-keys">
            <span class="import-review-label">Ключи автосопоставления</span>
            <label class="import-review-key">
              <input
                type="checkbox"
                :checked="importMatchKeys.includes('personnel_number')"
                @change="handleImportMatchKeyToggle('personnel_number', $event)"
              />
              <span>Табельный номер</span>
            </label>
            <label class="import-review-key">
              <input
                type="checkbox"
                :checked="importMatchKeys.includes('full_name')"
                @change="handleImportMatchKeyToggle('full_name', $event)"
              />
              <span>ФИО</span>
            </label>
            <span class="muted">Порядок проверки: сначала табельный номер, затем ФИО.</span>
          </div>

          <div class="import-review-summary">
            <span class="status-pill posted">Совпало: {{ importReviewMatchedCount }}</span>
            <span class="status-pill import-review-pill-create">Создать: {{ importReviewCreateCount }}</span>
            <span class="status-pill" :class="importReviewUnresolvedCount ? 'import-review-pill-alert' : 'draft'">
              Проверить: {{ importReviewUnresolvedCount }}
            </span>
          </div>
        </div>

        <div v-if="loadingImportPersonCatalog" class="notice notice-info">
          Загружаю справочник физлиц для сверки…
        </div>

        <div v-else-if="!importReviewRows.length" class="notice notice-warning">
          В импортируемом файле не найдено строк сотрудников.
        </div>

        <div v-else class="import-review-list">
          <article
            v-for="row in importReviewRows"
            :key="row.review_key"
            class="import-review-item"
            :class="`state-${getImportReviewRowStatus(row)}`"
          >
            <div class="import-review-main">
              <div class="import-review-title-row">
                <strong>{{ row.employee_name }}</strong>
                <span class="muted">Строка {{ row.source_line_number }}</span>
              </div>

              <div class="import-review-meta">
                <span v-if="row.personnel_number">Таб. № {{ row.personnel_number }}</span>
                <span v-if="row.position">Профессия: {{ row.position }}</span>
                <span>
                  Ставка:
                  {{ row.hourly_rate == null ? 'по физлицу' : `${formatNumber(row.hourly_rate)} руб/час` }}
                </span>
                <span>Часы: {{ formatNumber(row.total_hours) }}</span>
              </div>

              <div class="muted import-review-summary-line">
                {{ getImportReviewRowSummary(row) }}
              </div>
            </div>

            <div class="import-review-controls">
              <FormField label="Физлицо">
                <select
                  class="input"
                  :value="row.manual_employee_id ?? ''"
                  :disabled="row.create_new"
                  @change="handleImportReviewPersonChange(row, $event)"
                >
                  <option value="">Использовать автоподбор</option>
                  <option v-for="person in importPersonOptions" :key="person.id" :value="person.id">
                    {{ person.label }}
                  </option>
                </select>
              </FormField>

              <div class="import-review-buttons">
                <button class="button button-secondary" type="button" @click="markImportReviewRowForCreation(row)">
                  Создать физлицо
                </button>
                <button
                  v-if="row.create_new || row.manual_employee_id !== null"
                  class="button button-secondary"
                  type="button"
                  @click="resetImportReviewRow(row)"
                >
                  Сбросить
                </button>
              </div>

              <div v-if="row.create_new" class="notice notice-info import-review-create-note">
                Будет создано новое физлицо
                <span v-if="row.position">с должностью «{{ row.position }}»</span>
                <span v-if="row.personnel_number">и табельным номером {{ row.personnel_number }}</span>.
              </div>
            </div>
          </article>
        </div>

        <div class="toolbar">
          <button class="button button-primary" type="button" :disabled="applyingImportReview || loadingImportPersonCatalog" @click="applyImportReview">
            {{ applyingImportReview ? 'Импорт…' : 'Подтвердить и загрузить' }}
          </button>
          <button class="button button-secondary" type="button" :disabled="applyingImportReview" @click="closeImportReviewModal">
            Отмена
          </button>
        </div>
      </div>
    </Modal>
    <PrintFormatDialog
      :open="printOpen"
      title="Печать табеля"
      @close="printOpen = false"
      @select="runPrint"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import EntityPicker, { type PickerItem } from '../../components/common/EntityPicker.vue'
import FormField from '../../components/common/FormField.vue'
import Modal from '../../components/common/Modal.vue'
import PrintFormatDialog from '../../components/common/PrintFormatDialog.vue'
import TimesheetLinesEditor from '../../components/documents/TimesheetLinesEditor.vue'
import { useDocumentDensity } from '../../composables/useDocumentDensity'
import { useHeaderBar } from '../../composables/useHeaderBar'
import {
  autofillTimesheet,
  copyTimesheet,
  createTimesheet,
  exportTimesheet,
  getTimesheet,
  postTimesheet,
  previewTimesheetImport,
  printTimesheet,
  unpostTimesheet,
  updateTimesheet,
} from '../../api/documents'
import { createReference, listReferences } from '../../api/references'
import { listEstimates } from '../../api/documents'
import { useAuthStore } from '../../stores/auth'
import type { HeaderAction } from '../../stores/headerBar'
import type { Estimate, ObjectRecord, PersonRecord, Timesheet, TimesheetLine, TimesheetImportPreview } from '../../types/models'

type TimesheetImportMatchKey = 'personnel_number' | 'full_name'

type TimesheetImportReviewRow = TimesheetImportPreview['imported_rows'][number] & {
  review_key: string
  manual_employee_id: number | null
  create_new: boolean
  auto_employee_id: number | null
  auto_matched_by: TimesheetImportMatchKey | null
  auto_match_conflict: boolean
}

const props = defineProps<{ id?: string; tabId?: string }>()
const router = useRouter()
const auth = useAuthStore()
const { isCompactMode } = useDocumentDensity()

const saving = ref(false)
const autofilling = ref(false)
const error = ref('')
const message = ref('')
const importInput = ref<HTMLInputElement | null>(null)
const showImportReviewModal = ref(false)
const applyingImportReview = ref(false)
const loadingImportPersonCatalog = ref(false)
const importPreviewForReview = ref<TimesheetImportPreview | null>(null)
const importReviewRows = ref<TimesheetImportReviewRow[]>([])
const importMatchKeys = ref<TimesheetImportMatchKey[]>(['personnel_number', 'full_name'])
const importPersonCatalog = ref<PersonRecord[]>([])

const form = ref<Timesheet>({
  number: '',
  date: new Date().toISOString().slice(0, 10),
  object_id: null,
  estimate_id: null,
  foreman_id: null,
  month_year: new Date().toISOString().slice(0, 7),
  is_posted: false,
  total_hours: 0,
  total_amount: 0,
  lines: [],
})

const isEdit = computed(() => Boolean(props.id))
const isForemanUser = computed(() => auth.user?.role === 'foreman')
const canChangePosting = computed(() => {
  if (auth.user?.role === 'admin') {
    return true
  }
  return auth.user?.role === 'foreman' && auth.user.person_id === form.value.foreman_id
})

const headerTitle = computed(() => (isEdit.value ? `Табель ${form.value.number}` : 'Новый табель'))
const headerActions = computed<HeaderAction[]>(() => [
  { key: 'list', icon: '←', title: 'К списку', to: '/documents/timesheets' },
  { key: 'copy', icon: '⎘', title: 'Копировать', disabled: !isEdit.value || saving.value, onClick: copyDocument },
  { key: 'export', icon: '⤓', title: 'Экспорт', disabled: !isEdit.value, onClick: exportDocument },
  { key: 'print', icon: '⎙', title: 'Печать', disabled: !isEdit.value, onClick: printDocument },
  {
    key: 'save',
    icon: '💾',
    title: saving.value ? 'Сохранение…' : 'Сохранить',
    variant: 'primary',
    disabled: saving.value,
    onClick: save,
  },
  ...(isEdit.value && !form.value.is_posted && canChangePosting.value
    ? [{ key: 'post', icon: '✓', title: 'Провести', variant: 'success' as const, disabled: saving.value, onClick: postDocument }]
    : []),
  ...(isEdit.value && form.value.is_posted && canChangePosting.value
    ? [{ key: 'unpost', icon: '↺', title: 'Отменить проведение', variant: 'warning' as const, disabled: saving.value, onClick: unpostDocument }]
    : []),
])
useHeaderBar(props.tabId, headerTitle, headerActions)

const importPersonOptions = computed(() =>
  [...importPersonCatalog.value]
    .sort((left, right) => left.full_name.localeCompare(right.full_name, 'ru'))
    .map((person) => ({
      id: person.id,
      label: [person.full_name, person.personnel_number ? `таб. ${person.personnel_number}` : null, person.position ?? null]
        .filter(Boolean)
        .join(' · '),
    })),
)

const importReviewMatchedCount = computed(
  () => importReviewRows.value.filter((row) => getImportReviewRowStatus(row) === 'matched').length,
)
const importReviewCreateCount = computed(
  () => importReviewRows.value.filter((row) => getImportReviewRowStatus(row) === 'create').length,
)
const importReviewUnresolvedCount = computed(
  () => importReviewRows.value.filter((row) => getImportReviewRowStatus(row) === 'unresolved').length,
)

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value || 0)
}

function normalizeMatchText(value: string | null | undefined) {
  return (value ?? '').trim().replace(/\s+/g, ' ').toLocaleLowerCase('ru-RU')
}

function normalizePersonnelNumber(value: string | null | undefined) {
  const compact = (value ?? '').replace(/\s+/g, '').trim()
  if (!compact) {
    return ''
  }
  if (/^\d+$/.test(compact)) {
    return compact.replace(/^0+/, '') || '0'
  }
  return compact.toUpperCase()
}

function hasImportMatchKey(key: TimesheetImportMatchKey) {
  return importMatchKeys.value.includes(key)
}

function getPersonFromImportCatalog(personId: number | null | undefined) {
  if (!personId) {
    return null
  }
  return importPersonCatalog.value.find((person) => person.id === personId) ?? null
}

function resolveImportReviewRow(row: TimesheetImportReviewRow) {
  if (row.create_new) {
    return null
  }
  return row.manual_employee_id ?? row.auto_employee_id
}

function getImportReviewRowStatus(row: TimesheetImportReviewRow) {
  if (row.create_new) {
    return 'create'
  }
  return resolveImportReviewRow(row) ? 'matched' : 'unresolved'
}

function getImportReviewRowSummary(row: TimesheetImportReviewRow) {
  if (row.create_new) {
    return 'Будет создано новое физлицо из этой строки импорта.'
  }
  if (row.manual_employee_id) {
    return `Выбрано вручную: ${getPersonFromImportCatalog(row.manual_employee_id)?.full_name ?? 'сотрудник из справочника'}.`
  }
  if (row.auto_employee_id && row.auto_matched_by) {
    const keyLabel = row.auto_matched_by === 'personnel_number' ? 'табельному номеру' : 'ФИО'
    return `Автосопоставление выполнено по ${keyLabel}.`
  }
  if (row.auto_match_conflict) {
    return 'Найдено несколько конфликтующих совпадений. Выберите физлицо вручную или создайте новое.'
  }
  return 'Совпадение не найдено. Выберите физлицо вручную или создайте новое.'
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function normalizeDays(days: Record<number, number> | undefined, monthYear: string) {
  const [yearValue, monthValue] = monthYear.split('-').map(Number)
  const safeYear = yearValue || new Date().getFullYear()
  const safeMonth = monthValue || new Date().getMonth() + 1
  const daysInMonth = new Date(safeYear, safeMonth, 0).getDate()
  const normalized: Record<number, number> = {}
  for (let day = 1; day <= daysInMonth; day += 1) {
    normalized[day] = Number(days?.[day] ?? 0)
  }
  return normalized
}

function normalizeLine(line: TimesheetLine, lineNumber: number, monthYear: string): TimesheetLine {
  const days = normalizeDays(line.days, monthYear)
  const totalHours = Number(Object.values(days).reduce((sum, value) => sum + Number(value || 0), 0).toFixed(2))
  const hourlyRate = Math.max(0, Number(line.hourly_rate || 0))
  return {
    ...line,
    line_number: lineNumber,
    hourly_rate: hourlyRate,
    days,
    total_hours: totalHours,
    total_amount: Number((totalHours * hourlyRate).toFixed(2)),
  }
}

function recomputeTotals() {
  form.value.lines = form.value.lines.map((line, index) => normalizeLine(line, index + 1, form.value.month_year))
  form.value.total_hours = Number(form.value.lines.reduce((sum, line) => sum + Number(line.total_hours || 0), 0).toFixed(2))
  form.value.total_amount = Number(form.value.lines.reduce((sum, line) => sum + Number(line.total_amount || 0), 0).toFixed(2))
}

function refreshTotals() {
  form.value.total_hours = Number(form.value.lines.reduce((sum, line) => sum + Number(line.total_hours || 0), 0).toFixed(2))
  form.value.total_amount = Number(form.value.lines.reduce((sum, line) => sum + Number(line.total_amount || 0), 0).toFixed(2))
}

function buildPayloadLines() {
  return form.value.lines
    .filter((line) => Number(line.employee_id || 0) > 0)
    .map((line, index) => normalizeLine(line, index + 1, form.value.month_year))
}

async function loadObjectPage(params: { search: string; page: number; pageSize: number }) {
  const response = await listReferences('objects', {
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
    sort_order: 'asc',
  })
  return {
    items: (response.data as ObjectRecord[])
      .filter((item) => !item.is_group)
      .map((item) => ({
        id: item.id,
        label: item.name,
        caption: item.address ?? null,
      })),
    pages: response.pagination?.pages ?? 1,
  }
}

async function loadPersonPage(params: { search: string; page: number; pageSize: number }) {
  const response = await listReferences('persons', {
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
    sort_order: 'asc',
  })
  return {
    items: (response.data as PersonRecord[])
      .filter((item) => !item.is_group)
      .map((item) => ({
        id: item.id,
        label: item.full_name,
        caption: [item.personnel_number ? `Таб. № ${item.personnel_number}` : null, item.position ?? null].filter(Boolean).join(' · ') || null,
      })),
    pages: response.pagination?.pages ?? 1,
  }
}

async function loadEstimatePage(params: { search: string; page: number; pageSize: number }) {
  const response = await listEstimates({
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
    sort_order: 'desc',
    object_id: form.value.object_id ?? undefined,
  })
  return {
    items: (response.data as Estimate[]).map((item) => ({
      id: item.id ?? 0,
      label: item.number,
      caption: item.object_name ?? null,
    })),
    pages: response.pagination?.pages ?? 1,
  }
}

function handleObjectChange(item: PickerItem | null) {
  form.value.object_name = item?.label ?? null
  if (!item) {
    form.value.object_id = null
    form.value.estimate_id = null
    form.value.estimate_number = null
  }
}

function handleEstimateChange(item: PickerItem | null) {
  form.value.estimate_number = item?.label ?? null
  if (!item) {
    form.value.estimate_id = null
  }
}

function handleForemanChange(item: PickerItem | null) {
  form.value.foreman_name = item?.label ?? null
  if (!item) {
    form.value.foreman_id = null
  }
}

async function findReferenceIdByName(kind: 'objects' | 'persons', value: string) {
  const normalized = value.trim().toLowerCase()
  let page = 1
  let pages = 1

  while (page <= pages) {
    const response = await listReferences(kind, {
      page,
      page_size: 50,
      search: value,
      sort_order: 'asc',
    })
    const items = response.data as (ObjectRecord | PersonRecord)[]
    const exact = items.find((item) => {
      if ('full_name' in item) {
        return !item.is_group && item.full_name.trim().toLowerCase() === normalized
      }
      return !item.is_group && item.name.trim().toLowerCase() === normalized
    })
    if (exact) {
      return exact.id
    }
    pages = response.pagination?.pages ?? 1
    page += 1
  }

  return null
}

async function findEstimateIdByNumber(value: string, objectId: number | null | undefined) {
  const normalized = value.trim().toLowerCase()
  let page = 1
  let pages = 1

  while (page <= pages) {
    const response = await listEstimates({
      page,
      page_size: 50,
      search: value,
      sort_order: 'desc',
      object_id: objectId ?? undefined,
    })
    const exact = (response.data as Estimate[]).find((item) => item.number.trim().toLowerCase() === normalized)
    if (exact?.id) {
      return exact.id
    }
    pages = response.pagination?.pages ?? 1
    page += 1
  }

  return null
}

async function loadDocument() {
  if (!props.id) {
    if (isForemanUser.value) {
      form.value.foreman_id = auth.user?.person_id ?? null
    }
    return
  }
  const response = await getTimesheet(Number(props.id))
  form.value = response.data
  message.value = response.message ?? ''
  recomputeTotals()
}

function validateForm() {
  if (!form.value.date) {
    return 'Дата обязательна'
  }
  if (!form.value.object_id) {
    return 'Объект обязателен'
  }
  if (!form.value.month_year) {
    return 'Период обязателен'
  }
  return ''
}

async function save() {
  error.value = ''
  message.value = ''
  const validationError = validateForm()
  if (validationError) {
    error.value = validationError
    return
  }

  recomputeTotals()
  saving.value = true
  try {
    const payload = {
      ...form.value,
      lines: buildPayloadLines(),
    }
    if (props.id) {
      const response = await updateTimesheet(Number(props.id), payload)
      form.value = response.data
      message.value = response.message ?? 'Табель обновлен'
    } else {
      const response = await createTimesheet(payload)
      message.value = response.message ?? 'Табель создан'
      form.value = response.data
      await router.replace(`/documents/timesheets/${response.data.id}`)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сохранить табель'
  } finally {
    saving.value = false
  }
}

async function postDocument() {
  if (!props.id) {
    return
  }
  error.value = ''
  saving.value = true
  try {
    const savePayload = {
      ...form.value,
      lines: buildPayloadLines(),
    }
    const saved = await updateTimesheet(Number(props.id), savePayload)
    form.value = saved.data
    await postTimesheet(Number(props.id))
    await loadDocument()
    message.value = 'Табель проведен'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось провести табель'
  } finally {
    saving.value = false
  }
}

async function unpostDocument() {
  if (!props.id) {
    return
  }
  error.value = ''
  try {
    await unpostTimesheet(Number(props.id))
    await loadDocument()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось отменить проведение'
  }
}

async function printDocument() {
  if (!props.id) {
    return
  }
  printOpen.value = true
}

const printOpen = ref(false)

async function runPrint(format: 'excel' | 'pdf') {
  if (!props.id) {
    return
  }
  try {
    const blob = await printTimesheet(Number(props.id), format)
    downloadBlob(blob, `timesheet_${props.id}.${format === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сформировать печатную форму'
  }
}

async function exportDocument() {
  if (!props.id) {
    return
  }
  const selected = window.prompt('Введите формат экспорта: json или excel', 'json')
  const format = selected === 'excel' ? 'excel' : 'json'
  try {
    const blob = await exportTimesheet(Number(props.id), format)
    downloadBlob(blob, `timesheet_${props.id}.${format === 'json' ? 'json' : 'xlsx'}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось экспортировать табель'
  }
}

async function copyDocument() {
  if (!props.id) {
    return
  }
  error.value = ''
  try {
    const response = await copyTimesheet(Number(props.id))
    await router.push(`/documents/timesheets/${response.data.id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось скопировать табель'
  }
}

function triggerImport() {
  importInput.value?.click()
}

async function applyImportDocumentInfo(documentInfo: TimesheetImportPreview['document_info'], importedMonth: string) {
  form.value.month_year = importedMonth
  if (documentInfo.date) {
    form.value.date = documentInfo.date
  }
  if (!form.value.object_id && documentInfo.object_name) {
    form.value.object_id = await findReferenceIdByName('objects', documentInfo.object_name)
    form.value.object_name = documentInfo.object_name
  }
  if (isForemanUser.value) {
    form.value.foreman_id = auth.user?.person_id ?? form.value.foreman_id
  } else if (!form.value.foreman_id && documentInfo.foreman_name) {
    form.value.foreman_id = await findReferenceIdByName('persons', documentInfo.foreman_name)
    form.value.foreman_name = documentInfo.foreman_name
  }
  if (!form.value.estimate_id && documentInfo.estimate_number) {
    form.value.estimate_id = await findEstimateIdByNumber(documentInfo.estimate_number, form.value.object_id)
    form.value.estimate_number = documentInfo.estimate_number
  }
}

function applyImportLines(lines: TimesheetLine[], importedMonth: string) {
  form.value.lines = lines.map((line, index) =>
    normalizeLine(
      line,
      index + 1,
      importedMonth,
    ),
  )
  recomputeTotals()
}

async function applyImportPreview(preview: TimesheetImportPreview) {
  const importedMonth = String(preview.document_info.month_year || form.value.month_year)
  await applyImportDocumentInfo(preview.document_info, importedMonth)
  applyImportLines(preview.lines, importedMonth)
}

async function ensureImportPersonCatalogLoaded(force = false) {
  if (importPersonCatalog.value.length && !force) {
    return
  }

  loadingImportPersonCatalog.value = true
  try {
    const items: PersonRecord[] = []
    let page = 1
    let pages = 1

    while (page <= pages) {
      const response = await listReferences('persons', {
        page,
        page_size: 50,
        sort_order: 'asc',
      })
      items.push(...(response.data as PersonRecord[]).filter((person) => !person.is_group))
      pages = response.pagination?.pages ?? 1
      page += 1
    }

    const seen = new Set<number>()
    importPersonCatalog.value = items.filter((person) => {
      if (seen.has(person.id)) {
        return false
      }
      seen.add(person.id)
      return true
    })
  } finally {
    loadingImportPersonCatalog.value = false
  }
}

function refreshImportReviewMatches() {
  const personnelMap = new Map<string, PersonRecord[]>()
  const nameMap = new Map<string, PersonRecord[]>()

  for (const person of importPersonCatalog.value) {
    const normalizedNumber = normalizePersonnelNumber(person.personnel_number ?? null)
    if (normalizedNumber) {
      const items = personnelMap.get(normalizedNumber) ?? []
      items.push(person)
      personnelMap.set(normalizedNumber, items)
    }

    const normalizedName = normalizeMatchText(person.full_name)
    if (normalizedName) {
      const items = nameMap.get(normalizedName) ?? []
      items.push(person)
      nameMap.set(normalizedName, items)
    }
  }

  importReviewRows.value = importReviewRows.value.map((row) => {
    const personnelMatches =
      hasImportMatchKey('personnel_number') && row.personnel_number
        ? (personnelMap.get(normalizePersonnelNumber(row.personnel_number)) ?? [])
        : []
    const nameMatches =
      hasImportMatchKey('full_name') && row.employee_name
        ? (nameMap.get(normalizeMatchText(row.employee_name)) ?? [])
        : []

    let autoEmployeeId: number | null = null
    let autoMatchedBy: TimesheetImportMatchKey | null = null
    let autoMatchConflict = false

    if (personnelMatches.length > 0) {
      if (personnelMatches.length !== 1) {
        autoMatchConflict = true
      } else if (nameMatches.length > 0 && (nameMatches.length !== 1 || nameMatches[0]?.id !== personnelMatches[0]?.id)) {
        autoMatchConflict = true
      } else {
        autoEmployeeId = personnelMatches[0]?.id ?? null
        autoMatchedBy = 'personnel_number'
      }
    } else if (nameMatches.length > 0) {
      if (nameMatches.length !== 1) {
        autoMatchConflict = true
      } else {
        autoEmployeeId = nameMatches[0]?.id ?? null
        autoMatchedBy = 'full_name'
      }
    }

    return {
      ...row,
      auto_employee_id: autoEmployeeId,
      auto_matched_by: autoMatchedBy,
      auto_match_conflict: autoMatchConflict,
    }
  })
}

async function openImportReviewModal(preview: TimesheetImportPreview) {
  await ensureImportPersonCatalogLoaded()
  importPreviewForReview.value = preview
  importMatchKeys.value = ['personnel_number', 'full_name']
  importReviewRows.value = (preview.imported_rows || []).map((row, index) => ({
    ...row,
    review_key: `${row.source_line_number}-${row.employee_name}-${index}`,
    manual_employee_id: null,
    create_new: false,
    auto_employee_id: row.matched_employee_id ?? null,
    auto_matched_by: row.matched_by ?? null,
    auto_match_conflict: false,
  }))
  refreshImportReviewMatches()
  showImportReviewModal.value = true
}

function closeImportReviewModal() {
  showImportReviewModal.value = false
  applyingImportReview.value = false
  importPreviewForReview.value = null
  importReviewRows.value = []
}

function handleImportMatchKeyToggle(key: TimesheetImportMatchKey, event: Event) {
  const target = event.target as HTMLInputElement | null
  const enabled = Boolean(target?.checked)
  const next = enabled
    ? [...new Set([...importMatchKeys.value, key])]
    : importMatchKeys.value.filter((item) => item !== key)
  importMatchKeys.value = next
  refreshImportReviewMatches()
}

function handleImportReviewPersonChange(row: TimesheetImportReviewRow, event: Event) {
  const target = event.target as HTMLSelectElement | null
  const value = Number(target?.value || 0)
  row.manual_employee_id = value > 0 ? value : null
  row.create_new = false
}

function markImportReviewRowForCreation(row: TimesheetImportReviewRow) {
  row.manual_employee_id = null
  row.create_new = true
}

function resetImportReviewRow(row: TimesheetImportReviewRow) {
  row.manual_employee_id = null
  row.create_new = false
}

async function ensureImportedPersonExistsFromReviewRow(row: TimesheetImportReviewRow) {
  const normalizedName = normalizeMatchText(row.employee_name)
  const normalizedNumber = normalizePersonnelNumber(row.personnel_number ?? null)
  const existingPerson =
    importPersonCatalog.value.find((person) => normalizedNumber && normalizePersonnelNumber(person.personnel_number ?? null) === normalizedNumber)
    ?? importPersonCatalog.value.find((person) => normalizeMatchText(person.full_name) === normalizedName)
  if (existingPerson) {
    return existingPerson
  }

  const response = await createReference('persons', {
    full_name: row.employee_name,
    personnel_number: row.personnel_number ?? null,
    hourly_rate: Number(row.hourly_rate ?? 0),
    position: row.position ?? null,
    phone: null,
    marked_for_deletion: false,
    is_group: false,
  })
  const createdPerson = response.data as PersonRecord
  importPersonCatalog.value = [...importPersonCatalog.value, createdPerson]
  refreshImportReviewMatches()
  return createdPerson
}

async function applyImportReview() {
  if (!importPreviewForReview.value) {
    return
  }
  if (importReviewUnresolvedCount.value > 0) {
    error.value = 'Для продолжения сопоставьте все строки импорта с физлицами или отметьте их на создание.'
    return
  }

  applyingImportReview.value = true
  error.value = ''
  message.value = ''
  try {
    const createdEmployees: PersonRecord[] = []
    const importedMonth = String(importPreviewForReview.value.document_info.month_year || form.value.month_year)
    const preparedLines: TimesheetLine[] = []

    for (const [index, row] of importReviewRows.value.entries()) {
      let person = getPersonFromImportCatalog(resolveImportReviewRow(row))
      if (row.create_new || !person) {
        person = await ensureImportedPersonExistsFromReviewRow(row)
        createdEmployees.push(person)
      }
      const hourlyRate = row.hourly_rate ?? Number(person.hourly_rate || 0)
      preparedLines.push(
        normalizeLine(
          {
            line_number: index + 1,
            employee_id: person.id,
            employee_name: person.full_name,
            hourly_rate: hourlyRate,
            days: row.days,
            total_hours: row.total_hours,
            total_amount: Number((row.total_hours * hourlyRate).toFixed(2)),
          },
          index + 1,
          importedMonth,
        ),
      )
    }

    await applyImportDocumentInfo(importPreviewForReview.value.document_info, importedMonth)
    applyImportLines(preparedLines, importedMonth)
    closeImportReviewModal()
    message.value = createdEmployees.length
      ? `Импорт выполнен. Создано физлиц: ${createdEmployees.length}. Профессии из файла перенесены в должности новых записей.`
      : 'Импортированные строки загружены в открытую форму. При необходимости заполните смету вручную.'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось применить импорт табеля'
  } finally {
    applyingImportReview.value = false
  }
}

async function handleImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  try {
    const response = await previewTimesheetImport(file)
    await openImportReviewModal(response.data)
    message.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось импортировать файл'
  }
}

async function autofill() {
  if (!form.value.object_id) {
    error.value = 'Для автозаполнения выберите объект'
    return
  }
  if (form.value.lines.length && !window.confirm('Текущие строки будут заменены. Продолжить?')) {
    return
  }
  autofilling.value = true
  error.value = ''
  try {
    const response = await autofillTimesheet({
      object_id: Number(form.value.object_id),
      estimate_id: form.value.estimate_id ?? null,
      month_year: form.value.month_year,
    })
    form.value.lines = response.data.map((line, index) =>
      normalizeLine(line, index + 1, form.value.month_year),
    )
    recomputeTotals()
    message.value = response.message ?? 'Строки табеля заполнены по ежедневным отчетам'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось заполнить табель по отчетам'
  } finally {
    autofilling.value = false
  }
}

watch(() => form.value.lines, refreshTotals, { deep: true })

watch(
  () => form.value.object_id,
  (value, oldValue) => {
    if (oldValue !== undefined && oldValue !== null && value !== oldValue) {
      form.value.estimate_id = null
      form.value.estimate_number = null
    }
  },
)

watch(
  () => form.value.month_year,
  () => {
    form.value.lines = form.value.lines.map((line, index) => normalizeLine(line, index + 1, form.value.month_year))
    refreshTotals()
  },
)

watch(
  () => props.id,
  async () => {
    error.value = ''
    message.value = ''
    await loadDocument()
  },
)

onMounted(async () => {
  try {
    await auth.initialize()
    await loadDocument()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки табеля'
  }
})
</script>

<style scoped>
.doc-header-grid {
  grid-template-columns: minmax(6rem, 7rem) minmax(8rem, 9rem) repeat(auto-fit, minmax(180px, 1fr));
}

.document-workspace {
  min-height: 0;
}

.document-panel {
  flex: 0 0 auto;
}

.notice {
  border-radius: 16px;
  margin-top: 1rem;
  padding: 0.85rem 1rem;
}

.document-body {
  gap: 0.85rem;
  flex: 0 0 auto;
  height: auto;
  min-height: auto;
}

.notice-warning {
  background: rgba(245, 158, 11, 0.12);
  color: #92400e;
}

.notice-info {
  background: rgba(14, 116, 144, 0.1);
  color: #155e75;
}

.notice-error {
  background: rgba(185, 28, 28, 0.12);
  color: #991b1b;
}

.import-review-dialog {
  display: grid;
  gap: 1rem;
}

.import-review-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.import-review-keys {
  display: grid;
  gap: 0.45rem;
}

.import-review-label {
  font-size: 0.92rem;
  font-weight: 700;
}

.import-review-key {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.import-review-summary {
  display: flex;
  gap: 0.65rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.import-review-pill-create {
  background: rgba(14, 116, 144, 0.1);
  color: #155e75;
}

.import-review-pill-alert {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.import-review-list {
  display: grid;
  gap: 0.9rem;
  max-height: 100%;
  overflow: auto;
}

.import-review-item {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(20rem, 1fr);
  gap: 1rem;
  align-items: start;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  padding: 1rem;
}

.import-review-item.state-matched {
  border-color: rgba(21, 128, 61, 0.24);
}

.import-review-item.state-create {
  border-color: rgba(14, 116, 144, 0.24);
}

.import-review-item.state-unresolved {
  border-color: rgba(245, 158, 11, 0.34);
}

.import-review-main {
  display: grid;
  gap: 0.65rem;
}

.import-review-title-row {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: baseline;
}

.import-review-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.85rem;
  color: var(--text-soft);
}

.import-review-summary-line {
  min-height: 1.25rem;
}

.import-review-controls {
  display: grid;
  gap: 0.75rem;
}

.import-review-buttons {
  display: flex;
  gap: 0.65rem;
  flex-wrap: wrap;
}

.import-review-create-note {
  margin-top: 0;
}

@media (max-width: 767px) {
  .import-review-toolbar,
  .import-review-item,
  .import-review-title-row {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .import-review-summary {
    justify-content: flex-start;
  }
}
</style>
