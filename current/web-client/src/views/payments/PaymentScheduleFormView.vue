<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>
        <p v-if="saved" class="page-subtitle" style="color: var(--success)">Сохранено</p>

        <div class="form-grid">
          <FormField label="Номер">
            <input v-model="form.number" class="input" type="text" placeholder="Авто" />
          </FormField>
          <FormField label="Период с">
            <input v-model="form.date_from" class="input" type="date" :disabled="isPosted" />
          </FormField>
          <FormField label="Период по">
            <input v-model="form.date_to" class="input" type="date" :disabled="isPosted" />
          </FormField>
          <FormField label="Объект">
            <select v-model="form.object_id" class="select" :disabled="isPosted">
              <option value="">Не выбран</option>
              <option v-for="item in objects" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </FormField>
          <FormField label="Договор">
            <select v-model="form.contract_id" class="select" :disabled="isPosted">
              <option value="">Не выбран</option>
              <option v-for="item in contracts" :key="item.id" :value="item.id">{{ item.number }}</option>
            </select>
          </FormField>
          <FormField label="Ответственный">
            <select v-model="form.responsible_id" class="select" :disabled="isPosted">
              <option value="">Не выбран</option>
              <option v-for="item in persons" :key="item.id" :value="item.id">{{ item.full_name }}</option>
            </select>
          </FormField>
        </div>

        <div class="toolbar">
          <button class="button button-primary" type="button" title="Сохранить" :disabled="loading" @click="save">💾</button>
          <button v-if="auth.isAdmin && !isPosted" class="button button-success" type="button" title="Провести" @click="post">✓</button>
          <button v-if="auth.isAdmin && isPosted" class="button button-warning" type="button" title="Отменить проведение" @click="unpost">↺</button>
          <span class="toolbar-spacer" />
          <button v-if="!isPosted" class="button button-secondary" type="button" @click="suggestIncoming">Подобрать поступления</button>
          <button v-if="!isPosted" class="button button-secondary" type="button" @click="suggestPayroll">Подобрать зарплату</button>
          <button v-if="!isPosted" class="button button-secondary" type="button" @click="suggestGoodsReceipts">Из поступлений ТМЦ</button>
          <button v-if="!isPosted" class="button button-secondary" type="button" @click="suggestGoodsIssues">Из реализаций ТМЦ</button>
          <button v-if="!isPosted" class="button button-secondary" type="button" @click="addLine">+ Строка</button>
        </div>

        <DataTable :columns="lineColumns" :rows="form.lines as Record<string, unknown>[]" :loading="loading" empty-text="Нет плановых строк">
          <template #cell-direction="{ row }">
            <select v-model="(row as unknown as PaymentScheduleLine).direction" class="select select-sm" :disabled="isPosted">
              <option value="incoming">Поступление</option>
              <option value="outgoing">Платеж</option>
            </select>
          </template>
          <template #cell-category="{ row }">
            <select v-model="(row as unknown as PaymentScheduleLine).category" class="select select-sm" :disabled="isPosted">
              <option value="customer_stage">Этап заказчика</option>
              <option value="payroll">Зарплата</option>
              <option value="supplier">Поставщик</option>
              <option value="supplier_invoice">Счёт поставщика (по ТМЦ)</option>
              <option value="customer_invoice">Счёт заказчика (по ТМЦ)</option>
              <option value="tax">Налоги</option>
              <option value="other">Прочее</option>
            </select>
          </template>
          <template #cell-planned_date="{ row }">
            <input v-model="(row as unknown as PaymentScheduleLine).planned_date" class="input input-sm" type="date" :disabled="isPosted" />
          </template>
          <template #cell-counterparty_id="{ row }">
            <select v-model="(row as unknown as PaymentScheduleLine).counterparty_id" class="select select-sm" :disabled="isPosted">
              <option value="">—</option>
              <option v-for="item in counterparties" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </template>
          <template #cell-planned_amount="{ row }">
            <input v-model.number="(row as unknown as PaymentScheduleLine).planned_amount" class="input input-sm" type="number" step="0.01" min="0" :disabled="isPosted" />
          </template>
          <template #cell-description="{ row }">
            <input v-model="(row as unknown as PaymentScheduleLine).description" class="input input-sm" type="text" :disabled="isPosted" />
          </template>
          <template #cell-fact_amount="{ row }">
            {{ formatNumber((row as unknown as PaymentScheduleLine).fact_amount ?? 0) }}
          </template>
          <template #cell-actions="{ row }">
            <button v-if="!isPosted" class="button button-danger button-sm" type="button" @click="removeLineByRow(row as unknown as PaymentScheduleLine)">✕</button>
          </template>
        </DataTable>

        <div class="metric-grid">
          <article class="panel metric-card inner-card">
            <div class="metric-label">Поступления (план)</div>
            <div class="metric-value">{{ formatNumber(totalIncoming) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Платежи (план)</div>
            <div class="metric-value">{{ formatNumber(totalOutgoing) }}</div>
          </article>
          <article class="panel metric-card inner-card">
            <div class="metric-label">Чистый поток</div>
            <div class="metric-value" :style="{ color: netFlow >= 0 ? 'var(--success)' : 'var(--danger)' }">{{ formatNumber(netFlow) }}</div>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import {
  createPaymentSchedule,
  getPaymentSchedule,
  postPaymentSchedule,
  previewIncoming,
  previewPayroll,
  previewGoodsReceiptSuggestions,
  previewGoodsIssueSuggestions,
  unpostPaymentSchedule,
  updatePaymentSchedule,
} from '../../api/payments'
import { listReferences } from '../../api/references'
import { useAuthStore } from '../../stores/auth'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { useBasedOnPrefill } from '../../composables/useBasedOnPrefill'
import type { HeaderAction } from '../../stores/headerBar'
import type { ContractRecord, Counterparty, ObjectRecord, PaymentSchedule, PaymentScheduleLine, PersonRecord } from '../../types/models'

const props = defineProps<{ tabId?: string; id?: string }>()
const auth = useAuthStore()
const router = useRouter()
const { hasBasedOn, loadSource } = useBasedOnPrefill()

const isPosted = ref(false)
const loading = ref(false)
const error = ref('')
const saved = ref(false)

const objects = ref<ObjectRecord[]>([])
const contracts = ref<ContractRecord[]>([])
const counterparties = ref<Counterparty[]>([])
const persons = ref<PersonRecord[]>([])

const form = reactive({
  id: undefined as number | undefined,
  number: '',
  date_from: new Date().toISOString().slice(0, 10),
  date_to: new Date().toISOString().slice(0, 10),
  object_id: '' as number | '',
  contract_id: '' as number | '',
  responsible_id: '' as number | '',
  based_on_type: null as string | null,
  based_on_id: null as number | null,
  based_on_number: '' as string | null,
  lines: [] as PaymentScheduleLine[],
})

const headerActions = computed<HeaderAction[]>(() => [])
useHeaderBar(props.tabId, computed(() => form.id ? `Календарь №${form.number}` : 'Новый календарь'), headerActions)

const lineColumns = [
  { key: 'direction', label: 'Направление' },
  { key: 'category', label: 'Категория' },
  { key: 'planned_date', label: 'Дата план' },
  { key: 'counterparty_id', label: 'Контрагент' },
  { key: 'planned_amount', label: 'Сумма' },
  { key: 'description', label: 'Описание' },
  { key: 'fact_amount', label: 'Факт' },
  { key: 'actions', label: '' },
]

const totalIncoming = computed(() => form.lines.filter(l => l.direction === 'incoming').reduce((s, l) => s + (l.planned_amount || 0), 0))
const totalOutgoing = computed(() => form.lines.filter(l => l.direction === 'outgoing').reduce((s, l) => s + (l.planned_amount || 0), 0))
const netFlow = computed(() => totalIncoming.value - totalOutgoing.value)

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value || 0)
}

