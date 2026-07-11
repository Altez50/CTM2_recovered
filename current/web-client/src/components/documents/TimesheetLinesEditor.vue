<template>
  <section class="panel">
    <div class="panel-body">
      <div class="toolbar timesheet-toolbar">
        <div>
          <h2 class="page-title timesheet-title">Табличная часть</h2>
        </div>
        <button class="button button-secondary" type="button" :disabled="disabled" @click="addLine">
          Добавить сотрудника
        </button>
      </div>

      <div v-if="!lines.length" class="timesheet-empty">
        Добавьте хотя бы одного сотрудника, чтобы заполнить часы за месяц.
      </div>

      <div v-else class="timesheet-shell workspace-lines-shell">
        <div class="timesheet-layout">
          <div class="timesheet-pane timesheet-pane-left">
            <table class="line-table workspace-line-table fixed-table">
              <thead>
                <tr>
                  <th class="number-cell">№</th>
                  <th class="employee-head">Сотрудник</th>
                  <th class="rate-cell">Ставка</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, rowIndex) in lines" :key="`left-${rowIndex}-${line.employee_id}`">
                  <td class="number-cell">{{ rowIndex + 1 }}</td>
                  <td class="employee-cell">
                    <EntityPicker
                      class="timesheet-employee-picker"
                      :model-value="line.employee_id || null"
                      :selected-label="line.employee_name ?? null"
                      title="Выбор сотрудника"
                      description="Найдите и выберите сотрудника из справочника физлиц."
                      placeholder="Сотрудник"
                      search-placeholder="Поиск по ФИО или должности…"
                      empty-text="Сотрудники не найдены"
                      size="full"
                      compact
                      :disabled="disabled"
                      :load-page="loadEmployeePage"
                      @update:model-value="(value) => updateEmployeeId(rowIndex, value)"
                      @change="(item) => handleEmployeeChange(rowIndex, item)"
                    />
                  </td>
                  <td class="rate-cell">
                    <input
                      v-model.number="line.hourly_rate"
                      class="input dense-input timesheet-editable timesheet-rate-input"
                      type="number"
                      min="0"
                      step="0.01"
                      :data-ts-row="rowIndex"
                      data-ts-col="0"
                      :disabled="disabled"
                      @input="recalculateLine(line)"
                      @keydown="handleGridKeydown($event, rowIndex, 0)"
                    />
                  </td>
                </tr>
              </tbody>
              <tfoot>
                <tr>
                  <td colspan="3" class="footer-label">Итого</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div class="timesheet-pane timesheet-pane-center">
            <table class="line-table workspace-line-table days-table">
              <thead>
                <tr>
                  <th v-for="column in dayColumns" :key="column.day" :class="['day-head', { weekend: column.isWeekend }]">
                    {{ column.day }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, rowIndex) in lines" :key="`days-${rowIndex}-${line.employee_id}`">
                  <td
                    v-for="(column, dayIndex) in dayColumns"
                    :key="column.day"
                    :class="['day-cell', { weekend: column.isWeekend }]"
                  >
                    <input
                      v-model.number="line.days[column.day]"
                      class="input dense-input day-input timesheet-editable"
                      type="number"
                      min="0"
                      max="24"
                      step="0.5"
                      :data-ts-row="rowIndex"
                      :data-ts-col="dayIndex + 1"
                      :disabled="disabled"
                      @input="recalculateLine(line)"
                      @keydown="handleGridKeydown($event, rowIndex, dayIndex + 1)"
                    />
                  </td>
                </tr>
              </tbody>
              <tfoot>
                <tr>
                  <td
                    v-for="column in dayColumns"
                    :key="column.day"
                    :class="['footer-day', { weekend: column.isWeekend }]"
                  >
                    {{ formatNumber(dayTotal(column.day)) }}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div class="timesheet-pane timesheet-pane-right">
            <table class="line-table workspace-line-table fixed-table">
              <thead>
                <tr>
                  <th class="summary-hours-cell">Итого</th>
                  <th class="summary-amount-cell">Сумма</th>
                  <th class="action-cell"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, rowIndex) in lines" :key="`right-${rowIndex}-${line.employee_id}`">
                  <td class="summary-cell summary-hours-cell">{{ formatNumber(line.total_hours) }}</td>
                  <td class="summary-cell summary-amount-cell">{{ formatNumber(line.total_amount) }}</td>
                  <td class="action-cell">
                    <button class="button button-danger compact-button" type="button" :disabled="disabled" @click="removeLine(rowIndex)">×</button>
                  </td>
                </tr>
              </tbody>
              <tfoot>
                <tr>
                  <td class="summary-cell summary-hours-cell">{{ formatNumber(totalHours) }}</td>
                  <td class="summary-cell summary-amount-cell">{{ formatNumber(totalAmount) }}</td>
                  <td class="action-cell"></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EntityPicker, { type PickerItem } from '../common/EntityPicker.vue'
