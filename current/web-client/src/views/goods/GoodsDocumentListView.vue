<template>
  <div class="page-shell">
    <section class="panel">
      <div class="panel-body">
        <div class="toolbar">
          <input v-model="search" class="input toolbar-grow" type="search" placeholder="Поиск по номеру, контрагенту" />
          <select v-model="statusFilter" class="select">
            <option :value="''">Все</option>
            <option value="true">Проведённые</option>
            <option value="false">Черновики</option>
          </select>
          <button class="button button-secondary" type="button" title="Обновить" @click="loadItems">↻</button>
          <button class="button button-primary" type="button" @click="router.push(`${basePath}/new`)">{{ isReceipt ? 'Создать поступление' : 'Создать списание' }}</button>
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
          empty-text="Документов пока нет"
          selectable
          :selected-ids="selectedIds"
          @update:selected-ids="selectedIds = $event"
          @row-dblclick="handleRowDblClick"
        >
          <template #cell-number="{ row }">
            <RouterLink class="document-list-link" :to="`${basePath}/${(row as unknown as GoodsDocument).id}`">
              <strong>{{ (row as unknown as GoodsDocument).number }}</strong>
            </RouterLink>
          </template>
          <template #cell-sum_with_vat="{ row }">{{ formatNumber((row as unknown as GoodsDocument).sum_with_vat) }}</template>
          <template #cell-is_posted="{ row }">
            <span :class="['status-pill', (row as unknown as GoodsDocument).is_posted ? 'posted' : 'draft']">
              {{ (row as unknown as GoodsDocument).is_posted ? 'Проведён' : 'Черновик' }}
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
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from '../../components/common/DataTable.vue'
import SelectionActionBar from '../../components/common/SelectionActionBar.vue'
import { deleteGoodsDocument, listGoodsDocuments, postGoodsDocument, unpostGoodsDocument } from '../../api/goods'
import { useAuthStore } from '../../stores/auth'
import { useHeaderBar } from '../../composables/useHeaderBar'
import type { HeaderAction } from '../../stores/headerBar'
import type { GoodsDocument, GoodsKind } from '../../types/models'

const props = withDefaults(defineProps<{ tabId?: string; kind?: GoodsKind }>(), { kind: 'receipt' })
const auth = useAuthStore()
const router = useRouter()

const isReceipt = computed(() => props.kind === 'receipt')
const basePath = computed(() => (isReceipt.value ? '/goods/receipts' : '/goods/issues'))
const title = computed(() => (isReceipt.value ? 'Поступления ТМЦ' : 'Списания ТМЦ'))

const headerActions = computed<HeaderAction[]>(() => [
  { key: 'create', icon: '+', title: isReceipt.value ? 'Создать поступление' : 'Создать списание', variant: 'primary', to: `${basePath.value}/new` },
])
useHeaderBar(props.tabId, title, headerActions)

const rows = ref<GoodsDocument[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const statusFilter = ref<'' | 'true' | 'false'>('')
const page = ref(1)
const pagination = ref({ page: 1, pages: 1, total: 0 })
const selectedIds = ref<string[]>([])
let searchTimer = 0

const columns = [
  { key: 'number', label: 'Номер' },
  { key: 'date', label: 'Дата' },
  { key: 'organization_name', label: 'Организация' },
  { key: 'counterparty_name', label: isReceipt.value ? 'Поставщик' : 'Покупатель' },
  { key: 'contract_number', label: 'Договор' },
  { key: 'object_name', label: 'Объект' },
  { key: 'sum_without_vat', label: 'Сумма без НДС' },
  { key: 'sum_with_vat', label: 'С НДС' },
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
  router.push(`${basePath.value}/${id}`)
}

function handleRowDblClick(row: Record<string, unknown>) {
  router.push(`${basePath.value}/${(row as unknown as GoodsDocument).id}`)
}

async function loadItems() {
  loading.value = true
  error.value = ''
  try {
    const isPosted = statusFilter.value === '' ? null : statusFilter.value === 'true'
    const response = await listGoodsDocuments(props.kind, {
      page: page.value,
      page_size: 20,
      search: search.value,
      is_posted: isPosted,
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
      if (mode === 'post') await postGoodsDocument(props.kind, Number(id))
      else await unpostGoodsDocument(props.kind, Number(id))
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось изменить статус для ${failed} документов`
  }
}

async function removeSelected() {
  if (!selectedIds.value.length) return
  const label = selectedIds.value.length === 1 ? 'документ' : `${selectedIds.value.length} документов`
  if (!window.confirm(`Пометить ${label} на удаление?`)) return

  error.value = ''
  let failed = 0
  for (const id of selectedIds.value) {
    try {
      await deleteGoodsDocument(props.kind, Number(id))
    } catch {
      failed++
    }
  }
  await loadItems()
  if (failed > 0) {
    error.value = `Не удалось удалить ${failed} документов`
  }
}

watch(page, loadItems)
watch(statusFilter, () => { page.value = 1; loadItems() })
watch(search, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => { page.value = 1; loadItems() }, 300)
})

onMounted(loadItems)
</script>

<style scoped>
.pagination-row { justify-content: space-between; margin-top: 1rem; }
</style>
