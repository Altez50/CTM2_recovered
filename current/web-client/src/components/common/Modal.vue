<template>
  <Teleport to="body">
    <div v-if="open" ref="overlayRef" class="overlay" @click.self="$emit('close')">
      <div class="dialog panel" :class="[size === 'full' ? 'dialog-full' : '', { 'dialog-headerless': hideHeader }]">
        <header v-if="!hideHeader" class="dialog-header">
          <div>
            <h3 class="dialog-title">{{ title }}</h3>
          </div>
          <button class="button button-secondary close-button" type="button" @click="$emit('close')">
            Закрыть
          </button>
        </header>
        <div class="dialog-body" :class="{ 'dialog-body-flush': hideHeader }">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  description?: string
  size?: 'default' | 'full' | 'compact'
  hideHeader?: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const overlayRef = ref<HTMLElement | null>(null)
let lastFocusedElement: HTMLElement | null = null

function getFocusableElements() {
  const root = overlayRef.value
  if (!root) {
    return [] as HTMLElement[]
  }

  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => element.tabIndex !== -1)
}

function handleDocumentKeydown(event: KeyboardEvent) {
  if (!props.open) {
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }

  if (event.key !== 'Tab') {
    return
  }

  const focusable = getFocusableElements()
  if (!focusable.length) {
    event.preventDefault()
    return
  }

  const activeElement = document.activeElement as HTMLElement | null
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (!first || !last) {
    return
  }

  if (event.shiftKey) {
    if (!activeElement || activeElement === first || !overlayRef.value?.contains(activeElement)) {
      event.preventDefault()
      last.focus()
    }
    return
  }

  if (!activeElement || activeElement === last || !overlayRef.value?.contains(activeElement)) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
      document.addEventListener('keydown', handleDocumentKeydown)
      await nextTick()
      getFocusableElements()[0]?.focus()
      return
    }

    document.removeEventListener('keydown', handleDocumentKeydown)
    lastFocusedElement?.focus()
    lastFocusedElement = null
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleDocumentKeydown)
})
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(25, 15, 8, 0.48);
  display: grid;
  place-items: center;
  padding: 1rem;
  z-index: 10001;
}

.dialog {
  width: min(860px, 100%);
  max-height: calc(100vh - 2rem);
  overflow: auto;
}

.dialog-full {
  width: min(1200px, 100%);
  max-height: calc(100vh - 2rem);
  height: calc(100vh - 2rem);
  display: flex;
  flex-direction: column;
}

.dialog-full .dialog-body {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  padding: 1.2rem 1.25rem 0;
}

.dialog-title {
  margin: 0;
}

.dialog-description {
  margin: 0.35rem 0 0;
  color: var(--text-soft);
}

.dialog-body {
  padding: 1.25rem;
}

.dialog-body-flush {
  padding: 0;
}

.close-button {
  white-space: nowrap;
}

@media (max-width: 767px) {
  .overlay {
    padding: 0;
    align-items: end;
  }

  .dialog {
    width: 100%;
    max-height: 92vh;
    border-radius: 24px 24px 0 0;
  }

  .dialog-full {
    height: 92vh;
    max-height: 92vh;
  }

  .dialog-header {
    flex-direction: column;
  }
}
</style>
