<template>
  <div class="page-shell">
    <section class="panel"><div class="panel-body">
      <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>
      <div class="form-grid doc-header-grid">
        <FormField label="Номер"><input v-model="form.number" class="input" placeholder="авто" /></FormField>
        <FormField label="Дата"><input v-model="form.date" class="input" type="date" /></FormField>
        <FormField label="Период"><input v-model="form.period" class="input" placeholder="YYYY-MM" /></FormField>
      </div>
      <div class="toolbar" style="margin-top: 1rem">
        <button class="button button-secondary" @click="addLine" :disabled="form.is_distributed">+ Строка</button>
        <button class="button button-secondary" :disabled="!isEdit || form.is_distributed" title="Импорт/экспорт строк" @click="dataExchangeOpen = true">⇄ Обмен данными</button>
        <button class="button button-primary" title="Сохранить" :disabled="form.is_distributed || saving" @click="save">💾</button>
        <span v-if="form.id" :class="['status-pill', form.is_distributed ? 'posted' : 'draft']">{{ form.is_distributed ? 'Распределены' : 'Не распределены' }}</span>
      </div>
      <table class="line-table" style="margin-top: 1rem" v-if="form.lines.length">
        <thead><tr><th>№</th><th>Статья затрат</th><th>Контрагент</th><th class="num">Сумма</th><th>Описание</th><th></th></tr></thead>
        <tbody>
          <tr v-for="(line, i) in form.lines" :key="i">
            <td>{{ i + 1 }}</td>
            <td class="picker-cell"><EntityPicker :model-value="line.cost_element_id ?? null" :selected-label="line.cost_element_name ?? null" title="Выбор статьи затрат" placeholder="Выберите" search-placeholder="Поиск…" empty-text="Не найдено" size="compact" :disabled="form.is_distributed" :load-page="loadCostElementPage" @update:model-value="(v) => { line.cost_element_id = v }" @change="(item) => { line.cost_element_name = item?.label ?? null }" /></td>
            <td class="picker-cell"><EntityPicker :model-value="line.counterparty_id ?? null" :selected-label="line.counterparty_name ?? null" title="Выбор контрагента" placeholder="Выберите" search-placeholder="Поиск…" empty-text="Не найдено" size="compact" :disabled="form.is_distributed" :load-page="loadCounterpartyPage" @update:model-value="(v) => { line.counterparty_id = v }" @change="(item) => { line.counterparty_name = item?.label ?? null }" /></td>
            <td><input v-model.number="line.sum" class="input input-sm" type="number" step="0.01" :disabled="form.is_distributed" /></td>
            <td><input v-model="line.description" class="input input-sm" :disabled="form.is_distributed" /></td>
            <td><button class="button button-secondary button-sm" :disabled="form.is_distributed" @click="form.lines.splice(i, 1)">✕</button></td>
          </tr>
        </tbody>
      </table>
    </div></section>
    <DocumentDataExchangeDialog v-if="form.id" :open="dataExchangeOpen" kind="overhead-expenses" :doc-id="form.id" title="Накладные расходы" @close="dataExchangeOpen = false" @imported="reload" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute, onBeforeRouteLeave, type NavigationGuard } from 'vue-router'
import FormField from '../../components/common/FormField.vue'
import EntityPicker from '../../components/common/EntityPicker.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { OverheadExpense, OverheadExpenseLine, CostElement } from '../../types/costAccounting'
import { getOverheadExpense, createOverheadExpense, updateOverheadExpense, listCostElements } from '../../api/costAccounting'
import { listReferences } from '../../api/references'
import type { Counterparty } from '../../types/models'

const props = defineProps<{ tabId?: string; id?: string }>()
const router = useRouter(); const route = useRoute()
const isEdit = computed(() => !!(props.id || route.params.id))
useHeaderBar(props.tabId, computed(() => isEdit.value ? 'Накладные расходы' : 'Новые накладные расходы'), ref([]))
const error = ref(''); const dataExchangeOpen = ref(false); const today = new Date().toISOString().slice(0, 10); const thisMonth = today.slice(0, 7)
const saving = ref(false)
const emptyLine = (): OverheadExpenseLine => ({ line_number: 0, cost_element_id: null, counterparty_id: null, sum: 0, description: '' })
const form = ref<OverheadExpense>({ number: '', date: today, period: thisMonth, lines: [emptyLine()] })

// Dirty-flag tracking
const savedSnapshot = ref('')
const isDirty = computed(() => JSON.stringify(form.value) !== savedSnapshot.value)
function markSaved() { savedSnapshot.value = JSON.stringify(form.value) }

function addLine() { form.value.lines.push(emptyLine()) }

// ── Load-page functions for EntityPicker ──
async function loadCostElementPage(params: { search: string; page: number; pageSize: number }) {
  const resp = await listCostElements()
  const filtered = (resp.data as CostElement[]).filter(e =>
    !params.search || e.name.toLowerCase().includes(params.search.toLowerCase())
  )
  const start = (params.page - 1) * params.pageSize
  const sliced = filtered.slice(start, start + params.pageSize)
  return {
    items: sliced.map(e => ({ id: e.id, label: e.name, caption: e.code })),
    pages: Math.ceil(filtered.length / params.pageSize) || 1,
  }
}
async function loadCounterpartyPage(params: { search: string; page: number; pageSize: number }) {
  const resp = await listReferences('counterparties', { page: params.page, page_size: Math.min(params.pageSize, 50), search: params.search })
  return { items: (resp.data as Counterparty[]).map(c => ({ id: c.id, label: c.name, caption: c.inn ?? null })), pages: resp.pagination?.pages ?? 1 }
}

async function save() {
  error.value = ''
  saving.value = true
  try {
    const payload = { ...form.value, lines: form.value.lines.map((l, i) => ({ ...l, line_number: i + 1 })) }
    const r = isEdit.value ? await updateOverheadExpense(+(props.id || route.params.id), payload) : await createOverheadExpense(payload)
    if (!isEdit.value) { form.value = r.data; markSaved(); router.push(`/documents/overhead-expenses/${r.data.id}`) } else { form.value = r.data; markSaved() }
  } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка сохранения' } finally { saving.value = false }
}

onBeforeRouteLeave((() => {
  if (isDirty.value && !window.confirm('Есть несохранённые изменения. Покинуть страницу?')) return false
  return true
}) as NavigationGuard)

onMounted(async () => { if (isEdit.value) { try { const r = await getOverheadExpense(+(props.id || route.params.id)); form.value = r.data; markSaved() } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } } else { markSaved() } })

async function reload() { if (isEdit.value) { try { const r = await getOverheadExpense(+(props.id || route.params.id)); form.value = r.data; markSaved() } catch {} } }
</script>
<style scoped>
.doc-header-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }
.line-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.line-table th, .line-table td { padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); text-align: left; }
.line-table th.num, .line-table td.num { text-align: right; }
.input-sm { width: 100%; padding: 0.25rem 0.4rem; font-size: 0.82rem; } .button-sm { padding: 0.2rem 0.5rem; font-size: 0.75rem; }
.picker-cell { min-width: 160px; }
</style>
