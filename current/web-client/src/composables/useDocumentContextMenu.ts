import { computed, ref, type Ref } from 'vue'
import type { ContextMenuItem } from '../components/common/ContextMenu.vue'

export interface DocumentRow {
  id?: number | string
  is_posted?: boolean
  number?: string
}

interface UseContextMenuOptions<T extends DocumentRow> {
  onPost?: (row: T) => Promise<void>
  onUnpost?: (row: T) => Promise<void>
  onDelete: (row: T) => Promise<void>
  onRestore: (row: T) => Promise<void>
  hasPost?: boolean
}

export function useDocumentContextMenu<T extends DocumentRow>(opts: UseContextMenuOptions<T>) {
  const menuOpen = ref(false)
  const menuX = ref(0)
  const menuY = ref(0)
  const targetRow: Ref<T | null> = ref(null)

  function onContextMenu(row: T, event: MouseEvent) {
    targetRow.value = row
    menuX.value = event.clientX
    menuY.value = event.clientY
    menuOpen.value = true
  }

  function closeMenu() {
    menuOpen.value = false
    targetRow.value = null
  }

  const menuItems = computed<ContextMenuItem[]>(() => {
    const row = targetRow.value
    if (!row) return []
    const posted = !!row.is_posted
    const items: ContextMenuItem[] = []

    if (opts.hasPost !== false) {
      items.push({
        key: 'post',
        label: posted ? 'Отменить проведение' : 'Провести',
        icon: posted ? '\u2B1C' : '\u2714',
        disabled: false,
      })
    }
    items.push(
      {
        key: 'delete',
        label: 'Пометить на удаление',
        icon: '\u{1F5D1}',
        danger: true,
        disabled: posted,
      },
      {
        key: 'restore',
        label: 'Снять пометку на удаление',
        icon: '\u21A9',
        disabled: false,
      },
    )
    return items
  })

  async function onMenuSelect(key: string) {
    const row = targetRow.value
    if (!row) return
    try {
      switch (key) {
        case 'post':
          if (row.is_posted) await opts.onUnpost?.(row)
          else await opts.onPost?.(row)
          break
        case 'delete':
          await opts.onDelete(row)
          break
        case 'restore':
          await opts.onRestore(row)
          break
      }
    } finally {
      closeMenu()
    }
  }

  return {
    menuOpen,
    menuX,
    menuY,
    targetRow,
    onContextMenu,
    closeMenu,
    menuItems,
    onMenuSelect,
  }
}
