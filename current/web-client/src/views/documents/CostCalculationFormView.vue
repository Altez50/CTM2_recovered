<template>
  <div class="page-shell">
    <section class="panel"><div class="panel-body">
      <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>
      <div class="form-grid doc-header-grid">
        <FormField label="Номер"><input v-model="form.number" class="input" placeholder="авто" /></FormField>
        <FormField label="Дата"><input v-model="form.date" class="input" type="date" /></FormField>
        <FormField label="Период"><input v-model="form.period" class="input" placeholder="YYYY-MM" /></FormField>
        <FormField label="Объект (0=все)"><input v-model.number="form.object_id" class="input" type="number" min="0" /></FormField>
      </div>
      <div class="toolbar" style="margin-top: 1rem">
        <button class="button button-primary" title="Сохранить" @click="save">💾</button>
        <button v-if="form.id && form.status === 'draft'" class="button button-success" title="Рассчитать" @click="calculate">▶</button>
        <button v-if="form.status === 'calculated'" class="button button-success" title="Провести" @click="post">✓</button>
        <button v-if="form.status === 'posted'" class="button button-warning" title="Отменить проведение" @click="unpost">↺</button>
        <span :class="['status-pill', statusClass(form.status || 'draft')]">{{ statusLabel(form.status || 'draft') }}</span>
      </div>
      <p v-if="result" style="margin-top: 1rem">
        Рассчитано записей: <strong>{{ result.record_count }}</strong>. Статус: <strong>{{ result.status }}</strong>
      </p>
    </div></section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import FormField from '../../components/common/FormField.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { CostCalculation } from '../../types/costAccounting'
import { getCostCalculation, createCostCalculation, calculateCost, postCostCalculation, unpostCostCalculation } from '../../api/costAccounting'

const props = defineProps<{ tabId?: string; id?: string }>()
const router = useRouter(); const route = useRoute()
const isEdit = computed(() => !!(props.id || route.params.id))
useHeaderBar(props.tabId, computed(() => isEdit.value ? 'Расчёт себестоимости' : 'Новый расчёт себестоимости'), ref([]))
const error = ref(''); const today = new Date().toISOString().slice(0, 10); const thisMonth = today.slice(0, 7)
const form = ref<CostCalculation>({ number: '', period: thisMonth, date: today, object_id: 0, status: 'draft' })
const result = ref<{ record_count: number; status: string } | null>(null)

function statusClass(s: string) { return s === 'posted' ? 'posted' : s === 'calculated' ? 'success' : 'draft' }
function statusLabel(s: string) { return s === 'posted' ? 'Проведен' : s === 'calculated' ? 'Рассчитан' : 'Черновик' }

async function save() {
  error.value = ''
  try {
    const r = isEdit.value ? null : await createCostCalculation(form.value)
    if (r) { form.value = r.data; router.push(`/documents/cost-calculations/${r.data.id}`) }
  } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка сохранения' }
}
async function calculate() { try { const r = await calculateCost(form.value.id!); result.value = r.data; form.value.status = 'calculated' } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка расчёта' } }
async function post() { try { await postCostCalculation(form.value.id!); form.value.status = 'posted' } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка' } }
async function unpost() { if (!window.confirm('Отменить проведение?')) return; try { await unpostCostCalculation(form.value.id!); form.value.status = 'draft'; result.value = null } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка' } }

onMounted(async () => { if (isEdit.value) { try { const r = await getCostCalculation(+(props.id || route.params.id)); form.value = r.data } catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' } } })
</script>
<style scoped>
.doc-header-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }
.button-success { background: var(--success, #16a34a); color: #fff; } .button-warning { background: var(--warning, #f59e0b); color: #fff; }
.status-pill.success { background: rgba(34, 197, 94, 0.12); color: var(--success, #16a34a); }
</style>
