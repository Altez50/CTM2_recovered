<template>
  <Modal :open="open" :title="title ?? 'Печатная форма'" @close="$emit('close')">
    <p class="print-format-text">Выберите формат печатной формы:</p>
    <div class="print-format-actions">
      <button class="button button-primary print-format-button" type="button" @click="choose('excel')">
        <span class="print-format-label">Excel</span>
        <span class="print-format-hint">Электронная таблица</span>
      </button>
      <button class="button button-secondary print-format-button" type="button" @click="choose('pdf')">
        <span class="print-format-label">PDF</span>
        <span class="print-format-hint">Документ для печати</span>
      </button>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import Modal from './Modal.vue'

type PrintFormat = 'excel' | 'pdf'

defineProps<{
  open: boolean
  title?: string
}>()

const emit = defineEmits<{
  close: []
  select: [format: PrintFormat]
}>()

function choose(format: PrintFormat) {
  emit('select', format)
  emit('close')
}
</script>

<style scoped>
.print-format-text {
  margin: 0 0 1rem;
  color: var(--text-soft);
}

.print-format-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.print-format-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 1rem 1.25rem;
}

.print-format-label {
  font-size: 1.05rem;
  font-weight: 600;
}

.print-format-hint {
  font-size: 0.8rem;
  opacity: 0.75;
}

@media (max-width: 540px) {
  .print-format-actions {
    grid-template-columns: 1fr;
  }
}
</style>
