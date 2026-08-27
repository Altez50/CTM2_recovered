/**
 * Composable для Регистра работ (WORKS_REGISTRY_SPEC.md).
 *
 * Управляет состоянием списка: серверная загрузка с сортировкой и фильтрами,
 * цикл сортировки по клику на заголовок, быстрый отбор по колонкам,
 * интеграция с user_settings для сохранения состава колонок и сортировки,
 * экспорт в CSV/XLSX.
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { queryWorkExecution, buildExportUrl, type RegisterQuery } from '../api/registers'
import type { WorkExecutionItem } from '../types/models'
import { useListSettings, type ColumnState, type SortSetting } from './useListSettings'
import type { DocListColumn } from '../config/documentListTypes'

export type RegisterColumn = DocListColumn

export interface SortState {
  key: string
  order: 'asc' | 'desc' | null
}

/** Маппинг ключей колонок → f_* параметры для быстрого отбора. */
const FILTER_KEY_MAP: Record<string, string> = {
  customer_name: 'f_customer_id',
  contract_number: 'f_contract_id',
  object_name: 'f_object_id',
  estimate_number: 'f_estimate_id',
  work_name: 'f_work_id',
  recorder: 'f_recorder',
  period: 'f_period_from',
}

export function useWorksRegister(formName: string, defaultColumns: RegisterColumn[]) {
  const rows = ref<WorkExecutionItem[]>([])
  const loading = ref(false)
  const error = ref('')
  const page = ref(1)
  const pagination = reactive({ page: 1, pages: 1, total: 0, page_size: 50 })

  const sort = ref<SortState>({ key: 'period', order: 'desc' })
  const quickFilters = reactive<Record<string, string>>({})

  const totals = reactive({
    quantity_income: 0,
    quantity_expense: 0,
    sum_income: 0,
    sum_expense: 0,
    balance_quantity: 0,
    balance_sum: 0,
  })

  // Формные фильтры (верхняя панель)
  const formFilters = reactive({
    period_from: '',
    period_to: '',
    object_id: '' as number | '',
    estimate_id: '' as number | '',
    work_id: '' as number | '',
    customer_id: '' as number | '',
    contract_id: '' as number | '',
    group_by: '',
  })

  // Сохраняемые настройки (колонки + сортировка)
  const settings = useListSettings(formName, defaultColumns, { key: 'period', order: 'desc' })

  const effectiveColumns = computed(() => settings.effectiveColumns.value as RegisterColumn[])

  /** Сборка параметров запроса. */
  function buildQuery(): RegisterQuery {
    const params: RegisterQuery = {
      page: page.value,
      page_size: pagination.page_size,
      period_from: formFilters.period_from || undefined,
      period_to: formFilters.period_to || undefined,
      object_id: formFilters.object_id || undefined,
      estimate_id: formFilters.estimate_id || undefined,
      work_id: formFilters.work_id || undefined,
      customer_id: formFilters.customer_id || undefined,
      contract_id: formFilters.contract_id || undefined,
      group_by: formFilters.group_by || undefined,
    }
    if (sort.value.order) {
      params.sort_by = sort.value.key
      params.sort_order = sort.value.order
    }
    // Быстрый отбор
    for (const [colKey, value] of Object.entries(quickFilters)) {
      if (!value) continue
      const fKey = FILTER_KEY_MAP[colKey] || `f_${colKey}`
      params[fKey] = value
    }
    return params
  }

  async function loadItems() {
    loading.value = true
    error.value = ''
    try {
      const response = await queryWorkExecution(buildQuery())
      rows.value = response.data.items
      const t = response.data.totals
      totals.quantity_income = t.quantity_income
      totals.quantity_expense = t.quantity_expense
      totals.sum_income = t.sum_income
      totals.sum_expense = t.sum_expense
      totals.balance_quantity = t.balance_quantity
      totals.balance_sum = t.balance_sum
      if (response.pagination) {
        pagination.page = response.pagination.page
        pagination.pages = response.pagination.pages
        pagination.total = response.pagination.total
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Не удалось загрузить регистр'
    } finally {
      loading.value = false
    }
  }

  /** Цикл сортировки: asc → desc → null → asc. */
  function onSortChange(key: string) {
    if (sort.value.key !== key) {
      sort.value = { key, order: 'asc' }
    } else if (sort.value.order === 'asc') {
      sort.value = { key, order: 'desc' }
    } else if (sort.value.order === 'desc') {
      sort.value = { key: 'period', order: 'desc' }
    } else {
      sort.value = { key, order: 'asc' }
    }
    settings.saveSort({ key: sort.value.key, order: sort.value.order ?? 'desc' })
    page.value = 1
    loadItems()
  }

  function onFilterChange(colKey: string, value: string) {
    quickFilters[colKey] = value
    page.value = 1
    loadItems()
  }

  function resetQuickFilters() {
    for (const key of Object.keys(quickFilters)) {
      quickFilters[key] = ''
    }
    page.value = 1
    loadItems()
  }

  function applyFormFilters() {
    page.value = 1
    loadItems()
  }

  function exportData(format: 'csv' | 'xlsx') {
    const params = buildQuery()
    // При экспорте сбрасываем пагинацию
    params.page = 1
    params.page_size = 100000
    const url = buildExportUrl(params, format)
    const token = localStorage.getItem('access_token')
    // Открываем с заголовком авторизации через fetch
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then(r => {
        if (!r.ok) throw new Error('Экспорт не удался')
        return r.blob()
      })
      .then(blob => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = format === 'csv' ? 'Регистр_работ.csv' : 'Регистр_работ.xls'
        a.click()
        URL.revokeObjectURL(a.href)
      })
      .catch(e => { error.value = e.message })
  }

  function goToPage(p: number) {
    if (p < 1 || p > pagination.pages) return
    page.value = p
    loadItems()
  }

  onMounted(async () => {
    await settings.reload()
    // Восстанавливаем сортировку из настроек
    const saved = settings.effectiveSort.value
    if (saved?.key) {
      sort.value = saved as SortState
    }
    await loadItems()
  })

  return {
    rows,
    loading,
    error,
    page,
    pagination,
    sort,
    quickFilters,
    totals,
    formFilters,
    effectiveColumns,
    settings,
    loadItems,
    onSortChange,
    onFilterChange,
    resetQuickFilters,
    applyFormFilters,
    exportData,
    goToPage,
  }
}
