<template>
  <aside v-if="visible" class="estimate-work-catalog">
    <div class="estimate-work-catalog__content">
      <input
        v-model="search"
        class="input estimate-work-catalog__search-input"
        placeholder="Поиск: код, наименование, категория"
        type="search"
      />

      <div class="estimate-work-catalog__toolbar">
        <button class="button button-secondary estimate-work-catalog__up-button" type="button" :disabled="!canGoUp || isSearchMode" @click="goUp">
          Вверх
        </button>
        <p class="estimate-work-catalog__location">{{ locationLabel }}</p>
      </div>

      <div v-if="breadcrumbs.length && !isSearchMode" class="estimate-work-catalog__breadcrumbs">
        <button class="estimate-work-catalog__crumb" type="button" @click="currentParentId = null">
          Корень
        </button>
        <button
          v-for="crumb in breadcrumbs"
          :key="crumb.id"
          class="estimate-work-catalog__crumb"
          type="button"
          @click="currentParentId = crumb.id"
        >
          {{ crumb.name }}
        </button>
      </div>

      <div v-if="loading" class="estimate-work-catalog__state">
        Загрузка каталога работ…
      </div>

      <div v-else-if="error" class="estimate-work-catalog__state estimate-work-catalog__state--error">
        <p>{{ error }}</p>
        <button class="button button-secondary" type="button" @click="retry">Повторить</button>
      </div>

      <div v-else-if="catalog.length === 0" class="estimate-work-catalog__state">
        Каталог работ пока пуст.
      </div>

      <div v-else-if="visibleWorks.length === 0" class="estimate-work-catalog__state">
        {{ emptyMessage }}
      </div>

      <div v-else class="estimate-work-catalog__list">
        <div
          v-for="work in visibleWorks"
          :key="work.id"
          class="estimate-work-catalog__item"
          :class="{ 'estimate-work-catalog__item--group': work.is_group }"
          role="button"
          tabindex="0"
          :draggable="!work.is_group"
          @click="handleItemClick(work)"
          @keydown.enter.prevent="handleItemClick(work)"
          @keydown.space.prevent="handleItemClick(work)"
          @dragstart="handleDragStart($event, work)"
        >
          <div class="estimate-work-catalog__item-main">
            <span
              class="estimate-work-catalog__badge"
              :class="work.is_group ? 'estimate-work-catalog__badge--group' : 'estimate-work-catalog__badge--work'"
            >
              {{ work.is_group ? 'Группа' : 'Работа' }}
            </span>
            <button
              class="estimate-work-catalog__name-button"
              type="button"
              :title="work.is_group ? 'Открыть карточку группы' : 'Открыть карточку работы'"
              :aria-label="work.is_group ? 'Открыть карточку группы' : 'Открыть карточку работы'"
              @click.stop="openCard(work)"
            >
              {{ work.name }}
            </button>
          </div>

          <div class="estimate-work-catalog__item-meta">
            <span v-if="work.code">{{ work.code }}</span>
            <span v-if="!work.is_group && work.unit">{{ work.unit }}</span>
            <span v-if="!work.is_group">{{ formatNumber(work.price) }}</span>
          </div>

        </div>
      </div>
    </div>

    <WorkForm
      :open="editorOpen"
      :work-id="editorWorkId"
      @close="closeCardEditor"
      @saved="handleCardSaved"
    />
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { loadWorkCatalog } from '../../api/workCatalog'
import type { WorkDetail, WorkRecord } from '../../types/models'
import WorkForm from '../work/WorkForm.vue'

const props = withDefaults(defineProps<{
  visible?: boolean
}>(), {
  visible: true,
})

const emit = defineEmits<{
  'insert-work': [work: WorkRecord]
}>()

const search = ref('')
const catalog = ref<WorkRecord[]>([])
const loading = ref(false)
const error = ref('')
const currentParentId = ref<number | null>(null)
const editorOpen = ref(false)
const editorWorkId = ref<number | null>(null)

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

const locationLabel = computed(() => {
  if (isSearchMode.value) {
    return `Результаты поиска: ${visibleWorks.value.length}`
  }

  if (!breadcrumbs.value.length) {
    return 'Корень каталога'
  }

  return `Раздел: ${breadcrumbs.value.map((item) => item.name).join(' / ')}`
})

const emptyMessage = computed(() => {
  if (isSearchMode.value) {
    return 'Ничего не найдено'
  }

  if (currentParentId.value !== null) {
    return 'В этой группе пока нет доступных работ.'
  }

  return 'Каталог работ пока пуст.'
})

watch(
  () => props.visible,
  async (visible) => {
    if (visible) {
      await ensureCatalogLoaded()
    }
  },
  { immediate: true },
)

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

