<template>
  <section class="card">
    <h1>{{ doc?.number || 'Новые начальные остатки' }} · {{ doc?.is_posted ? 'Проведен' : 'Черновик' }}</h1>
    <p>Остатки действуют с указанной даты. Стоимость товара — общая стоимость строки без НДС; задолженность вводится отдельно от закупок и выручки.</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <fieldset :disabled="busy || doc?.is_posted || !canWrite">
      <label>Номер <input v-model="form.number" class="input" /></label>
      <label>Дата начала <input v-model="form.date" type="date" class="input" /></label>
      <label>Организация <EntityPicker v-model="form.organization_id" :selected-label="doc?.organization_name || ''" title="Организация" :load-page="loader('organizations')" /></label>
      <label>Комментарий <input v-model="form.description" class="input" /></label>
      <h2>Склад</h2><button class="button" @click="addInventory">Добавить товар</button>
      <div class="table-scroll"><table class="data-table"><thead><tr><th>Товар</th><th>Склад</th><th>Объект</th><th>Упаковка и аналитики</th><th>Ед.</th><th>Количество</th><th>Общая стоимость</th><th></th></tr></thead>
        <tbody><tr v-for="(line, index) in form.inventory" :key="index">
          <td><EntityPicker v-model="line.material_id" :selected-label="line.material_name || ''" title="Товар" :load-page="loader('materials')" @change="item => materialChanged(line, item)" /></td>
          <td><EntityPicker v-model="line.warehouse_id" :selected-label="line.warehouse_name || ''" title="Склад" :load-page="loader('warehouses', { organization_id: form.organization_id })" /></td>
          <td><EntityPicker :model-value="line.object_id ?? null" @update:model-value="value => line.object_id = value" title="Объект" :load-page="loader('objects')" /></td>
          <td><StockDimensionsEditor :line="line" /></td>
          <td>{{ line.unit_name || line.unit_id }}</td>
          <td><input v-model.number="line.quantity" aria-label="Начальное количество" type="number" min="0.000001" step="any" /></td>
          <td><input v-model.number="line.cost" aria-label="Начальная стоимость" type="number" min="0" step="0.01" /></td>
          <td><button @click="form.inventory.splice(index, 1)">Удалить строку</button></td>
        </tr></tbody></table></div>
      <h2>Взаиморасчеты</h2><button class="button" @click="addSettlement">Добавить задолженность</button>
      <div class="table-scroll"><table class="data-table"><thead><tr><th>Контрагент</th><th>Договор</th><th>Объект</th><th>Вид долга</th><th>Сумма</th><th></th></tr></thead>
        <tbody><tr v-for="(line, index) in form.settlements" :key="index">
          <td><EntityPicker v-model="line.counterparty_id" :selected-label="line.counterparty_name || ''" title="Контрагент" :load-page="loader('counterparties')" @update:model-value="line.contract_id = 0" /></td>
          <td><EntityPicker v-model="line.contract_id" :selected-label="line.contract_number || ''" title="Договор" :load-page="loader('contracts', { organization_id: form.organization_id, counterparty_id: line.counterparty_id })" /></td>
          <td><EntityPicker :model-value="line.object_id ?? null" @update:model-value="value => line.object_id = value" title="Объект расчетов" :load-page="loader('objects')" /></td>
          <td><select v-model="line.direction" aria-label="Вид начального долга"><option value="payable">Долг поставщику</option><option value="receivable">Долг покупателя</option></select></td>
          <td><input v-model.number="line.amount" aria-label="Начальная задолженность" type="number" min="0.01" step="0.01" /></td>
          <td><button @click="form.settlements.splice(index, 1)">Удалить строку</button></td>
        </tr></tbody></table></div>
    </fieldset>
    <div class="toolbar">
      <button class="button button-primary" :disabled="busy || doc?.is_posted || !canWrite" @click="run(save)">Сохранить</button>
      <button v-if="auth.isAdmin" class="button" :disabled="busy || doc?.is_posted" @click="run(post)">Провести</button>
      <button v-if="auth.isAdmin" class="button" :disabled="busy || !doc?.is_posted" @click="run(() => act('unpost'))">Отменить проведение</button>
      <button class="button" :disabled="busy || !doc || doc.is_posted || !canWrite" @click="run(remove)">Удалить</button>
      <button class="button" :disabled="busy || !doc" @click="run(showMovements)">Движения</button>
      <RouterLink to="/reports/inventory-turnover">Обороты и входящие остатки</RouterLink>
    </div><pre v-if="movements">{{ movements }}</pre>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import EntityPicker from '../../components/common/EntityPicker.vue'
