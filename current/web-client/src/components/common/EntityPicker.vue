<template>
  <div class="entity-picker">
    <!-- Единая рамка: поле + ○ открыть + ▼ выбор + ✕ очистить -->
    <div
      class="ref-input-row"
      :class="{ compact, disabled, 'has-error': !!error }"
    >
      <!-- Поле ввода (read-only display) -->
      <button
        type="button"
        class="ref-input-field"
        :class="{ placeholder: !hasSelection }"
        :disabled="disabled"
        :title="hasSelection ? triggerLabel : placeholder"
        @click="open = true"
        @keydown.f4.prevent="open = true"
      >
        <span class="ref-input-text">{{ triggerLabel }}</span>
      </button>

      <!-- Кнопка "Открыть" (○) — карточка выбранной сущности -->
      <button
        v-if="editKind && modelValue !== null && !disabled"
        type="button"
        class="ref-btn ref-btn-open"
        :class="{ compact }"
        title="Открыть карточку"
        aria-label="Открыть карточку"
        @click="openEdit"
      >
        ○
      </button>

      <!-- Кнопка "Выбор" (▼) — открыть форму выбора -->
      <button
        v-if="!disabled"
        type="button"
        class="ref-btn ref-btn-choose"
        :class="{ compact }"
        title="Выбрать (F4)"
        aria-label="Выбрать значение"
        @click="open = true"
      >
        ▼
      </button>

      <!-- Кнопка "Очистить" (✕) — сбросить значение -->
      <button
        v-if="clearable && modelValue !== null && !disabled"
        type="button"
        class="ref-btn ref-btn-clear"
        :class="{ compact }"
        title="Очистить"
        aria-label="Очистить значение"
        @click="clear"
      >
        ✕
      </button>
    </div>

    <Modal :open="open" :size="size" :title="title" :description="description" @close="open = false">
      <div :class="['picker-modal-body', size === 'full' ? 'picker-modal-body-full' : 'picker-modal-body-default']">
        <div class="picker-toolbar">
          <input
            ref="searchInput"
            v-model="search"
            class="input"
            type="search"
            :placeholder="searchPlaceholder"
          />
          <div class="picker-toolbar-actions">
            <button v-if="editKind" class="button button-primary" type="button" title="Создать новый элемент" @click="openCreate">+ Создать</button>
            <button class="button button-secondary" type="button" title="Обновить" :disabled="loading" @click="reload">↻</button>
          </div>
        </div>

        <div class="picker-content">
          <div v-if="loading" class="picker-state">
            Загрузка…
          </div>

          <div v-else-if="error" class="picker-state picker-state-error">
            <p>{{ error }}</p>
            <button class="button button-secondary" type="button" @click="reload">Повторить</button>
          </div>

          <div v-else-if="items.length === 0" class="picker-state">
            {{ emptyText }}
          </div>

          <div v-else class="picker-list">
            <button
              v-for="item in items"
              :key="item.id"
              type="button"
              class="picker-item"
              :class="{ selected: item.id === modelValue }"
              @click="selectItem(item)"
            >
              <span class="picker-item-main">{{ item.label }}</span>
              <span v-if="item.caption" class="picker-item-caption">{{ item.caption }}</span>
              <div v-if="detailFields && detailFields.length" class="picker-item-details">
                <span v-for="field in detailFields" :key="field" class="picker-item-detail">
                  {{ formatDetail(item.meta?.[field]) }}
                </span>
              </div>
            </button>
          </div>
        </div>

        <div class="picker-footer">
          <div class="picker-pagination">
            <button class="button button-secondary" type="button" :disabled="page <= 1 || loading" @click="page -= 1">Назад</button>
            <span class="muted">Страница {{ page }} из {{ pages }}</span>
            <button class="button button-secondary" type="button" :disabled="page >= pages || loading" @click="page += 1">Вперед</button>
          </div>
          <button v-if="clearable && modelValue !== null" class="button button-secondary" type="button" @click="clear">Очистить</button>
        </div>
      </div>
    </Modal>

    <ReferenceEditModal
      v-if="editKind"
      :open="editOpen"
      :kind="editKind"
      :id="createMode ? null : modelValue"
      @close="onEditClose"
      @saved="onEdited"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import Modal from './Modal.vue'