async function ensureCatalogLoaded(force = false) {
  if (!force && catalog.value.length) {
    return
  }

  loading.value = true
  error.value = ''

  try {
    catalog.value = await loadWorkCatalog(force)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить каталог работ'
  } finally {
    loading.value = false
  }
}

function goUp() {
  if (currentParentId.value === null) {
    return
  }

  const current = workById.value.get(currentParentId.value)
  currentParentId.value = current ? normalizeParentId(current.parent_id) : null
}

function handleItemClick(work: WorkRecord) {
  if (work.is_group) {
    currentParentId.value = work.id
    search.value = ''
    return
  }

  emit('insert-work', work)
}

function handleDragStart(event: DragEvent, work: WorkRecord) {
  if (work.is_group) {
    event.preventDefault()
    return
  }

  event.dataTransfer?.setData('application/x-ctm-work', JSON.stringify(work))
  event.dataTransfer?.setData('text/plain', work.name)
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'copy'
  }
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(value ?? 0)
}

async function retry() {
  await ensureCatalogLoaded(true)
}

function openCard(work: WorkRecord) {
  editorWorkId.value = work.id
  editorOpen.value = true
}

function closeCardEditor() {
  editorOpen.value = false
}

async function handleCardSaved(_savedWork: WorkDetail) {
  await ensureCatalogLoaded(true)
}
</script>

<style scoped>
.estimate-work-catalog {
  overflow-y: auto;
  overscroll-behavior: contain;
  min-height: 0;
}

.estimate-work-catalog__content {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  width: 100%;
  min-width: 0;
  padding: 0.85rem;
  border: 1px solid rgba(78, 52, 36, 0.08);
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(47, 36, 28, 0.02), rgba(178, 76, 45, 0.03)),
    rgba(255, 255, 255, 0.72);
  box-shadow: 0 10px 24px rgba(62, 38, 24, 0.06);
  min-height: 0;
}

.estimate-work-catalog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.estimate-work-catalog__eyebrow {
  margin: 0 0 0.2rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.72rem;
  color: var(--text-soft);
}

.estimate-work-catalog__title {
  margin: 0;
  font-size: 1.06rem;
}

.estimate-work-catalog__search-input {
  min-height: 2.1rem;
}

.estimate-work-catalog__location {
  margin: 0;
  color: var(--text-soft);
  font-size: 0.78rem;
  line-height: 1.35;
}

.estimate-work-catalog__toolbar {
  display: grid;
  gap: 0.45rem;
}

.estimate-work-catalog__up-button {
  min-height: 1.9rem;
  border-radius: 10px;
  padding: 0.32rem 0.6rem;
  font-size: 0.78rem;
}

.estimate-work-catalog__breadcrumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.estimate-work-catalog__crumb {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.85);
  color: var(--text);
  padding: 0.16rem 0.52rem;
  font-size: 0.74rem;
}

.estimate-work-catalog__state {
  border: 1px dashed var(--border);
  border-radius: 12px;
  padding: 0.8rem;
  color: var(--text-soft);
  text-align: center;
}

.estimate-work-catalog__state--error {
  display: grid;
  gap: 0.75rem;
  justify-items: center;
  color: var(--danger);
}

.estimate-work-catalog__state--error p {
  margin: 0;
}

.estimate-work-catalog__list {
  display: grid;
  gap: 0.3rem;
  min-height: 0;
  padding-right: 0.1rem;
}

.estimate-work-catalog__item {
  display: grid;
  gap: 0.22rem;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
  padding: 0.52rem 0.62rem;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 140ms ease,
    background-color 140ms ease,
    box-shadow 140ms ease;
}

.estimate-work-catalog__item:hover,
.estimate-work-catalog__item:focus-visible {
  outline: none;
  border-color: var(--accent-soft);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 0 0 3px rgba(178, 76, 45, 0.08);
}

.estimate-work-catalog__item--group {
  background: rgba(245, 241, 230, 0.96);
}

.estimate-work-catalog__item-main,
.estimate-work-catalog__item-meta {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.estimate-work-catalog__badge {
  border-radius: 999px;
  padding: 0.18rem 0.42rem;
  font-size: 0.66rem;
  line-height: 1;
}

.estimate-work-catalog__badge--group {
  background: rgba(145, 111, 57, 0.16);
  color: #6f5428;
}

.estimate-work-catalog__badge--work {
  background: rgba(30, 115, 96, 0.12);
  color: #1b5c4f;
}

.estimate-work-catalog__name-button {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.estimate-work-catalog__name-button:hover,
.estimate-work-catalog__name-button:focus-visible {
  outline: none;
  color: var(--accent);
  text-decoration: underline;
}

.estimate-work-catalog__item-meta {
  color: var(--text-soft);
  font-size: 0.74rem;
}

@media (max-width: 1100px) {
  .estimate-work-catalog {
    width: 100%;
    min-width: 0;
  }
}
</style>
