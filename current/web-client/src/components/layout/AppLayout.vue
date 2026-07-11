<template>
  <div :class="['layout', { workspace: isWorkspace, compact: isCompactMode }]">
    <div v-if="sidebarOpen" class="sidebar-overlay" @click="sidebarOpen = false"></div>
    <AppSidebar :open="sidebarOpen" :compact="isWorkspace || isCompactMode" @navigate="handleNavigate" />
    <main :class="['main-column', { workspace: isWorkspace }]">
      <AppHeader
        :user="auth.user!"
        :compact="isWorkspace || isCompactMode"
        :sidebar-open="sidebarOpen"
        @toggle-menu="toggleSidebar"
        @logout="handleLogout"
      />
      <section :class="['content', { workspace: isWorkspace }]">
        <WorkspaceContent />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import WorkspaceContent from './WorkspaceContent.vue'
import { useAuthStore } from '../../stores/auth'
import { useUiDensity } from '../../composables/useUiDensity'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const sidebarOpen = ref(false)
const isWorkspace = computed(() => Boolean(route.meta.workspace))
const { isCompactMode } = useUiDensity()

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function handleNavigate() {
  sidebarOpen.value = false
}

async function handleLogout() {
  await auth.logout()
  await router.push({ name: 'login' })
}
</script>

<style scoped>
.layout {
  padding: 1rem;
  min-height: 100vh;
  overflow-x: clip;
}

.layout.workspace {
  padding: 0.75rem;
}

.main-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-height: calc(100vh - 2rem);
}

.main-column.workspace {
  gap: 0.75rem;
  min-height: calc(100vh - 1.5rem);
}

.content {
  min-width: 0;
  flex: 1 1 auto;
}

.content > * {
  min-width: 0;
}

.content.workspace {
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.content.workspace > * {
  flex: 1 1 auto;
  min-height: 0;
}

.sidebar-overlay {
  position: fixed;
  inset: 0;
  z-index: 35;
  background: rgba(25, 15, 8, 0.14);
  backdrop-filter: blur(2px);
}

@media (max-width: 767px) {
  .layout {
    padding: 0.75rem;
  }

  .sidebar-overlay {
    background: rgba(25, 15, 8, 0.32);
  }
}
</style>
