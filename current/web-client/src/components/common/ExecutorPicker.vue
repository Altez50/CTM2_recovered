<template>
  <div class="entity-picker">
    <!-- Единая рамка: поле (двойной клик = открыть) + ▼ выбрать + ✕ очистить -->
    <div class="ref-input-row" :class="{ compact, disabled }">
      <button
        type="button"
        class="ref-input-field"
        :class="{ placeholder: selectedIds.length === 0 }"
        :disabled="disabled"
        :title="triggerLabel"
        @dblclick="openPicker"
        @keydown.f4.prevent="openPicker"
      >
        <span class="ref-input-text">{{ triggerLabel }}</span>
      </button>

      <button
        v-if="!disabled"
        type="button"
        class="ref-btn ref-btn-choose"
        :class="{ compact }"
        title="Выбрать исполнителей (двойной клик)"
        aria-label="Выбрать исполнителей"
        @click="openPicker"
      >
        ▼
      </button>

      <button
        v-if="clearable && selectedIds.length > 0 && !disabled"
        type="button"
        class="ref-btn ref-btn-clear"
        :class="{ compact }"
        title="Очистить"
        aria-label="Очистить исполнителей"
        @click="clear"
      >
        ✕
      </button>
    </div>

    <Modal :open="open" size="full" :title="title" @close="cancel">
      <div class="picker-modal-body picker-modal-body-full">
        <div class="picker-toolbar">
          <input
            ref="searchInput"
            v-model="search"
            class="input"
            type="search"
            :placeholder="searchPlaceholder"
          />
          <div class="picker-toolbar-actions">
            <button v-if="editKind" class="button button-primary" type="button" title="Создать нового сотрудника" @click="openCreate">+ Создать</button>
            <button class="button button-secondary" type="button" title="Обновить" :disabled="loading" @click="reload">↻</button>
          </div>
        </div>

        <div class="picker-content">
          <div v-if="loading" class="picker-state">Загрузка…</div>

          <div v-else-if="error" class="picker-state picker-state-error">
            <p>{{ error }}</p>
            <button class="button button-secondary" type="button" @click="reload">Повторить</button>
          </div>

          <div v-else-if="items.length === 0" class="picker-state">{{ emptyText }}</div>

          <div v-else class="picker-list">
            <div
              v-for="item in items"
              :key="item.id"
              class="picker-item"
              :class="{ selected: isPicked(item.id) }"
              @click="toggle(item)"
            >
              <span class="check-box" :class="{ checked: isPicked(item.id) }">{{ isPicked(item.id) ? '☑' : '☐' }}</span>
              <span class="picker-item-main">{{ item.label }}</span>
              <span v-if="item.caption" class="picker-item-caption">{{ item.caption }}</span>
              <button
                v-if="editKind"
                type="button"
                class="picker-item-open"
                title="Открыть карточку"
                aria-label="Открыть карточку сотрудника"
                @click.stop="openEdit(item.id)"
              >
                ○
              </button>
            </div>
          </div>
        </div>

        <div class="picker-footer">
          <div class="picker-pagination">
            <button class="button button-secondary" type="button" :disabled="page <= 1 || loading" @click="page -= 1">Назад</button>
            <span class="muted">Страница {{ page }} из {{ pages }}</span>
            <button class="button button-secondary" type="button" :disabled="page >= pages || loading" @click="page += 1">Вперед</button>
          </div>
          <div class="picker-footer-actions">
            <span class="muted">Выбрано: {{ draftIds.length }}</span>
            <button class="button button-secondary" type="button" @click="cancel">Отмена</button>
            <button class="button button-primary" type="button" @click="apply">Готово</button>
          </div>
        </div>
      </div>
    </Modal>

    <ReferenceEditModal
      v-if="editKind"
      :open="editOpen"
      :kind="editKind"
      :id="createMode ? null : editId"
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
}

interface PickerResult {
  items: PickerItem[]
  pages: number
}

const props = withDefaults(
  defineProps<{
    /** Выбранные ID исполнителей (мульти-выбор). */
    modelValue: number[]
    /** Подписи для отображения выбранных (из API: executor_names). */
    selectedLabels?: string[]
    title?: string
    placeholder?: string
    searchPlaceholder?: string
    emptyText?: string
    clearable?: boolean
    disabled?: boolean
    compact?: boolean
    loadPage: (params: { search: string; page: number; pageSize: number }) => Promise<PickerResult>
    editKind?: ReferenceKind
  }>(),
  {
    selectedLabels: () => [],
    title: 'Выбор исполнителей',
    placeholder: 'Двойной клик для выбора',
    searchPlaceholder: 'Поиск по ФИО…',
    emptyText: 'Сотрудники не найдены',
    clearable: true,
    disabled: false,
    compact: false,
    editKind: undefined,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: number[]]
  change: [value: PickerItem[]]
}>()

