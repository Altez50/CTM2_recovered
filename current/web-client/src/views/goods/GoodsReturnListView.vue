<template>
  <section class="card">
    <h1>Возвраты товаров</h1>
    <div class="toolbar">
      <button class="btn btn-primary" @click="router.push('/goods/returns/new')">Создать возврат</button>
      <button class="btn" :disabled="busy" @click="load">Обновить</button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <table class="table">
      <thead><tr><th>Номер</th><th>Дата</th><th>Вид</th><th>Основание</th><th>Организация</th><th>Контрагент</th><th>Сумма</th><th>Статус</th></tr></thead>
      <tbody><tr v-for="doc in documents" :key="doc.id">
        <td><RouterLink :to="`/goods/returns/${doc.id}`">{{ doc.number }}</RouterLink></td><td>{{ doc.date }}</td>
        <td>{{ doc.kind === 'customer' ? 'От клиента' : 'Поставщику' }}</td><td>{{ doc.source_number }}</td>
        <td>{{ doc.organization_name }}</td><td>{{ doc.counterparty_name }}</td><td>{{ doc.sum_with_vat.toFixed(2) }}</td><td>{{ doc.is_posted ? 'Проведен' : 'Черновик' }}</td>
      </tr></tbody>
    </table>
    <div class="toolbar"><button class="btn" :disabled="busy || page === 1" @click="page--; load()">Назад</button><span>{{ page }} / {{ pages }}</span><button class="btn" :disabled="busy || page >= pages" @click="page++; load()">Далее</button></div>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listReturns, type GoodsReturn } from '../../api/returns'
const router = useRouter()
const documents = ref<GoodsReturn[]>([])
const error = ref('')
const busy = ref(false)
const page = ref(1)
const pages = ref(1)
async function load() {
  busy.value = true
  error.value = ''
  try { const response = await listReturns(page.value); documents.value = response.data; pages.value = response.pagination?.pages ?? 1 }
  catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' }
  finally { busy.value = false }
}
onMounted(load)
</script>
