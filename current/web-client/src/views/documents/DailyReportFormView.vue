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
          <FormField label="Смета">
            <EntityPicker
              :model-value="form.estimate_id ?? null"
              :selected-label="form.estimate_number ?? null"
              title="Выбор сметы"
              description="Найдите и выберите смету."
              placeholder="Выберите смету"
              search-placeholder="Поиск по номеру…"
              empty-text="Сметы не найдены"
              size="full"
              :disabled="form.is_posted"
              :load-page="loadEstimatePage"
              @update:model-value="(value) => { form.estimate_id = value }"
              @change="handleEstimateChange"
            />
          </FormField>
          <FormField label="Прораб">
            <EntityPicker
              :model-value="form.foreman_id ?? null"
              :selected-label="form.foreman_name ?? null"
              title="Выбор прораба"
              description="Найдите и выберите сотрудника-прораба."
              placeholder="Выберите прораба"
              search-placeholder="Поиск по ФИО…"
              empty-text="Сотрудники не найдены"
              size="full"
              :load-page="loadPersonPage"
              @update:model-value="(value) => { form.foreman_id = value }"
              @change="handleForemanChange"
            />
          </FormField>
          <FormField label="Доп.соглашение">
            <EntityPicker
              :model-value="form.supplementary_agreement_id ?? null"
              :selected-label="form.supplementary_agreement_number ?? null"
              title="Выбор доп.соглашения"
              description="Найдите и выберите доп.соглашение."
              placeholder="Выберите доп.соглашение"
              search-placeholder="Поиск по номеру…"
              empty-text="Доп.соглашения не найдены"
              size="full"
              :load-page="loadContractPage"
              @update:model-value="(value) => { form.supplementary_agreement_id = value }"
              @change="handleSupplementaryAgreementChange"
            />
          </FormField>
        </div>

        <div class="toolbar">
          <button class="button button-secondary" type="button" @click="fillFromEstimate">Заполнить из сметы</button>
          <button class="button button-secondary" type="button" @click="addLine">Добавить строку</button>
          <button v-if="isEdit" :disabled="form.is_posted" class="button button-secondary" type="button" title="Импорт/экспорт строк" @click="dataExchangeOpen = true">⇄ Обмен данными</button>
          <label class="sum-toggle">
            <input v-model="showSumColumns" type="checkbox" />
            Суммовые колонки
          </label>
          <button v-if="isEdit" class="button button-secondary" type="button" @click="printAct('excel')">Акт (Excel)</button>
          <button v-if="isEdit" class="button button-secondary" type="button" @click="printAct('pdf')">Акт (PDF)</button>
          <span class="status-pill" :class="form.is_posted ? 'posted' : 'draft'">
            {{ form.is_posted ? 'Проведен' : 'Черновик' }}
          </span>
        </div>

        <div class="lines-shell workspace-lines-shell">
          <table class="line-table workspace-line-table">
            <thead>
              <tr>
                <th>№</th>
                <th>Группа</th>
                <th>Работа</th>
                <th>План</th>
                <th>Кол-во</th>
                <th>Отклонение</th>
                <th v-if="showSumColumns">Ед.</th>
                <th v-if="showSumColumns">Цена</th>
                <th v-if="showSumColumns">Сумма</th>
                <th>Исполнители</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in form.lines" :key="line.line_number">
                <td>{{ line.line_number }}</td>
                <td><input v-model="line.is_group" type="checkbox" @change="recomputeAll" /></td>
                <td>
                  <input v-if="line.is_group" v-model="line.group_name" class="input dense-input" placeholder="Название группы" />
                  <WorkPicker
                    v-else
                    :model-value="line.work_id ?? null"
                    :selected-label="line.work_name ?? null"
                    :compact="isCompactMode"
                    @update:model-value="(val) => { line.work_id = val }"
                    @change="(work) => handleWorkChange(line, work)"
                  />
                </td>
                <td>
                  <input
                    v-model.number="line.planned_labor"
                    class="input dense-input"
                    type="number"
                    step="0.01"
                    @input="recomputeLine(line)"
                  />
                </td>
                <td>
                  <input
                    v-if="!line.is_group"
                    v-model.number="line.quantity"
                    class="input dense-input"
                    type="number"
                    step="0.001"
                    @input="recomputeLine(line)"
                  />
                </td>
                <td>{{ formatNumber(line.deviation_percent) }}%</td>
                <td v-if="showSumColumns">
                  <input
                    v-if="!line.is_group"
                    v-model="line.unit"
                    class="input dense-input"
                    placeholder="ед."
                  />
                </td>
                <td v-if="showSumColumns">
                  <input
                    v-if="!line.is_group"
                    v-model.number="line.price"
                    class="input dense-input"
                    type="number"
                    step="0.01"
                    @input="recomputeLine(line)"
                  />
                </td>
                <td v-if="showSumColumns">
                  <span v-if="!line.is_group">{{ formatNumber(line.actual_sum) }}</span>
                </td>
                <td>
                  <select v-model="line.executor_ids" class="select dense-input" multiple>
                    <option v-for="person in persons" :key="person.id" :value="person.id">{{ person.full_name }}</option>
                  </select>
                </td>
                <td>
                  <button class="button button-danger compact-button" type="button" @click="removeLine(line.line_number)">×</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>
      </div>
    </section>
    <DocumentDataExchangeDialog v-if="isEdit" :open="dataExchangeOpen" kind="daily-reports" :doc-id="Number(props.id)" title="Дневной отчёт" @close="dataExchangeOpen = false" @imported="loadDocument" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import EntityPicker, { type PickerItem } from '../../components/common/EntityPicker.vue'
