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
      >
        <li
          v-for="item in items"
          :key="item.key"
          :class="['ctx-item', { disabled: item.disabled, danger: item.danger }]"
          @click="onClick(item)"
        >
          <span class="ctx-icon">{{ item.icon }}</span>
          <span class="ctx-label">{{ item.label }}</span>
        </li>
      </ul>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
export interface ContextMenuItem {
  key: string
  label: string
  icon?: string
  disabled?: boolean
  danger?: boolean
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

// Clamp menu so it stays within viewport
const px = computed(() => {
  const maxX = window.innerWidth - 220
  return Math.min(props.x, maxX)
})
const py = computed(() => {
  const maxY = window.innerHeight - props.items.length * 40 - 20
  return Math.min(props.y, Math.max(props.y, maxY))
})

import { computed } from 'vue'

function onClick(item: ContextMenuItem) {
  if (item.disabled) return
  emit('select', item.key)
  emit('close')
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

.ctx-icon {
  width: 1.2rem;
  text-align: center;
  font-size: 0.95rem;
}

.ctx-label {
  flex: 1;
}
</style>
