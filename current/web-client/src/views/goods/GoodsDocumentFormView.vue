<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <p v-if="error" class="message-banner message-error">{{ error }}</p>
        <p v-if="info" class="message-banner message-success">{{ info }}</p>

        <div class="form-grid">
          <FormField label="Номер">
            <input v-model="form.number" class="input" type="text" :disabled="isPosted" placeholder="авто при сохранении" />
          </FormField>
          <FormField label="Дата">
            <input v-model="form.date" class="input" type="date" :disabled="isPosted" />
          </FormField>
          <FormField label="Организация">
            <EntityPicker
              v-model="form.organization_id"
              :selected-label="orgLabel"
              :disabled="isPosted"
              compact
              title="Выбор организации"
              search-placeholder="Поиск организации…"
              :load-page="loadOrgs"
            />
          </FormField>
          <FormField :label="isReceipt ? 'Контрагент (поставщик)' : 'Контрагент (покупатель)'">
            <EntityPicker
              v-model="form.counterparty_id"
              :selected-label="cpLabel"
              :disabled="isPosted"
              compact
              title="Выбор контрагента"
              search-placeholder="Поиск контрагента…"
              :load-page="loadCounterparties"
            />
          </FormField>
          <FormField label="Договор">
            <EntityPicker
              v-model="form.contract_id"
              :selected-label="contractLabel"
              :disabled="isPosted"
              compact
              title="Выбор договора"
              search-placeholder="Поиск договора…"
              :load-page="loadContracts"
            />
          </FormField>
          <FormField label="Объект">
            <EntityPicker
              v-model="form.object_id"
              :selected-label="objectLabel"
              :disabled="isPosted"
              compact
              title="Выбор объекта"
              search-placeholder="Поиск объекта…"
              :load-page="loadObjects"
            />
          </FormField>
          <FormField label="Описание" class="field-span-2">
            <input v-model="form.description" class="input" type="text" :disabled="isPosted" />
          </FormField>
        </div>

        <div class="toolbar document-toolbar">
          <button class="button button-primary" type="button" title="Сохранить" :disabled="loading" @click="save">💾</button>
          <button v-if="!isPosted" class="button button-success" type="button" title="Провести" :disabled="!form.id" @click="post">✓</button>
          <button v-else class="button button-warning" type="button" title="Отменить проведение" @click="unpost">↺</button>
          <span class="status-pill" :class="isPosted ? 'posted' : 'draft'">{{ isPosted ? 'Проведён' : 'Черновик' }}</span>
          <div class="toolbar-grow"></div>
          <button class="button button-secondary" type="button" @click="openMovements">Движения по регистрам</button>
          <button class="button button-secondary" type="button" :disabled="isPosted" @click="triggerImport">Загрузить из Excel…</button>
          <button class="button button-secondary" type="button" :disabled="isPosted || loading || !linesWithoutMaterial.length" title="Создать карточки материалов по наименованиям строк без материала" @click="createMissingMaterials">Создать материалы</button>
          <button class="button button-secondary" type="button" :disabled="!form.id" @click="doExport">Выгрузить в Excel</button>
          <input ref="fileInput" type="file" accept=".xlsx,.xls" hidden @change="handleImportFile" />
        </div>

        <GoodsLinesEditor :lines="form.lines" :disabled="isPosted" :totals="totals" @update:lines="onLinesUpdate" />
      </div>
    </section>

    <DocumentMovementsModal
      :open="movementsOpen"
      :kind="kind"
      :document-id="form.id ?? null"
      @close="movementsOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import EntityPicker from '../../components/common/EntityPicker.vue'
