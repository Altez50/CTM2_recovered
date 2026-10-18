<template>
  <div class="page-shell"><section class="panel"><div class="panel-body">
    <p v-if="error" class="message-banner message-error">{{ error }}</p>
    <p v-if="info" class="message-banner message-success">{{ info }}</p>
    <div class="form-grid">
      <FormField label="Номер"><input v-model="form.number" class="input" :disabled="readOnly" placeholder="авто при записи" /></FormField>
      <FormField label="Дата"><input v-model="form.date" class="input" type="date" :disabled="readOnly" /></FormField>
      <FormField label="Организация">
        <select v-model.number="form.organization_id" class="select" :disabled="readOnly" @change="onOrganizationChange">
          <option :value="0">Выберите организацию</option>
          <option v-for="o in organizations" :key="o.id" :value="o.id">{{ o.name }}</option>
        </select>
      </FormField>
      <FormField label="Склад-отправитель">
        <select v-model.number="form.source_warehouse_id" class="select" :disabled="readOnly" @change="onWarehouseChange('source')">
          <option :value="0">Выберите склад</option>
          <option v-for="w in availableWarehouses" :key="w.id" :value="w.id">{{ w.name }}</option>
        </select>
      </FormField>
      <FormField label="Склад-получатель">
        <select v-model.number="form.destination_warehouse_id" class="select" :disabled="readOnly" @change="onWarehouseChange('destination')">
          <option :value="0">Выберите склад</option>
          <option v-for="w in availableWarehouses" :key="w.id" :value="w.id">{{ w.name }}</option>
        </select>
      </FormField>
      <FormField label="Объект-источник">
        <select v-model="form.source_object_id" class="select" :disabled="readOnly">
          <option :value="null">Без объекта</option>
          <option v-for="o in objects" :key="o.id" :value="o.id">{{ o.name }}</option>
        </select>
      </FormField>
      <FormField label="Объект-получатель">
        <select v-model="form.destination_object_id" class="select" :disabled="readOnly">
          <option :value="null">Без объекта</option>
          <option v-for="o in objects" :key="o.id" :value="o.id">{{ o.name }}</option>
        </select>
      </FormField>
      <FormField label="Ответственный">
        <select v-model="form.responsible_id" class="select" :disabled="readOnly">
          <option :value="null">Не указан</option>
          <option v-for="p in persons" :key="p.id" :value="p.id">{{ p.full_name }}</option>
        </select>
      </FormField>
      <FormField label="Описание"><input v-model="form.description" class="input" :disabled="readOnly" /></FormField>
    </div>

    <div class="toolbar">
      <button class="button button-primary" type="button" :disabled="busy || readOnly" @click="save">Сохранить</button>
      <button v-if="canWrite && !isPosted" class="button button-success" type="button" :disabled="busy" v-show="auth.isAdmin" @click="post">Провести</button>
      <button v-else class="button button-warning" type="button" :disabled="busy" v-show="auth.isAdmin" @click="unpost">Отменить проведение</button>
      <button class="button button-secondary" type="button" :disabled="!documentId || busy" @click="copy">Копировать</button>
      <button class="button button-secondary" type="button" :disabled="!documentId || busy" @click="loadMovements">Движения</button>
      <button class="button button-secondary" type="button" :disabled="!documentId || isPosted || busy" @click="remove">Пометить на удаление</button>
      <span class="status-pill" :class="isPosted ? 'posted' : 'draft'">{{ isPosted ? 'Проведён' : 'Черновик' }}</span>
    </div>

    <div class="toolbar"><h3>Материалы</h3><div class="toolbar-grow"></div>
      <button class="button button-secondary" type="button" :disabled="readOnly" @click="addLine">+ Строка</button>
    </div>
    <div class="table-scroll"><table class="data-table"><thead><tr>
      <th>№</th><th>Материал</th><th>Упаковка и аналитики</th><th>Ед.</th><th>Количество</th><th>Учётная цена</th><th>Сумма</th><th>Примечание</th><th></th>
    </tr></thead><tbody>
      <tr v-for="(line, index) in form.lines" :key="index">
        <td>{{ index + 1 }}</td>
        <td><select v-model.number="line.material_id" class="select" :disabled="readOnly" @change="onMaterialChange(line)">
          <option :value="0">Выберите материал</option>
          <option v-for="m in materials" :key="m.id" :value="m.id">{{ m.code }} {{ m.name }}</option>
        </select></td>
        <td><StockDimensionsEditor :line="line" :disabled="readOnly" /></td>
        <td><select v-model.number="line.unit_id" class="select" :disabled="readOnly">
          <option :value="0">Ед.</option><option v-for="u in units" :key="u.id" :value="u.id">{{ u.name }}</option>
        </select></td>
        <td><input v-model.number="line.quantity" class="input" type="number" min="0.000001" step="any" :disabled="readOnly" /></td>
        <td>{{ formatMoney(line.unit_cost) }}</td><td>{{ formatMoney(line.sum) }}</td>
        <td><input v-model="line.note" class="input" :disabled="readOnly" /></td>
        <td><button v-if="canWrite && !isPosted" class="button button-secondary" type="button" @click="form.lines.splice(index, 1)">✕</button></td>
      </tr>
    </tbody></table></div>
    <p v-if="!form.lines.length" class="muted">Добавьте материалы для перемещения.</p>

    <div v-if="movements.length" class="panel-body">
      <h3>Движения по складам</h3>
      <table class="data-table"><thead><tr><th>Строка</th><th>Сторона</th><th>Склад</th><th>Материал</th><th>Приход</th><th>Расход</th><th>Сумма</th></tr></thead>
      <tbody><tr v-for="movement in movements" :key="movement.id">
        <td>{{ movement.line_number }}</td><td>{{ movement.movement_side === 'source' ? 'Отправитель' : 'Получатель' }}</td>
        <td>{{ movement.warehouse_name }}</td><td>{{ movement.material_name }}</td>
        <td>{{ movement.quantity_income }}</td><td>{{ movement.quantity_expense }}</td>
        <td>{{ formatMoney(movement.sum_income || movement.sum_expense) }}</td>
      </tr></tbody></table>
    </div>
  </div></section></div>