const selectedIds = computed(() => props.modelValue)

const triggerLabel = computed(() => {
  if (props.selectedLabels.length > 0) return props.selectedLabels.join(', ')
  return props.placeholder
})

const open = ref(false)
const editOpen = ref(false)
const createMode = ref(false)
const editId = ref<number | null>(null)
const search = ref('')
const page = ref(1)
const pages = ref(1)
const items = ref<PickerItem[]>([])
const loading = ref(false)
const error = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
let searchTimer = 0

// Черновик выбора: накапливается в модальной форме, применяется по «Готово».
const draftIds = ref<number[]>([])
const draftLabels = ref<Map<number, string>>(new Map())

function isPicked(id: number): boolean {
  return draftIds.value.includes(id)
}

function toggle(item: PickerItem) {
  const idx = draftIds.value.indexOf(item.id)
  if (idx >= 0) {
    draftIds.value.splice(idx, 1)
  } else {
    draftIds.value.push(item.id)
  }
  draftLabels.value.set(item.id, item.label)
}

function openPicker() {
  if (props.disabled) return
  open.value = true
}

function apply() {
  const picked: PickerItem[] = draftIds.value.map((id) => ({
    id,
    label: draftLabels.value.get(id) ?? '',
  }))
  emit('update:modelValue', [...draftIds.value])
  emit('change', picked)
  open.value = false
}

function cancel() {
  open.value = false
}

function clear() {
  emit('update:modelValue', [])
  emit('change', [])
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
    // Сохраняем подписи для возможных выбранных элементов этой страницы.
    response.items.forEach((item) => {
      draftLabels.value.set(item.id, item.label)
    })
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

function openEdit(id: number) {
  createMode.value = false
  editId.value = id
  editOpen.value = true
}

function openCreate() {
  createMode.value = true
  editId.value = null
  editOpen.value = true
}

function onEditClose() {
  editOpen.value = false
  createMode.value = false
}

function onEdited(record: ReferenceRecordLike) {
  const label = String(record.full_name ?? record.name ?? '')
  if (createMode.value && record.id) {
    if (!draftIds.value.includes(record.id)) {
      draftIds.value.push(record.id)
    }
    draftLabels.value.set(record.id, label)
  } else if (record.id) {
    draftLabels.value.set(record.id, label)
  }
  editOpen.value = false
  createMode.value = false
  if (open.value) {
    loadItems()
  }
}

watch(open, async (value) => {
  if (!value) {
    search.value = ''
    page.value = 1
    return
  }
  // Инициализируем черновик текущим выбором.
  draftIds.value = [...props.modelValue]
  draftLabels.value = new Map()
  props.modelValue.forEach((id, i) => {
    draftLabels.value.set(id, props.selectedLabels[i] ?? '')
  })
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

/* === Кнопки === */
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

/* === Modal === */
.picker-modal-body {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 0.65rem;
  min-height: 0;
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
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.55rem;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
  padding: 0.5rem 0.7rem;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease;
  user-select: none;
}

.picker-item:hover {
  background: var(--accent-ghost);
  border-color: var(--accent-soft);
}

.picker-item.selected {
  border-color: var(--accent);
  background: var(--accent-ghost);
}

.check-box {
  font-size: 1.05rem;
  line-height: 1;
  color: var(--text-soft);
}

.check-box.checked {
  color: var(--accent);
}

.picker-item-main {
  font-weight: 600;
  font-size: 0.88rem;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker-item-caption {
  color: var(--text-soft);
  font-size: 0.78rem;
  line-height: 1.2;
}

.picker-item-open {
  flex: 0 0 auto;
  border: none;
  background: transparent;
  color: var(--text-soft);
  cursor: pointer;
  font-size: 0.95rem;
  padding: 0 0.2rem;
  border-radius: 8px;
  transition: background 120ms, color 120ms;
}

.picker-item-open:hover {
  background: var(--accent-ghost);
  color: var(--accent);
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
  flex-wrap: wrap;
}

.picker-pagination {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.picker-footer-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.muted {
  color: var(--text-soft);
  font-size: 0.85rem;
}

@media (max-width: 767px) {
  .picker-toolbar {
    grid-template-columns: minmax(0, 1fr);
  }

  .picker-pagination {
    justify-content: space-between;
  }
}
</style>
