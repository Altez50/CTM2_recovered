<template>
  <div class="command-bar">
    <div class="command-group">
      <slot name="create">
        <button class="button button-primary" type="button" @click="config.createRoute ? routerPush(config.createRoute) : null">
          {{ config.createLabel }}
        </button>
      </slot>
      <button
        class="button button-secondary"
        type="button"
        :disabled="!state.canOpen || !state.singleRow.value"
        title="Открыть документ"
        @click="state.openSelected()"
      >
        Открыть
      </button>
      <button
        v-if="config.api.copy"
        class="button button-secondary"
        type="button"
        :disabled="!state.canOpen || !state.singleRow.value"
        title="Скопировать"
        @click="state.copySelected()"
      >
        Копировать
      </button>
      <template v-if="config.hasPost !== false">
        <button
          class="button button-secondary"
          type="button"
          :disabled="!state.canPostSelected.value"
          title="Провести"
          @click="state.postSelected()"
        >
          Провести
        </button>
        <button
          class="button button-secondary"
          type="button"
          :disabled="!state.canUnpostSelected.value"
          title="Отменить проведение"
          @click="state.unpostSelected()"
        >
          Отменить
        </button>
      </template>
      <!-- Ввод на основании -->
      <div v-if="config.baseOn?.length" class="base-on-wrap">
        <button
          class="button button-secondary"
          type="button"
          :disabled="!state.canBaseOn.value"
          title="Ввод на основании"
          @click="onBaseOnClick"
        >
          Ввести на основании ▾
        </button>
        <ul v-if="showBaseMenu" class="base-menu panel" @click.stop>
          <li v-for="target in config.baseOn" :key="target.kind">
            <button type="button" class="base-menu-item" @click="chooseBaseOn(target.kind)">{{ target.label }}</button>
          </li>
        </ul>
      </div>
      <button
        class="button button-secondary danger"
        type="button"
        :disabled="!state.canDeleteSelected.value"
        @click="state.removeSelected()"
      >
        Удалить
      </button>
      <slot name="commands" />
    </div>

    <div class="command-group">
      <span v-if="state.hasSelection.value" class="selection-chip">
        Выбрано: {{ state.selectionCount.value }}
      </span>
      <button
        class="button button-secondary"
        :class="{ active: state.filterRowVisible.value }"
        type="button"
        title="Отбор по колонкам"
        @click="state.toggleFilterRow()"
      >
        Отбор
      </button>
      <button class="button button-secondary" type="button" title="Настройка списка" @click="$emit('open-settings')">
        Настройка
      </button>
      <button class="button button-secondary" type="button" title="Обновить" @click="state.loadItems()">
        Обновить
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { DocumentListState } from '../../composables/useDocumentList'
import type { DocListConfig } from '../../config/documentListTypes'

const props = defineProps<{
  state: DocumentListState
  config: DocListConfig
}>()

defineEmits<{ 'open-settings': [] }>()

const router = useRouter()
const showBaseMenu = ref(false)

function routerPush(route: string) {
  void router.push(route)
}

function onBaseOnClick() {
  // Один адресат — сразу переход, иначе — открыть выпадающее меню.
  if (props.config.baseOn?.length === 1) {
    props.state.openBaseOn(props.config.baseOn[0].kind)
  } else {
    showBaseMenu.value = !showBaseMenu.value
  }
}

function chooseBaseOn(kind: string) {
  showBaseMenu.value = false
  props.state.openBaseOn(kind)
}

function onDocClick() {
  showBaseMenu.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<style scoped>
.command-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
}

.command-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.command-bar .button {
  min-height: 2.3rem;
}

.command-bar .button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.command-bar .button.danger {
  color: #c0392b;
}

.command-bar .button.active {
  border-color: var(--accent);
  color: var(--accent);
}

.selection-chip {
  font-size: 0.85rem;
  color: var(--accent);
  padding: 0.2rem 0.6rem;
  border: 1px solid var(--accent);
  border-radius: 999px;
}

.base-on-wrap {
  position: relative;
}

.base-menu {
  position: absolute;
  top: calc(100% + 0.3rem);
  left: 0;
  list-style: none;
  margin: 0;
  padding: 0.35rem;
  min-width: 200px;
  z-index: 50;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
}

.base-menu-item {
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  padding: 0.45rem 0.6rem;
  cursor: pointer;
  border-radius: 6px;
  color: var(--text);
  font: inherit;
}

.base-menu-item:hover {
  background: var(--bg-soft, #f5f5f5);
}
</style>