import { listReferences } from '../../api/references'
import type { PersonRecord, TimesheetLine } from '../../types/models'

const props = withDefaults(
  defineProps<{
    modelValue: TimesheetLine[]
    monthYear: string
    disabled?: boolean
  }>(),
  {
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: TimesheetLine[]]
}>()

const lines = ref<TimesheetLine[]>([])

const dayColumns = computed(() => {
  const [yearValue, monthValue] = props.monthYear.split('-').map(Number)
  const safeYear = yearValue || new Date().getFullYear()
  const safeMonth = monthValue || new Date().getMonth() + 1
  const daysInMonth = new Date(safeYear, safeMonth, 0).getDate()
  return Array.from({ length: daysInMonth }, (_, index) => {
    const day = index + 1
    const dateValue = new Date(safeYear, safeMonth - 1, day)
    return {
      day,
      isWeekend: dateValue.getDay() === 0 || dateValue.getDay() === 6,
    }
  })
})

const totalHours = computed(() => lines.value.reduce((sum, line) => sum + Number(line.total_hours || 0), 0))
const totalAmount = computed(() => lines.value.reduce((sum, line) => sum + Number(line.total_amount || 0), 0))

function buildDays(source: Record<number, number> | undefined) {
  const normalized: Record<number, number> = {}
  for (const column of dayColumns.value) {
    const value = Number(source?.[column.day] ?? 0)
    normalized[column.day] = Number.isFinite(value) ? value : 0
  }
  return normalized
}

function normalizeLine(line: TimesheetLine, lineNumber: number): TimesheetLine {
  const hourlyRate = Number(line.hourly_rate ?? 0)
  const normalizedDays = buildDays(line.days)
  const totalHoursValue = Number(
    Object.values(normalizedDays).reduce((sum, value) => sum + Number(value || 0), 0).toFixed(2),
  )
  return {
    ...line,
    line_number: lineNumber,
    employee_id: Number(line.employee_id || 0),
    hourly_rate: Number.isFinite(hourlyRate) && hourlyRate >= 0 ? hourlyRate : 0,
    days: normalizedDays,
    total_hours: totalHoursValue,
    total_amount: Number((totalHoursValue * (Number.isFinite(hourlyRate) ? hourlyRate : 0)).toFixed(2)),
  }
}

function syncFromProps() {
  lines.value = (props.modelValue || []).map((line, index) => normalizeLine(line, index + 1))
}

function emitUpdate() {
  emit(
    'update:modelValue',
    lines.value.map((line, index) => normalizeLine(line, index + 1)),
  )
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value || 0)
}

function recalculateLine(line: TimesheetLine) {
  line.hourly_rate = Math.max(0, Number(line.hourly_rate || 0))
  for (const column of dayColumns.value) {
    const rawValue = Number(line.days[column.day] || 0)
    line.days[column.day] = Math.min(24, Math.max(0, Number.isFinite(rawValue) ? rawValue : 0))
  }
  const totalHoursValue = Number(
    Object.values(line.days).reduce((sum, value) => sum + Number(value || 0), 0).toFixed(2),
  )
  line.total_hours = totalHoursValue
  line.total_amount = Number((totalHoursValue * Number(line.hourly_rate || 0)).toFixed(2))
  emitUpdate()
}

