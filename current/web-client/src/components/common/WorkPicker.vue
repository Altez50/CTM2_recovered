<template>
  <div class="work-picker">
    <!-- Единая рамка: поле + ○ открыть + ▼ выбор + ✕ очистить -->
    <div class="ref-input-row" :class="{ compact: props.compact }">
      <!-- Поле ввода (read-only display) -->
      <button
        type="button"
        class="ref-input-field"
        :class="{ placeholder: !hasSelection }"
        @click="open = true"
        @keydown.f4.prevent="open = true"
      >
        <span class="ref-input-text">{{ triggerLabel }}</span>
      </button>

      <!-- Кнопка "Открыть" (○) — карточка выбранной работы -->
      <button
        v-if="props.showOpenButton"
        type="button"
        class="ref-btn ref-btn-open"
        :class="{ compact: props.compact }"
        :disabled="props.modelValue === null"
        :title="props.modelValue !== null ? 'Открыть карточку выбранной работы' : 'Сначала выберите работу'"
        aria-label="Открыть карточку выбранной работы"
        @click="openCurrentSelectionCard"
      >
        ○
      </button>

      <!-- Кнопка "Выбор" (▼) -->
      <button
        type="button"
        class="ref-btn ref-btn-choose"
        :class="{ compact: props.compact }"
        title="Выбрать (F4)"
        aria-label="Выбрать работу"
        @click="open = true"
      >
        ▼
      </button>

      <!-- Кнопка "Очистить" (✕) -->
      <button
        v-if="props.modelValue !== null"
        type="button"
        class="ref-btn ref-btn-clear"
        :class="{ compact: props.compact }"
        title="Очистить"
        aria-label="Очистить значение"
        @click="clear"
      >
        ✕
      </button>
    </div>

    <Modal :open="open" size="full" title="Выбор работы" description="Найдите и выберите работу из справочника" @close="open = false">
      <div class="picker-modal-body" @keydown="handleKeydown">
        <input
          ref="searchInput"
          v-model="search"
          class="input"
          placeholder="Поиск по названию или коду…"
        />

        <div class="picker-toolbar">
          <button class="button button-secondary" type="button" :disabled="!canGoUp || isSearchMode" @click="goUp">
            На уровень выше
          </button>
          <p class="picker-path">{{ locationLabel }}</p>
        </div>

        <div v-if="loading" class="picker-state">
          Загрузка справочника работ…
        </div>

        <div v-else-if="error" class="picker-state picker-state-error">
          <p>{{ error }}</p>
          <button class="button button-secondary" type="button" @click="retry">Повторить</button>
        </div>

        <div v-else-if="isCatalogEmpty" class="picker-state">
          В справочнике работ пока нет доступных элементов.
        </div>

        <div v-else-if="visibleWorks.length === 0" class="picker-state">
          {{ emptyMessage }}
        </div>

        <div v-else class="work-list">
          <div
            v-for="work in visibleWorks"
            :key="work.id"
            :ref="(element) => setItemRef(element, work.id)"
            class="work-item"
            :class="{
              selected: work.id === modelValue,
              active: work.id === activeWorkId,
              group: work.is_group,
            }"
            role="button"
            tabindex="0"
            :title="work.is_group ? 'Открыть группу' : 'Выбрать работу'"
            @click="activate(work)"
            @focus="activeWorkId = work.id"
            @keydown.enter.prevent="activate(work)"
            @keydown.space.prevent="activate(work)"
          >
            <span class="work-leading">
              <span class="work-kind-badge" :class="work.is_group ? 'kind-group' : 'kind-leaf'">
                {{ work.is_group ? 'Группа' : 'Работа' }}
              </span>
              <button
                type="button"
                class="work-open-button"
                :title="work.is_group ? 'Открыть карточку группы' : 'Открыть карточку работы'"
                :aria-label="work.is_group ? 'Открыть карточку группы' : 'Открыть карточку работы'"
                @click.stop="openCard(work)"
              >
                [O]
              </button>
              <span class="work-name">{{ work.name }}</span>
            </span>
            <span v-if="work.code" class="work-meta">{{ work.code }}</span>
            <span v-if="!work.is_group && work.unit" class="work-meta">{{ work.unit }}</span>
          </div>
        </div>

        <div class="picker-footer">
          <button
            v-if="modelValue !== null"
            type="button"
            class="button button-secondary"
            @click="clear"
          >
            Очистить
          </button>
        </div>
      </div>
    </Modal>

    <WorkForm
      :open="editorOpen"
      :work-id="editorWorkId"
      @close="closeCardEditor"
      @saved="handleCardSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUpdate, ref, watch } from 'vue'
