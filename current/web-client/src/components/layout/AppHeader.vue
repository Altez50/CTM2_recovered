<template>
  <header :class="['header', 'panel', { compact, overlay }]">
    <div class="header-row">
      <div class="header-left">
        <button
          class="button button-secondary menu-toggle"
          type="button"
          :aria-label="sidebarOpen ? 'Свернуть меню' : 'Открыть меню'"
          :title="sidebarOpen ? 'Свернуть меню' : 'Открыть меню'"
          @click="$emit('toggle-menu')"
        >
          <span class="menu-glyph" aria-hidden="true">☰</span>
        </button>
        <h1 class="header-page-title" :title="activeTitle">{{ activeTitle }}</h1>
      </div>
      <WorkspaceTabs :compact="compact" />
      <div class="header-actions">
        <div class="user-card">
          <span class="muted">{{ user.role }}</span>
          <strong>{{ user.full_name || user.username }}</strong>
        </div>
        <button class="button button-primary" type="button" @click="$emit('logout')">Выйти</button>
      </div>
    </div>
    <div v-if="hasActions" class="header-toolbar">
      <DocumentActionIcon
        v-for="action in activeActions"
        :key="action.key"
        :title="action.title"
        :icon="action.icon"
        :variant="action.variant ?? 'neutral'"
        :disabled="action.disabled"
        :to="action.to"
        @click="action.onClick?.()"
      />
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { UserInfo } from '../../types/models'
import WorkspaceTabs from './WorkspaceTabs.vue'
import DocumentActionIcon from '../common/DocumentActionIcon.vue'
import { useHeaderBarStore } from '../../stores/headerBar'

defineProps<{
  user: UserInfo
  sidebarOpen: boolean
  compact?: boolean
  overlay?: boolean
}>()

defineEmits<{
  'toggle-menu': []
  logout: []
}>()

const headerBar = useHeaderBarStore()
const activeTitle = computed(() => headerBar.activeEntry?.title ?? 'CTM')
const activeActions = computed(() => headerBar.activeEntry?.actions ?? [])
const hasActions = computed(() => activeActions.value.length > 0)
</script>

<style scoped>
.header {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  padding: 1rem 1.25rem;
}

.header.overlay {
  box-shadow: 0 24px 48px rgba(62, 38, 24, 0.16);
}

.header.compact {
  gap: 0.5rem;
  padding: 0.6rem 0.85rem;
}

.header-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  min-width: 0;
}

.header.compact .header-row {
  gap: 0.75rem;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  min-width: 0;
}

.header-page-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 22rem;
}

.header.compact .header-page-title {
  font-size: 0.98rem;
}

.header-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.85rem;
}

.user-card {
  display: grid;
  min-width: 0;
}

.menu-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.35rem;
  min-width: 2.35rem;
  padding: 0;
  aspect-ratio: 1;
}

button.button {
  min-height: 2.35rem;
}

.menu-glyph {
  font-size: 1.05rem;
  line-height: 1;
}

@media (max-width: 767px) {
  .header-row {
    flex-wrap: wrap;
  }

  .header-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .menu-toggle {
    width: 2.35rem;
  }

  .header-page-title {
    max-width: 60vw;
  }
}
</style>
