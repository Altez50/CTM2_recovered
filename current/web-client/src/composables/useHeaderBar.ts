import { onBeforeUnmount, watch, type Ref } from 'vue'
import { useHeaderBarStore, type HeaderAction } from '../stores/headerBar'

/**
 * Регистрирует заголовок и команды активного вида в глобальном хидере.
 *
 * Вызывается в setup вида; передаваемые реактивные title/actions
 * синхронизируются с реестром (по id таба), при размонтировании — удаляются.
 */
export function useHeaderBar(
  tabId: string | undefined,
  title: Ref<string>,
  actions: Ref<HeaderAction[]>,
) {
  const store = useHeaderBarStore()
  const id = tabId ?? '__no_tab__'

  watch(
    [title, actions],
    () => {
      store.setEntry(id, { title: title.value, actions: actions.value })
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    store.removeEntry(id)
  })
}