import StockDimensionsEditor from '../../components/documents/StockDimensionsEditor.vue'
import { listReferences, type ReferenceListParams } from '../../api/references'
import { getOpening, saveOpening, openingAction, openingMovements, type OpeningBalance, type OpeningInventory, type OpeningPayload } from '../../api/openingBalances'
import { useAuthStore } from '../../stores/auth'
import type { ReferenceKind } from '../../types/models'
const props = defineProps<{ id?: string }>()
const auth = useAuthStore(), router = useRouter()
const canWrite = computed(() => ['admin', 'manager'].includes(auth.user?.role ?? ''))
const doc = ref<OpeningBalance>(), error = ref(''), message = ref(''), busy = ref(false), movements = ref(''), savedSignature = ref('')
const form = reactive<OpeningPayload>({ number: '', date: new Date().toISOString().slice(0, 10), organization_id: 0, description: '', inventory: [], settlements: [] })
function loader(kind: ReferenceKind, filters: ReferenceListParams = {}) {
  return async (params: { search: string; page: number; pageSize: number }) => {
    const response = await listReferences(kind, { ...filters, search: params.search, page: params.page, page_size: params.pageSize })
    return { items: response.data.filter(item => !('is_group' in item && item.is_group)).map(item => ({ id: item.id,
      label: String('number' in item ? item.number : 'name' in item ? item.name : item.id), meta: { ...item } })), pages: response.pagination?.pages ?? 1 }
  }
}
function addInventory() { form.inventory.push({ material_id: 0, warehouse_id: 0, unit_id: 0, quantity: 1, cost: 0 }) }
function addSettlement() { form.settlements.push({ counterparty_id: 0, contract_id: 0, direction: 'payable', amount: 0 }) }
function materialChanged(line: OpeningInventory, item: { label?: string; meta?: Record<string, unknown> } | null) {
  line.material_name = item?.label; line.unit_id = Number(item?.meta?.unit_id ?? 0); line.unit_name = String(item?.meta?.unit_name ?? '')
  line.package_id = null; line.characteristic_id = null; line.series_id = null
  line.package_name = null; line.characteristic_name = null; line.series_name = null; line.conversion_factor = 1
}
function payload(): OpeningPayload {
  return { number: form.number, date: form.date, organization_id: form.organization_id, description: form.description,
    inventory: form.inventory.map(line => ({ material_id: line.material_id, warehouse_id: line.warehouse_id, unit_id: line.unit_id,
      object_id: line.object_id ?? null, quantity: line.quantity, cost: line.cost, package_id: line.package_id ?? null,
      characteristic_id: line.characteristic_id ?? null, series_id: line.series_id ?? null })),
    settlements: form.settlements.map(line => ({ counterparty_id: line.counterparty_id, contract_id: line.contract_id,
      object_id: line.object_id ?? null, direction: line.direction, amount: line.amount })) }
}
function apply(value: OpeningBalance) { doc.value = value; Object.assign(form, { ...value, description: value.description ?? '' }); savedSignature.value = JSON.stringify(payload()) }
async function run(action: () => Promise<unknown>) {
  busy.value = true; error.value = ''; message.value = ''
  try { await action(); message.value = 'Готово' } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка операции' }
  finally { busy.value = false }
}
async function save() {
  apply((await saveOpening(payload(), doc.value?.id)).data)
  await router.replace(`/goods/opening-balances/${doc.value!.id}`)
}
async function post() {
  if (!doc.value) await save()
  else if (JSON.stringify(payload()) !== savedSignature.value) throw new Error('Сначала сохраните изменения и проверьте начальные остатки')
  await act('post')
}
async function act(action: 'post' | 'unpost') { if (doc.value) apply((await openingAction(doc.value.id, action)).data) }
async function remove() { if (doc.value && window.confirm('Удалить начальные остатки?')) { await openingAction(doc.value.id, 'delete'); await router.push('/goods/opening-balances') } }
async function showMovements() { if (doc.value) movements.value = JSON.stringify((await openingMovements(doc.value.id)).data, null, 2) }
onMounted(() => run(async () => { if (props.id) apply((await getOpening(Number(props.id))).data) }))
</script>
<style scoped>fieldset { border: 0; display: grid; gap: .75rem; } label { display: flex; gap: .75rem; align-items: center; } pre, .table-scroll { overflow: auto; } td { min-width: 130px; }</style>
