<template>
  <section class="panel panel-body">
    <h1>{{ purchaseTitles[kind] }} · {{ doc?.number || 'Новый документ' }}</h1>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <p v-if="kind === 'orders'">Согласование заказа фиксирует план. Долг и склад появляются при приемке.</p>
    <p v-if="kind === 'acquisitions' && source?.receipt_mode === 'order'">Приобретение отражает долг. Товар принимается отдельным приходным ордером.</p>
    <p v-if="kind === 'receipt-orders'">Ордер отражает физическое количество по цене согласованного заказа. Долг отражается приобретением.</p>
    <fieldset :disabled="readOnly">
      <label>Номер <input v-model="form.number" class="input" /></label><label>Дата <input v-model="form.date" type="date" class="input" /></label>
      <template v-if="kind === 'orders'">
        <label>Организация <EntityPicker v-model="form.organization_id" :selected-label="labels.organization" title="Выбор организации" :load-page="loadOrganizations" @change="clearOwners" /></label>
        <label>Контрагент <EntityPicker v-model="form.counterparty_id" :selected-label="labels.counterparty" title="Выбор контрагента" :load-page="loadCounterparties" @change="form.contract_id = null; labels.contract = ''" /></label>
        <label>Договор <EntityPicker v-model="form.contract_id" :selected-label="labels.contract" title="Выбор договора" :load-page="loadContracts" /></label>
        <label>Склад <EntityPicker v-model="form.warehouse_id" :selected-label="labels.warehouse" title="Выбор склада" :load-page="loadWarehouses" /></label>
        <label>Объект <EntityPicker v-model="form.object_id" :selected-label="labels.object" title="Выбор объекта" :load-page="loadObjects" /></label>
        <GoodsLinesEditor :lines="goodsLines" :disabled="readOnly" @update:lines="setGoodsLines" />
        <button type="button" class="button" @click="addService">+ Услуга</button>
        <div v-for="(row, index) in serviceLines" :key="index" class="service-line">
          <label>Услуга <input v-model="row.name" class="input" /></label><label>Количество услуги <input v-model.number="row.quantity" type="number" min="0" step="any" /></label>
          <label>Цена услуги без НДС <input v-model.number="row.price_without_vat" type="number" min="0" step="any" /></label><label>НДС услуги % <input v-model.number="row.vat_rate" type="number" min="0" max="100" /></label>
          <button type="button" @click="form.lines = form.lines.filter(line => line !== row)">Удалить услугу</button>
        </div>
      </template>
      <template v-else>
        <label>Основание <EntityPicker v-model="sourceId" :selected-label="source?.number" :disabled="!!doc" title="Выбор основания" :load-page="loadSources" @change="selectSource" /></label>
        <p v-if="source">{{ source.organization_name }} · {{ source.counterparty_name }} · {{ source.contract_number }} · {{ source.warehouse_name || 'Услуги' }}</p>
        <table v-if="source"><thead><tr><th>Строка основания</th><th>Упаковка / характеристика / серия</th><th>Количество</th><th v-if="kind === 'discrepancies' && source.receipt_mode === 'order'">Принято по строке ордера</th></tr></thead><tbody>
          <tr v-for="(row, index) in form.basisLines" :key="row.source_line_id"><td>{{ source.lines[index]?.name }}<span v-if="source.lines[index]?.line_type === 'service'"> · Услуга</span></td>
            <td>{{ [source.lines[index]?.package_name, source.lines[index]?.characteristic_name, source.lines[index]?.series_name].filter(Boolean).join(' / ') }}</td>
            <td><input :aria-label="`Количество строки ${index + 1}`" v-model.number="row.quantity" :disabled="kind === 'receipt-orders' && source.lines[index]?.line_type === 'service'" type="number" min="0" step="any" /></td>
            <td v-if="kind === 'discrepancies' && source.receipt_mode === 'order'"><select :aria-label="`Строка ордера ${index + 1}`" v-model.number="row.receipt_line_id"><option :value="null">Выберите строку</option><option v-for="option in receiptOptions(source.lines[index]?.order_line_id)" :key="option.id" :value="option.id">{{ option.label }}</option></select></td>
          </tr></tbody></table>
        <p>Строки с нулевым количеством не включаются в документ. Цены, НДС и аналитики сохраняются из основания.</p>
      </template>
      <label>Описание <input v-model="form.description" class="input" /></label>
    </fieldset>
    <div class="toolbar">
      <button v-if="canWrite" class="button button-primary" :disabled="readOnly" @click="save">Сохранить</button>
      <button v-if="auth.isAdmin && doc && !doc.is_posted" class="button" :disabled="busy" @click="change('post')">{{ kind === 'orders' ? 'Согласовать' : 'Провести' }}</button>
      <button v-if="auth.isAdmin && doc?.is_posted" class="button" :disabled="busy" @click="change('unpost')">{{ kind === 'orders' ? 'Отменить согласование' : 'Отменить проведение' }}</button>
      <button v-if="canWrite && doc && !doc.is_posted" class="button" :disabled="busy" @click="change('delete')">Удалить</button>
      <button v-if="doc" class="button" :disabled="busy" @click="showMovements">Движения</button>
      <span>{{ doc?.is_posted ? (kind === 'orders' ? 'Согласован' : 'Проведен') : 'Черновик' }}</span>
    </div>
    <nav v-if="doc?.is_posted && canWrite" class="toolbar"><RouterLink v-for="child in childKinds" :key="child" :to="`/purchases/${child}/new?source=${doc.id}`">{{ purchaseTitles[child] }}</RouterLink></nav>
    <table v-if="kind === 'orders' && doc"><thead><tr><th>Товар/услуга</th><th>Заказано</th><th>Принято</th><th>Открыто</th><th>Отменено</th><th>Недопоставка</th></tr></thead><tbody><tr v-for="row in doc.lines" :key="row.id"><td>{{ row.name }}</td><td>{{ row.quantity }}</td><td>{{ row.received_quantity }}</td><td>{{ row.open_quantity }}</td><td>{{ row.cancelled_quantity }}</td><td>{{ row.shortage_quantity }}</td></tr></tbody></table>
    <section v-if="movements"><h2>Движения документа</h2>
      <p v-if="!movements.inventory.length && !movements.settlements.length && !movements.expenses.length">Учетных движений нет</p>
      <table v-if="movements.inventory.length"><thead><tr><th>Строка</th><th>Приход</th><th>Расход</th><th>Стоимость прихода</th><th>Стоимость расхода</th></tr></thead><tbody><tr v-for="row in movements.inventory" :key="row.line_number"><td>{{ row.line_number }}</td><td>{{ row.quantity_income }}</td><td>{{ row.quantity_expense }}</td><td>{{ row.sum_income }}</td><td>{{ row.sum_expense }}</td></tr></tbody></table>
      <p v-for="row in movements.settlements" :key="row.line_number">Начисление долга: {{ row.accrual_amount }}</p><p v-for="row in movements.expenses" :key="row.id">{{ row.name }} · Расход без НДС: {{ row.expense_amount }}</p>
    </section>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EntityPicker from '../../components/common/EntityPicker.vue'
