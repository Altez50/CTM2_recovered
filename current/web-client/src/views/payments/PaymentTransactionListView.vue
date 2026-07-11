<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру, контрагенту" />
          <select v-model="filterDirection" class="select">
            <option value="">Все направления</option>
            <option value="incoming">Поступления</option>
            <option value="outgoing">Платежи</option>
          </select>
          <button class="button button-secondary" type="button" title="Обновить" @click="loadItems">↻</button>
          <button class="button button-primary" type="button" @click="showForm = !showForm">+ Платёж</button>
        </div>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <SelectionActionBar
          :selected-count="selectedIds.length"
          @deselect-all="selectedIds = []"
        >
          <button
            v-if="auth.isAdmin && canPostSelected"
            class="button button-secondary"
            type="button"
            title="Провести"
            @click="changePostingSelected('post')"
          >
            ✓
          </button>
          <button
            v-if="auth.isAdmin && canUnpostSelected"
            class="button button-secondary"
            type="button"
            title="Отменить проведение"
            @click="changePostingSelected('unpost')"
          >
            ↺
          </button>
          <button
            class="button button-danger"
            type="button"
            title="Удалить"
            @click="removeSelected"
          >
            ✕
          </button>
        </SelectionActionBar>

        <DataTable
          :columns="columns"
          :rows="rows as Record<string, unknown>[]"
          :loading="loading"
          empty-text="Платежей пока нет"
          selectable
          :selected-ids="selectedIds"
          @update:selected-ids="selectedIds = $event"
        >
          <template #cell-direction="{ row }">
            <span :class="['status-pill', (row as unknown as PaymentTransaction).direction === 'incoming' ? 'posted' : 'draft']">
              {{ (row as unknown as PaymentTransaction).direction === 'incoming' ? 'Поступление' : 'Платеж' }}
            </span>
          </template>
          <template #cell-amount="{ row }">
            {{ formatNumber((row as unknown as PaymentTransaction).amount) }}
          </template>
          <template #cell-is_posted="{ row }">
            <span :class="['status-pill', (row as unknown as PaymentTransaction).is_posted ? 'posted' : 'draft']">
              {{ (row as unknown as PaymentTransaction).is_posted ? 'Проведен' : 'Черновик' }}
            </span>
          </template>
        </DataTable>

        <div class="toolbar pagination-row">
          <span class="muted">Страница {{ pagination.page }} из {{ pagination.pages }}. Всего: {{ pagination.total }}</span>
          <div class="table-actions">
            <button class="button button-secondary" type="button" :disabled="page <= 1" @click="page -= 1">Назад</button>
            <button class="button button-secondary" type="button" :disabled="page >= pagination.pages" @click="page += 1">Вперед</button>
          </div>
        </div>

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
                  <option value="outgoing">Платеж</option>
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
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import DataTable from '../../components/common/DataTable.vue'
import FormField from '../../components/common/FormField.vue'
import SelectionActionBar from '../../components/common/SelectionActionBar.vue'
import {
  createPaymentTransaction,
  deletePaymentTransaction,
  listPaymentTransactions,
  postPaymentTransaction,
  unpostPaymentTransaction,
} from '../../api/payments'
import { listReferences } from '../../api/references'
import { useAuthStore } from '../../stores/auth'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import type { Counterparty, PaymentTransaction } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
const auth = useAuthStore()

useHeaderBar(props.tabId, computed(() => 'Платежи (факт)'), computed<HeaderAction[]>(() => []))

const rows = ref<PaymentTransaction[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const filterDirection = ref('')
const page = ref(1)
const pagination = ref({ page: 1, pages: 1, total: 0 })
const showForm = ref(false)
const counterparties = ref<Counterparty[]>([])
const selectedIds = ref<string[]>([])

const newTx = reactive({
  date: new Date().toISOString().slice(0, 10),
  direction: 'outgoing' as 'incoming' | 'outgoing',
  category: 'other' as 'customer_stage' | 'payroll' | 'supplier' | 'tax' | 'other',
  counterparty_id: '' as number | '',
  amount: 0,
  description: '',
})

const columns = [
  { key: 'number', label: 'Номер' },
  { key: 'date', label: 'Дата' },
  { key: 'direction', label: 'Направление' },
  { key: 'category', label: 'Категория' },
  { key: 'counterparty_name', label: 'Контрагент' },
  { key: 'amount', label: 'Сумма' },
  { key: 'is_posted', label: 'Статус' },
]

const canPostSelected = computed(() => {
  if (!selectedIds.value.length) return false
  return selectedIds.value.every((id) => {
    const row = rows.value.find((r) => String(r.id) === id)
    return row && !row.is_posted
  })
})

const canUnpostSelected = computed(() => {
  if (!selectedIds.value.length) return false
  return selectedIds.value.every((id) => {
    const row = rows.value.find((r) => String(r.id) === id)
    return row && row.is_posted
  })
})

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value || 0)
}

async function loadItems() {
  loading.value = true
  error.value = ''
  try {
    const response = await listPaymentTransactions({
      page: page.value,
      page_size: 20,
      search: search.value,
      direction: filterDirection.value,
    })
    rows.value = response.data
    pagination.value = {
      page: response.pagination?.page ?? 1,
      pages: response.pagination?.pages ?? 1,
      total: response.pagination?.total ?? 0,
    }
    selectedIds.value = []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

async function changePostingSelected(mode: 'post' | 'unpost') {
  if (!selectedIds.value.length) return
  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      if (mode === 'post') {
        await postPaymentTransaction(Number(id))
      } else {
        await unpostPaymentTransaction(Number(id))
      }
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось изменить статус для ${failed} платежей`
  }
}

async function removeSelected() {
  if (!selectedIds.value.length) return
  const label = selectedIds.value.length === 1 ? 'платёж' : `${selectedIds.value.length} платежей`
  if (!window.confirm(`Пометить ${label} на удаление?`)) return

  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      await deletePaymentTransaction(Number(id))
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось удалить ${failed} платежей`
  }
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
    newTx.amount = 0
    newTx.description = ''
    await loadItems()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка создания'
  }
}

watch(page, loadItems)
watch(search, () => {
  page.value = 1
  loadItems()
})
watch(filterDirection, () => {
  page.value = 1
  loadItems()
})

onMounted(async () => {
  try {
    const cpRes = await listReferences('counterparties', { page_size: 100 })
    counterparties.value = cpRes.data as Counterparty[]
    await loadItems()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  }
})
</script>

<style scoped>
.pagination-row {
  justify-content: space-between;
  margin-top: 1rem;
}
.inner-panel {
  margin-top: 1rem;
}
</style>
