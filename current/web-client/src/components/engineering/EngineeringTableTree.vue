<template>
  <div class="eng-tree">
    <input
      v-model="query"
      class="input eng-tree-search"
      type="search"
      placeholder="Поиск таблиц и полей…"
    />
    <div class="eng-tree-body">
      <div v-for="cat in filteredCategories" :key="cat.id" class="eng-cat">
        <button type="button" class="eng-cat-head" @click="toggleCat(cat.id)">
          <span class="eng-arrow">{{ openCats.has(cat.id) ? '▾' : '▸' }}</span>
          <span>{{ cat.label }}</span>
          <span class="eng-cat-count">{{ cat.tables.length }}</span>
        </button>
        <div v-if="openCats.has(cat.id)" class="eng-cat-body">
          <div v-for="t in cat.tables" :key="t.name" class="eng-table">
            <div
              :class="['eng-table-head', { active: selectedTable === t.name }]"
              :title="t.name"
              @click="$emit('select-table', t.name)"
              @dblclick="!compact ? toggleTable(t.name) : null"
            >
              <span v-if="!compact" class="eng-arrow small">{{ openTables.has(t.name) ? '▾' : '▸' }}</span>
              <span class="eng-table-syn">{{ t.synonym }}</span>
            </div>
            <div v-if="!compact && openTables.has(t.name)" class="eng-fields">
              <button
                v-for="f in t.fields"
                :key="f.name"
                type="button"
                class="eng-field"
                :title="`${f.synonym} (${f.name}, ${f.type})`"
                @click="$emit('insert-token', qualified ? `${t.synonym}.${f.synonym}` : f.synonym)"
                @dblclick="$emit('insert-token', `${t.synonym}.${f.synonym}`)"
              >
                <span class="eng-field-syn">{{ f.synonym }}</span>
                <span class="eng-field-name">{{ f.name }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="filteredCategories.every((c) => c.tables.length === 0)" class="eng-empty">
        Ничего не найдено
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { EngineeringCatalog, EngineeringField } from '../../api/engineering'

const props = defineProps<{
  catalog: EngineeringCatalog | null
  selectedTable?: string
  /** compact: только список таблиц (без полей) — для просмотрщика. */
  compact?: boolean
  /** qualified: при клике вставлять «Таблица.Поле». */
  qualified?: boolean
}>()

defineEmits<{
  'select-table': [name: string]
  'insert-token': [token: string]
}>()

const query = ref('')
const openCats = ref<Set<string>>(new Set())
const openTables = ref<Set<string>>(new Set())

function toggleCat(id: string) {
  const next = new Set(openCats.value)
  next.has(id) ? next.delete(id) : next.add(id)
  openCats.value = next
}

function toggleTable(name: string) {
  const next = new Set(openTables.value)
  next.has(name) ? next.delete(name) : next.add(name)
  openTables.value = next
}

// Разворачиваем первую категорию при загрузке каталога.
watch(
  () => props.catalog,
  (cat) => {
    if (cat && cat.categories.length && openCats.value.size === 0) {
      openCats.value = new Set([cat.categories[0].id])
    }
  },
  { immediate: true },
)

function fieldMatches(f: EngineeringField, q: string) {
  const ql = q.toLowerCase()
  return f.synonym.toLowerCase().includes(ql) || f.name.toLowerCase().includes(ql)
}

const filteredCategories = computed(() => {
  const cat = props.catalog
  if (!cat) return []
  const q = query.value.trim().toLowerCase()
  if (!q) return cat.categories
  return cat.categories
    .map((c) => ({
      ...c,
      tables: c.tables.filter((t) => {
        const byName = t.synonym.toLowerCase().includes(q) || t.name.toLowerCase().includes(q)
        const byField = t.fields.some((f) => fieldMatches(f, q))
        return byName || byField
      }),
    }))
    .filter((c) => c.tables.length > 0)
})
</script>

<style scoped>
.eng-tree {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}
.eng-tree-search {
  margin-bottom: 0.5rem;
}
.eng-tree-body {
  overflow: auto;
  flex: 1;
  min-height: 0;
}
.eng-cat {
  margin-bottom: 0.25rem;
}
.eng-cat-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  font-weight: 600;
  padding: 0.3rem 0.25rem;
  cursor: pointer;
  border-radius: 6px;
}
.eng-cat-head:hover {
  background: var(--bg-soft, #f5f5f5);
}
.eng-arrow {
  width: 1ch;
  color: var(--muted, #888);
}
.eng-arrow.small {
  font-size: 0.8rem;
}
.eng-cat-count {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--muted, #888);
  background: var(--bg-soft, #eee);
  border-radius: 999px;
  padding: 0 0.4rem;
}
.eng-cat-body {
  padding-left: 0.5rem;
}
.eng-table-head {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.4rem;
  cursor: pointer;
  border-radius: 6px;
  border: 1px solid transparent;
}
.eng-table-head:hover {
  background: var(--bg-soft, #f5f5f5);
}
.eng-table-head.active {
  background: color-mix(in srgb, var(--accent, #2962ff) 14%, transparent);
  border-color: var(--accent, #2962ff);
}
.eng-table-syn {
  font-size: 0.92rem;
}
.eng-fields {
  padding-left: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
.eng-field {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  text-align: left;
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  font-size: 0.82rem;
  padding: 0.18rem 0.4rem;
  cursor: pointer;
  border-radius: 4px;
}
.eng-field:hover {
  background: var(--bg-soft, #f5f5f5);
}
.eng-field-name {
  color: var(--muted, #999);
  font-size: 0.72rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.eng-empty {
  color: var(--muted, #888);
  padding: 1rem;
  text-align: center;
}
</style>
