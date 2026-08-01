/**
 * Загрузка/сохранение настроек списка пользователя (состав колонок, сортировка).
 * См. DOCUMENT_LIST_SPEC.md, разделы 3.3.5, 4.3, 6.
 *
 * Хранилище — user_settings (ключи `columns`, `sort`). Значения — строковый JSON.
 * Новые колонки конфига, отсутствующие в сохранённых настройках, добавляются в конец
 * видимыми (раздел 3.3.5, п.5).
 */
import { computed, onMounted, ref } from 'vue'
import { getUserSettings, putUserSettings, deleteUserSetting } from '../api/system'
import type { DocListColumn } from '../config/documentListTypes'

export interface ColumnState {
  key: string
  visible: boolean
}

export interface SortSetting {
  key: string
  order: 'asc' | 'desc'
}

export function useListSettings(
  formName: string,
  configColumns: DocListColumn[],
  defaultSort: SortSetting,
) {
  const savedColumns = ref<ColumnState[] | null>(null)
  const savedSort = ref<SortSetting | null>(null)
  const loaded = ref(false)
  let saveTimer = 0

  async function load() {
    try {
      const res = await getUserSettings(formName)
      const raw = res.data ?? {}
      if (raw.columns) {
        try {
          savedColumns.value = JSON.parse(raw.columns)
        } catch {
          savedColumns.value = null
        }
      }
      if (raw.sort) {
        try {
          savedSort.value = JSON.parse(raw.sort)
        } catch {
          savedSort.value = null
        }
      }
    } catch {
      // Настройки могли не сохраняться (например, нет прав) — используем умолчания.
    }
    loaded.value = true
  }

  /** Эффективные колонки с runtime-видимостью и порядком из настроек. */
  const effectiveColumns = computed<DocListColumn[]>(() => {
    const map = new Map(configColumns.map((c) => [c.key, { ...c }]))
    const result: DocListColumn[] = []
    if (savedColumns.value) {
      for (const cs of savedColumns.value) {
        const col = map.get(cs.key)
        if (col) {
          result.push({ ...col, visible: cs.visible })
          map.delete(cs.key)
        }
      }
    }
    // Оставшиеся колонки конфига (новые) — в конец, видимыми по умолчанию.
    for (const col of map.values()) {
      result.push({ ...col, visible: col.defaultVisible !== false })
    }
    return result
  })

  const effectiveSort = computed<SortSetting>(() => savedSort.value ?? defaultSort)

  function schedulePersist(payload: Record<string, string>) {
    window.clearTimeout(saveTimer)
    saveTimer = window.setTimeout(() => {
      void putUserSettings(formName, payload)
    }, 400)
  }

  async function saveColumns(states: ColumnState[]) {
    savedColumns.value = states
    schedulePersist({ columns: JSON.stringify(states) })
  }

  async function saveSort(sort: SortSetting) {
    savedSort.value = sort
    schedulePersist({ sort: JSON.stringify(sort) })
  }

  async function resetColumns() {
    savedColumns.value = null
    try {
      await deleteUserSetting(formName, 'columns')
    } catch {
      /* ignore */
    }
  }

  onMounted(load)

  return {
    loaded,
    effectiveColumns,
    effectiveSort,
    savedColumns,
    savedSort,
    saveColumns,
    saveSort,
    resetColumns,
    reload: load,
  }
}