async function loadEmployeePage(params: { search: string; page: number; pageSize: number }) {
  const response = await listReferences('persons', {
    page: params.page,
    page_size: Math.min(params.pageSize, 50),
    search: params.search,
    sort_order: 'asc',
  })
  const items = (response.data as PersonRecord[])
    .filter((person) => !person.is_group)
    .map((person) => ({
      id: person.id,
      label: person.full_name,
      caption: [
        person.personnel_number ? `Таб. № ${person.personnel_number}` : null,
        person.position,
        `Ставка ${formatNumber(Number(person.hourly_rate || 0))} руб/час`,
      ].filter(Boolean).join(' · '),
      meta: {
        hourly_rate: Number(person.hourly_rate || 0),
      },
    }))
  return {
    items,
    pages: response.pagination?.pages ?? 1,
  }
}

function updateEmployeeId(rowIndex: number, value: number | null) {
  const line = lines.value[rowIndex]
  if (!line) {
    return
  }
  line.employee_id = value ?? 0
}

function handleEmployeeChange(rowIndex: number, item: PickerItem | null) {
  const line = lines.value[rowIndex]
  if (!line) {
    return
  }
  if (!item) {
    line.employee_id = 0
    line.employee_name = null
    line.hourly_rate = 0
    recalculateLine(line)
    return
  }
  const duplicateIndex = lines.value.findIndex((entry, index) => index !== rowIndex && entry.employee_id === item.id)
  if (duplicateIndex >= 0) {
    window.alert('Этот сотрудник уже добавлен в табель.')
    line.employee_id = 0
    line.employee_name = null
    line.hourly_rate = 0
    recalculateLine(line)
    return
  }
  line.employee_id = item.id
  line.employee_name = item.label
  line.hourly_rate = Math.max(0, Number(item.meta?.hourly_rate || 0))
  recalculateLine(line)
}

function createLine(): TimesheetLine {
  return normalizeLine(
    {
      line_number: lines.value.length + 1,
      employee_id: 0,
      employee_name: null,
      hourly_rate: 0,
      days: {},
      total_hours: 0,
      total_amount: 0,
    },
    lines.value.length + 1,
  )
}

function addLine() {
  lines.value.push(createLine())
  emitUpdate()
}

function removeLine(index: number) {
  lines.value.splice(index, 1)
  lines.value = lines.value.map((line, lineIndex) => normalizeLine(line, lineIndex + 1))
  emitUpdate()
}

function dayTotal(day: number) {
  return lines.value.reduce((sum, line) => sum + Number(line.days[day] || 0), 0)
}

function handleGridKeydown(event: KeyboardEvent, rowIndex: number, columnIndex: number) {
  if (event.key !== 'Enter') {
    return
  }
  event.preventDefault()
  const inputs = Array.from(
    document.querySelectorAll<HTMLInputElement | HTMLSelectElement>('.timesheet-editable'),
  )
  const current = event.target as HTMLInputElement | HTMLSelectElement
  const currentIndex = inputs.indexOf(current)
  if (currentIndex >= 0 && currentIndex + 1 < inputs.length) {
    inputs[currentIndex + 1]?.focus()
  } else {
    const nextRow = rowIndex + 1
    if (nextRow < lines.value.length) {
      const selector = `[data-ts-row="${nextRow}"][data-ts-col="${columnIndex}"]`
      document.querySelector<HTMLInputElement | HTMLSelectElement>(selector)?.focus()
    }
  }
}

watch(
  () => [props.modelValue, props.monthYear],
  () => {
    syncFromProps()
  },
  { immediate: true, deep: true },
)
</script>

<style scoped>
.timesheet-toolbar {
  justify-content: space-between;
}

.timesheet-title {
  font-size: 1.08rem;
}

.timesheet-subtitle {
  margin-top: 0.18rem;
}

.timesheet-shell {
  overflow: auto;
}

.timesheet-layout {
  display: flex;
  align-items: flex-start;
  min-width: 0;
  --timesheet-head-height: 2.1rem;
  --timesheet-row-height: 2.35rem;
  --timesheet-footer-height: 1.95rem;
}

