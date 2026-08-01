/**
 * Контекстное меню строки списка документов (DOCUMENT_LIST_SPEC.md, раздел 3.4.4 / 5.2.4).
 * Построение пунктов с подменю «Ввести на основании» и диспетчер команд.
 */
import { computed, ref } from 'vue'
import type { ContextMenuItem } from '../components/common/ContextMenu.vue'
import type { DocListConfig, DocListRow } from '../config/documentListTypes'
import type { DocumentListState } from './useDocumentList'

export function useDocumentListContextMenu(config: DocListConfig, state: DocumentListState) {
  const menuOpen = ref(false)
  const menuX = ref(0)
  const menuY = ref(0)
  const targetRow = ref<DocListRow | null>(null)

  const menuItems = computed<ContextMenuItem[]>(() => {
    const row = targetRow.value
    if (!row) return []
    const items: ContextMenuItem[] = [
      { key: 'open', label: 'Открыть', icon: '▢' },
    ]
    if (config.api.copy) items.push({ key: 'copy', label: 'Копировать', icon: '⧉' })
    items.push({ type: 'separator' })

    if (config.hasPost !== false) {
      const canManage = state.canManagePosting(row)
      const posted = config.postedWhen ? config.postedWhen(row) : !!row.is_posted
      if (posted) {
        items.push({ key: 'toggle-post', label: 'Отменить проведение', icon: '⊘', disabled: !canManage || !!row.marked_for_deletion })
      } else {
        items.push({ key: 'toggle-post', label: 'Провести', icon: '✓', disabled: !canManage || !!row.marked_for_deletion })
      }
    }

    const deletable = config.canDeleteWhen ? config.canDeleteWhen(row) : !row.is_posted

    if (row.marked_for_deletion) {
      items.push({ key: 'restore', label: 'Снять пометку на удаление', icon: '↺' })
    } else {
      items.push({
        key: 'delete',
        label: 'Пометить на удаление',
        icon: '✕',
        danger: true,
        disabled: !deletable,
      })
    }

    if (config.baseOn?.length) {
      items.push({ type: 'separator' })
      items.push({
        key: 'based_on',
        label: 'Ввести на основании',
        icon: '⤵',
        disabled: false,
        submenu: config.baseOn.map((t) => ({ key: t.kind, label: t.label })),
      })
    }

    return items
  })

  function onContextMenu(row: DocListRow, event: MouseEvent) {
    targetRow.value = row
    menuX.value = event.clientX
    menuY.value = event.clientY
    // ПКМ по строке — выделяем её (поведение тонкого клиента).
    const id = String(row.id ?? '')
    if (id && !state.selectedIds.value.includes(id)) {
      state.selectedIds.value = [id]
    }
    menuOpen.value = true
  }

  function closeMenu() {
    menuOpen.value = false
  }

  function onSelect(key: string) {
    const row = targetRow.value
    if (!row || row.id == null) {
      closeMenu()
      return
    }
    const id = row.id as number
    if (key === 'open') state.openItem(id)
    else if (key === 'copy') void state.copyItem(id)
    else if (key === 'toggle-post') {
      const posted = config.postedWhen ? config.postedWhen(row) : !!row.is_posted
      void (posted ? state.unpostOne(id) : state.postOne(id))
    } else if (key === 'delete') void state.removeOne(id)
    else if (key === 'restore') void state.restoreOne(id)
    else if (key.startsWith('based_on/')) {
      const kind = key.slice('based_on/'.length)
      state.openBaseOn(kind)
    }
    closeMenu()
  }

  return { menuOpen, menuX, menuY, targetRow, menuItems, onContextMenu, closeMenu, onSelect }
}