import { loadWorkCatalog } from '../../api/workCatalog'
import type { WorkDetail, WorkRecord } from '../../types/models'
import Modal from './Modal.vue'
import WorkForm from '../work/WorkForm.vue'

const props = withDefaults(defineProps<{
  modelValue: number | null
  selectedLabel?: string | null
  compact?: boolean
  showOpenButton?: boolean
}>(), {
  selectedLabel: null,
  compact: false,
  showOpenButton: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  change: [work: WorkRecord | null]
}>()

const open = ref(false)
const search = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
const catalog = ref<WorkRecord[]>([])
const loading = ref(false)
const error = ref('')
const currentParentId = ref<number | null>(null)
const activeWorkId = ref<number | null>(null)
const itemRefs = ref<Map<number, HTMLElement>>(new Map())

const editorOpen = ref(false)
const editorWorkId = ref<number | null>(null)

const selectedWork = computed(() =>
  props.modelValue !== null ? catalog.value.find((work) => work.id === props.modelValue) ?? null : null,
)

const hasSelection = computed(() => props.modelValue !== null || Boolean(props.selectedLabel))

const triggerLabel = computed(() => {
  if (selectedWork.value) {
    return selectedWork.value.name
  }
  if (props.modelValue !== null && props.selectedLabel) {
    return props.selectedLabel
  }
  return 'Выберите работу'
})

const workById = computed(() => {
  const result = new Map<number, WorkRecord>()
  catalog.value.forEach((work) => result.set(work.id, work))
  return result
})

const worksByParent = computed(() => {
  const result = new Map<number | null, WorkRecord[]>()

  catalog.value.forEach((work) => {
    const parentId = normalizeParentId(work.parent_id)
    const siblings = result.get(parentId) ?? []
    siblings.push(work)
    result.set(parentId, siblings)
  })

  result.forEach((works, key) => {
    result.set(key, sortWorks(works))
  })

  return result
})

const breadcrumbs = computed(() => {
  const result: WorkRecord[] = []
  let pointer = currentParentId.value

  while (pointer !== null) {
    const current = workById.value.get(pointer)
    if (!current) {
      break
    }
    result.unshift(current)
    pointer = normalizeParentId(current.parent_id)
  }

  return result
})

const isSearchMode = computed(() => search.value.trim().length > 0)

const visibleWorks = computed(() => {
  const query = search.value.trim().toLowerCase()

  if (!query) {
    return worksByParent.value.get(currentParentId.value) ?? []
  }

  return sortWorks(
    catalog.value.filter((work) => {
      const code = (work.code ?? '').toLowerCase()
      return work.name.toLowerCase().includes(query) || code.includes(query)
    }),
  )
})

const canGoUp = computed(() => currentParentId.value !== null)
const isCatalogEmpty = computed(() => catalog.value.length === 0)

const emptyMessage = computed(() => {
  if (isSearchMode.value) {
    return 'Ничего не найдено'
  }
  if (currentParentId.value !== null) {
    return 'В этой группе пока нет элементов.'
  }
  return 'В справочнике работ пока нет доступных элементов.'
})

const locationLabel = computed(() => {
  if (isSearchMode.value) {
    return `Результаты поиска: ${visibleWorks.value.length}`
  }
  if (!breadcrumbs.value.length) {
    return 'Корень справочника'
  }
  return `Текущая группа: ${breadcrumbs.value.map((item) => item.name).join(' / ')}`
})

watch(open, async (value) => {
  if (!value) {
    search.value = ''
    currentParentId.value = null
    activeWorkId.value = null
    return
  }

  search.value = ''
  error.value = ''
  await nextTick()
  searchInput.value?.focus()
  await ensureCatalogLoaded()
  alignToCurrentSelection()
  await nextTick()
  searchInput.value?.focus()
})

watch([visibleWorks, () => props.modelValue], async () => {
  if (!open.value) {
    return
  }

  syncActiveWork()
  await nextTick()
  scrollActiveWorkIntoView()
})

onBeforeUpdate(() => {
  itemRefs.value = new Map<number, HTMLButtonElement>()
})

function normalizeParentId(value?: number | null) {
  return value ?? null
}

function sortWorks(items: WorkRecord[]) {
  return [...items].sort((left, right) => {
    if (left.is_group !== right.is_group) {
      return left.is_group ? -1 : 1
    }

    const codeDiff = (left.code ?? '').localeCompare(right.code ?? '', 'ru', {
      numeric: true,
      sensitivity: 'base',
    })
    if (codeDiff !== 0) {
      return codeDiff
    }

    return left.name.localeCompare(right.name, 'ru', { numeric: true, sensitivity: 'base' })
  })
}

function setItemRef(element: unknown, workId: number) {
  if (element instanceof HTMLElement) {
    itemRefs.value.set(workId, element)
  }
}

async function ensureCatalogLoaded(force = false) {
  loading.value = true
  error.value = ''

  try {
    catalog.value = await loadWorkCatalog(force)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить список работ'
  } finally {
    loading.value = false
  }
}

function alignToCurrentSelection() {
  const selected = props.modelValue !== null ? workById.value.get(props.modelValue) ?? null : null
  currentParentId.value = selected ? normalizeParentId(selected.parent_id) : null
  syncActiveWork()
}

function syncActiveWork() {
  if (!visibleWorks.value.length) {
    activeWorkId.value = null
    return
  }

  const selectedVisible =
    props.modelValue !== null ? visibleWorks.value.find((work) => work.id === props.modelValue) ?? null : null

  if (selectedVisible) {
    activeWorkId.value = selectedVisible.id
    return
  }

  if (activeWorkId.value && visibleWorks.value.some((work) => work.id === activeWorkId.value)) {
    return
  }

  activeWorkId.value = visibleWorks.value[0]?.id ?? null
}

function scrollActiveWorkIntoView() {
  if (!activeWorkId.value) {
    return
  }
  itemRefs.value.get(activeWorkId.value)?.scrollIntoView({ block: 'nearest' })
}

function moveActive(step: number) {
  if (!visibleWorks.value.length) {
    return
  }

  const currentIndex = visibleWorks.value.findIndex((work) => work.id === activeWorkId.value)
  const safeIndex = currentIndex >= 0 ? currentIndex : 0
  const nextIndex = Math.min(Math.max(safeIndex + step, 0), visibleWorks.value.length - 1)
  const next = visibleWorks.value[nextIndex]
  activeWorkId.value = next?.id ?? null
  nextTick(() => {
    if (next) {
      itemRefs.value.get(next.id)?.focus()
    }
  })
}

function goUp() {
  if (currentParentId.value === null) {
    return
  }

  const current = workById.value.get(currentParentId.value)
  currentParentId.value = current ? normalizeParentId(current.parent_id) : null
}

function activate(work: WorkRecord) {
  if (work.is_group) {
    currentParentId.value = work.id
    search.value = ''
    activeWorkId.value = null
    return
  }

  emit('update:modelValue', work.id)
  emit('change', work)
  open.value = false
}

function clear() {
  emit('update:modelValue', null)
  emit('change', null)
  open.value = false
}

function handleKeydown(event: KeyboardEvent) {
  if (loading.value || error.value) {
    return
  }

  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      moveActive(1)
      break
    case 'ArrowUp':
      event.preventDefault()
      moveActive(-1)
      break
    case 'PageDown':
      event.preventDefault()
      moveActive(10)
      break
    case 'PageUp':
      event.preventDefault()
      moveActive(-10)
      break
    case 'Enter': {
      const current = visibleWorks.value.find((work) => work.id === activeWorkId.value)
      if (!current) {
        return
      }
      event.preventDefault()
      activate(current)
      break
    }
    case 'Backspace':
      if (!isSearchMode.value && canGoUp.value) {
        event.preventDefault()
        goUp()
      }
      break
    default:
      break
  }
}

