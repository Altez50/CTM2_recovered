<template>
  <section class="panel panel-body">
    <h1>{{ purchaseTitles[kind] }}</h1>
    <p v-if="error" role="alert">{{ error }}</p>
    <nav class="toolbar"><RouterLink v-for="(title, key) in purchaseTitles" :key="key" :to="`/purchases/${key}`">{{ title }}</RouterLink></nav>
    <div class="toolbar"><RouterLink v-if="auth.canWriteTrade" class="button button-primary" :to="`/purchases/${kind}/new`">Создать документ</RouterLink><button class="button" @click="load">Обновить</button></div>
    <table><thead><tr><th>Номер</th><th>Дата</th><th>Организация</th><th>Контрагент</th><th>Договор</th><th>Сумма с НДС</th><th>Статус</th></tr></thead>
      <tbody><tr v-for="doc in documents" :key="doc.id"><td><RouterLink :to="`/purchases/${kind}/${doc.id}`">{{ doc.number }}</RouterLink></td><td>{{ doc.date }}</td><td>{{ doc.organization_name }}</td><td>{{ doc.counterparty_name }}</td><td>{{ doc.contract_number }}</td><td>{{ money(doc.sum_with_vat) }}</td><td>{{ doc.is_posted ? (kind === 'orders' ? 'Согласован' : 'Проведен') : 'Черновик' }}</td></tr></tbody></table>
    <p v-if="!documents.length">Документов нет</p>
    <div class="toolbar"><button :disabled="page === 1" @click="page--; load()">Назад</button><span>Страница {{ page }} из {{ pages }}</span><button :disabled="page >= pages" @click="page++; load()">Далее</button></div>
    <template v-if="kind === 'acquisitions'"><h2>Расходы услуг</h2><p>Расход без НДС: {{ money(expenses.reduce((sum, row) => sum + row.expense_amount, 0)) }}</p>
      <table><thead><tr><th>Дата</th><th>Услуга</th><th>Договор</th><th>Расход без НДС</th></tr></thead><tbody><tr v-for="row in expenses" :key="row.id"><td>{{ row.period }}</td><td>{{ row.name }}</td><td>{{ row.contract_id }}</td><td>{{ money(row.expense_amount) }}</td></tr></tbody></table></template>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { listPurchases, purchaseExpenses, purchaseTitles, type PurchaseKind, type PurchaseDocument, type PurchaseExpense } from '../../api/purchases'
const props = defineProps<{ kind: PurchaseKind }>()
const auth = useAuthStore(), documents = ref<PurchaseDocument[]>([]), expenses = ref<PurchaseExpense[]>([]), error = ref(''), page = ref(1), pages = ref(1)
const money = (value: number) => new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
async function load() {
  error.value = ''
  try { const result = await listPurchases(props.kind, page.value); documents.value = result.data; pages.value = result.pagination?.pages ?? 1; if (props.kind === 'acquisitions') expenses.value = (await purchaseExpenses()).data }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Ошибка загрузки' }
}
onMounted(load)
</script>
