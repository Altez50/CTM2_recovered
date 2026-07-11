<template>
  <div :class="['workspace-tabs', { compact }]">
    <div ref="scrollerRef" class="tabs-scroller">
      <button
        v-for="tab in workspace.tabs"
        :key="tab.id"
        :ref="(el) => setTabRef(tab.id, el as HTMLElement | null)"
        :class="['tab', { active: tab.id === workspace.activeId, dirty: tab.dirty }]"
        type="button"
        :title="tab.title"
        @click="onActivate(tab.id)"
        @auxclick="onAuxClick(tab.id, $event)"
        @middle-click.prevent="onMiddleClick(tab.id)"
      >
        <span class="tab-label">{{ tab.title }}</span>
        <span v-if="tab.dirty" class="tab-dirty-marker" aria-hidden="true">●</span>
        <span
          v-if="tab.closable"
          class="tab-close"
          role="button"
          tabindex="-1"
          :title="`Закрыть «${tab.title}»`"
          @click.stop="onClose(tab.id)"
          @keydown.enter.stop="onClose(tab.id)"
        >
          <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
            <path d="M2 2 L10 10 M10 2 L2 10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none" />
          </svg>
        </span>
      </button>
    </div>

    <button
      v-if="workspace.count > 1"
      class="tabs-overflow"
      type="button"
      title="Действия со вкладками"
      @click="toggleMenu"
    >
      ⋯
      <div v-if="menuOpen" class="tabs-menu panel" @click.stop>
        <button class="tabs-menu-item" type="button" :disabled="workspace.count < 2" @click="onDuplicate">
          Дублировать активную
        </button>
        <button class="tabs-menu-item" type="button" :disabled="workspace.count < 2" @click="onCloseOthers">
          Закрыть остальные
        </button>
        <button class="tabs-menu-item" type="button" @click="onCloseAll">
          Закрыть все
        </button>
      </div>
    </button>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useWorkspaceStore, type WorkspaceTab } from '../../stores/workspace'

defineProps<{
  compact?: boolean
}>()

const workspace = useWorkspaceStore()
const scrollerRef = ref<HTMLElement | null>(null)
const tabRefs = new Map<string, HTMLElement>()
const menuOpen = ref(false)

function setTabRef(id: string, el: HTMLElement | null) {
  if (el) {
    tabRefs.set(id, el)
  } else {
    tabRefs.delete(id)
  }
}

function onActivate(id: string) {
  workspace.select(id)
}

function onClose(id: string) {
  const ok = workspace.close(id)
  if (!ok) {
    if (window.confirm('На вкладке есть несохранённые изменения. Закрыть принудительно?')) {
      workspace.close(id, true)
    }
  }
}

function onAuxClick(id: string, event: MouseEvent) {
  // Средняя кнопка мыши — закрыть (как в браузерах/IDE).
  if (event.button === 1) {
    event.preventDefault()
    onClose(id)
  }
}

function onMiddleClick(id: string) {
  onClose(id)
}

function onDuplicate() {
  if (workspace.activeId) {
    workspace.duplicate(workspace.activeId)
  }
  menuOpen.value = false
}

function onCloseOthers() {
  if (!workspace.activeId) {
    menuOpen.value = false
    return
  }
  const ok = workspace.closeOthers(workspace.activeId)
  if (!ok) {
    if (window.confirm('Среди остальных вкладок есть несохранённые изменения. Закрыть принудительно?')) {
      workspace.closeOthers(workspace.activeId!, true)
    }
  }
  menuOpen.value = false
}

function onCloseAll() {
  const ok = workspace.closeAll()
  if (!ok) {
    if (window.confirm('Есть несохранённые изменения. Закрыть все вкладки принудительно?')) {
      workspace.closeAll(true)
    }
  }
  menuOpen.value = false
}

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

// Прокрутка к активному табу, чтобы он всегда был виден.
watch(
  () => workspace.activeId,
  async (id) => {
    if (!id) return
    await nextTick()
    const el = tabRefs.get(id)
    if (!el || !scrollerRef.value) return
    const container = scrollerRef.value
    const rect = el.getBoundingClientRect()
    const view = container.getBoundingClientRect()
    if (rect.left < view.left) {
      container.scrollLeft -= view.left - rect.left - 8
    } else if (rect.right > view.right) {
      container.scrollLeft += rect.right - view.right + 8
    }
  },
)

// Закрытие меню по клику вне.
function onDocumentClick(event: MouseEvent) {
  if (!menuOpen.value) return
  const target = event.target as HTMLElement | null
  if (target && !target.closest('.tabs-overflow')) {
    menuOpen.value = false
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('click', onDocumentClick)
}

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    document.removeEventListener('click', onDocumentClick)
  }
})

// Экспонируем для потенциальных тестов.
defineExpose({ workspace })
</script>

<style scoped>
.workspace-tabs {
  display: flex;
  align-items: stretch;
  gap: 0.4rem;
  min-width: 0;
  flex: 1 1 auto;
}

.tabs-scroller {
  display: flex;
  align-items: stretch;
  gap: 0.3rem;
  overflow-x: auto;
  scrollbar-width: thin;
  scroll-behavior: smooth;
  min-width: 0;
  flex: 1 1 auto;
  padding-bottom: 0.15rem;
}

.tabs-scroller::-webkit-scrollbar {
  height: 4px;
}

.tabs-scroller::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 999px;
}

.tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  max-width: 16rem;
  padding: 0.5rem 0.85rem;
  border: 1px solid transparent;
  border-radius: 14px;
  background: transparent;
  color: var(--text-soft);
  font-weight: 600;
  white-space: nowrap;
  transition:
    background-color 140ms ease,
    color 140ms ease,
    border-color 140ms ease;
}

.tab:hover {
  background: var(--surface-muted);
  color: var(--text);
}

.tab.active {
  background: var(--surface-strong);
  border-color: var(--border);
  color: var(--text);
  box-shadow: 0 4px 12px rgba(62, 38, 24, 0.06);
}

.tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.tab-dirty-marker {
  color: var(--accent);
  font-size: 0.6rem;
  line-height: 1;
}

.tab-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.15rem;
  height: 1.15rem;
  border-radius: 999px;
  color: var(--text-soft);
  cursor: pointer;
  transition:
    background-color 120ms ease,
    color 120ms ease;
}

.tab-close:hover {
  background: var(--accent-ghost);
  color: var(--accent);
}

.tab:not(.active) .tab-close {
  opacity: 0.55;
}

.tab:not(:hover) .tab-close {
  opacity: 0.4;
}

.tab.dirty .tab-close {
  opacity: 1;
}

.workspace-tabs.compact .tab {
  padding: 0.36rem 0.6rem;
  font-size: 0.88rem;
  border-radius: 11px;
  max-width: 13rem;
}

.workspace-tabs.compact .tab-close {
  width: 1rem;
  height: 1rem;
}

.tabs-overflow {
  position: relative;
  align-self: center;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  color: var(--text-soft);
  padding: 0.4rem 0.55rem;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.tabs-overflow:hover {
  color: var(--text);
}

.tabs-menu {
  position: absolute;
  top: calc(100% + 0.4rem);
  right: 0;
  z-index: 60;
  min-width: 13rem;
  padding: 0.35rem;
  display: grid;
  gap: 0.15rem;
}

.tabs-menu-item {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--text);
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  font-size: 0.9rem;
  cursor: pointer;
}

.tabs-menu-item:hover:not(:disabled) {
  background: var(--surface-muted);
}

.tabs-menu-item:disabled {
  color: var(--text-soft);
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