import FormField from '../../components/common/FormField.vue'
import GoodsLinesEditor from '../../components/documents/GoodsLinesEditor.vue'
import DocumentMovementsModal from '../../components/documents/DocumentMovementsModal.vue'
import {
  createGoodsDocument,
  deleteGoodsDocument,
  exportGoodsLines,
  getGoodsDocument,
  postGoodsDocument,
  previewGoodsLinesImport,
  unpostGoodsDocument,
  updateGoodsDocument,
} from '../../api/goods'
import { listReferences, createReference } from '../../api/references'
import { useAuthStore } from '../../stores/auth'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { useBasedOnPrefill } from '../../composables/useBasedOnPrefill'
import type { HeaderAction } from '../../stores/headerBar'
import type { ContractRecord, Counterparty, GoodsDocumentPayload, GoodsKind, GoodsLine, GoodsLineInput, MaterialRecord, ObjectRecord, OrganizationRecord } from '../../types/models'

const props = withDefaults(defineProps<{ tabId?: string; id?: string; kind?: GoodsKind }>(), { kind: 'receipt' })
const auth = useAuthStore()
const router = useRouter()
const { hasBasedOn, loadSource } = useBasedOnPrefill()

const isReceipt = computed(() => props.kind === 'receipt')
const basePath = computed(() => (isReceipt.value ? '/goods/receipts' : '/goods/issues'))
const docTitle = computed(() => (isReceipt.value ? 'Поступление ТМЦ' : 'Списание ТМЦ'))

const isPosted = ref(false)
const loading = ref(false)
const error = ref('')
const info = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const movementsOpen = ref(false)

const form = reactive({
  id: undefined as number | undefined,
  number: '',
  date: new Date().toISOString().slice(0, 10),
  organization_id: null as number | null,
  counterparty_id: null as number | null,
  contract_id: null as number | null,
  object_id: null as number | null,
  responsible_id: null as number | null,
  description: '',
  auto_schedule: true,
  based_on_type: null as string | null,
  based_on_id: null as number | null,
  based_on_number: null as string | null,
  lines: [] as GoodsLine[],
})

const headerActions = computed<HeaderAction[]>(() => [
  { key: 'save', icon: '✓', title: 'Сохранить', variant: 'primary', action: save },
  { key: 'movements', icon: '⇄', title: 'Движения по регистрам', variant: 'neutral', action: openMovements },
  { key: 'refresh', icon: '↻', title: 'Обновить', variant: 'neutral', action: reload },
])
useHeaderBar(props.tabId, computed(() => (form.id ? `${docTitle.value} №${form.number}` : `Новый: ${docTitle.value}`)), headerActions)

const totals = computed(() => {
  const sumWithoutVat = form.lines.reduce((s, l) => s + (Number(l.sum_without_vat) || 0), 0)
  const vat = form.lines.reduce((s, l) => s + (Number(l.vat_amount) || 0), 0)
  return {
    sum_without_vat: Math.round(sumWithoutVat * 100) / 100,
    vat_amount: Math.round(vat * 100) / 100,
    sum_with_vat: Math.round((sumWithoutVat + vat) * 100) / 100,
  }
})

const linesWithoutMaterial = computed(() =>
  form.lines.filter((l) => !l.material_id && (l.name || '').trim()),
)

// Denormalized labels for the pickers (set when loading an existing document).
const orgLabel = ref('')
const cpLabel = ref('')
const contractLabel = ref('')
const objectLabel = ref('')

function formatMoney(value: number) {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0)
}

function onLinesUpdate(lines: GoodsLine[]) {
  form.lines = lines
}

// --- picker loaders ---
async function loadOrgs(p: { search: string; page: number; pageSize: number }) {
  const res = await listReferences('organizations', { search: p.search, page: p.page, page_size: p.pageSize })
  return { items: (res.data as OrganizationRecord[]).map((o) => ({ id: o.id, label: o.name })), pages: res.pagination?.pages ?? 1 }
}
async function loadCounterparties(p: { search: string; page: number; pageSize: number }) {
  const res = await listReferences('counterparties', { search: p.search, page: p.page, page_size: p.pageSize })
  return { items: (res.data as Counterparty[]).map((c) => ({ id: c.id, label: c.name })), pages: res.pagination?.pages ?? 1 }
}
async function loadContracts(p: { search: string; page: number; pageSize: number }) {
  const res = await listReferences('contracts', { search: p.search, page: p.page, page_size: p.pageSize })
  return { items: (res.data as ContractRecord[]).map((c) => ({ id: c.id, label: c.number })), pages: res.pagination?.pages ?? 1 }
}
async function loadObjects(p: { search: string; page: number; pageSize: number }) {
  const res = await listReferences('objects', { search: p.search, page: p.page, page_size: p.pageSize })
  return { items: (res.data as ObjectRecord[]).map((o) => ({ id: o.id, label: o.name })), pages: res.pagination?.pages ?? 1 }
}