function openCard(work: WorkRecord) {
  editorWorkId.value = work.id
  editorOpen.value = true
}

function openCurrentSelectionCard() {
  if (props.modelValue === null) {
    return
  }

  editorWorkId.value = props.modelValue
  editorOpen.value = true
}

async function retry() {
  await ensureCatalogLoaded(true)
  alignToCurrentSelection()
}

function closeCardEditor() {
  editorOpen.value = false
}

async function handleCardSaved(savedWork: WorkDetail) {
  await ensureCatalogLoaded(true)
  alignToCurrentSelection()

  if (props.modelValue === savedWork.id) {
    const refreshed = catalog.value.find((work) => work.id === savedWork.id) ?? savedWork
    emit('change', refreshed)
  }
}
</script>

<style scoped>
.work-picker {
  width: 100%;
}

/* === Единая рамка (контейнер) === */
.ref-input-row {
  display: flex;
  align-items: stretch;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.8);
  overflow: hidden;
  transition: border-color 140ms ease, box-shadow 140ms ease;
}

.ref-input-row:hover,
.ref-input-row:focus-within {
  border-color: var(--accent-soft);
  box-shadow: 0 0 0 3px var(--accent-ghost);
}

/* === Поле ввода === */
.ref-input-field {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 42px;
  display: flex;
  align-items: center;
  border: none;
  background: transparent;
  padding: 0.65rem 0.75rem;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: var(--text);
  outline: none;
}

