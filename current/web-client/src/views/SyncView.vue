<template>
  <div class="page-shell">
    <section v-if="status" class="panel">
      <div class="panel-body">
        <h2 class="page-title">Синхронизация</h2>
        <p class="page-subtitle">Обмен бизнес-объектами между базами по UUID и временным меткам.</p>

        <div class="sync-grid">
          <div class="sync-field">
            <div class="sync-field-label">Локальный узел</div>
            <div class="sync-field-value">
              <strong>{{ status.local_node.code }}</strong>
              <span class="muted"> · {{ status.local_node.name }}</span>
            </div>
          </div>
          <div class="sync-field">
            <div class="sync-field-label">Версия схемы</div>
            <div class="sync-field-value"><code>{{ status.schema_version }}</code></div>
          </div>
          <div class="sync-field">
            <div class="sync-field-label">Изменений в очереди</div>
            <div class="sync-field-value">{{ status.pending_changes }}</div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="error" class="panel">
      <div class="panel-body">
        <strong style="color: var(--danger)">Не удалось загрузить статус.</strong>
        <p class="page-subtitle">{{ error }}</p>
      </div>
    </section>

    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <h3 class="section-title">Удалённые узлы</h3>
          <button class="button button-secondary" type="button" title="Обновить" :disabled="loading" @click="loadStatus">
            ↻
          </button>
        </div>

        <div v-if="status && status.nodes.length" class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Код</th>
                <th>Название</th>
                <th class="num">Получено до</th>
                <th class="num">Отправлено до</th>
                <th>Последний приём</th>
                <th>Последняя отправка</th>
                <th class="actions-col"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="node in status.nodes" :key="node.id">
                <td><strong>{{ node.code }}</strong></td>
                <td>{{ node.name }}</td>
                <td class="num">{{ node.received_packet_no }}</td>
                <td class="num">{{ node.sent_packet_no }}</td>
                <td>{{ formatTimestamp(node.last_sync_in) }}</td>
                <td>{{ formatTimestamp(node.last_sync_out) }}</td>
                <td class="actions-col">
                  <button
                    class="button button-primary button-sm"
                    type="button"
                    :disabled="exchangingNodeId === node.id"
                    @click="runExchange(node)"
                  >
                    {{ exchangingNodeId === node.id ? 'Обмен…' : 'Обмен' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="page-subtitle muted">Зарегистрированных удалённых узлов нет.</p>
      </div>
    </section>

    <section class="panel">
      <div class="panel-body">
        <h3 class="section-title">Регистрация удалённого узла</h3>
        <p class="page-subtitle">
          Код удалённой базы обычно соответствует имени файла её БД, например <code>OFFICE-01</code>.
        </p>
        <form class="sync-form" @submit.prevent="submitRegister">
          <input v-model="registerCode" class="input" placeholder="Код узла (например OFFICE-01)" required />
          <input v-model="registerName" class="input" placeholder="Название узла" required />
          <button class="button button-primary" type="submit" :disabled="registering">
            {{ registering ? 'Регистрация…' : 'Зарегистрировать' }}
          </button>
        </form>
        <p v-if="registerError" class="page-subtitle" style="color: var(--danger)">{{ registerError }}</p>
      </div>
    </section>

    <section v-if="conflicts.length || conflictsLoaded" class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <h3 class="section-title">Конфликты ({{ conflicts.length }})</h3>
          <button class="button button-secondary button-sm" type="button" title="Обновить" :disabled="conflictsLoading" @click="loadConflicts">
            ↻
          </button>
        </div>
        <p v-if="conflictsLoaded && !conflicts.length" class="page-subtitle muted">Неразрешённых конфликтов нет.</p>
        <div v-if="conflicts.length" class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Тип</th>
                <th>Документ</th>
                <th>Локальная метка</th>
                <th>Удалённая метка</th>
                <th>Исход</th>
                <th>Поступило</th>
                <th class="actions-col"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="conflict in conflicts" :key="conflict.id">
                <td><strong>{{ entityTypeLabel(conflict.entity_type) }}</strong></td>
                <td>
                  <div>{{ entityDocumentLabel(conflict) }}</div>
                  <code class="muted" :title="conflict.entity_uuid">{{ conflict.entity_uuid?.slice(0, 8) }}…</code>
                </td>
                <td>{{ formatTimestamp(conflict.local_updated_at) }}</td>
                <td>{{ formatTimestamp(conflict.remote_updated_at) }}</td>
                <td>
                  <span class="badge" :class="resolutionBadgeClass(conflict)">{{ resolutionLabel(conflict) }}</span>
                </td>
                <td>{{ formatTimestamp(conflict.arrival_time) }}</td>
                <td class="actions-col">
                  <button
                    class="button button-danger button-sm"
                    type="button"
                    :disabled="resolvingId === conflict.id"
                    @click="confirmResolve(conflict)"
                  >
                    {{ resolvingId === conflict.id ? '…' : 'Применить удалённую' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="conflictError" class="page-subtitle" style="color: var(--danger)">{{ conflictError }}</p>
      </div>
    </section>

    <section v-if="lastExchange" class="panel">
      <div class="panel-body">
        <h3 class="section-title">Результат последнего обмена</h3>
        <div class="sync-grid">
          <div class="sync-field">
            <div class="sync-field-label">Принято</div>
            <div class="sync-field-value">{{ lastExchange.processed_count }}</div>
          </div>
          <div class="sync-field">
            <div class="sync-field-label">Пропущено</div>
            <div class="sync-field-value">{{ lastExchange.skipped_count }}</div>
          </div>
          <div class="sync-field">
            <div class="sync-field-label">Ошибок</div>
            <div class="sync-field-value" :class="{ 'danger-text': lastExchange.error_count > 0 }">
              {{ lastExchange.error_count }}
            </div>
          </div>
          <div class="sync-field">
            <div class="sync-field-label">Отправлено</div>
            <div class="sync-field-value">{{ lastExchange.outgoing_count }}</div>
          </div>
        </div>

        <details v-if="lastExchange.conflicts.length" class="sync-details" open>
          <summary>Конфликты ({{ lastExchange.conflicts.length }})</summary>
          <ul class="sync-list">
            <li v-for="(conflict, idx) in lastExchange.conflicts" :key="idx">
              <strong>{{ entityTypeLabel(conflict.entity_type) }}</strong>
              <code>{{ conflict.entity_uuid?.slice(0, 8) }}…</code>
              <span class="badge" :class="resolutionBadgeClass(conflict)">{{ resolutionLabel(conflict) }}</span>
              <div class="muted sync-ts">
                локальная: {{ formatTimestamp(conflict.local_updated_at) }}
                · удалённая: {{ formatTimestamp(conflict.remote_updated_at) }}
              </div>
            </li>
          </ul>
        </details>

        <details v-if="lastExchange.errors.length" class="sync-details" open>
          <summary>Ошибки применения ({{ lastExchange.errors.length }})</summary>
          <ul class="sync-list">
            <li v-for="(errLine, idx) in lastExchange.errors" :key="idx">{{ errLine }}</li>
          </ul>
        </details>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { exchangeSync, fetchSyncConflicts, fetchSyncStatus, registerSyncNode, resolveSyncConflict } from '../api/sync'
import { useHeaderBar } from '../composables/useHeaderBar'
import type { HeaderAction } from '../stores/headerBar'
import type { SyncConflictRecord, SyncExchangeResponse, SyncNodeInfo, SyncStatusResponse } from '../types/models'

const props = defineProps<{ tabId?: string }>()

const headerActions = computed<HeaderAction[]>(() => [
  { key: 'refresh', icon: '↻', title: 'Обновить статус', variant: 'primary', onClick: () => loadStatus() },
])
useHeaderBar(props.tabId, computed(() => 'Синхронизация'), headerActions)

const status = ref<SyncStatusResponse | null>(null)
const loading = ref(false)
const error = ref('')

const registerCode = ref('')
const registerName = ref('')
const registering = ref(false)
const registerError = ref('')

const exchangingNodeId = ref<string | null>(null)

const conflicts = ref<SyncConflictRecord[]>([])
const conflictsLoaded = ref(false)
const conflictsLoading = ref(false)
const conflictError = ref('')
const resolvingId = ref<string | null>(null)
const lastExchange = ref<SyncExchangeResponse | null>(null)

async function loadStatus() {
  loading.value = true
  error.value = ''
  try {
    status.value = await fetchSyncStatus()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

async function submitRegister() {
  registering.value = true
  registerError.value = ''
  try {
    await registerSyncNode(registerCode.value.trim(), registerName.value.trim())
    registerCode.value = ''
    registerName.value = ''
    await loadStatus()
  } catch (err) {
    registerError.value = err instanceof Error ? err.message : 'Ошибка регистрации'
  } finally {
    registering.value = false
  }
}

async function runExchange(node: SyncNodeInfo) {
  if (!status.value) {
    return
  }
  exchangingNodeId.value = node.id
  try {
    // Manual exchange: send no incoming changes, just pull outgoing using the
    // node's last received cursor (sent_packet_no on this base).
    const response = await exchangeSync({
      schema_version: status.value.schema_version,
      node_id: node.id,
      node_code: node.code,
      node_name: node.name,
      last_received_change_id: node.sent_packet_no,
      batch_size: 100,
      changes: [],
    })
    lastExchange.value = response
    await loadStatus()
  } catch (err) {
    lastExchange.value = null
    error.value = err instanceof Error ? err.message : 'Ошибка обмена'
  } finally {
    exchangingNodeId.value = null
  }
}

function formatTimestamp(value?: string | null) {
  if (!value) {
    return '—'
  }
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      dateStyle: 'short',
      timeStyle: 'medium',
    }).format(new Date(value))
  } catch {
    return value
  }
}

const ENTITY_TYPE_LABELS: Record<string, string> = {
  estimates: 'Смета',
  daily_reports: 'Наряд',
  timesheets: 'Табель',
  works: 'Работа',
  materials: 'Материал',
  units: 'Ед. изм.',
  persons: 'Физ. лицо',
  counterparties: 'Контрагент',
  objects: 'Объект',
  organizations: 'Организация',
}

function entityTypeLabel(entityType: string): string {
  return ENTITY_TYPE_LABELS[entityType] ?? entityType
}

// Человекочитаемый идентификатор конфликтующего документа, выводится из payload.
// Для документов — номер + дата, для справочников — имя/код.
function entityDocumentLabel(conflict: SyncConflictRecord): string {
  const payload = conflict.payload ?? {}
  const get = (key: string): string | undefined => {
    const value = payload[key]
    return typeof value === 'string' && value.trim() ? value.trim() : undefined
  }
  switch (conflict.entity_type) {
    case 'estimates':
    case 'daily_reports':
    case 'timesheets':
      return [get('number'), get('date') || get('month_year')].filter(Boolean).join(' от ') || '—'
    case 'works':
      return [get('code'), get('name')].filter(Boolean).join(' · ') || '—'
    case 'materials':
    case 'units':
    case 'persons':
    case 'counterparties':
    case 'objects':
    case 'organizations':
      return get('name') || get('full_name') || get('code') || '—'
    default:
      return '—'
  }
}

// Перевод внутренних кодов исхода конфликта в читаемый вид.
function resolutionLabel(conflict: SyncConflictRecord): string {
  const raw = conflict.conflict_resolution || conflict.resolution || ''
  if (!raw) return '—'
  if (raw === 'local-wins') return 'Локальная новее'
  if (raw === 'remote-wins-manual') return 'Применена удалённая'
  if (raw === 'PENDING' || raw === 'pending') return 'Ожидает'
  return raw
}

// CSS-класс бейджа исхода конфликта.
function resolutionBadgeClass(conflict: SyncConflictRecord): string {
  const raw = conflict.conflict_resolution || conflict.resolution || ''
  if (raw === 'remote-wins-manual') return 'badge-ok'
  if (raw === 'local-wins') return 'badge-warn'
  return 'badge-muted'
}

async function loadConflicts() {
  conflictsLoading.value = true
  conflictError.value = ''
  try {
    const response = await fetchSyncConflicts()
    conflicts.value = response.conflicts
  } catch (err) {
    conflictError.value = err instanceof Error ? err.message : 'Ошибка загрузки конфликтов'
  } finally {
    // Mark as loaded even on failure so the conflicts panel stays visible —
    // otherwise the whole section (including the error message) is hidden by
    // the v-if="conflicts.length || conflictsLoaded" guard and the user sees
    // neither the conflicts nor the reason they failed to load.
    conflictsLoaded.value = true
    conflictsLoading.value = false
  }
}

async function confirmResolve(conflict: SyncConflictRecord) {
  if (!conflict.id) {
    return
  }
  const ok = window.confirm(
    `Применить удалённую версию для ${conflict.entity_type}?\nЛокальные данные будут перезаписаны.`,
  )
  if (!ok) {
    return
  }
  resolvingId.value = conflict.id
  try {
    await resolveSyncConflict(conflict.id)
    await loadConflicts()
  } catch (err) {
    conflictError.value = err instanceof Error ? err.message : 'Ошибка разрешения конфликта'
  } finally {
    resolvingId.value = null
  }
}

onMounted(() => {
  loadStatus()
  loadConflicts()
})
</script>

<style scoped>
.sync-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.sync-field-label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.sync-field-value {
  margin-top: 0.25rem;
  font-size: 1.05rem;
}

.section-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
}

.table-wrap {
  margin-top: 0.75rem;
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}

.data-table th,
.data-table td {
  padding: 0.6rem 0.7rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.data-table th {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.data-table td.num,
.data-table th.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.actions-col {
  text-align: right;
  white-space: nowrap;
}

.button-sm {
  padding: 0.3rem 0.7rem;
  font-size: 0.82rem;
}

.sync-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.75rem;
}

.sync-form .input {
  flex: 1 1 14rem;
}

.sync-details {
  margin-top: 0.9rem;
}

.sync-list {
  margin: 0.5rem 0 0;
  padding-left: 1.2rem;
  display: grid;
  gap: 0.3rem;
  font-size: 0.9rem;
}

.danger-text {
  color: var(--danger);
}

.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
}

.badge-warn {
  background: var(--warning-bg, rgba(200, 130, 0, 0.15));
  color: var(--warning-fg, #8a5a00);
}

.badge-ok {
  background: var(--success-bg, rgba(40, 140, 60, 0.15));
  color: var(--success-fg, #1f6b34);
}

.badge-muted {
  background: rgba(0, 0, 0, 0.06);
  color: var(--text-soft);
}

.sync-ts {
  margin-top: 0.2rem;
  font-size: 0.82rem;
}

code {
  padding: 0.1rem 0.35rem;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.05);
  font-size: 0.85em;
}
</style>
