<template>
  <section class="card"><h1>Начальные остатки</h1>
    <RouterLink v-if="canWrite" class="button button-primary" to="/goods/opening-balances/new">Создать начальные остатки</RouterLink>
    <p v-if="error" role="alert">{{ error }}</p>
    <table class="data-table"><thead><tr><th>Номер</th><th>Дата начала</th><th>Организация</th><th>Статус</th></tr></thead>
      <tbody><tr v-for="doc in docs" :key="doc.id"><td><RouterLink :to="`/goods/opening-balances/${doc.id}`">{{ doc.number }}</RouterLink></td>
        <td>{{ doc.date }}</td><td>{{ doc.organization_name }}</td><td>{{ doc.is_posted ? 'Проведен' : 'Черновик' }}</td></tr></tbody></table>
    <button :disabled="page === 1" @click="page--; load()">Назад</button> {{ page }} / {{ pages }}
    <button :disabled="page >= pages" @click="page++; load()">Вперед</button>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { listOpenings, type OpeningBalance } from '../../api/openingBalances'
const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'manager'].includes(auth.user?.role ?? ''))
const docs = ref<OpeningBalance[]>([]), page = ref(1), pages = ref(1), error = ref('')
async function load() {
  try { const result = await listOpenings(page.value); docs.value = result.data; pages.value = result.pagination?.pages ?? 1 }
  catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' }
}
onMounted(load)
</script>
