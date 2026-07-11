<template>
  <div class="page-shell">
    <section class="panel"><div class="panel-body">
      <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>
      <div class="form-grid doc-header-grid">
        <FormField label="Номер"><input v-model="form.number" class="input" placeholder="авто" :disabled="form.is_posted" /></FormField>
        <FormField label="Дата"><input v-model="form.date" class="input" type="date" :disabled="form.is_posted" /></FormField>
        <FormField label="Объект">
          <EntityPicker
            :model-value="form.object_id ?? null"
            :selected-label="form.object_name ?? null"
            title="Выбор объекта" description="Найдите и выберите объект строительства."
            placeholder="Выберите объект" search-placeholder="Поиск по названию…"
            empty-text="Объекты не найдены" size="full"
            :disabled="form.is_posted"
            :load-page="loadObjectPage"
            @update:model-value="(v) => { form.object_id = v }"
            @change="(item) => { form.object_name = item?.label ?? null }"
          />
        </FormField>
        <FormField label="Смета">
          <EntityPicker
            :model-value="form.estimate_id ?? null"
            :selected-label="form.estimate_number ?? null"
            title="Выбор сметы" description="Найдите и выберите смету."
            placeholder="Выберите смету" search-placeholder="Поиск по номеру…"
            empty-text="Сметы не найдены" size="full"
            :disabled="form.is_posted"
            :load-page="loadEstimatePage"
            @update:model-value="(v) => { form.estimate_id = v }"
            @change="(item) => { form.estimate_number = item?.label ?? null }"
          />
        </FormField>
        <FormField label="Прораб">
          <EntityPicker
            :model-value="form.foreman_id ?? null"
            :selected-label="form.foreman_name ?? null"
            title="Выбор прораба" description="Найдите и выберите сотрудника."
            placeholder="Выберите прораба" search-placeholder="Поиск по ФИО…"
            empty-text="Сотрудники не найдены" size="full"
            :disabled="form.is_posted"
            :load-page="loadPersonPage"
            @update:model-value="(v) => { form.foreman_id = v }"
            @change="(item) => { form.foreman_name = item?.label ?? null }"
          />
        </FormField>
        <FormField label="Склад"><input v-model="form.warehouse" class="input" :disabled="form.is_posted" /></FormField>
      </div>
      <div class="toolbar" style="margin-top: 1rem">
        <button class="button button-secondary" @click="addLine" :disabled="form.is_posted">+ Строка</button>
        <button class="button button-primary" title="Сохранить" @click="save">💾</button>
        <button v-if="isEdit && !form.is_posted" class="button button-success" title="Провести" @click="post">✓</button>
        <button v-if="isEdit && form.is_posted" class="button button-warning" title="Отменить проведение" @click="unpost">↺</button>
        <span v-if="form.id" :class="['status-pill', form.is_posted ? 'posted' : 'draft']">{{ form.is_posted ? 'Проведен' : 'Черновик' }}</span>
      </div>
      <table class="line-table" style="margin-top: 1rem" v-if="form.lines.length">
        <thead><tr><th>№</th><th>Работа</th><th>Материал</th><th class="num">Лимит</th><th class="num">Списано</th><th class="num">Цена</th><th class="num">Сумма</th><th></th></tr></thead>
        <tbody>
          <tr v-for="(line, i) in form.lines" :key="i">
            <td>{{ i + 1 }}</td>
            <td class="picker-cell"><WorkPicker :model-value="line.work_id ?? null" :selected-label="line.work_name ?? null" compact @update:model-value="(v) => { line.work_id = v }" @change="(w) => { line.work_name = w?.name ?? null }" /></td>
            <td class="picker-cell"><EntityPicker :model-value="line.material_id ?? null" :selected-label="line.material_name ?? null" title="Выбор материала" placeholder="Выберите" search-placeholder="Поиск…" empty-text="Не найдено" size="compact" :disabled="form.is_posted" edit-kind="materials" :load-page="loadMaterialPage" @update:model-value="(v) => { line.material_id = v }" @change="(item) => { line.material_name = item?.label ?? null; if (item?.meta?.price) { line.price = item.meta.price as number; calcLine(line) } }" /></td>
            <td class="num">{{ line.planned_quantity }}</td>
            <td><input v-model.number="line.actual_quantity" class="input input-sm" type="number" step="0.01" :disabled="form.is_posted" /></td>
            <td><input v-model.number="line.price" class="input input-sm" type="number" step="0.01" :disabled="form.is_posted" @change="calcLine(line)" /></td>
            <td class="num">{{ (line.actual_quantity * line.price).toFixed(2) }}</td>
            <td><button class="button button-secondary button-sm" @click="form.lines.splice(i, 1)" :disabled="form.is_posted">✕</button></td>
          </tr>
        </tbody>
      </table>
    </div></section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import FormField from '../../components/common/FormField.vue'
