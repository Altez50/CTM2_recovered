<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @click="$emit('close')">
      <div class="modal panel" role="dialog" aria-modal="true" @click.stop>
        <header class="modal-header">
          <h2 class="modal-title">Настройка списка</h2>
          <button class="button button-secondary" type="button" @click="$emit('close')">✕</button>
        </header>

        <div class="modal-body">
          <p class="muted settings-hint">Отметьте видимые колонки и задайте их порядок.</p>
          <ul class="column-list">
            <li v-for="(col, index) in working" :key="col.key" class="column-item">
              <label class="column-check">
                <input v-model="col.visible" type="checkbox" :disabled="working.filter((c) => c.visible).length <= 1 && col.visible" />
                <span>{{ col.label }}</span>
              </label>
              <div class="column-order">
                <button class="button button-secondary" type="button" :disabled="index === 0" title="Вверх" @click="move(index, -1)">↑</button>
                <button class="button button-secondary" type="button" :disabled="index === working.length - 1" title="Вниз" @click="move(index, 1)">↓</button>
              </div>
            </li>
          </ul>
        </div>

        <footer class="modal-footer">
          <button class="button button-secondary" type="button" @click="$emit('reset')">По умолчанию</button>
          <div class="modal-footer-right">
            <button class="button button-secondary" type="button" @click="$emit('close')">Отмена</button>
            <button class="button button-primary" type="button" :disabled="!canApply" @click="apply">ОК</button>
          </div>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ColumnState } from '../../composables/useListSettings'

interface WorkingColumn extends ColumnState {
  label: string
}

const props = defineProps<{
  open: boolean
  /** Полный состав колонок конфига (для подписей). */
  columns: { key: string; label: string }[]
  /** Текущие состояния видимости/порядка. */
  states: ColumnState[]
}>()

const emit = defineEmits<{
  close: []
  apply: [states: ColumnState[]]
  reset: []
}>()

const working = ref<WorkingColumn[]>([])

watch(
  () => [props.open, props.states, props.columns] as const,
  ([isOpen]) => {
    if (!isOpen) return
    const labelByKey = new Map(props.columns.map((c) => [c.key, c.label]))
    working.value = props.states.map((s) => ({ ...s, label: labelByKey.get(s.key) ?? s.key }))
  },
  { immediate: true, deep: true },
)

const canApply = computed(() => working.value.some((c) => c.visible))

function move(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= working.value.length) return
  const arr = [...working.value]
  ;[arr[index], arr[target]] = [arr[target], arr[index]]
  working.value = arr
}

function apply() {
  emit('apply', working.value.map(({ key, visible }) => ({ key, visible })))
  emit('close')
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(40, 28, 18, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10001;
  padding: 1rem;
}

.modal {
  width: min(440px, 96vw);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.modal-title {
  margin: 0;
  font-size: 1.05rem;
}

.modal-body {
  overflow: auto;
}

.settings-hint {
  margin: 0 0 0.5rem;
  font-size: 0.85rem;
}

.column-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.4rem;
}

.column-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.column-check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.column-order {
  display: flex;
  gap: 0.3rem;
}

.column-order .button {
  min-width: 2rem;
  padding: 0 0.4rem;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
}

.modal-footer-right {
  display: flex;
  gap: 0.5rem;
}
</style>
