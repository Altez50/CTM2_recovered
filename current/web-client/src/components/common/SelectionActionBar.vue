<template>
  <div v-if="selectedCount > 0" class="selection-action-bar">
    <span class="selection-action-bar__count">Выбрано: {{ selectedCount }}</span>
    <div class="selection-action-bar__actions">
      <slot />
      <button
        class="button button-secondary selection-action-bar__deselect"
        type="button"
        @click="$emit('deselect-all')"
      >
        ✕
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  selectedCount: number
}>()

defineEmits<{
  'deselect-all': []
}>()
</script>

<style scoped>
.selection-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  padding: 0.48rem 0.75rem;
  border: 1px solid rgba(178, 76, 45, 0.2);
  border-radius: 14px;
  background: rgba(178, 76, 45, 0.06);
}

.selection-action-bar__count {
  font-weight: 600;
  font-size: 0.88rem;
  color: var(--accent);
  white-space: nowrap;
}

.selection-action-bar__actions {
  display: flex;
  align-items: center;
  gap: 0.42rem;
  flex-wrap: wrap;
}

.selection-action-bar__deselect {
  margin-left: 0.25rem;
}
</style>
