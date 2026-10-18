<template>
  <section class="card">
    <h1>{{ doc?.number || 'Новая корректировка цены' }} <small>{{ doc?.is_posted ? 'Проведена' : 'Черновик' }}</small></h1>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <fieldset :disabled="busy || doc?.is_posted || !canWrite">
      <label>Вид корректировки <select aria-label="Вид корректировки" v-model="kind" :disabled="!!doc" @change="resetSource"><option value="sale">Цены продажи</option><option value="purchase">Цены закупки</option></select></label>
      <label>Дата <input v-model="date" type="date" /></label><label>Номер <input v-model="number" /></label>
      <label>Основание <select aria-label="Основание" v-model="sourceId" :disabled="!!doc" @change="loadSource"><option :value="0">Выберите проведенный документ</option><option v-for="source in sources" :key="source.id" :value="source.id">{{ source.number }} · {{ source.date }} · {{ source.counterparty_name }}</option></select></label>
      <div class="toolbar"><button class="btn" :disabled="sourcePage === 1" @click="sourcePage--; loadSources()">Предыдущие основания</button><span>{{ sourcePage }} / {{ sourcePages }}</span><button class="btn" :disabled="sourcePage >= sourcePages" @click="sourcePage++; loadSources()">Следующие основания</button></div>
      <p v-if="original">{{ original.organization_name }} · {{ original.counterparty_name }} · Договор {{ original.contract_number }} · {{ original.warehouse_name }} · {{ original.object_name }}</p>
      <label>Комментарий <input v-model="description" /></label>
      <table class="table"><thead><tr><th>Товар</th><th>Количество основания</th><th>Прежняя цена без НДС</th><th>Новая цена без НДС</th><th>НДС, %</th></tr></thead><tbody>
        <tr v-for="line in lines" :key="line.source_line_id"><td>{{ line.name }}<small v-if="line.analytics"> · {{ line.analytics }}</small></td><td>{{ line.quantity }}</td><td>{{ line.old_price }}</td><td><input v-model.number="line.new_price" type="number" min="0" step="0.000001" :aria-label="`Новая цена ${line.name}`" /></td><td>{{ line.vat_rate }}</td></tr>
      </tbody></table>
    </fieldset>
    <p>Количество товара не меняется. Суммы начисляются отдельной корректировкой.</p>
    <p v-if="kind === 'purchase'">Если товар уже расходовался, изменение закупочной стоимости требует пересчета себестоимости и пока недоступно.</p>
    <p v-if="doc">Изменение без НДС: {{ doc.delta_without_vat.toFixed(2) }} · НДС: {{ doc.delta_vat.toFixed(2) }} · С НДС: {{ doc.delta_with_vat.toFixed(2) }}</p>
    <div class="toolbar">
      <button class="btn btn-primary" :disabled="busy || doc?.is_posted || !canWrite" @click="run(save)">Сохранить</button>
      <button v-if="auth.isAdmin" class="btn" :disabled="busy || doc?.is_posted" @click="run(post)">Провести</button>
      <button v-if="auth.isAdmin" class="btn" :disabled="busy || !doc?.is_posted" @click="run(unpost)">Отменить проведение</button>
      <button class="btn" :disabled="busy || !doc || doc.is_posted || !canWrite" @click="run(remove)">Удалить</button>
      <button class="btn" :disabled="busy || !doc" @click="run(showMovements)">Движения</button>
    </div>
    <pre v-if="movements">{{ movements }}</pre>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { listGoodsDocuments } from '../../api/goods'