</template>

<script setup lang="ts">
import { useAuthStore } from '../../stores/auth'
const auth = useAuthStore()
const canWrite = computed(() => auth.canWriteTrade)
const readOnly = computed(() => isPosted.value || !canWrite.value)
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import FormField from '../../components/common/FormField.vue'
import StockDimensionsEditor from '../../components/documents/StockDimensionsEditor.vue'
import { copyGoodsTransfer, deleteGoodsTransfer, getGoodsTransfer, getGoodsTransferMovements, postGoodsTransfer, saveGoodsTransfer, unpostGoodsTransfer } from '../../api/goods'
import { listReferences } from '../../api/references'
import { listUnits } from '../../api/works'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { GoodsTransferLine, GoodsTransferPayload, InventoryMovementItem, MaterialRecord, ObjectRecord, OrganizationRecord, PersonRecord, UnitRecord, WarehouseRecord } from '../../types/models'

const props = defineProps<{ tabId?: string; id?: string }>()
const router = useRouter()
const documentId = ref<number | null>(props.id ? Number(props.id) : null)
const isPosted = ref(false)
const busy = ref(false)
const error = ref('')
const info = ref('')
const organizations = ref<OrganizationRecord[]>([])
const warehouses = ref<WarehouseRecord[]>([])
const objects = ref<ObjectRecord[]>([])
const persons = ref<PersonRecord[]>([])
const materials = ref<MaterialRecord[]>([])
const units = ref<UnitRecord[]>([])
const movements = ref<(InventoryMovementItem & { id: number; movement_side?: string | null })[]>([])
const form = reactive<GoodsTransferPayload>({
  number: '', date: new Date().toISOString().slice(0, 10), organization_id: 0,
  source_warehouse_id: 0, destination_warehouse_id: 0,
  source_object_id: null, destination_object_id: null, responsible_id: null,
  description: '', lines: [],
})
const availableWarehouses = computed(() => warehouses.value.filter((w) => w.organization_id === form.organization_id))
useHeaderBar(props.tabId, computed(() => documentId.value ? `Перемещение №${form.number}` : 'Новое перемещение ТМЦ'), computed(() => []))