import FormField from '../../components/common/FormField.vue'
import WorkPicker from '../../components/common/WorkPicker.vue'
import DocumentDataExchangeDialog from '../../components/documents/DocumentDataExchangeDialog.vue'
import { useDocumentDensity } from '../../composables/useDocumentDensity'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { createDailyReport, getDailyReport, getEstimate, listEstimates, postDailyReport, printDailyReportAct, unpostDailyReport, updateDailyReport } from '../../api/documents'
import { listReferences } from '../../api/references'
import { useAuthStore } from '../../stores/auth'
import type { HeaderAction } from '../../stores/headerBar'
import type { ContractRecord, DailyReport, DailyReportLine, Estimate, PersonRecord } from '../../types/models'

const props = defineProps<{ id?: string; tabId?: string }>()
const router = useRouter()
const auth = useAuthStore()

const persons = ref<PersonRecord[]>([])
const { isCompactMode } = useDocumentDensity()
const saving = ref(false)
const error = ref('')
const showSumColumns = ref(false)
const dataExchangeOpen = ref(false)

const form = ref<DailyReport>({
  number: '',
  date: new Date().toISOString().slice(0, 10),
  estimate_id: null,
  foreman_id: null,
  supplementary_agreement_id: null,
  is_posted: false,
  lines: [],
})

const isEdit = Boolean(props.id)
const canChangePosting = computed(() => auth.isAdmin && isEdit)

