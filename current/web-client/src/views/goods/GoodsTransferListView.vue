<template>
  <div class="page-shell">
    <section class="panel"><div class="panel-body">
      <div class="toolbar">
        <input v-model="search" class="input toolbar-grow" type="search" placeholder="Номер, описание или склад" @input="load" />
        <RouterLink class="button button-primary" to="/goods/transfers/new">+ Перемещение</RouterLink>
      </div>
      <p v-if="error" class="message-banner message-error">{{ error }}</p>
      <DataTable :columns="columns" :rows="rows as Record<string, unknown>[]" :loading="loading" empty-text="Перемещений пока нет" @row-dblclick="openRow">
        <template #cell-number="{ row }">
          <RouterLink :to="`/goods/transfers/${(row as GoodsTransfer).id}`">{{ (row as GoodsTransfer).number }}</RouterLink>
        </template>
        <template #cell-is_posted="{ row }">{{ (row as GoodsTransfer).is_posted ? 'Проведён' : 'Черновик' }}</template>
      </DataTable>
      <div class="toolbar">
        <span class="muted">Страница {{ page }} из {{ pages }}. Всего {{ total }}</span>
        <div class="toolbar-grow"></div>
        <button class="button button-secondary" type="button" :disabled="page <= 1" @click="page--; load()">Назад</button>
        <button class="button button-secondary" type="button" :disabled="page >= pages" @click="page++; load()">Вперёд</button>
      </div>
    </div></section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from '../../components/common/DataTable.vue'
import { listGoodsTransfers } from '../../api/goods'
import { useHeaderBar } from '../../composables/useHeaderBar'
import { useWorkspaceStore } from '../../stores/workspace'
import type { GoodsTransfer } from '../../types/models'

const props = defineProps<{ tabId?: string }>()
const router = useRouter()
const workspace = useWorkspaceStore()
useHeaderBar(props.tabId, computed(() => 'Перемещения ТМЦ'), computed(() => []))
const rows = ref<GoodsTransfer[]>([])
const search = ref('')
const error = ref('')
const loading = ref(false)
const page = ref(1)
const pages = ref(1)
const total = ref(0)
const columns = [
  { key: 'date', label: 'Дата' }, { key: 'number', label: 'Номер' },
  { key: 'organization_name', label: 'Организация' },
  { key: 'source_warehouse_name', label: 'Склад-отправитель' },
  { key: 'destination_warehouse_name', label: 'Склад-получатель' },
  { key: 'line_count', label: 'Строк' }, { key: 'sum', label: 'Сумма' },
  { key: 'responsible_name', label: 'Ответственный' }, { key: 'is_posted', label: 'Статус' },
]
async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await listGoodsTransfers({ page: page.value, page_size: 20, search: search.value })
    rows.value = response.data
    pages.value = response.pagination?.pages ?? 1
    total.value = response.pagination?.total ?? 0
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}
function openRow(row: Record<string, unknown>) { void router.push(`/goods/transfers/${row.id}`) }
watch(() => workspace.activeId, (id, oldId) => { if (id === props.tabId && oldId !== id) void load() })
onMounted(load)
</script>
