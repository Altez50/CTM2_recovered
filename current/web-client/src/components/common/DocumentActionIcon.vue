<template>
  <component
    :is="componentTag"
    v-bind="componentProps"
    class="document-action-icon"
    :class="[`document-action-icon--${variant}`, { 'is-disabled': disabled }]"
    :title="title"
    :aria-label="title"
    @click="handleClick"
  >
    <span class="document-action-icon__glyph" aria-hidden="true">{{ icon }}</span>
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

const props = withDefaults(
  defineProps<{
    title: string
    icon: string
    to?: RouteLocationRaw
    variant?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger'
    disabled?: boolean
  }>(),
  {
    variant: 'neutral',
    disabled: false,
  },
)

const emit = defineEmits<{
  (event: 'click', payload: MouseEvent): void
}>()

const isLink = computed(() => props.to !== undefined)
const componentTag = computed(() => (isLink.value ? RouterLink : 'button'))
const componentProps = computed(() => {
  if (isLink.value) {
    return {
      to: props.to,
      tabindex: props.disabled ? -1 : undefined,
    }
  }

  return {
    type: 'button',
    disabled: props.disabled,
  }
})

function handleClick(event: MouseEvent) {
  if (props.disabled) {
    event.preventDefault()
    event.stopPropagation()
    return
  }

  emit('click', event)
}
</script>

<style scoped>
.document-action-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: 1px solid rgba(108, 92, 76, 0.16);
  border-radius: 0.7rem;
  background: rgba(255, 251, 247, 0.92);
  color: var(--text-soft);
  text-decoration: none;
  box-shadow: 0 10px 20px rgba(64, 49, 34, 0.08);
  transition:
    transform 140ms ease,
    box-shadow 140ms ease,
    border-color 140ms ease,
    background-color 140ms ease,
    color 140ms ease;
}

.document-action-icon:hover,
.document-action-icon:focus-visible {
  transform: translateY(-1px);
  outline: none;
  box-shadow: 0 14px 28px rgba(64, 49, 34, 0.12);
}

.document-action-icon:focus-visible {
  border-color: rgba(178, 76, 45, 0.38);
}

.document-action-icon.is-disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.document-action-icon__glyph {
  font-family:
    'Segoe UI Symbol',
    'Segoe UI Emoji',
    'Noto Sans Symbols 2',
    'Noto Sans Symbols',
    sans-serif;
  font-size: 1rem;
  line-height: 1;
  font-weight: 700;
}

.document-action-icon--primary {
  color: var(--accent);
  background: rgba(178, 76, 45, 0.1);
  border-color: rgba(178, 76, 45, 0.18);
}

.document-action-icon--success {
  color: var(--success);
  background: rgba(45, 122, 68, 0.11);
  border-color: rgba(45, 122, 68, 0.18);
}

.document-action-icon--warning {
  color: #93652a;
  background: rgba(201, 150, 74, 0.14);
  border-color: rgba(201, 150, 74, 0.2);
}

.document-action-icon--danger {
  color: #a33a3a;
  background: rgba(187, 89, 89, 0.12);
  border-color: rgba(187, 89, 89, 0.18);
}
</style>
