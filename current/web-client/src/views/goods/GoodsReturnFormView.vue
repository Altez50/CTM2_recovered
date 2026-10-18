<template>
  <section class="card">
    <h1>{{ doc?.number || 'Новый возврат товаров' }} <small>{{ doc?.is_posted ? 'Проведен' : 'Черновик' }}</small></h1>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <fieldset :disabled="busy || doc?.is_posted || !canWrite">
      <label>Вид возврата <select v-model="kind" :disabled="!!doc" @change="resetSource"><option value="customer">От клиента</option><option value="supplier">Поставщику</option></select></label>
      <label>Дата <input v-model="date" type="date" /></label>
      <label>Номер <input v-model="number" /></label>
      <label>Основание <select aria-label="Основание" v-model="sourceId" :disabled="!!doc" @change="loadSource"><option :value="0">Выберите проведенный документ</option><option v-for="source in sources" :key="source.id" :value="source.id">{{ source.number }} · {{ source.date }} · {{ source.counterparty_name }}</option></select></label>
      <div class="toolbar"><button class="btn" :disabled="sourcePage === 1" @click="sourcePage--; loadSources()">Предыдущие основания</button><span>{{ sourcePage }} / {{ sourcePages }}</span><button class="btn" :disabled="sourcePage >= sourcePages" @click="sourcePage++; loadSources()">Следующие основания</button></div>
      <p v-if="original">{{ original.organization_name }} · {{ original.counterparty_name }} · Договор {{ original.contract_number }} · {{ original.warehouse_name }} · {{ original.object_name }}</p>
      <label>Комментарий <input v-model="description" /></label>
      <table class="table"><thead><tr><th>Товар</th><th>Доступно к возврату</th><th>Вернуть</th><th>Цена без НДС</th><th>НДС, %</th></tr></thead>
        <tbody><tr v-for="line in lines" :key="line.source_line_id"><td>{{ line.name }}<small v-if="line.analytics"> · {{ line.analytics }}</small></td><td>{{ line.limit }}</td><td><input v-model.number="line.quantity" type="number" min="0" :max="line.limit" step="0.000001" :aria-label="`Вернуть ${line.name}`" /></td><td>{{ line.price }}</td><td>{{ line.vat }}</td></tr></tbody>
      </table>
    </fieldset>
    <p v-if="doc">Сумма с НДС: {{ doc.sum_with_vat.toFixed(2) }} · Исходная себестоимость: {{ doc.inventory_cost.toFixed(2) }}</p>
    <div class="toolbar">
      <button class="btn btn-primary" :disabled="busy || doc?.is_posted || !canWrite" @click="run(save)">Сохранить</button>
      <button v-if="auth.isAdmin" class="btn" :disabled="busy || doc?.is_posted || !canWrite" @click="run(post)">Провести</button>
      <button v-if="auth.isAdmin" class="btn" :disabled="busy || !doc?.is_posted" @click="run(() => act('unpost'))">Отменить проведение</button>
      <button class="btn" :disabled="busy || !canWrite || !doc || doc.is_posted" @click="run(remove)">Удалить</button>
      <button class="btn" :disabled="busy || !doc" @click="run(showMovements)">Движения</button>
    </div>
    <template v-if="doc">
      <h2>{{ kind === 'customer' ? 'Возврат денег клиенту' : 'Получение денег от поставщика' }}</h2>
      <p>Сумма к возврату проверяется в аналитике основания на дату платежа.</p>
      <label>Дата платежа <input v-model="refundDate" type="date" :disabled="busy" /></label>
      <label>Сумма <input v-model.number="refundAmount" type="number" min="0.01" step="0.01" :disabled="busy" /></label>
      <button class="btn" :disabled="busy || !canWrite || !doc.is_posted || refundAmount <= 0" @click="run(createRefund)">Создать возврат денег</button>
      <table class="table"><thead><tr><th>Номер</th><th>Дата</th><th>Сумма</th><th>Статус</th><th>Действия</th></tr></thead><tbody>
        <tr v-for="refund in doc.refunds" :key="refund.id"><td>{{ refund.number }}</td><td>{{ refund.date }}</td><td>{{ refund.amount.toFixed(2) }}</td><td>{{ refund.is_posted ? 'Проведен' : 'Черновик' }}</td>
          <td><button v-if="auth.isAdmin" class="btn" :disabled="busy || !doc.is_posted" @click="run(() => actRefund(refund.id, refund.is_posted ? 'unpost' : 'post'))">{{ refund.is_posted ? 'Отменить' : 'Провести' }}</button><button class="btn" :disabled="busy || !canWrite || refund.is_posted" @click="run(() => actRefund(refund.id, 'delete'))">Удалить</button></td>
        </tr>
      </tbody></table>
    </template>
    <pre v-if="movements">{{ movements }}</pre>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { listGoodsDocuments } from '../../api/goods'