import GoodsLinesEditor from '../../components/documents/GoodsLinesEditor.vue'
import { listReferences } from '../../api/references'
import { purchaseTitles, purchaseSources, listPurchases, getPurchase, savePurchase, changePurchase, purchaseMovements, type PurchaseKind, type PurchaseDocument, type PurchaseOrderLine, type PurchaseBasisLine, type PurchaseMovements } from '../../api/purchases'
import type { GoodsLine, ReferenceKind } from '../../types/models'
import { useAuthStore } from '../../stores/auth'
const props = defineProps<{ kind: PurchaseKind; id?: string; tabId?: string }>()
const auth = useAuthStore(), route = useRoute(), router = useRouter(), canWrite = computed(() => auth.canWriteTrade)
const doc = ref<PurchaseDocument | null>(null), source = ref<PurchaseDocument | null>(null), sourceId = ref<number | null>(null), receiptDocs = ref<PurchaseDocument[]>([])
const error = ref(''), message = ref(''), busy = ref(false), movements = ref<PurchaseMovements | null>(null)
const readOnly = computed(() => busy.value || !!doc.value?.is_posted || (!!props.id && !doc.value) || !canWrite.value)
const form = reactive({ number: '', date: new Date().toISOString().slice(0, 10), organization_id: null as number | null, counterparty_id: null as number | null,
  contract_id: null as number | null, warehouse_id: null as number | null, object_id: null as number | null, estimate_id: null as number | null,
  description: '', lines: [] as PurchaseOrderLine[], basisLines: [] as PurchaseBasisLine[] })
