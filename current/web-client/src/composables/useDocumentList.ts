/**
 * Единый механизм списка документов (DOCUMENT_LIST_SPEC.md, раздел 5.2).
 *
 * Состояние (rows/loading/error/search/page/pagination/selectedIds/sort/filters),
 * серверная загрузка с сортировкой и быстрым отбором, команды над выделенным
 * (провести/отменить/пометить на удаление/восстановить/копировать/открыть),
 * «Ввод на основании». Вид-страница передаёт только конфиг и слоты ячеек.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useListSettings } from './useListSettings'
import type { DocListConfig, DocListRow } from '../config/documentListTypes'

export type DocumentListState = ReturnType<typeof useDocumentList>

export function useDocumentList(config: DocListConfig) {
  const router = useRouter()
  const auth = useAuthStore()

  const settings = useListSettings(config.formName, config.columns, config.defaultSort)

  const rows = ref<DocListRow[]>([])
  const loading = ref(false)
  const error = ref('')
  const search = ref('')
  const page = ref(1)
  const pagination = ref({ page: 1, pages: 1, total: 0 })
  const selectedIds = ref<string[]>([])

  const sort = ref<{ key: string | null; order: 'asc' | 'desc' | null }>({
    key: config.defaultSort.key,
    order: config.defaultSort.order,
  })
  const filters = ref<Record<string, string>>({})
  const filterRowVisible = ref(false)

  let searchTimer = 0
  let filterTimer = 0
  let userTouchedSort = false

  // Применяем сохранённую пользователем сортировку после загрузки настроек
  // (только если пользователь ещё не менял сортировку кликом).
  watch(
    () => settings.loaded.value,
    (ready) => {
      if (ready && !userTouchedSort) {
        const s = settings.effectiveSort.value
        sort.value = { key: s.key, order: s.order }
        void loadItems()
      }
    },
  )

  function buildQuery(): Record<string, string | number | undefined> {
    const query: Record<string, string | number | undefined> = {
      page: page.value,
      page_size: 20,
      search: search.value || undefined,
      sort_by: sort.value.key ?? undefined,
      sort_order: sort.value.order ?? undefined,
    }
    for (const [key, value] of Object.entries(filters.value)) {
      if (value) query[`f_${key}`] = value
    }
    const extra = config.extraQuery?.() ?? {}
    return { ...query, ...extra }
  }

  async function loadItems() {
    loading.value = true
    error.value = ''
    try {
      const response = await config.api.list(buildQuery())
      rows.value = (response.data ?? []) as DocListRow[]
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

  function onSortChange(key: string) {
    userTouchedSort = true
    let next: { key: string | null; order: 'asc' | 'desc' | null }
    if (sort.value.key !== key) {
      next = { key, order: 'asc' }
    } else if (sort.value.order === 'asc') {
      next = { key, order: 'desc' }
    } else if (sort.value.order === 'desc') {
      next = { key: null, order: null } // цикл: снять сортировку
    } else {
      next = { key, order: 'asc' }
    }
    sort.value = next
    page.value = 1
    // Сохраняем сортировку: при сбросе — умолчание конфига.
    const toSave = next.key && next.order ? { key: next.key, order: next.order } : config.defaultSort
    void settings.saveSort(toSave)
    void loadItems()
  }

  function onFilterChange(key: string, value: string) {
    const next = { ...filters.value }
    if (value) next[key] = value
    else delete next[key]
    filters.value = next
    page.value = 1
    window.clearTimeout(filterTimer)
    filterTimer = window.setTimeout(loadItems, 300)
  }

  function clearFilters() {
    filters.value = {}
    page.value = 1
    void loadItems()
  }

  function toggleFilterRow() {
    filterRowVisible.value = !filterRowVisible.value
  }

  // ── Выделение и права ──────────────────────────────────────────────────
  function rowById(id: string | number): DocListRow | undefined {
    return rows.value.find((r) => String(r.id) === String(id))
  }

  function canManagePosting(row: DocListRow): boolean {
    if (config.hasPost === false) return false
    if (config.canManagePosting) return config.canManagePosting(auth.user, row)
    return auth.isAdmin
  }

  function isPostable(row: DocListRow): boolean {
    if (config.postableWhen) return config.postableWhen(row)
    return !row.is_posted
  }

  function isPosted(row: DocListRow): boolean {
    if (config.postedWhen) return config.postedWhen(row)
    return !!row.is_posted
  }

  function isDeletable(row: DocListRow): boolean {
    if (config.canDeleteWhen) return config.canDeleteWhen(row)
    return !row.is_posted
  }

  const canOpen = config.canOpen !== false

  const selectionCount = computed(() => selectedIds.value.length)
  const hasSelection = computed(() => selectionCount.value > 0)
  const singleRow = computed<DocListRow | null>(() =>
    selectedIds.value.length === 1 ? rowById(selectedIds.value[0]) ?? null : null,
  )

  const canPostSelected = computed(() => {
    if (!hasSelection.value) return false
    return selectedIds.value.every((id) => {
      const row = rowById(id)
      return row && isPostable(row) && !row.marked_for_deletion && canManagePosting(row)
    })
  })

  const canUnpostSelected = computed(() => {
    if (!hasSelection.value) return false
    return selectedIds.value.every((id) => {
      const row = rowById(id)
      return row && isPosted(row) && !row.marked_for_deletion && canManagePosting(row)
    })
  })

  const canDeleteSelected = computed(() =>
    hasSelection.value && selectedIds.value.every((id) => {
      const row = rowById(id)
      return row && isDeletable(row)
    }),
  )

  const canBaseOn = computed(() => canOpen && selectedIds.value.length === 1 && !!config.baseOn?.length)

  // ── Команды ────────────────────────────────────────────────────────────
  function openItem(id: number | string) {
    if (!canOpen) return
    void router.push(config.itemRoute(id))
  }

  function openSelected() {
    if (!canOpen) return
    if (singleRow.value) openItem(singleRow.value.id as number)
  }

  async function copyItem(id: number | string) {
    if (!config.api.copy) return
    try {
      const response = await config.api.copy(Number(id))
      void router.push(config.itemRoute(response.data.id))
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Не удалось скопировать'
    }
  }

  function copySelected() {
    if (singleRow.value) void copyItem(singleRow.value.id as number)
  }

  // Однострочные операции (контекстное меню) — без подтверждения, обратимы.
  async function postOne(id: number | string) {
    error.value = ''
    try {
      await config.api.post?.(Number(id))
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Ошибка проведения'
    }
    await loadItems()
  }

  async function unpostOne(id: number | string) {
    error.value = ''
    try {
      await config.api.unpost?.(Number(id))
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Ошибка отмены проведения'
    }
    await loadItems()
  }

  async function removeOne(id: number | string) {
    error.value = ''
    try {
      await config.api.remove?.(Number(id))
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Не удалось пометить на удаление'
    }
    await loadItems()
  }

  async function restoreOne(id: number | string) {
    error.value = ''
    try {
      await config.api.restore?.(Number(id))
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Не удалось восстановить'
    }
    await loadItems()
  }

  async function changePostingSelected(mode: 'post' | 'unpost') {
    if (!selectedIds.value.length) return
    error.value = ''
    let failed = 0
    for (const id of selectedIds.value) {
      try {
        if (mode === 'post') await config.api.post?.(Number(id))
        else await config.api.unpost?.(Number(id))
      } catch {
        failed++
      }
    }
    await loadItems()
    if (failed > 0) {
      error.value = `Не удалось изменить статус для ${failed} из ${selectedIds.value.length + failed} ${config.labels.many}`
    }
  }

  function postSelected() {
    void changePostingSelected('post')
  }

  function unpostSelected() {
    void changePostingSelected('unpost')
  }

  async function removeSelected() {
    if (!selectedIds.value.length) return
    const count = selectedIds.value.length
    const label = count === 1 ? config.labels.one : `${count} ${config.labels.few}`
    if (!window.confirm(`Пометить ${label} на удаление?`)) return
    error.value = ''
    let failed = 0
    for (const id of selectedIds.value) {
      try {
        await config.api.remove?.(Number(id))
      } catch {
        failed++
      }
    }
    await loadItems()
    if (failed > 0) {
      error.value = `Не удалось удалить ${failed} из ${count + failed} ${config.labels.many}`
    }
  }

  async function restoreSelected() {
    if (!selectedIds.value.length) return
    error.value = ''
    let failed = 0
    for (const id of selectedIds.value) {
      try {
        await config.api.restore?.(Number(id))
      } catch {
        failed++
      }
    }
    await loadItems()
    if (failed > 0) {
      error.value = `Не удалось восстановить ${failed} из ${selectedIds.value.length + failed} ${config.labels.many}`
    }
  }

  // ── Ввод на основании (раздел 3.6) ─────────────────────────────────────
  function openBaseOn(targetKind: string) {
    const row = singleRow.value
    if (!row) return
    const target = config.baseOn?.find((t) => t.kind === targetKind)
    if (!target) return
    void router.push({
      path: target.createRoute,
      query: {
        based_on_type: config.formName,
        based_on_id: String(row.id ?? ''),
        based_on_number: row.number ?? '',
      },
    })
  }

  watch(page, () => void loadItems())
  watch(search, () => {
    window.clearTimeout(searchTimer)
    searchTimer = window.setTimeout(() => {
      page.value = 1
      void loadItems()
    }, 300)
  })

  return {
    // настройки
    settings,
    effectiveColumns: settings.effectiveColumns,
    // состояние
    rows,
    loading,
    error,
    search,
    page,
    pagination,
    selectedIds,
    sort,
    filters,
    filterRowVisible,
    // computed
    selectionCount,
    hasSelection,
    singleRow,
    canPostSelected,
    canUnpostSelected,
    canDeleteSelected,
    canBaseOn,
    canOpen,
    canManagePosting,
    // действия
    loadItems,
    onSortChange,
    onFilterChange,
    clearFilters,
    toggleFilterRow,
    openItem,
    openSelected,
    copyItem,
    copySelected,
    postOne,
    unpostOne,
    removeOne,
    restoreOne,
    postSelected,
    unpostSelected,
    removeSelected,
    restoreSelected,
    openBaseOn,
  }
}