function addLine() { form.lines.push({ line_number: form.lines.length + 1, material_id: 0, unit_id: 0, quantity: 1, note: '' }) }
function onMaterialChange(line: GoodsTransferLine) {
  const material = materials.value.find((m) => m.id === line.material_id)
  line.name = material?.name ?? ''
  line.unit_id = material?.unit_id ?? 0
  line.package_id = null; line.characteristic_id = null; line.series_id = null
  line.package_name = null; line.characteristic_name = null; line.series_name = null; line.conversion_factor = 1
}
function onOrganizationChange() { form.source_warehouse_id = 0; form.destination_warehouse_id = 0 }
function onWarehouseChange(side: 'source' | 'destination') {
  const id = side === 'source' ? form.source_warehouse_id : form.destination_warehouse_id
  const warehouse = warehouses.value.find((w) => w.id === id)
  if (side === 'source') form.source_object_id = warehouse?.default_object_id ?? null
  else form.destination_object_id = warehouse?.default_object_id ?? null
}
function formatMoney(value?: number) { return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0) }
async function loadDocument(id: number) {
  const response = await getGoodsTransfer(id)
  const doc = response.data
  Object.assign(form, {
    number: doc.number, date: doc.date, organization_id: doc.organization_id,
    source_warehouse_id: doc.source_warehouse_id, destination_warehouse_id: doc.destination_warehouse_id,
    source_object_id: doc.source_object_id ?? null, destination_object_id: doc.destination_object_id ?? null,
    responsible_id: doc.responsible_id ?? null, description: doc.description ?? '',
    lines: doc.lines.map((line) => ({ ...line })),
  })
  documentId.value = id
  isPosted.value = doc.is_posted
}
async function save(): Promise<boolean> {
  error.value = ''; info.value = ''
  if (!form.organization_id || !form.source_warehouse_id || !form.destination_warehouse_id) { error.value = 'Укажите организацию и оба склада'; return false }
  if (form.source_warehouse_id === form.destination_warehouse_id) { error.value = 'Выберите разные склады'; return false }
  if (!form.lines.length) { error.value = 'Добавьте хотя бы один материал'; return false }
  busy.value = true
  try {
    const payload: GoodsTransferPayload = { ...form, lines: form.lines.map((line, index) => ({
      line_number: index + 1, material_id: Number(line.material_id), name: line.name,
      unit_id: Number(line.unit_id), quantity: Number(line.quantity), note: line.note,
      package_id: line.package_id ?? null, characteristic_id: line.characteristic_id ?? null, series_id: line.series_id ?? null,
    })) }
    const response = await saveGoodsTransfer(payload, documentId.value ?? undefined)
    documentId.value = response.data.id
    await loadDocument(response.data.id)
    if (!props.id) await router.replace(`/goods/transfers/${response.data.id}`)
    info.value = 'Сохранено'
    return true
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка сохранения'; return false }
  finally { busy.value = false }
}
async function post() {
  if (!(await save()) || !documentId.value) return
  busy.value = true
  try { await postGoodsTransfer(documentId.value); await loadDocument(documentId.value); info.value = 'Перемещение проведено' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка проведения' }
  finally { busy.value = false }
}
async function unpost() {
  if (!documentId.value) return
  busy.value = true
  try { await unpostGoodsTransfer(documentId.value); await loadDocument(documentId.value); movements.value = []; info.value = 'Проведение отменено' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка отмены' }
  finally { busy.value = false }
}
async function copy() {
  if (!documentId.value) return
  try { const response = await copyGoodsTransfer(documentId.value); await router.push(`/goods/transfers/${response.data.id}`) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка копирования' }
}
async function remove() {
  if (!documentId.value || !window.confirm('Пометить перемещение на удаление?')) return
  try { await deleteGoodsTransfer(documentId.value); await router.push('/goods/transfers') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка удаления' }
}
async function loadMovements() {
  if (!documentId.value) return
  try { const response = await getGoodsTransferMovements(documentId.value); movements.value = response.data.inventory as typeof movements.value }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка загрузки движений' }
}
onMounted(async () => {
  try {
    const [org, wh, obj, person, mat, unit] = await Promise.all([
      listReferences('organizations', { page_size: 500 }), listReferences('warehouses', { page_size: 500 }),
      listReferences('objects', { page_size: 500 }), listReferences('persons', { page_size: 500 }),
      listReferences('materials', { page_size: 500 }), listUnits(),
    ])
    organizations.value = org.data as OrganizationRecord[]
    warehouses.value = wh.data as WarehouseRecord[]
    objects.value = obj.data as ObjectRecord[]
    persons.value = person.data as PersonRecord[]
    materials.value = (mat.data as MaterialRecord[]).filter((m) => !m.is_group)
    units.value = unit.data
    if (documentId.value) await loadDocument(documentId.value)
    else addLine()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка загрузки' }
})
</script>