async function loadDocument(id: number) {
  const res = await getGoodsDocument(props.kind, id)
  const d = res.data
  form.id = d.id
  form.number = d.number
  form.date = d.date
  form.organization_id = d.organization_id ?? null
  form.counterparty_id = d.counterparty_id ?? null
  form.contract_id = d.contract_id ?? null
  form.object_id = d.object_id ?? null
  form.description = d.description ?? ''
  form.lines = d.lines.map((l) => ({ ...l }))
  isPosted.value = d.is_posted
  orgLabel.value = d.organization_name ?? ''
  cpLabel.value = d.counterparty_name ?? ''
  contractLabel.value = d.contract_number ?? ''
  objectLabel.value = d.object_name ?? ''
}

async function reload() {
  if (form.id) await loadDocument(form.id)
}

function openMovements() {
  if (!form.id) {
    info.value = 'Сначала сохраните документ'
    return
  }
  movementsOpen.value = true
}

function buildPayload(): GoodsDocumentPayload {
  return {
    id: form.id,
    number: form.number || '',
    date: form.date,
    organization_id: form.organization_id ?? 0,
    counterparty_id: form.counterparty_id,
    contract_id: form.contract_id,
    object_id: form.object_id,
    description: form.description || null,
    auto_schedule: form.auto_schedule,
    based_on_type: form.based_on_type ?? null,
    based_on_id: form.based_on_id ?? null,
    based_on_number: form.based_on_number ?? null,
    lines: form.lines.map<GoodsLineInput>((l, i) => ({
      id: l.id,
      uuid: l.uuid ?? null,
      line_number: i + 1,
      material_id: l.material_id ?? null,
      name: l.name || '(без наименования)',
      unit_id: l.unit_id ?? null,
      unit: l.unit ?? null,
      quantity: Number(l.quantity) || 0,
      price_without_vat: Number(l.price_without_vat) || 0,
      vat_rate: Number(l.vat_rate) || 20,
      object_id: l.object_id ?? null,
      drawing_code: l.drawing_code ?? null,
      note: l.note ?? null,
    })),
  }
}