.ref-input-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.95rem;
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
  transition: background 140ms ease, color 140ms ease;
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

.ref-btn-open:hover:not(:disabled),
.ref-btn-open:focus-visible {
  background: var(--accent-ghost);
  color: var(--accent);
}

.ref-btn-open:disabled {
  color: var(--text-soft);
  cursor: not-allowed;
  opacity: 0.5;
}

/* === Compact mode === */
.ref-input-row.compact {
  border-radius: 9px;
}

.ref-input-row.compact .ref-input-field {
  min-height: 1.8rem;
  padding: 0.18rem 0.42rem;
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
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  flex: 1;
  min-height: 0;
}

.picker-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.picker-path {
  margin: 0;
  color: var(--text-soft);
  text-align: right;
}

.picker-state {
  border: 1px dashed var(--border);
  border-radius: 16px;
  color: var(--text-soft);
  padding: 1rem;
  text-align: center;
}

.picker-state-error {
  display: grid;
  gap: 0.75rem;
  justify-items: center;
  color: var(--danger);
}

.picker-state-error p {
  margin: 0;
}

.work-list {
  display: grid;
  gap: 0.3rem;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 0.25rem;
}

.work-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.7);
  padding: 0.6rem 0.85rem;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
}

.work-item:hover {
  background: var(--accent-ghost);
  border-color: var(--accent-soft);
}

.work-item.selected {
  background: var(--accent-ghost);
  border-color: var(--accent);
}

.work-item.active {
  box-shadow: 0 0 0 3px var(--accent-ghost);
}

.work-item.group {
  background: rgba(245, 241, 230, 0.92);
}

.work-leading {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex: 1;
  min-width: 0;
}

.work-kind-badge {
  border-radius: 999px;
  font-size: 0.72rem;
  line-height: 1;
  padding: 0.3rem 0.55rem;
  white-space: nowrap;
  border: 1px solid transparent;
}

.kind-group {
  background: rgba(145, 111, 57, 0.16);
  color: #6f5428;
}

.kind-leaf {
  background: rgba(30, 115, 96, 0.12);
  color: #1b5c4f;
}

.work-open-button {
  min-width: 2.1rem;
  padding-inline: 0.34rem;
}

.work-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.95rem;
}

.work-meta {
  font-size: 0.8rem;
  color: var(--text-soft);
  white-space: nowrap;
}

.picker-footer {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 767px) {
  .picker-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .picker-path {
    text-align: left;
  }

  .work-item {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}
</style>