const headerTitle = computed(() => (isEdit ? `Отчет ${form.value.number}` : 'Новый ежедневный отчет'))
const headerActions = computed<HeaderAction[]>(() => [
  { key: 'list', icon: '←', title: 'К списку', to: '/documents/daily-reports' },
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

function createLine(): DailyReportLine {
  return {
    line_number: form.value.lines.length + 1,
    work_id: null,
    work_name: null,
    planned_labor: 0,
    actual_labor: 0,
    deviation_percent: 0,
    quantity: 0,
    unit: '',
    price: 0,
    actual_sum: 0,
    executor_ids: [],
    is_group: false,
    group_name: '',
    parent_group_id: null,
    is_collapsed: false,
  }
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value || 0)
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function recomputeLine(line: DailyReportLine) {
  if (line.is_group) {
    line.deviation_percent = 0
    line.actual_sum = 0
    line.actual_labor = 0
    return
  }
  // quantity заменяет actual_labor — синхронизируем для backend/регистра.
  line.actual_labor = Number(line.quantity) || 0
  if (line.planned_labor === 0) {
    line.deviation_percent = line.actual_labor === 0 ? 0 : 100
  } else {
    line.deviation_percent = Number((((line.actual_labor - line.planned_labor) / line.planned_labor) * 100).toFixed(2))
  }
  // Фактическая сумма = факт. количество × цена.
  line.actual_sum = Number(((Number(line.quantity) || 0) * (Number(line.price) || 0)).toFixed(2))
}

function recomputeAll() {
  // Перенумерация на месте: нельзя пересоздавать объекты строк (v-model/@input
  // теряют связь со значениями, и пересчёт суммы отстанет на одно нажатие).
  form.value.lines.forEach((line, index) => {
    line.line_number = index + 1
  })
}

// Реактивный пересчёт отклонения и фактической суммы по любому изменению строки
// (факт. количество, цена, трудоёмкость) — без зависимости от порядка v-model/@input.
watch(
  () => form.value.lines,
  (lines) => {
    lines.forEach(recomputeLine)
  },
  { deep: true },
)

function addLine() {
  form.value.lines.push(createLine())
}

function handleWorkChange(line: DailyReportLine, work: { name: string; unit?: string | null } | null) {
  line.work_name = work?.name ?? null
  // auto-fill unit from the selected work (DailyReportLine has a `unit` field)
  line.unit = work?.unit ?? ''
}

function removeLine(lineNumber: number) {
  form.value.lines = form.value.lines.filter((line) => line.line_number !== lineNumber)
  recomputeAll()
}

async function fillFromEstimate() {
  if (!form.value.estimate_id) {
    error.value = 'Сначала выберите смету'
    return
  }
  try {
    const response = await getEstimate(Number(form.value.estimate_id))
    form.value.lines = response.data.lines.map((line) => ({
      line_number: line.line_number,
      work_id: line.work_id,
      work_name: line.work_name,
      planned_labor: line.planned_labor,
      actual_labor: line.is_group ? 0 : line.quantity,
      deviation_percent: line.is_group ? 0 : -100,
      quantity: line.is_group ? 0 : line.quantity,
      unit: line.is_group ? '' : (line.unit ?? ''),
      price: line.is_group ? 0 : line.price,
      actual_sum: line.is_group ? 0 : line.sum,
      executor_ids: [],
      is_group: line.is_group,
      group_name: line.group_name,
      parent_group_id: line.parent_group_id,
      is_collapsed: line.is_collapsed,
    }))
    recomputeAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось заполнить строки из сметы'
  }
}

async function printAct(format: 'pdf' | 'excel') {
  if (!props.id) return
  try {
    const blob = await printDailyReportAct(Number(props.id), format)
    downloadBlob(blob, `act_report_${props.id}.${format === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сформировать акт'
  }
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

function handleForemanChange(item: PickerItem | null) {
  form.value.foreman_name = item?.label ?? null
  if (!item) form.value.foreman_id = null
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

function handleSupplementaryAgreementChange(item: PickerItem | null) {
  form.value.supplementary_agreement_number = item?.label ?? null
  if (!item) form.value.supplementary_agreement_id = null
}

async function loadEstimatePage(params: { search: string; page: number; pageSize: number }) {
  const response = await listEstimates({
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
    sort_order: 'desc',
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

function handleEstimateChange(item: PickerItem | null) {
  form.value.estimate_number = item?.label ?? null
  if (!item) {
    form.value.estimate_id = null
  }
}

async function loadDocument() {
  if (!props.id) return
  const response = await getDailyReport(Number(props.id))
  form.value = response.data
  recomputeAll()
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const payload: DailyReport = {
      ...form.value,
      lines: form.value.lines.map((line, index) => ({
        ...line,
        line_number: index + 1,
        actual_labor: Number(line.quantity) || 0,
      })),
    }
    if (props.id) {
      await updateDailyReport(Number(props.id), payload)
      await loadDocument()
    } else {
      const response = await createDailyReport(payload)
      await router.replace(`/documents/daily-reports/${response.data.id}`)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось сохранить отчет'
  } finally {
    saving.value = false
  }
}

async function postDocument() {
  if (!props.id) return
  saving.value = true
  error.value = ''
  try {
    await postDailyReport(Number(props.id))
    await loadDocument()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось провести отчет'
  } finally {
    saving.value = false
  }
}

async function unpostDocument() {
  if (!props.id) return
  saving.value = true
  error.value = ''
  try {
    await unpostDailyReport(Number(props.id))
    await loadDocument()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось отменить проведение'
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  // Сначала грузим сам документ — это критично. Справочник физлиц
  // (для селектора исполнителей) грузим отдельно, чтобы его неудача
  // не блокировала отображение данных отчёта.
  try {
    await loadDocument()
    if (!form.value.lines.length) {
      addLine()
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки отчёта'
  }
  try {
    const personsResult = await listReferences('persons', { page_size: 50 })
    persons.value = personsResult.data as PersonRecord[]
  } catch {
    // Не критично: селектор исполнителей будет пуст.
  }
})
</script>

<style scoped>
.doc-header-grid {
  grid-template-columns: minmax(6rem, 7rem) minmax(8rem, 9rem) repeat(auto-fit, minmax(180px, 1fr));
}

.lines-shell {
  overflow: auto;
}

.line-table {
  width: 100%;
  border-collapse: collapse;
}

.line-table th,
.line-table td {
  border-bottom: 1px solid var(--border);
  padding: 0.55rem;
  vertical-align: top;
}

.sum-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.875rem;
  cursor: pointer;
  user-select: none;
}

.dense-input {
  min-width: 0;
}

.compact-button {
  min-width: 44px;
}
</style>
