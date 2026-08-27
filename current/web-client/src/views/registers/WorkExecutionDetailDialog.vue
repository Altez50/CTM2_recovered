<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @click="$emit('close')">
      <div class="modal panel detail-modal" role="dialog" aria-modal="true" @click.stop>
        <header class="modal-header">
          <h2 class="modal-title">Детализация движений</h2>
          <button class="button button-secondary" type="button" @click="$emit('close')">✕</button>
        </header>

        <div v-if="parentRow" class="detail-context">
          <span v-if="parentRow.object_name" class="ctx-chip">Объект: {{ parentRow.object_name }}</span>
          <span v-if="parentRow.estimate_number" class="ctx-chip">Смета: {{ parentRow.estimate_number }}</span>
          <span v-if="parentRow.work_name" class="ctx-chip">Работа: {{ parentRow.work_name }}</span>
        </div>

        <div class="modal-body">
          <div v-if="loading" class="loading-state">Загрузка…</div>
          <table v-else-if="movements.length" class="detail-table">
            <thead>
              <tr>
                <th>Период</th>
                <th>Регистратор</th>
                <th>Приход кол-во</th>
                <th>Расход кол-во</th>
                <th>Приход сумма</th>
                <th>Расход сумма</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="m in movements"
                :key="`${m.recorder_type}-${m.recorder_id}-${m.line_number}`"
                class="detail-row"
                @dblclick="openDocument(m)"
              >
                <td>{{ m.period }}</td>
                <td>
                  <RouterLink v-if="m.recorder_type === 'estimate'" :to="`/documents/estimates/${m.recorder_id}`" class="doc-link">
                    Смета {{ m.recorder_number || `#${m.recorder_id}` }}
                  </RouterLink>
                  <RouterLink v-else-if="m.recorder_type === 'daily_report'" :to="`/documents/daily-reports/${m.recorder_id}`" class="doc-link">
                    Рапорт {{ m.recorder_number || `#${m.recorder_id}` }}
                  </RouterLink>
                  <span v-else>—</span>
                </td>
                <td class="num">{{ fmt(m.quantity_income) }}</td>
                <td class="num">{{ fmt(m.quantity_expense) }}</td>
                <td class="num">{{ fmt(m.sum_income) }}</td>
                <td class="num">{{ fmt(m.sum_expense) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">Нет движений</div>
        </div>

        <footer class="modal-footer">
          <button class="button button-secondary" type="button" @click="$emit('close')">Закрыть</button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { queryWorkExecution } from '../../api/registers'
import type { WorkExecutionItem } from '../../types/models'

const props = defineProps<{
  open: boolean
  parentRow: WorkExecutionItem | null
  periodFrom?: string
  periodTo?: string
}>()

const emit = defineEmits<{ close: [] }>()

const movements = ref<WorkExecutionItem[]>([])
const loading = ref(false)

function fmt(v: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v || 0)
}

function openDocument(m: WorkExecutionItem) {
  if (m.recorder_type === 'estimate') {
    window.location.hash = `#/documents/estimates/${m.recorder_id}`
  } else if (m.recorder_type === 'daily_report') {
    window.location.hash = `#/documents/daily-reports/${m.recorder_id}`
  }
}

async function loadMovements() {
  if (!props.parentRow) return
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: 1,
      page_size: 200,
      period_from: props.periodFrom || undefined,
      period_to: props.periodTo || undefined,
    }
    if (props.parentRow.object_id) params.object_id = props.parentRow.object_id
    if (props.parentRow.estimate_id) params.estimate_id = props.parentRow.estimate_id
    if (props.parentRow.work_id) params.work_id = props.parentRow.work_id
    if (props.parentRow.customer_id) params.customer_id = props.parentRow.customer_id
    if (props.parentRow.contract_id) params.contract_id = props.parentRow.contract_id
    const res = await queryWorkExecution(params)
    movements.value = res.data.items
  } catch {
    movements.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.open, (val) => {
  if (val) loadMovements()
})
</script>

<style scoped>
.detail-modal {
  max-width: 900px;
  width: 90vw;
}

.detail-context {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid var(--border, #e0d6cc);
}

.ctx-chip {
  background: var(--hover-bg, rgba(0, 0, 0, 0.05));
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
}

.modal-body {
  max-height: 60vh;
  overflow: auto;
  padding: 0;
}

.detail-table {
  width: 100%;
  border-collapse: collapse;
}

.detail-table th {
  position: sticky;
  top: 0;
  background: var(--panel-bg, #f5f0eb);
  padding: 0.4rem 0.6rem;
  text-align: left;
  font-size: 0.8rem;
  font-weight: 600;
  border-bottom: 1px solid var(--border, #e0d6cc);
}

.detail-table td {
  padding: 0.35rem 0.6rem;
  font-size: 0.85rem;
  border-bottom: 1px solid var(--border-light, #eee);
}

.detail-row {
  cursor: pointer;
}

.detail-row:hover {
  background: var(--hover-bg, rgba(0, 0, 0, 0.03));
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.doc-link {
  color: var(--primary, #b24c2d);
  text-decoration: none;
  font-weight: 600;
}

.doc-link:hover {
  text-decoration: underline;
}

.loading-state,
.empty-state {
  padding: 2rem;
  text-align: center;
  color: var(--text-soft, #888);
}
</style>
