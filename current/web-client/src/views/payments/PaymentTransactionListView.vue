<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar search-row">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру, контрагенту" />
        </div>

        <ListCommandBar :state="state" :config="config" @open-settings="settingsOpen = true">
          <template #create>
            <button class="button button-primary" type="button" @click="showForm = !showForm">+ Платёж</button>
          </template>
        </ListCommandBar>

        <section v-if="showForm" class="panel inner-panel">
          <div class="panel-body">
            <h3>Новый платёж</h3>
            <div class="form-grid">
              <FormField label="Дата">
                <input v-model="newTx.date" class="input" type="date" />
              </FormField>
              <FormField label="Направление">
                <select v-model="newTx.direction" class="select">
                  <option value="incoming">Поступление</option>
                  <option value="outgoing">Платёж</option>
                </select>
              </FormField>
              <FormField label="Категория">
                <select v-model="newTx.category" class="select">
                  <option value="customer_stage">Этап заказчика</option>
                  <option value="payroll">Зарплата</option>
                  <option value="supplier">Поставщик</option>
                  <option value="tax">Налоги</option>
                  <option value="other">Прочее</option>
                </select>
              </FormField>
              <FormField label="Контрагент">
                <select v-model="newTx.counterparty_id" class="select">
                  <option value="">—</option>
                  <option v-for="item in counterparties" :key="item.id" :value="item.id">{{ item.name }}</option>
                </select>
              </FormField>
              <FormField label="Сумма">
                <input v-model.number="newTx.amount" class="input" type="number" step="0.01" min="0" />
              </FormField>
              <FormField label="Описание">
                <input v-model="newTx.description" class="input" type="text" />
              </FormField>
            </div>
            <div class="toolbar">
              <button class="button button-primary" type="button" @click="createTx">Создать</button>
              <button class="button button-secondary" type="button" @click="showForm = false">Отмена</button>
            </div>
          </div>
        </section>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <DataTable
          :columns="effectiveColumns"
          :rows="rows as Record<string, unknown>[]"
          :loading="loading"
          empty-text="Платежей пока нет"
          selectable
          :selected-ids="selectedIds"
          sortable
          :sort="sort"
          :filterable="filterRowVisible"
          :filters="filters"
          @update:selected-ids="selectedIds = $event"
          @row-contextmenu="(row, ev) => ctx.onContextMenu(row as DocListRow, ev)"
          @sort-change="onSortChange"
          @filter-change="onFilterChange"
        >
          <template #cell-number="{ row }">
            <strong>{{ (row as DocListRow).number }}</strong>
          </template>
          <template #cell-date="{ row }">{{ formatDate((row as DocListRow).date as string) }}</template>
          <template #cell-direction="{ row }">
            <span :class="['status-pill', (row as DocListRow).direction === 'incoming' ? 'posted' : 'draft']">
              {{ (row as DocListRow).direction === 'incoming' ? 'Поступление' : 'Платёж' }}
            </span>
          </template>
          <template #cell-amount="{ row }">
            {{ formatNumber((row as DocListRow).amount as number) }}
          </template>
          <template #cell-is_posted="{ row }">
            <span :class="['status-pill', (row as DocListRow).is_posted ? 'posted' : 'draft']">
              {{ (row as DocListRow).is_posted ? 'Проведён' : 'Черновик' }}
            </span>
          </template>
        </DataTable>

        <div class="toolbar pagination-row">
          <span class="muted">Страница {{ pagination.page }} из {{ pagination.pages }}. Всего: {{ pagination.total }}</span>
          <div class="table-actions">
            <button class="button button-secondary" type="button" :disabled="page <= 1" @click="page -= 1">Назад</button>
            <button class="button button-secondary" type="button" :disabled="page >= pagination.pages" @click="page += 1">Вперёд</button>
          </div>
        </div>
      </div>
    </section>

    <ListSettingsDialog
      :open="settingsOpen"
      :columns="config.columns"
      :states="settingsStates"
      @close="settingsOpen = false"
      @apply="onApplyColumns"
      @reset="onResetColumns"
    />
    <ContextMenu
      :open="ctx.menuOpen.value"
      :items="ctx.menuItems.value"
      :x="ctx.menuX.value"
      :y="ctx.menuY.value"
      @close="ctx.closeMenu()"
      @select="ctx.onSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import ContextMenu from '../../components/common/ContextMenu.vue'
import ListCommandBar from '../../components/documents/ListCommandBar.vue'
import ListSettingsDialog from '../../components/documents/ListSettingsDialog.vue'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { useDocumentList } from '../../composables/useDocumentList'
import { useDocumentListContextMenu } from '../../composables/useDocumentListContextMenu'
import { paymentTransactionListConfig } from '../../config/documentLists'
import { createPaymentTransaction } from '../../api/payments'
import { listReferences } from '../../api/references'
import type { Counterparty } from '../../types/models'
import type { DocListRow } from '../../config/documentListTypes'
import type { ColumnState } from '../../composables/useListSettings'

const props = defineProps<{ tabId?: string }>()
const config = paymentTransactionListConfig
const state = useDocumentList(config)
const ctx = useDocumentListContextMenu(config, state)

useHeaderBar(props.tabId, computed(() => config.title), computed(() => []))

const {
  rows, loading, error, search, page, pagination, selectedIds,
  sort, filters, filterRowVisible, effectiveColumns,
  onSortChange, onFilterChange,
} = state

const settingsOpen = ref(false)
const settingsStates = computed<ColumnState[]>(() => {
  const saved = state.settings.savedColumns.value
  return saved ?? config.columns.map((c) => ({ key: c.key, visible: c.defaultVisible !== false }))
})

function onApplyColumns(states: ColumnState[]) {
  void state.settings.saveColumns(states)
}
function onResetColumns() {
  void state.settings.resetColumns()
}

const showForm = ref(false)
const counterparties = ref<Counterparty[]>([])
const newTx = reactive({
  date: new Date().toISOString().slice(0, 10),
  direction: 'outgoing' as 'incoming' | 'outgoing',
  category: 'other' as 'customer_stage' | 'payroll' | 'supplier' | 'tax' | 'other',
  counterparty_id: '' as number | '',
  amount: 0,
  description: '',
})

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const [y, m, d] = value.split('-').map(Number)
  if (!y || !m || !d) return value
  return new Date(y, m - 1, d).toLocaleDateString('ru-RU')
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value ?? 0)
}

async function createTx() {
  try {
    await createPaymentTransaction({
      date: newTx.date,
      direction: newTx.direction,
      category: newTx.category,
      counterparty_id: newTx.counterparty_id || null,
      amount: newTx.amount,
      description: newTx.description || null,
    })
    showForm.value = false
    await state.loadItems()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка создания'
  }
}

onMounted(async () => {
  try {
    const cpRes = await listReferences('counterparties', { page_size: 100 })
    counterparties.value = cpRes.data as Counterparty[]
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки контрагентов'
  }
})
</script>

<style scoped>
.search-row { margin-bottom: 0.75rem; }
.pagination-row { justify-content: space-between; margin-top: 1rem; }
.inner-panel { margin-top: 1rem; }
</style>
