<template>
  <section class="panel panel-body">
    <h1>{{ saleTitles[kind] }}</h1>
    <p v-if="error" role="alert">{{ error }}</p>
    <nav class="toolbar"><RouterLink v-for="(title, key) in saleTitles" :key="key" :to="`/sales/${key}`">{{ title }}</RouterLink></nav>
    <div class="toolbar"><RouterLink v-if="auth.canWriteTrade" class="button button-primary" :to="`/sales/${kind}/new`">Создать документ</RouterLink><button class="button" @click="load">Обновить</button></div>
    <table><thead><tr><th>Номер</th><th>Дата</th><th>Организация</th><th>Контрагент</th><th>Договор</th><th>Сумма с НДС</th><th>Статус</th></tr></thead>
      <tbody><tr v-for="doc in documents" :key="doc.id"><td><RouterLink :to="`/sales/${kind}/${doc.id}`">{{ doc.number }}</RouterLink></td><td>{{ doc.date }}</td><td>{{ doc.organization_name }}</td><td>{{ doc.counterparty_name }}</td><td>{{ doc.contract_number }}</td><td>{{ money(doc.sum_with_vat) }}</td><td>{{ doc.is_posted ? (kind === 'orders' ? 'Подтвержден' : 'Проведен') : 'Черновик' }}</td></tr></tbody></table>
    <p v-if="!documents.length">Документов нет</p>
    <div class="toolbar"><button :disabled="page === 1" @click="page--; load()">Назад</button><span>Страница {{ page }} из {{ pages }}</span><button :disabled="page >= pages" @click="page++; load()">Далее</button></div>
    <template v-if="kind === 'realizations'"><h2>Выручка продаж</h2><p>Выручка без НДС: {{ money(expenses.reduce((sum, row) => sum + row.revenue_amount, 0)) }}</p>
      <table><thead><tr><th>Дата</th><th>Услуга</th><th>Договор</th><th>Выручка без НДС</th></tr></thead><tbody><tr v-for="row in expenses" :key="row.id"><td>{{ row.period }}</td><td>{{ row.name }}</td><td>{{ row.contract_id }}</td><td>{{ money(row.revenue_amount) }}</td></tr></tbody></table></template>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { listSales, salesRevenue, saleTitles, type SaleKind, type SaleDocument, type SaleRevenue } from '../../api/sales'
const props = defineProps<{ kind: SaleKind }>()
const auth = useAuthStore(), documents = ref<SaleDocument[]>([]), expenses = ref<SaleRevenue[]>([]), error = ref(''), page = ref(1), pages = ref(1)
const money = (value: number) => new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
async function load() {
  error.value = ''
  try { const result = await listSales(props.kind, page.value); documents.value = result.data; pages.value = result.pagination?.pages ?? 1; if (props.kind === 'realizations') expenses.value = (await salesRevenue()).data }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка загрузки' }
}
onMounted(load)
</script>