function addLine() {
  form.lines.push({
    line_number: form.lines.length + 1,
    direction: 'outgoing',
    category: 'other',
    planned_date: form.date_from,
    planned_amount: 0,
  })
}

function removeLine(index: number) {
  form.lines.splice(index, 1)
  form.lines.forEach((l, i) => { l.line_number = i + 1 })
}

function removeLineByRow(row: PaymentScheduleLine) {
  const index = form.lines.indexOf(row)
  if (index >= 0) {
    removeLine(index)
  }
}

async function loadOptions() {
  const [objRes, ctRes, cpRes, pRes] = await Promise.all([
    listReferences('objects', { page_size: 100 }),
    listReferences('contracts', { page_size: 100 }),
    listReferences('counterparties', { page_size: 100 }),
    listReferences('persons', { page_size: 100 }),
  ])
  objects.value = objRes.data as ObjectRecord[]
  contracts.value = ctRes.data as ContractRecord[]
  counterparties.value = cpRes.data as Counterparty[]
  persons.value = pRes.data as PersonRecord[]
}

async function loadSchedule(id: number) {
  const res = await getPaymentSchedule(id)
  const s = res.data
  form.id = s.id
  form.number = s.number
  form.date_from = s.date_from
  form.date_to = s.date_to
  form.object_id = s.object_id ?? ''
  form.contract_id = s.contract_id ?? ''
  form.responsible_id = s.responsible_id ?? ''
  form.lines = s.lines.map(l => ({ ...l }))
  isPosted.value = s.is_posted
}