import { getPriceAdjustment, getPriceAdjustmentSource, savePriceAdjustment, priceAdjustmentAction, priceAdjustmentMovements, type PriceAdjustment, type PriceAdjustmentKind } from '../../api/priceAdjustments'
import type { GoodsDocument } from '../../types/models'
import { stockDimensionsLabel } from '../../utils/stockDimensions'
const props = defineProps<{ id?: string }>()
const router = useRouter()
const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'manager'].includes(auth.user?.role ?? ''))
const doc = ref<PriceAdjustment>()
const kind = ref<PriceAdjustmentKind>('sale')
const date = ref(new Date().toLocaleDateString('en-CA'))
const number = ref('')
const description = ref('')
const sourceId = ref(0)
const sources = ref<GoodsDocument[]>([])
const original = ref<GoodsDocument>()
const sourcePage = ref(1)
const sourcePages = ref(1)
const lines = ref<{ source_line_id: number; name: string; analytics: string; quantity: number; old_price: number; new_price: number; vat_rate: number }[]>([])
const busy = ref(false)
const error = ref('')
const message = ref('')
const movements = ref('')
async function run(action: () => Promise<unknown>) {
  busy.value = true; error.value = ''; message.value = ''
  try { await action(); message.value = 'Готово' }
  catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка операции' }
  finally { busy.value = false }
}
async function loadSources() {
  try {
    const response = await listGoodsDocuments(kind.value === 'sale' ? 'issue' : 'receipt', { is_posted: true, page: sourcePage.value, page_size: 50 })
    sources.value = response.data; sourcePages.value = response.pagination?.pages ?? 1
    if (original.value && !sources.value.some(s => s.id === original.value?.id)) sources.value.unshift(original.value)
  } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки оснований' }
}
async function resetSource() { sourceId.value = 0; original.value = undefined; lines.value = []; sourcePage.value = 1; await loadSources() }
async function loadSource() {
  if (!sourceId.value) { original.value = undefined; lines.value = []; return }
  try {
    const response = await getPriceAdjustmentSource(kind.value, sourceId.value, doc.value?.id)
    original.value = response.data
    lines.value = response.data.lines.filter(l => l.material_id && l.unit_id && l.quantity > 0).map(l => {
      const saved = doc.value?.lines.find(s => s.source_line_id === l.id)
      return { source_line_id: l.id!, name: l.name, analytics: stockDimensionsLabel(saved ?? l), quantity: l.quantity, old_price: saved?.old_price ?? l.effective_price, new_price: saved?.new_price ?? l.effective_price, vat_rate: l.vat_rate }
    })
  } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки основания'; original.value = undefined; lines.value = [] }
}
async function refresh() {
  if (!doc.value) return
  doc.value = (await getPriceAdjustment(doc.value.id)).data
  kind.value = doc.value.kind; sourceId.value = doc.value.source_id; number.value = doc.value.number; date.value = doc.value.date; description.value = doc.value.description ?? ''
  await loadSource()
}
async function save(navigate = true) {
  if (!original.value) throw new Error('Выберите основание')
  if (lines.value.some(l => typeof l.new_price !== 'number' || !Number.isFinite(l.new_price) || l.new_price < 0)) throw new Error('Укажите неотрицательные новые цены')
  const changed = lines.value.filter(l => l.new_price !== l.old_price)
  if (!changed.length) throw new Error('Измените цену хотя бы одной строки')
  doc.value = (await savePriceAdjustment({ kind: kind.value, source_id: sourceId.value, date: date.value, number: number.value, description: description.value, lines: changed.map(l => ({ source_line_id: l.source_line_id, new_price: l.new_price })) }, doc.value?.id)).data
  await refresh()
  if (navigate) await router.replace(`/goods/price-adjustments/${doc.value!.id}`)
}
async function post() {
  if (!doc.value) await save(false)
  else {
    const changed = number.value !== doc.value.number || date.value !== doc.value.date || description.value !== (doc.value.description ?? '')
      || lines.value.some(line => line.new_price !== (doc.value!.lines.find(saved => saved.source_line_id === line.source_line_id)?.new_price ?? line.old_price))
    if (changed) throw new Error('Сначала сохраните изменения и проверьте суммы корректировки')
  }
  // Posting an existing draft must preserve its baseline. An automatic PUT
  // here would silently rebase a stale draft onto another correction's price.
  await priceAdjustmentAction(doc.value!.id, 'post'); await refresh(); await router.replace(`/goods/price-adjustments/${doc.value!.id}`)
}
async function unpost() { if (doc.value) { await priceAdjustmentAction(doc.value.id, 'unpost'); await refresh() } }
async function remove() { if (doc.value && window.confirm('Удалить корректировку?')) { await priceAdjustmentAction(doc.value.id, 'delete'); await router.push('/goods/price-adjustments') } }
async function showMovements() { if (doc.value) movements.value = JSON.stringify((await priceAdjustmentMovements(doc.value.id)).data, null, 2) }
onMounted(() => run(async () => {
  if (props.id) { doc.value = (await getPriceAdjustment(Number(props.id))).data; await refresh() }
  await loadSources()
}))
</script>
<style scoped>
fieldset { display: grid; gap: 1rem; border: 0; padding: 0; }
label { display: flex; gap: .75rem; align-items: center; }
small { font-size: 1rem; }
pre { overflow: auto; max-height: 30rem; }
</style>
