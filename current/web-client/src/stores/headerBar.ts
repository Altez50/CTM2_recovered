import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { useWorkspaceStore } from './workspace'

export type HeaderActionVariant = 'neutral' | 'primary' | 'success' | 'warning' | 'danger'

/**
 * Описание одной кнопки глобального тулбара хидера.
 * Либо навигационная (to), либо командная (onClick).
 */
export interface HeaderAction {
  key: string
  icon: string
  title: string
  variant?: HeaderActionVariant
  disabled?: boolean
  onClick?: () => void
  to?: RouteLocationRaw
}

export interface HeaderEntry {
  title: string
  actions: HeaderAction[]
}

/**
 * Реестр заголовков и команд форм, ключом является id таба.
 *
 * MDI-клиент держит все открытые виды смонтированными (v-show), поэтому
 * простая «последняя запись» не работает: нужен слот на каждый таб.
 * Хидер читает entry активного таба и рендерит его заголовок и тулбар.
 */
export const useHeaderBarStore = defineStore('headerBar', () => {
  const entries = ref<Record<string, HeaderEntry>>({})
  const workspace = useWorkspaceStore()

  function setEntry(id: string, entry: HeaderEntry) {
    entries.value[id] = entry
  }

  function removeEntry(id: string) {
    delete entries.value[id]
  }

  const activeEntry = computed<HeaderEntry | null>(() => {
    const id = workspace.activeId
    if (!id) return null
    return entries.value[id] ?? null
  })

  return { entries, setEntry, removeEntry, activeEntry }
})
