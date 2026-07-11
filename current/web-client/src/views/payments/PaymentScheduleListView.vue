<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру, объекту, договору" />
          <button class="button button-primary" type="button" @click="router.push('/payments/schedules/new')">Создать календарь</button>
          <button class="button button-secondary" type="button" title="Обновить" @click="loadItems">↻</button>
        </div>

        <p v-if="error" class="page-subtitle" style="color: var(--danger)">{{ error }}</p>

        <SelectionActionBar
          :selected-count="selectedIds.length"
          @deselect-all="selectedIds = []"
        >
          <button
            v-if="selectedIds.length === 1"
            class="button button-secondary"
            type="button"
            @click="openItem(Number(selectedIds[0]))"
          >
            Открыть
          </button>
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
          empty-text="Календарей пока нет"
          selectable
          :selected-ids="selectedIds"
          @update:selected-ids="selectedIds = $event"
          @row-dblclick="handleRowDblClick"
        >
          <template #cell-number="{ row }">
            <RouterLink class="document-list-link" :to="`/payments/schedules/${(row as unknown as PaymentSchedule).id}`">
              <strong>{{ (row as unknown as PaymentSchedule).number }}</strong>
            </RouterLink>
          </template>
          <template #cell-total_incoming="{ row }">
            {{ formatNumber((row as unknown as PaymentSchedule).total_incoming) }}
          </template>
          <template #cell-total_outgoing="{ row }">
            {{ formatNumber((row as unknown as PaymentSchedule).total_outgoing) }}
          </template>
          <template #cell-is_posted="{ row }">
            <span :class="['status-pill', (row as unknown as PaymentSchedule).is_posted ? 'posted' : 'draft']">
              {{ (row as unknown as PaymentSchedule).is_posted ? 'Проведен' : 'Черновик' }}
            </span>
          </template>
        </DataTable>

        <div class="toolbar pagination-row">
          <span class="muted">
            Страница {{ pagination.page }} из {{ pagination.pages }}. Всего: {{ pagination.total }}
          </span>
          <div class="table-actions">
            <button class="button button-secondary" type="button" :disabled="page <= 1" @click="page -= 1">Назад</button>
            <button class="button button-secondary" type="button" :disabled="page >= pagination.pages" @click="page += 1">Вперед</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from '../../components/common/DataTable.vue'
import SelectionActionBar from '../../components/common/SelectionActionBar.vue'
import { deletePaymentSchedule, listPaymentSchedules, postPaymentSchedule, unpostPaymentSchedule } from '../../api/payments'
import { useAuthStore } from '../../stores/auth'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import type { PaymentSchedule } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
const auth = useAuthStore()
const router = useRouter()

const headerActions = computed<HeaderAction[]>(() => [
  { key: 'create', icon: '+', title: 'Создать календарь', variant: 'primary', to: '/payments/schedules/new' },
])
useHeaderBar(props.tabId, computed(() => 'Платёжные календари'), headerActions)

const rows = ref<PaymentSchedule[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const page = ref(1)
const pagination = ref({ page: 1, pages: 1, total: 0 })
const selectedIds = ref<string[]>([])
let searchTimer = 0

const columns = [
  { key: 'number', label: 'Номер' },
  { key: 'date_from', label: 'Период с' },
  { key: 'date_to', label: 'Период по' },
  { key: 'object_name', label: 'Объект' },
  { key: 'contract_number', label: 'Договор' },
  { key: 'total_incoming', label: 'Поступления' },
  { key: 'total_outgoing', label: 'Платежи' },
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

function openItem(id: number) {
  router.push(`/payments/schedules/${id}`)
}

function handleRowDblClick(row: Record<string, unknown>) {
  router.push(`/payments/schedules/${(row as unknown as PaymentSchedule).id}`)
}

async function loadItems() {
  loading.value = true
  error.value = ''
  try {
    const response = await listPaymentSchedules({
      page: page.value,
      page_size: 20,
      search: search.value,
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
        await postPaymentSchedule(Number(id))
      } else {
        await unpostPaymentSchedule(Number(id))
      }
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось изменить статус для ${failed} календарей`
  }
}

async function removeSelected() {
  if (!selectedIds.value.length) return
  const label = selectedIds.value.length === 1 ? 'календарь' : `${selectedIds.value.length} календарей`
  if (!window.confirm(`Пометить ${label} на удаление?`)) return

  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      await deletePaymentSchedule(Number(id))
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось удалить ${failed} календарей`
  }
}

watch(page, loadItems)
watch(search, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    loadItems()
  }, 300)
})

onMounted(loadItems)
</script>

<style scoped>
.pagination-row {
  justify-content: space-between;
  margin-top: 1rem;
}
</style>
