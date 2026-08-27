<template>
  <div class="page-shell eng-view">
    <div class="toolbar eng-tabs">
      <button
        :class="['button', tab === 'browser' ? 'button-primary' : 'button-secondary']"
        type="button"
        @click="tab = 'browser'"
      >
        Просмотр таблиц
      </button>
      <button
        :class="['button', tab === 'console' ? 'button-primary' : 'button-secondary']"
        type="button"
        @click="tab = 'console'"
      >
        Консоль запросов
      </button>
      <span v-if="catalogError" class="muted" style="color: var(--danger)">{{ catalogError }}</span>
    </div>

    <div v-if="catalogLoading" class="empty-state">Загрузка каталога таблиц…</div>
    <template v-else>
      <TablesBrowser v-if="tab === 'browser'" :catalog="catalog" />
      <TablesConsole v-else :catalog="catalog" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import TablesBrowser from '../../components/engineering/TablesBrowser.vue'
import TablesConsole from '../../components/engineering/TablesConsole.vue'
import { getEngineeringCatalog, type EngineeringCatalog } from '../../api/engineering'

const tab = ref<'browser' | 'console'>('browser')
const catalog = ref<EngineeringCatalog | null>(null)
const catalogLoading = ref(true)
const catalogError = ref('')

async function loadCatalog() {
  catalogLoading.value = true
  catalogError.value = ''
  try {
    const resp = await getEngineeringCatalog()
    catalog.value = resp.data
  } catch (err) {
    catalogError.value = err instanceof Error ? err.message : 'Не удалось загрузить каталог таблиц'
  } finally {
    catalogLoading.value = false
  }
}

onMounted(loadCatalog)
</script>

<style scoped>
.eng-view {
  height: 100%;
  min-height: 0;
}
.eng-tabs {
  justify-content: flex-start;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
</style>