async function save() {
  if (!form.organization_id) {
    error.value = 'Укажите организацию'
    return
  }
  loading.value = true
  error.value = ''
  info.value = ''
  try {
    const payload = buildPayload()
    const res = form.id ? await updateGoodsDocument(props.kind, form.id, payload) : await createGoodsDocument(props.kind, payload)
    form.id = res.data.id
    form.number = res.data.number
    isPosted.value = res.data.is_posted
    info.value = 'Сохранено'
    if (props.id !== String(res.data.id)) {
      router.replace(`${basePath.value}/${res.data.id}`)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка сохранения'
  } finally {
    loading.value = false
  }
}

async function createMissingMaterials() {
  const missing = linesWithoutMaterial.value
  if (!missing.length) return
  const uniqueNames = new Set(missing.map((l) => l.name.trim()))
  if (!window.confirm(`Создать карточки материалов по наименованиям строк?\n\nБудет создано материалов: ${uniqueNames.size}.\nСтрок без материала: ${missing.length}.`)) return
  error.value = ''
  info.value = ''
  loading.value = true
  try {
    const cache = new Map<string, { id: number; code?: string | null }>()
    let created = 0
    for (const line of missing) {
      const key = line.name.trim()
      let mat = cache.get(key)
      if (!mat) {
        const res = await createReference('materials', {
          name: key,
          code: null,
          unit_id: line.unit_id ?? null,
          price: Number(line.price_without_vat) || 0,
        })
        const data = res.data as unknown as MaterialRecord
        mat = { id: data.id, code: data.code ?? null }
        cache.set(key, mat)
        created++
      }
      line.material_id = mat.id
      line.material_code = mat.code ?? null
    }
    if (form.id) await save()
    info.value = `Создано материалов: ${created}` + (form.id ? ' • документ сохранён' : ' • сохраните документ')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка создания материалов'
  } finally {
    loading.value = false
  }
}

async function post() {
  if (!form.id) return
  try {
    await postGoodsDocument(props.kind, form.id, form.auto_schedule)
    isPosted.value = true
    await loadDocument(form.id)
    info.value = 'Документ проведён'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка проведения'
  }
}

async function unpost() {
  if (!form.id) return
  try {
    await unpostGoodsDocument(props.kind, form.id)
    isPosted.value = false
    await loadDocument(form.id)
    info.value = 'Проведение отменено'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка отмены'
  }
}

// --- Excel import / export ---
function triggerImport() {
  fileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  error.value = ''
  info.value = ''
  try {
    const preview = await previewGoodsLinesImport(props.kind, file)
    const rows = preview.rows || []
    if (!rows.length) {
      error.value = 'В файле не найдено строк для импорта'
      return
    }
    // Replace lines with the parsed rows (keeping server-computed totals).
    form.lines = rows.map((r, i) => ({
      line_number: i + 1,
      material_id: r.material_id ?? null,
      name: r.name || '',
      unit: r.unit ?? null,
      quantity: Number(r.quantity) || 0,
      price_without_vat: Number(r.price_without_vat) || 0,
      vat_rate: Number(r.vat_rate) || 20,
      vat_amount: Number(r.vat_amount) || 0,
      sum_without_vat: Number(r.sum_without_vat) || 0,
      sum_with_vat: Number(r.sum_with_vat) || 0,
      drawing_code: r.drawing_code ?? null,
      note: r.note ?? null,
    }))
    info.value = `Загружено строк: ${rows.length}` + (preview.warnings?.length ? ` • предупреждений: ${preview.warnings.length}` : '')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка импорта'
  }
}

async function doExport() {
  if (!form.id) {
    info.value = 'Сначала сохраните документ'
    return
  }
  try {
    const blob = await exportGoodsLines(props.kind, form.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${isReceipt.value ? 'receipt' : 'issue'}_${form.id}.xls`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка экспорта'
  }
}

onMounted(async () => {
  try {
    if (props.id) {
      await loadDocument(Number(props.id))
    } else if (hasBasedOn) {
      const result = await loadSource()
      if (result) {
        const { source, meta } = result
        if (source.organization_id) form.organization_id = source.organization_id
        if (source.organization_name) orgLabel.value = source.organization_name
        if (source.counterparty_id) form.counterparty_id = source.counterparty_id
        if (source.counterparty_name) cpLabel.value = source.counterparty_name
        if (source.contract_id) form.contract_id = source.contract_id
        if (source.contract_number) contractLabel.value = source.contract_number
        if (source.object_id) form.object_id = source.object_id
        if (source.object_name) objectLabel.value = source.object_name
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
.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem 1rem; margin-bottom: 1rem; }
.field-span-2 { grid-column: span 2; }
.document-toolbar { margin: 0.5rem 0 1rem; align-items: center; gap: 0.5rem; }
.message-banner { padding: 0.5rem 0.75rem; border-radius: 4px; margin-bottom: 0.75rem; }
.message-error { background: var(--danger-bg, #fde8e8); color: var(--danger, #b00020); }
.message-success { background: var(--success-bg, #e8f5e9); color: var(--success, #1b7a3d); }
</style>