import ReferenceEditModal from './ReferenceEditModal.vue'
import type { ReferenceKind } from '../../types/models'
import type { ReferenceRecordLike } from '../../composables/referenceFields'

export interface PickerItem {
  id: number
  label: string
  caption?: string | null
  meta?: Record<string, unknown>
}

interface PickerResult {
  items: PickerItem[]
  pages: number
}

const props = withDefaults(
  defineProps<{
    modelValue: number | null
    selectedLabel?: string | null
    title: string
    description?: string
    placeholder?: string
    searchPlaceholder?: string
    emptyText?: string
    clearable?: boolean
    disabled?: boolean
    compact?: boolean
    size?: 'default' | 'full' | 'compact'
    loadPage: (params: { search: string; page: number; pageSize: number }) => Promise<PickerResult>
    editKind?: ReferenceKind
    detailFields?: string[]
  }>(),
  {
    selectedLabel: null,
    description: undefined,
    placeholder: 'Выберите значение',
    searchPlaceholder: 'Поиск…',
    emptyText: 'Ничего не найдено',
    clearable: true,
    disabled: false,
    compact: false,
    size: 'default',
    editKind: undefined,
    detailFields: undefined,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  change: [value: PickerItem | null]
}>()

const open = ref(false)
const editOpen = ref(false)
const createMode = ref(false)
const search = ref('')
const page = ref(1)
const pages = ref(1)
const items = ref<PickerItem[]>([])
const loading = ref(false)
const error = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
let searchTimer = 0

const selectedItem = computed(() => items.value.find((item) => item.id === props.modelValue) ?? null)
const hasSelection = computed(() => props.modelValue !== null || Boolean(props.selectedLabel))
const triggerLabel = computed(() => selectedItem.value?.label ?? props.selectedLabel ?? props.placeholder)

function formatDetail(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)
  }
  return String(value)
}

async function loadItems() {
  loading.value = true
  error.value = ''
  try {
    const response = await props.loadPage({
      search: search.value.trim(),
      page: page.value,
      pageSize: 20,
    })
    items.value = response.items
    pages.value = Math.max(response.pages || 1, 1)
    if (page.value > pages.value) {
      page.value = pages.value
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить список'
    items.value = []
    pages.value = 1
  } finally {
    loading.value = false
  }
}

function reload() {
  loadItems()
}

function selectItem(item: PickerItem) {
  emit('update:modelValue', item.id)
  emit('change', item)
  open.value = false
}

function clear() {
  emit('update:modelValue', null)
  emit('change', null)
  open.value = false
}

const LABEL_FIELDS: Record<ReferenceKind, string> = {
  counterparties: 'name',
  objects: 'name',
  works: 'name',
  persons: 'name',
  organizations: 'name',
  contracts: 'number',
  materials: 'name',
}

function onEdited(record: ReferenceRecordLike) {
  if (!props.editKind) return
  const labelField = LABEL_FIELDS[props.editKind]
  const label = String(record[labelField] ?? '')
  if (createMode.value && record.id) {
    emit('update:modelValue', record.id)
    emit('change', { id: record.id, label })
  } else {
    emit('change', { id: props.modelValue ?? 0, label })
  }
  createMode.value = false
  if (open.value) {
    loadItems()
  }
}

function openEdit() {
  createMode.value = false
  editOpen.value = true
}

function openCreate() {
  createMode.value = true
  editOpen.value = true
}

function onEditClose() {
  editOpen.value = false
  createMode.value = false
}

watch(open, async (value) => {
  if (!value) {
    search.value = ''
    page.value = 1
    return
  }
  page.value = 1
  await loadItems()
  await nextTick()
  searchInput.value?.focus()
})

watch(page, () => {
  if (open.value) {
    loadItems()
  }
})

watch(search, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    if (open.value) {
      loadItems()
    }
  }, 250)
})
</script>

<style scoped>
/* === Единая рамка (контейнер) === */
.ref-input-row {
  display: flex;
  align-items: stretch;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-input, 18px);
  background: rgba(255, 255, 255, 0.8);
  overflow: hidden;
  transition: border-color 120ms, box-shadow 120ms;
}

.ref-input-row:hover,
.ref-input-row:focus-within {
  border-color: var(--accent-soft);
  box-shadow: 0 0 0 3px var(--accent-ghost);
}

