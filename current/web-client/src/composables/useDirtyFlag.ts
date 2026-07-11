import { onBeforeUnmount, watch, type Ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'

/**
 * Связывает состояние «грязности» формы с активным табом рабочего пространства.
 *
 * Использование:
 *
 *   const isDirty = ref(false)
 *   useDirtyFlag(isDirty)
 *
 *   // либо:
 *   const form = reactive({ ... })
 *   useDirtyFlag(() => hasUnsavedChanges(form))
 *
 * При изменении флага композабл проставляет dirty=true/false активному табу,
 * что блокирует закрытие без подтверждения и помечает таб точкой в шапке.
 */
export function useDirtyFlag(source: Ref<boolean> | (() => boolean)): void {
  const workspace = useWorkspaceStore()

  function resolve(): boolean {
    return typeof source === 'function' ? source() : source.value
  }

  function sync() {
    const tab = workspace.activeTab
    if (!tab) return
    workspace.markDirty(tab.id, resolve())
  }

  if (typeof source === 'function') {
    // Геттер-режим: пересчитываем по watch на store.activeId и периодически
    // нецелесообразно — используем явный API. Вызываем на ключевых хуках.
    watch(() => workspace.activeId, sync, { immediate: true })
  } else {
    watch(source, sync, { immediate: true })
    watch(() => workspace.activeId, sync)
  }

  onBeforeUnmount(() => {
    // При размонтировании формы считаем её сохранённой (компонент закрыт корректно).
    const tab = workspace.activeTab
    if (tab) {
      workspace.markDirty(tab.id, false)
    }
  })
}