const labels = reactive({ organization: '', counterparty: '', contract: '', warehouse: '', object: '' })
const goodsLines = computed(() => form.lines.filter(row => row.line_type === 'goods'))
const serviceLines = computed(() => form.lines.filter(row => row.line_type === 'service'))
const childKinds = computed<PurchaseKind[]>(() => props.kind === 'orders' ? (doc.value?.receipt_mode === 'order' ? ['receipt-orders', 'acquisitions', 'cancellations'] : ['acquisitions', 'cancellations']) : props.kind === 'acquisitions' ? ['discrepancies'] : props.kind === 'discrepancies' ? ['quantity-adjustments'] : [])
function setGoodsLines(lines: GoodsLine[]) { form.lines = [...lines.map(row => ({ ...row, line_type: 'goods' as const })), ...serviceLines.value] }
function addService() { form.lines.push({ line_type: 'service', line_number: form.lines.length + 1, name: '', quantity: 1, price_without_vat: 0, vat_rate: 0, sum_without_vat: 0, vat_amount: 0, sum_with_vat: 0 }) }
function clearOwners() { form.contract_id = null; form.warehouse_id = null; labels.contract = ''; labels.warehouse = '' }
type PickerPage = { search: string; page: number; pageSize: number }
function referenceLoader(kind: ReferenceKind, filters: Record<string, string | number | null> = {}) { return async (p: PickerPage) => { const result = await listReferences(kind, { search: p.search, page: p.page, page_size: p.pageSize, ...filters }); return { items: (result.data as { id: number; name?: string; number?: string }[]).map(row => ({ id: row.id, label: row.name || row.number || String(row.id) })), page: p.page, pages: result.pagination?.pages ?? 1, total: result.pagination?.total ?? result.data.length } } }
const loadOrganizations = (p: PickerPage) => referenceLoader('organizations')(p), loadCounterparties = (p: PickerPage) => referenceLoader('counterparties')(p), loadObjects = (p: PickerPage) => referenceLoader('objects')(p)
const loadWarehouses = (p: PickerPage) => referenceLoader('warehouses', { organization_id: form.organization_id })(p)
const loadContracts = (p: PickerPage) => referenceLoader('contracts', { organization_id: form.organization_id, counterparty_id: form.counterparty_id })(p)
async function loadSources(p: PickerPage) { const result = await listPurchases(purchaseSources[props.kind]!, p.page); return { items: result.data.filter(row => row.is_posted && row.number.toLocaleLowerCase().includes(p.search.toLocaleLowerCase())).map(row => ({ id: row.id, label: row.number })), page: p.page, pages: result.pagination?.pages ?? 1, total: result.pagination?.total ?? result.data.length } }
async function selectSource() {
  error.value = ''
  try { if (!sourceId.value) { source.value = null; form.basisLines = []; return }
    source.value = (await getPurchase(purchaseSources[props.kind]!, sourceId.value)).data
    form.basisLines = source.value.lines.map(row => ({ source_line_id: row.id, quantity: props.kind === 'receipt-orders' ? (row.line_type === 'service' ? 0 : Math.max(0, row.open_quantity ?? row.quantity)) : props.kind === 'acquisitions' ? Math.max(0, row.quantity - (row.financial_quantity ?? 0) - (row.cancelled_quantity ?? 0) - (row.shortage_quantity ?? 0)) : props.kind === 'cancellations' ? Math.max(0, row.quantity - Math.max(row.received_quantity ?? 0, row.financial_quantity ?? 0) - (row.cancelled_quantity ?? 0) - (row.shortage_quantity ?? 0)) : row.quantity, receipt_line_id: null }))
    receiptDocs.value = []
    if (props.kind === 'discrepancies' && source.value.receipt_mode === 'order') {
      const orderId = source.value.order_id
      let page = 1, pages = 1
      do {
        const result = await listPurchases('receipt-orders', page)
        receiptDocs.value.push(...result.data.filter(row => row.is_posted && row.order_id === orderId))
        pages = result.pagination?.pages ?? 1
      } while (++page <= pages)
    }
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка загрузки основания' }
}
function receiptOptions(orderLineId?: number) { return receiptDocs.value.flatMap(receipt => receipt.lines.filter(row => row.order_line_id === orderLineId).map(row => ({ id: row.id, label: `${receipt.number} · ${row.name} · ${row.quantity}` }))) }
function orderLinesPayload() { const keys = ['line_type', 'name', 'material_id', 'unit_id', 'unit', 'quantity', 'price_without_vat', 'vat_rate', 'object_id', 'package_id', 'characteristic_id', 'series_id', 'drawing_code', 'note'] as const
  return form.lines.map((row, index) => ({ line_number: index + 1, ...Object.fromEntries(keys.filter(key => row[key] !== undefined).map(key => [key, row[key]])) })) }
async function save() {
  if (readOnly.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { const common = { number: form.number, date: form.date, description: form.description || null }
    const payload = props.kind === 'orders' ? { ...common, organization_id: form.organization_id, counterparty_id: form.counterparty_id, contract_id: form.contract_id, warehouse_id: form.warehouse_id, object_id: form.object_id, estimate_id: form.estimate_id, lines: orderLinesPayload() } : { ...common, source_id: sourceId.value, lines: form.basisLines.filter(row => row.quantity > 0).map(row => ({ source_line_id: row.source_line_id, quantity: row.quantity, ...(props.kind === 'discrepancies' ? { receipt_line_id: row.receipt_line_id } : {}) })) }
    doc.value = (await savePurchase(props.kind, payload, doc.value?.id)).data; form.number = doc.value.number; message.value = 'Сохранено'
    if (!props.id) await router.replace(`/purchases/${props.kind}/${doc.value.id}`)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка сохранения' } finally { busy.value = false }
}
async function change(action: 'post' | 'unpost' | 'delete') { if (!doc.value || busy.value) return; busy.value = true; error.value = ''
  try { const result = await changePurchase(props.kind, doc.value.id, action); if (action === 'delete') await router.push(`/purchases/${props.kind}`); else doc.value = result.data; movements.value = null }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка операции' } finally { busy.value = false } }
async function showMovements() { if (!doc.value) return; error.value = ''; try { movements.value = (await purchaseMovements(props.kind, doc.value.id)).data } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка загрузки движений' } }
onMounted(async () => { try {
  if (props.id) { doc.value = (await getPurchase(props.kind, Number(props.id))).data; const saved = doc.value
    Object.assign(form, { number: saved.number, date: saved.date, organization_id: saved.organization_id, counterparty_id: saved.counterparty_id, contract_id: saved.contract_id, warehouse_id: saved.warehouse_id ?? null, object_id: saved.object_id ?? null, estimate_id: saved.estimate_id ?? null, description: saved.description ?? '', lines: saved.lines.map(row => ({ ...row })) })
    Object.assign(labels, { organization: saved.organization_name ?? '', counterparty: saved.counterparty_name ?? '', contract: saved.contract_number ?? '', warehouse: saved.warehouse_name ?? '', object: saved.object_name ?? '' })
    if (saved.source_id) { sourceId.value = saved.source_id; await selectSource(); form.basisLines = source.value!.lines.map(row => { const line = saved.lines.find(item => item.source_line_id === row.id); return { source_line_id: row.id, quantity: line?.quantity ?? 0, receipt_line_id: line?.receipt_line_id ?? null } }) }
  } else if (route.query.source) { sourceId.value = Number(route.query.source); await selectSource() }
} catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка загрузки' } })
</script>
<style scoped>
fieldset { display: flex; flex-wrap: wrap; gap: 1rem; border: 0; padding: 0; }
fieldset > label { display: flex; flex-direction: column; min-width: 14rem; }
.goods-lines-editor, .service-line { width: 100%; }
.service-line { display: flex; gap: .75rem; flex-wrap: wrap; }
table { width: 100%; margin: 1rem 0; border-collapse: collapse; } td, th { padding: .5rem; text-align: left; }
</style>