.ref-input-row.disabled {
  opacity: 0.6;
  background: var(--surface-muted);
  cursor: not-allowed;
}

.ref-input-row.disabled:hover {
  border-color: var(--border);
  box-shadow: none;
}

.ref-input-row.has-error {
  border-color: var(--danger);
}

.ref-input-row.has-error:hover,
.ref-input-row.has-error:focus-within {
  border-color: var(--danger);
  box-shadow: 0 0 0 3px rgba(160, 50, 50, 0.12);
}

/* === Поле ввода (без собственной рамки) === */
.ref-input-field {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 42px;
  display: flex;
  align-items: center;
  border: none;
  background: transparent;
  padding: 0.7rem 0.85rem;
  cursor: pointer;
  text-align: left;
  transition: background 120ms;
  font: inherit;
  color: var(--text-main);
  outline: none;
}

.ref-input-row.disabled .ref-input-field {
  cursor: not-allowed;
}

.ref-input-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.93rem;
}

.ref-input-field.placeholder .ref-input-text {
  color: var(--text-soft);
}

/* === Кнопки (без обводки) === */
.ref-btn {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--accent);
  font-size: 0.85rem;
  font-weight: 700;
  cursor: pointer;
  min-width: 27px;
  padding: 0 0.4rem;
  transition: background 120ms, color 120ms;
}

.ref-btn:hover,
.ref-btn:focus-visible {
  outline: none;
  background: var(--accent-ghost);
}

.ref-btn:active {
  background: var(--accent-soft);
  color: #fff;
}

.ref-btn-clear {
  color: var(--danger);
}

.ref-btn-clear:hover,
.ref-btn-clear:focus-visible {
  background: rgba(160, 50, 50, 0.1);
}

.ref-btn-clear:active {
  background: var(--danger);
  color: #fff;
}

.ref-btn-open {
  color: var(--text-soft);
}

.ref-btn-open:hover,
.ref-btn-open:focus-visible {
  background: var(--accent-ghost);
  color: var(--accent);
}

/* === Compact mode === */
.ref-input-row.compact {
  border-radius: 10px;
}

.ref-input-row.compact .ref-input-field {
  min-height: 32px;
  padding: 0.3rem 0.55rem;
}

.ref-input-row.compact .ref-input-text {
  font-size: 0.84rem;
}

.ref-btn.compact {
  min-width: 21px;
  font-size: 0.76rem;
  padding: 0 0.3rem;
}

/* === Modal (unchanged) === */

.picker-modal-body {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 0.65rem;
  min-height: 0;
}

.picker-modal-body-default {
  height: min(32rem, calc(100vh - 14rem));
  max-height: calc(100vh - 12rem);
}

.picker-modal-body-full {
  height: 100%;
}

.picker-content {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.picker-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.65rem;
  align-items: center;
}

.picker-toolbar .input {
  flex: 1;
}

.picker-toolbar-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.picker-list {
  display: grid;
  align-content: start;
  gap: 0.28rem;
  min-height: 0;
  flex: 1 1 auto;
  overflow: auto;
  padding-right: 0.15rem;
}

.picker-item {
  display: grid;
  gap: 0.15rem;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
  padding: 0.5rem 0.7rem;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease;
}

.picker-item:hover {
  background: var(--accent-ghost);
  border-color: var(--accent-soft);
}

.picker-item.selected {
  border-color: var(--accent);
  background: var(--accent-ghost);
}

.picker-item-main {
  font-weight: 600;
  font-size: 0.88rem;
  line-height: 1.3;
}

.picker-item-caption {
  color: var(--text-soft);
  font-size: 0.78rem;
  line-height: 1.2;
}

.picker-item-details {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.1rem;
}

.picker-item-detail {
  color: var(--text-soft);
  font-size: 0.78rem;
  line-height: 1.2;
  white-space: nowrap;
}

.picker-state {
  color: var(--text-soft);
  min-height: 0;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  justify-content: center;
  padding: 1rem 0.15rem;
}

.picker-state-error {
  color: var(--danger);
}

.picker-state p {
  margin: 0;
}

.picker-footer {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
}

.picker-pagination {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

@media (max-width: 767px) {
  .picker-toolbar,
  .picker-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .picker-toolbar {
    grid-template-columns: minmax(0, 1fr);
  }

  .picker-pagination {
    justify-content: space-between;
  }
}
</style>
