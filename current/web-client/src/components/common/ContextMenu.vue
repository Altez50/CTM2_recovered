<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="ctx-backdrop"
      @click="$emit('close')"
      @contextmenu.prevent="$emit('close')"
    >
      <ul
        class="ctx-menu"
        :style="{ left: px + 'px', top: py + 'px' }"
        @click.stop
        @contextmenu.prevent.stop
      >
        <template v-for="(item, idx) in items" :key="item.key ?? `sep-${idx}`">
          <li v-if="item.type === 'separator'" class="ctx-separator" />
          <li
            v-else
            :class="['ctx-item', { disabled: item.disabled, danger: item.danger, has_submenu: !!item.submenu, submenu_open: openSubmenu === idx }]"
            @click="onClick(item)"
            @mouseenter="onItemEnter(idx, item)"
            @mouseleave="onItemLeave"
          >
            <span class="ctx-icon">{{ item.icon }}</span>
            <span class="ctx-label">{{ item.label }}</span>
            <span v-if="item.submenu" class="ctx-chevron">▸</span>
            <ul
              v-if="item.submenu && openSubmenu === idx"
              class="ctx-menu ctx-submenu"
              :style="{ left: subX + 'px', top: subY + 'px' }"
              @click.stop
              @mouseenter="cancelSubClose()"
              @mouseleave="scheduleSubClose()"
            >
              <template v-for="(sub, sIdx) in item.submenu" :key="sub.key ?? `sub-sep-${sIdx}`">
                <li v-if="sub.type === 'separator'" class="ctx-separator" />
                <li
                  v-else
                  :class="['ctx-item', { disabled: sub.disabled, danger: sub.danger }]"
                  @click="onSubClick(item, sub)"
                >
                  <span class="ctx-icon">{{ sub.icon }}</span>
                  <span class="ctx-label">{{ sub.label }}</span>
                </li>
              </template>
            </ul>
          </li>
        </template>
      </ul>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

export interface ContextMenuItem {
  /** Пункт-разделитель, если type === 'separator'. */
  type?: 'separator'
  key?: string
  label?: string
  icon?: string
  disabled?: boolean
  danger?: boolean
  /** Подменю (один уровень). */
  submenu?: ContextMenuItem[]
}

const props = withDefaults(
  defineProps<{
    open: boolean
    items: ContextMenuItem[]
    x: number
    y: number
  }>(),
  {
    open: false,
    items: () => [],
    x: 0,
    y: 0,
  },
)

const emit = defineEmits<{ close: []; select: [key: string] }>()

const openSubmenu = ref<number | null>(null)
const subX = ref(0)
const subY = ref(0)
let subCloseTimer = 0

function isParent(item: ContextMenuItem): boolean {
  return Array.isArray(item.submenu) && item.submenu.length > 0 && item.type !== 'separator'
}

function isLeaf(item: ContextMenuItem): boolean {
  return item.type !== 'separator' && item.key !== undefined && !isParent(item)
}

// Clamp menu so it stays within viewport
const px = computed(() => {
  const maxX = window.innerWidth - 220
  return Math.min(props.x, maxX)
})
const py = computed(() => {
  const maxY = window.innerHeight - props.items.length * 40 - 20
  return Math.min(props.y, Math.max(props.y, maxY))
})

function onClick(item: ContextMenuItem) {
  if (!isLeaf(item) || item.disabled || item.key === undefined) return
  emit('select', item.key)
  emit('close')
}

function onSubClick(parent: ContextMenuItem, sub: ContextMenuItem) {
  if (!isLeaf(sub) || sub.disabled || sub.key === undefined) return
  // Составной ключ «parent.key/sub.key» — позволяет обработчику различать пункты подменю.
  emit('select', parent.key ? `${parent.key}/${sub.key}` : sub.key)
  emit('close')
}

function onItemEnter(idx: number, item: ContextMenuItem) {
  if (!isParent(item)) {
    openSubmenu.value = null
    return
  }
  openSubmenu.value = idx
  // Позиционируем подменю справа от пункта, в пределах viewport.
  const maxX = window.innerWidth - 230
  const maxY = window.innerHeight - (item.submenu?.length ?? 0) * 40 - 20
  subX.value = Math.min(px.value + 214, maxX)
  subY.value = Math.min(py.value + idx * 40, Math.max(0, maxY))
}

function onItemLeave() {
  scheduleSubClose()
}

function scheduleSubClose() {
  window.clearTimeout(subCloseTimer)
  subCloseTimer = window.setTimeout(() => {
    openSubmenu.value = null
  }, 120)
}

function cancelSubClose() {
  window.clearTimeout(subCloseTimer)
}
</script>

<style scoped>
.ctx-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
}

.ctx-menu {
  position: fixed;
  list-style: none;
  margin: 0;
  padding: 0.35rem 0;
  background: var(--bg-panel, #fff);
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.18);
  min-width: 200px;
  z-index: 10000;
  font-size: 0.88rem;
}

.ctx-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.9rem;
  cursor: pointer;
  white-space: nowrap;
  position: relative;
  transition: background 0.12s;
}

.ctx-item:hover {
  background: var(--bg-soft, #f5f5f5);
}

.ctx-item.disabled {
  opacity: 0.4;
  cursor: default;
}

.ctx-item.disabled:hover {
  background: none;
}

.ctx-item.danger {
  color: #c0392b;
}

.ctx-item.danger:hover {
  background: rgba(192, 57, 43, 0.08);
}

.ctx-item.has_submenu.submenu_open {
  background: var(--bg-soft, #f5f5f5);
}

.ctx-icon {
  width: 1.2rem;
  text-align: center;
  font-size: 0.95rem;
}

.ctx-label {
  flex: 1;
}

.ctx-chevron {
  opacity: 0.6;
  font-size: 0.75rem;
}

.ctx-separator {
  height: 1px;
  margin: 0.35rem 0.6rem;
  background: var(--border, #ddd);
}

.ctx-submenu {
  min-width: 200px;
}
</style>