function buildPayload() {
  return {
    number: form.number,
    date_from: form.date_from,
    date_to: form.date_to,
    object_id: form.object_id || null,
    contract_id: form.contract_id || null,
    responsible_id: form.responsible_id || null,
    based_on_type: form.based_on_type || null,
    based_on_id: form.based_on_id || null,
    based_on_number: form.based_on_number || null,
    lines: form.lines.map((l, i) => ({
      line_number: i + 1,
      direction: l.direction,
      category: l.category,
      planned_date: l.planned_date,
      counterparty_id: l.counterparty_id || null,
      contract_id: l.contract_id || null,
      estimate_id: l.estimate_id || null,
      object_id: l.object_id || null,
      planned_amount: l.planned_amount,
      description: l.description || null,
      source_kind: l.source_kind || 'manual',
      source_ref: l.source_ref || null,
      is_group: false,
    })),
  }
}

async function save() {
  loading.value = true
  error.value = ''
  saved.value = false
  try {
    const payload = buildPayload()
    let res: { data: PaymentSchedule }
    if (form.id) {
      res = await updatePaymentSchedule(form.id, payload)
    } else {
      res = await createPaymentSchedule(payload)
    }
    form.id = res.data.id
    form.number = res.data.number
    isPosted.value = res.data.is_posted
    saved.value = true
    if (props.id !== String(res.data.id)) {
      router.replace(`/payments/schedules/${res.data.id}`)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка сохранения'
  } finally {
    loading.value = false
  }
}

async function post() {
  if (!form.id) return
  try {
    await postPaymentSchedule(form.id)
    isPosted.value = true
    await loadSchedule(form.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка проведения'
  }
}

async function unpost() {
  if (!form.id) return
  try {
    await unpostPaymentSchedule(form.id)
    isPosted.value = false
    await loadSchedule(form.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка отмены проведения'
  }
}

async function suggestIncoming() {
  try {
    const res = await previewIncoming({
      date_from: form.date_from,
      date_to: form.date_to,
      object_id: form.object_id || null,
      contract_id: form.contract_id || null,
    })
    if (!res.data.length) {
      error.value = 'Нет выполненных работ за выбранный период'
      return
    }
    res.data.forEach(s => {
      form.lines.push({
        line_number: form.lines.length + 1,
        direction: 'incoming',
        category: 'customer_stage',
        planned_date: s.planned_date,
        counterparty_id: s.counterparty_id ?? null,
        contract_id: s.contract_id ?? null,
        estimate_id: s.estimate_id ?? null,
        object_id: s.object_id ?? null,
        planned_amount: s.planned_amount,
        description: s.description ?? null,
        source_kind: 'work_execution',
        source_ref: s.source_ref ?? null,
      })
    })
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка автоподбора'
  }
}

async function suggestPayroll() {
  try {
    const res = await previewPayroll({
      date_from: form.date_from,
      date_to: form.date_to,
      object_id: form.object_id || null,
    })
    if (!res.data.length) {
      error.value = 'Нет начисленной зарплаты за выбранный период'
      return
    }
    res.data.forEach(s => {
      form.lines.push({
        line_number: form.lines.length + 1,
        direction: 'outgoing',
        category: 'payroll',
        planned_date: s.planned_date,
        planned_amount: s.planned_amount,
        description: s.description ?? null,
        source_kind: 'payroll',
        source_ref: s.source_ref ?? null,
      })
    })
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка автоподбора'
  }
}

async function suggestGoodsReceipts() {
  try {
    const res = await previewGoodsReceiptSuggestions({
      date_from: form.date_from,
      date_to: form.date_to,
      object_id: form.object_id || null,
    })
    if (!res.data.length) {
      error.value = 'Нет неоплаченных проведённых поступлений ТМЦ за период'
      return
    }
    res.data.forEach((s) => {
      form.lines.push({
        line_number: form.lines.length + 1,
        direction: 'outgoing',
        category: 'supplier_invoice',
        planned_date: s.planned_date,
        counterparty_id: s.counterparty_id ?? null,
        contract_id: s.contract_id ?? null,
        object_id: s.object_id ?? null,
        planned_amount: s.planned_amount,
        description: s.description ?? null,
        source_kind: 'goods_receipt',
        source_ref: s.source_ref ?? null,
      })
    })
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка автоподбора'
  }
}

async function suggestGoodsIssues() {
  try {
    const res = await previewGoodsIssueSuggestions({
      date_from: form.date_from,
      date_to: form.date_to,
      object_id: form.object_id || null,
    })
    if (!res.data.length) {
      error.value = 'Нет неоплаченных проведённых реализаций ТМЦ за период'
      return
    }
    res.data.forEach((s) => {
      form.lines.push({
        line_number: form.lines.length + 1,
        direction: 'incoming',
        category: 'customer_invoice',
        planned_date: s.planned_date,
        counterparty_id: s.counterparty_id ?? null,
        contract_id: s.contract_id ?? null,
        object_id: s.object_id ?? null,
        planned_amount: s.planned_amount,
        description: s.description ?? null,
        source_kind: 'goods_issue',
        source_ref: s.source_ref ?? null,
      })
    })
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка автоподбора'
  }
}

onMounted(async () => {
  try {
    await loadOptions()
    if (props.id) {
      await loadSchedule(Number(props.id))
    } else if (hasBasedOn) {
      const result = await loadSource()
      if (result) {
        const { source, meta } = result
        if (source.object_id) form.object_id = source.object_id
        if (source.contract_id) form.contract_id = source.contract_id
        if (source.responsible_id) form.responsible_id = source.responsible_id
        form.based_on_type = meta.based_on_type
        form.based_on_id = meta.based_on_id
        form.based_on_number = meta.based_on_number
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  }
})
</script>

<style scoped>
.inner-card {
  background: rgba(255, 255, 255, 0.7);
}
.toolbar-spacer {
  flex: 1;
}
.input-sm, .select-sm {
  width: 100%;
  min-width: 90px;
}
.button-sm {
  padding: 0.15rem 0.5rem;
}
</style>
