<template>
  <section class="card">
    <h1>Корректировки цен</h1>
    <div class="toolbar"><button v-if="canWrite" class="btn btn-primary" @click="router.push('/goods/price-adjustments/new')">Создать корректировку</button><button class="btn" :disabled="busy" @click="load">Обновить</button></div>
    <p v-if="error" role="alert">{{ error }}</p>
    <table class="table"><thead><tr><th>Номер</th><th>Дата</th><th>Вид</th><th>Основание</th><th>Организация</th><th>Контрагент</th><th>Изменение с НДС</th><th>Статус</th></tr></thead><tbody>
      <tr v-for="doc in documents" :key="doc.id"><td><RouterLink :to="`/goods/price-adjustments/${doc.id}`">{{ doc.number }}</RouterLink></td><td>{{ doc.date }}</td><td>{{ doc.kind === 'sale' ? 'Продажа' : 'Закупка' }}</td><td>{{ doc.source_number }}</td><td>{{ doc.organization_name }}</td><td>{{ doc.counterparty_name }}</td><td>{{ doc.delta_with_vat.toFixed(2) }}</td><td>{{ doc.is_posted ? 'Проведена' : 'Черновик' }}</td></tr>
    </tbody></table>
    <div class="toolbar"><button class="btn" :disabled="busy || page === 1" @click="page--; load()">Назад</button><span>{{ page }} / {{ pages }}</span><button class="btn" :disabled="busy || page >= pages" @click="page++; load()">Далее</button></div>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { listPriceAdjustments, type PriceAdjustment } from '../../api/priceAdjustments'
const router = useRouter()
const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'manager'].includes(auth.user?.role ?? ''))
const documents = ref<PriceAdjustment[]>([])
const page = ref(1)
const pages = ref(1)
const busy = ref(false)
const error = ref('')
async function load() {
  busy.value = true; error.value = ''
  try { const response = await listPriceAdjustments(page.value); documents.value = response.data; pages.value = response.pagination?.pages ?? 1 }
  catch (err) { error.value = err instanceof Error ? err.message : 'Ошибка загрузки' }
  finally { busy.value = false }
}
onMounted(load)
</script>
