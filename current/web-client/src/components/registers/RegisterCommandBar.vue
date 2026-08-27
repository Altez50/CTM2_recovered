<template>
  <div class="register-cmd-bar">
    <div class="cmd-left">
      <button class="cmd-btn" type="button" title="Обновить" @click="$emit('refresh')">
        <span class="cmd-glyph">↻</span>
      </button>
      <div class="cmd-dropdown">
        <button class="cmd-btn" type="button" title="Экспорт" @click="showExport = !showExport">
          <span class="cmd-glyph">⤓</span>
          <span class="cmd-label">Экспорт</span>
        </button>
        <div v-if="showExport" class="dropdown-menu" @mouseleave="showExport = false">
          <button class="dropdown-item" type="button" @click="doExport('xlsx'); showExport = false">Excel</button>
          <button class="dropdown-item" type="button" @click="doExport('csv'); showExport = false">CSV</button>
        </div>
      </div>
    </div>
    <div class="cmd-right">
      <button
        class="cmd-btn"
        :class="{ active: filterable }"
        type="button"
        title="Быстрый отбор"
        @click="$emit('toggle-filter')"
      >
        <span class="cmd-glyph">▦</span>
        <span class="cmd-label">Фильтр</span>
      </button>
      <button class="cmd-btn" type="button" title="Настройка списка" @click="$emit('settings')">
        <span class="cmd-glyph">⚙</span>
        <span class="cmd-label">Настройка</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ filterable: boolean }>()
const emit = defineEmits<{
  refresh: []
  'toggle-filter': []
  settings: []
  export: [format: 'csv' | 'xlsx']
}>()

const showExport = ref(false)

function doExport(format: 'csv' | 'xlsx') {
  emit('export', format)
}
</script>

<style scoped>
.register-cmd-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--border, #e0d6cc);
  flex-wrap: wrap;
}

.cmd-left,
.cmd-right {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.cmd-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.5rem;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--text, #333);
  font-size: 0.85rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.cmd-btn:hover {
  background: var(--hover-bg, rgba(0, 0, 0, 0.05));
  border-color: var(--border-light, #ddd);
}

.cmd-btn.active {
  background: var(--primary-bg, rgba(178, 76, 45, 0.1));
  border-color: var(--primary, #b24c2d);
  color: var(--primary, #b24c2d);
}

.cmd-glyph {
  font-size: 1rem;
  line-height: 1;
}

.cmd-label {
  font-size: 0.8rem;
}

.cmd-dropdown {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 100;
  min-width: 120px;
  background: var(--panel-bg, #fff);
  border: 1px solid var(--border, #e0d6cc);
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  padding: 0.2rem 0;
}

.dropdown-item {
  display: block;
  width: 100%;
  padding: 0.35rem 0.75rem;
  border: none;
  background: transparent;
  color: var(--text, #333);
  font-size: 0.85rem;
  text-align: left;
  cursor: pointer;
}

.dropdown-item:hover {
  background: var(--hover-bg, rgba(0, 0, 0, 0.05));
}
</style>