import EntityPicker from '../../components/common/EntityPicker.vue'
import WorkPicker from '../../components/common/WorkPicker.vue'
import type { PickerItem } from '../../components/common/EntityPicker.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { MaterialConsumption, MaterialConsumptionLine } from '../../types/costAccounting'
import { getMaterialConsumption, createMaterialConsumption, updateMaterialConsumption, postMaterialConsumption, unpostMaterialConsumption } from '../../api/costAccounting'
import { listReferences } from '../../api/references'
import { listEstimates } from '../../api/documents'
import type { Estimate } from '../../types/models'
import type { ObjectRecord, PersonRecord, MaterialRecord } from '../../types/models'

const props = defineProps<{ tabId?: string; id?: string }>()
const router = useRouter(); const route = useRoute()
const isEdit = computed(() => !!props.id || !!route.params.id)
useHeaderBar(props.tabId, computed(() => isEdit.value ? 'Расход материалов' : 'Новый расход материалов'), ref([]))

const error = ref('')
const today = new Date().toISOString().slice(0, 10)

const emptyLine = (): MaterialConsumptionLine => ({ line_number: 0, work_id: null, material_id: null, planned_quantity: 0, actual_quantity: 0, price: 0, sum: 0, cost_element_id: null })

const form = ref<MaterialConsumption>({ number: '', date: today, object_id: null, estimate_id: null, foreman_id: null, warehouse: '', lines: [emptyLine()] })

function calcLine(line: MaterialConsumptionLine) { line.sum = +(line.actual_quantity * line.price).toFixed(2) }
function addLine() { form.value.lines.push(emptyLine()) }

// ── Load-page functions for EntityPicker ──
async function loadObjectPage(params: { search: string; page: number; pageSize: number }) {
  const resp = await listReferences('objects', { page: params.page, page_size: Math.min(params.pageSize, 50), search: params.search })
  return { items: (resp.data as ObjectRecord[]).map(o => ({ id: o.id, label: o.name, caption: o.address ?? null })), pages: resp.pagination?.pages ?? 1 }
}
async function loadEstimatePage(params: { search: string; page: number; pageSize: number }) {
  const resp = await listEstimates({ page: params.page, page_size: Math.min(params.pageSize, 50), search: params.search, sort_order: 'desc' })
  return { items: (resp.data as Estimate[]).map(e => ({ id: e.id ?? 0, label: e.number, caption: e.object_name ?? null })), pages: resp.pagination?.pages ?? 1 }
}
async function loadPersonPage(params: { search: string; page: number; pageSize: number }) {
  const resp = await listReferences('persons', { page: params.page, page_size: Math.min(params.pageSize, 50), search: params.search })
  return { items: (resp.data as PersonRecord[]).map(p => ({ id: p.id, label: p.full_name ?? '', caption: p.position ?? null })), pages: resp.pagination?.pages ?? 1 }
}
async function loadMaterialPage(params: { search: string; page: number; pageSize: number }) {
  const resp = await listReferences('materials', { page: params.page, page_size: Math.min(params.pageSize, 50), search: params.search })
  return { items: (resp.data as MaterialRecord[]).map(m => ({ id: m.id, label: m.name, caption: m.unit_name ?? null, meta: { price: m.price ?? 0 } })), pages: resp.pagination?.pages ?? 1 }
}

async function save() {
  error.value = ''
  try {
    const payload = { ...form.value, lines: form.value.lines.map((l, i) => ({ ...l, line_number: i + 1, sum: +(l.actual_quantity * l.price).toFixed(2) })) }
    const r = isEdit.value ? await updateMaterialConsumption(+(props.id || route.params.id), payload) : await createMaterialConsumption(payload)
    if (!isEdit.value) router.push(`/documents/material-consumptions/${r.data.id}`)
    else form.value = r.data
  } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка сохранения' }
}

async function post() { try { await postMaterialConsumption(form.value.id!); form.value.is_posted = true } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка проведения' } }
async function unpost() { try { await unpostMaterialConsumption(form.value.id!); form.value.is_posted = false } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка отмены' } }

onMounted(async () => {
  if (isEdit.value) { try { const r = await getMaterialConsumption(+(props.id || route.params.id)); form.value = r.data } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } }
})
</script>

<style scoped>
.doc-header-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }
.line-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.line-table th, .line-table td { padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); text-align: left; }
.line-table th.num, .line-table td.num { text-align: right; }
.input-sm { width: 100%; padding: 0.25rem 0.4rem; font-size: 0.82rem; }
.button-sm { padding: 0.2rem 0.5rem; font-size: 0.75rem; }
.button-success { background: var(--success, #16a34a); color: #fff; }
.button-warning { background: var(--warning, #f59e0b); color: #fff; }
.picker-cell { min-width: 160px; }
</style>