.timesheet-pane {
  min-width: 0;
  display: flex;
  align-items: flex-start;
}

.timesheet-pane-left {
  flex: 0 0 18rem;
  border-right: 1px solid var(--border);
}

.timesheet-pane-center {
  flex: 1 1 auto;
  overflow-x: auto;
}

.timesheet-pane-right {
  flex: 0 0 10.5rem;
  border-left: 1px solid var(--border);
}

.line-table {
  border-collapse: collapse;
  width: 100%;
}

.line-table th,
.line-table td {
  border-bottom: 1px solid var(--border);
  padding: 0.24rem 0.28rem;
  vertical-align: middle;
  white-space: nowrap;
  box-sizing: border-box;
}

.workspace-line-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: rgba(255, 250, 244, 0.96);
}

.line-table thead th {
  height: var(--timesheet-head-height);
}

.line-table tbody tr {
  height: var(--timesheet-row-height);
}

.line-table tbody td {
  height: var(--timesheet-row-height);
}

.line-table tfoot td {
  height: var(--timesheet-footer-height);
}

.fixed-table {
  table-layout: fixed;
}

.days-table {
  width: max-content;
}

.number-cell {
  width: 2.4rem;
  min-width: 2.4rem;
  text-align: center;
}

.employee-head,
.employee-cell {
  width: 10.85rem;
  min-width: 10.85rem;
  max-width: 10.85rem;
}

.rate-cell {
  width: 4.75rem;
  min-width: 4.75rem;
}

.dense-input {
  min-width: 0;
}

.timesheet-editable {
  height: 1.95rem;
  min-height: 1.95rem;
}

.timesheet-rate-input {
  width: 100%;
  text-align: right;
}

.day-head,
.day-cell,
.day-input {
  width: 2.2rem;
  min-width: 2.2rem;
}

.day-input {
  padding-inline: 0.16rem;
  text-align: center;
}

.summary-hours-cell {
  width: 4rem;
  min-width: 4rem;
}

.summary-amount-cell {
  width: 4.8rem;
  min-width: 4.8rem;
}

.action-cell {
  width: 1.7rem;
  min-width: 1.7rem;
  text-align: center;
}

.summary-cell {
  background: rgba(20, 83, 45, 0.06);
  font-weight: 700;
  text-align: right;
}

.weekend {
  background: rgba(185, 28, 28, 0.06);
}

.footer-label,
.footer-day {
  font-weight: 700;
}

.empty-cell {
  color: var(--text-soft);
  padding: 1rem;
  text-align: center;
}

.timesheet-empty {
  color: var(--text-soft);
  padding: 1rem 0.25rem 0.1rem;
  text-align: center;
}

.timesheet-employee-picker {
  width: 100%;
}

.timesheet-employee-picker :deep(.picker-trigger.compact) {
  min-height: 1.95rem;
  height: 1.95rem;
  padding: 0.18rem 0.42rem;
  gap: 0.35rem;
  border-radius: 10px;
}

.timesheet-employee-picker :deep(.picker-text) {
  font-size: 0.78rem;
}

.timesheet-employee-picker :deep(.picker-icon) {
  font-size: 0.68rem;
}

.compact-button {
  min-width: 2rem;
  padding-inline: 0;
}

input[type='number']::-webkit-outer-spin-button,
input[type='number']::-webkit-inner-spin-button {
  margin: 0;
  -webkit-appearance: none;
}

input[type='number'] {
  appearance: textfield;
}

@media (max-width: 1440px) {
  .timesheet-pane-left {
    flex-basis: 16.75rem;
  }

  .employee-head,
  .employee-cell {
    width: 9.9rem;
    min-width: 9.9rem;
    max-width: 9.9rem;
  }

  .day-head,
  .day-cell,
  .day-input {
    width: 2rem;
    min-width: 2rem;
  }
}

@media (max-width: 1024px) {
  .timesheet-layout {
    min-width: 900px;
  }
}
</style>
