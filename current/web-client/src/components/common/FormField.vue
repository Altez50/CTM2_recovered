<template>
  <label class="field">
    <span class="field-label">{{ label }}</span>
    <slot />
    <span v-if="hint" class="field-hint">{{ hint }}</span>
    <span v-if="error" class="field-error">{{ error }}</span>
  </label>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  hint?: string
  error?: string
}>()
</script>

<style scoped>
.field {
  display: grid;
  gap: 0.45rem;
}

.field-label {
  font-size: 0.92rem;
  font-weight: 600;
}

.field-hint {
  color: var(--text-soft);
  font-size: 0.85rem;
}

.field-error {
  color: var(--danger);
  font-size: 0.85rem;
}
</style>