import { getReturnSource, getReturn, saveReturn, returnAction, returnMovements, saveRefund, refundAction, type GoodsReturn } from '../../api/returns'
import type { GoodsDocument } from '../../types/models'
import { stockDimensionsLabel } from '../../utils/stockDimensions'
const props = defineProps<{ id?: string }>()
const router = useRouter()
const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'manager'].includes(auth.user?.role ?? ''))
const doc = ref<GoodsReturn>()
const kind = ref<'customer' | 'supplier'>('customer')
const date = ref(new Date().toLocaleDateString('en-CA'))
const number = ref('')
const description = ref('')
const sourceId = ref(0)
const sourcePage = ref(1)
const sourcePages = ref(1)
const sources = ref<GoodsDocument[]>([])
const original = ref<GoodsDocument>()
const lines = ref<{ source_line_id: number; name: string; analytics: string; limit: number; quantity: number; price: number; vat: number }[]>([])
const busy = ref(false)
const error = ref('')
const message = ref('')
const movements = ref('')
const refundDate = ref(date.value)
const refundAmount = ref(0)
async function run(action: () => Promise<unknown>) {
  busy.value = true; error.value = ''; message.value = ''
  try { await action(); message.value = 'Готово' } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка операции' }
  finally { busy.value = false }
}
async function loadSources() {
  try {
    const response = await listGoodsDocuments(kind.value === 'customer' ? 'issue' : 'receipt', { is_posted: true, page: sourcePage.value, page_size: 50 })
    sources.value = response.data; sourcePages.value = response.pagination?.pages ?? 1
    if (original.value && !sources.value.some(s => s.id === original.value?.id)) sources.value.unshift(original.value)
  } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки оснований' }
}
async function resetSource() { sourceId.value = 0; original.value = undefined; lines.value = []; sourcePage.value = 1; await loadSources() }
async function loadSource() {
  if (!sourceId.value) { original.value = undefined; lines.value = []; return }
  try {
    const response = await getReturnSource(kind.value, sourceId.value, doc.value?.id)
    original.value = response.data
    lines.value = response.data.lines.filter(l => l.material_id && l.unit_id).map(l => ({ source_line_id: l.id!, name: l.name, analytics: stockDimensionsLabel(l), limit: l.returnable_quantity, quantity: doc.value?.lines.find(r => r.source_line_id === l.id)?.quantity ?? 0, price: l.price_without_vat, vat: l.vat_rate }))
  } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки основания'; original.value = undefined; lines.value = [] }
}
async function refresh() {
  if (!doc.value?.id) return
  doc.value = (await getReturn(doc.value.id)).data
  kind.value = doc.value.kind; sourceId.value = doc.value.source_id; date.value = doc.value.date; number.value = doc.value.number; description.value = doc.value.description ?? ''
  await loadSource()
}
async function save(navigate = true) {
  if (!original.value || !lines.value.some(l => l.quantity > 0)) throw new Error('Выберите основание и количество возврата')
  doc.value = (await saveReturn({ kind: kind.value, source_id: sourceId.value, date: date.value, number: number.value, description: description.value, lines: lines.value.filter(l => l.quantity > 0).map(l => ({ source_line_id: l.source_line_id, quantity: l.quantity })) }, doc.value?.id)).data
  await refresh()
  if (navigate) await router.replace(`/goods/returns/${doc.value!.id}`)
}
async function post() { await save(false); await act('post'); await router.replace(`/goods/returns/${doc.value!.id}`) }
async function act(action: 'post' | 'unpost') { if (doc.value) { await returnAction(doc.value.id, action); await refresh() } }
async function remove() { if (doc.value && window.confirm('Удалить возврат?')) { await returnAction(doc.value.id, 'delete'); await router.push('/goods/returns') } }
async function showMovements() { if (doc.value) movements.value = JSON.stringify((await returnMovements(doc.value.id)).data, null, 2) }
async function createRefund() { if (doc.value) { await saveRefund({ return_id: doc.value.id, date: refundDate.value, amount: refundAmount.value }); await refresh() } }
async function actRefund(id: number, action: 'post' | 'unpost' | 'delete') { await refundAction(id, action); await refresh() }
onMounted(() => run(async () => {
  if (props.id) { doc.value = (await getReturn(Number(props.id))).data; await refresh() }
  await loadSources()
}))
</script>
<style scoped>
fieldset { display: grid; gap: 1rem; border: 0; padding: 0; }
label { display: flex; gap: .75rem; align-items: center; }
small { font-size: 1rem; }
pre { overflow: auto; max-height: 30rem; }
</style>
