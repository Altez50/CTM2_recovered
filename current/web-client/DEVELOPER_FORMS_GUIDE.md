# Руководство разработчика: Формы списков

## Быстрый старт

### 1. Создание простой формы списка

```vue
<template>
  <AppLayout>
    <DataTable
      :columns="columns"
      :data="table.data.value"
      :loading="table.loading.value"
      :pagination="table.pagination.value"
      @row-click="handleEdit"
      @page-change="handlePageChange"
      @search="handleSearch"
      @sort="handleSort"
      @refresh="loadData"
    >
      <template #header-actions>
        <button @click="handleCreate">Создать</button>
      </template>
    </DataTable>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTable } from '@/composables/useTable'
import * as api from '@/api/myapi'

const router = useRouter()
const table = useTable()

const columns = [
  { key: 'id', label: 'ID', width: '80px' },
  { key: 'name', label: 'Наименование' },
]

async function loadData() {
  table.loading.value = true
  try {
    const response = await api.getItems(table.queryParams.value)
    table.data.value = response.data
    table.pagination.value = response.pagination
  } finally {
    table.loading.value = false
  }
}

function handlePageChange(page: number) {
  table.setPage(page)
  loadData()
}

function handleSearch(query: string) {
  table.setSearch(query)
  loadData()
}

function handleSort(sortBy: string, sortOrder: 'asc' | 'desc') {
  table.setSort(sortBy, sortOrder)
  loadData()
}

function handleCreate() {
  router.push('/items/new')
}

function handleEdit(item: any) {
  router.push(`/items/${item.id}`)
}

onMounted(() => {
  loadData()
})
</script>
```

---

## 2. Добавление фильтров

### Шаг 1: Подключить useFilters

```typescript
import { useFilters } from '@/composables/useFilters'

const filters = useFilters({
  dateFrom: null as string | null,
  dateTo: null as string | null,
  status: null as string | null,
  categoryId: null as number | null,
})
```

### Шаг 2: Добавить has-filters в DataTable

```vue
<DataTable
  :has-filters="true"
  @apply-filters="handleApplyFilters"
  @clear-filters="handleClearFilters"
>
```

### Шаг 3: Добавить слот filters

```vue
<template #filters>
  <!-- Период -->
  <DateRangePicker
    v-model:from="filters.filters.value.dateFrom"
    v-model:to="filters.filters.value.dateTo"
    label="Период"
  />
  
  <!-- Статус -->
  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">
      Статус
    </label>
    <select
      v-model="filters.filters.value.status"
      class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 text-sm"
    >
      <option :value="null">Все</option>
      <option value="active">Активные</option>
      <option value="inactive">Неактивные</option>
    </select>
  </div>
  
  <!-- Категория -->
  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">
      Категория
    </label>
    <select
      v-model="filters.filters.value.categoryId"
      class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 text-sm"
    >
      <option :value="null">Все категории</option>
      <option v-for="cat in categories" :key="cat.id" :value="cat.id">
        {{ cat.name }}
      </option>
    </select>
  </div>
</template>
```

### Шаг 4: Обработчики фильтров

```typescript
function handleApplyFilters() {
  filters.applyFilters()
  table.setPage(1) // Сброс на первую страницу
  loadData()
}

function handleClearFilters() {
  filters.clearAllFilters()
  table.setPage(1)
  loadData()
}

// В loadData добавить фильтры
async function loadData() {
  table.loading.value = true
  try {
    const params = {
      ...table.queryParams.value,
      ...filters.getQueryParams() // Добавить параметры фильтров
    }
    const response = await api.getItems(params)
    table.data.value = response.data
    table.pagination.value = response.pagination
  } finally {
    table.loading.value = false
  }
}
```

---

## 3. Массовые операции

### Шаг 1: Включить selectable

```vue
<DataTable
  :selectable="true"
  @selection-change="handleSelectionChange"
>
```

### Шаг 2: Добавить слот bulk-actions

```vue
<template #bulk-actions="{ selected }">
  <button
    @click="handleBulkDelete"
    class="px-3 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
  >
    Удалить ({{ selected.length }})
  </button>
  
  <button
    @click="handleBulkActivate"
    class="px-3 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
  >
    Активировать ({{ selected.length }})
  </button>
</template>
```

### Шаг 3: Обработчики

```typescript
const tableRef = ref<InstanceType<typeof DataTable>>()
const selectedItems = ref<any[]>([])

function handleSelectionChange(items: any[]) {
  selectedItems.value = items
}

async function handleBulkDelete() {
  if (selectedItems.value.length === 0) return
  
  if (!confirm(`Удалить выбранные элементы (${selectedItems.value.length})?`)) {
    return
  }

  try {
    const ids = selectedItems.value.map(item => item.id)
    const result = await api.bulkDelete(ids)
    
    if (result.errors.length > 0) {
      alert(`${result.message}\n\nОшибки:\n${result.errors.join('\n')}`)
    } else {
      alert(result.message)
    }
    
    tableRef.value?.clearSelection()
    await loadData()
  } catch (error: any) {
    alert(error.response?.data?.detail || 'Ошибка при удалении')
  }
}
```

---

## 4. Кастомные ячейки

### Иконки статусов

```vue
<template #cell-is_posted="{ value }">
  <div class="flex items-center justify-center">
    <span
      :class="[
        'inline-flex items-center justify-center w-6 h-6 rounded-full',
        value ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'
      ]"
      :title="value ? 'Проведен' : 'Не проведен'"
    >
      <!-- Галочка -->
      <svg v-if="value" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
      </svg>
      <!-- Кружок -->
      <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <circle cx="10" cy="10" r="3" />
      </svg>
    </span>
  </div>
</template>
```

### Форматирование даты

```vue
<template #cell-date="{ value }">
  {{ formatDate(value) }}
</template>

<script setup lang="ts">
function formatDate(dateString: string): string {
  if (!dateString) return '—'
  return new Date(dateString).toLocaleDateString('ru-RU')
}
</script>
```

### Форматирование чисел

```vue
<template #cell-amount="{ value }">
  {{ formatNumber(value) }}
</template>

<script setup lang="ts">
function formatNumber(value: number): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}
</script>
```

### Бейджи

```vue
<template #cell-status="{ value }">
  <span
    :class="[
      'px-2 py-1 text-xs font-semibold rounded-full',
      value === 'active' ? 'bg-green-100 text-green-800' :
      value === 'pending' ? 'bg-yellow-100 text-yellow-800' :
      'bg-gray-100 text-gray-800'
    ]"
  >
    {{ getStatusLabel(value) }}
  </span>
</template>

<script setup lang="ts">
function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: 'Активен',
    pending: 'Ожидает',
    inactive: 'Неактивен'
  }
  return labels[status] || status
}
</script>
```

---

## 5. Действия для строк

```vue
<template #actions="{ row }">
  <div class="flex gap-2">
    <button
      @click.stop="handleEdit(row)"
      class="text-blue-600 hover:text-blue-900"
    >
      Изменить
    </button>
    <button
      v-if="!row.is_deleted"
      @click.stop="handleDelete(row)"
      class="text-red-600 hover:text-red-900"
    >
      Удалить
    </button>
    <button
      v-if="row.can_post && !row.is_posted"
      @click.stop="handlePost(row)"
      class="text-green-600 hover:text-green-900"
    >
      Провести
    </button>
  </div>
</template>
```

---

## 6. Настройка колонок

### Базовая конфигурация

```typescript
const columns = [
  { 
    key: 'id', 
    label: 'ID', 
    width: '80px',
    sortable: true  // По умолчанию true
  },
  { 
    key: 'name', 
    label: 'Наименование',
    width: '300px'
  },
  { 
    key: 'status', 
    label: 'Статус',
    width: '120px',
    sortable: false  // Отключить сортировку
  },
]
```

### Рекомендуемые ширины

| Тип данных | Ширина |
|------------|--------|
| ID | 80-100px |
| Код | 100-120px |
| Номер документа | 100-120px |
| Дата | 100-120px |
| Иконка/Статус | 40-60px |
| Сумма | 120-150px |
| Короткий текст | 150-200px |
| Средний текст | 200-300px |
| Длинный текст | 300-400px |
| Email | 200-250px |
| Телефон | 150px |

---

## 7. Загрузка справочников для фильтров

```typescript
import { useReferencesStore } from '@/stores/references'

const referencesStore = useReferencesStore()
const objects = ref<any[]>([])
const categories = ref<any[]>([])

async function loadReferences() {
  try {
    await Promise.all([
      referencesStore.fetchConstructionObjects(),
      referencesStore.fetchCategories()
    ])
    
    objects.value = referencesStore.constructionObjects
    categories.value = referencesStore.categories
  } catch (error) {
    console.error('Failed to load references:', error)
  }
}

onMounted(async () => {
  await loadReferences()
  loadData()
})
```

---

## 8. Период по умолчанию (для документов)

```typescript
onMounted(async () => {
  await loadReferences()
  
  // Установить текущий месяц
  const today = new Date()
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1)
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  
  filters.filters.value.dateFrom = formatDate(firstDay)
  filters.filters.value.dateTo = formatDate(lastDay)
  filters.applyFilters()
  
  loadData()
})

function formatDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
```

---

## 9. Обработка ошибок

```typescript
async function loadData() {
  table.loading.value = true
  try {
    const params = {
      ...table.queryParams.value,
      ...filters.getQueryParams()
    }
    const response = await api.getItems(params)
    table.data.value = response.data
    table.pagination.value = response.pagination
  } catch (error: any) {
    console.error('Failed to load data:', error)
    
    // Показать уведомление пользователю
    const message = error.response?.data?.detail || 'Ошибка при загрузке данных'
    alert(message) // Или использовать toast/notification
  } finally {
    table.loading.value = false
  }
}
```

---

## 10. Полный пример формы документа

```vue
<template>
  <AppLayout>
    <div class="space-y-6">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Документы</h2>
        <p class="mt-1 text-sm text-gray-600">Управление документами</p>
      </div>

      <DataTable
        ref="tableRef"
        :columns="columns"
        :data="table.data.value"
        :loading="table.loading.value"
        :pagination="table.pagination.value"
        :selectable="true"
        :has-filters="true"
        @row-click="handleEdit"
        @page-change="handlePageChange"
        @search="handleSearch"
        @sort="handleSort"
        @selection-change="handleSelectionChange"
        @refresh="loadData"
        @apply-filters="handleApplyFilters"
        @clear-filters="handleClearFilters"
      >
        <template #filters>
          <DateRangePicker
            v-model:from="filters.filters.value.dateFrom"
            v-model:to="filters.filters.value.dateTo"
            label="Период"
          />
          
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Объект
            </label>
            <select
              v-model="filters.filters.value.objectId"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option :value="null">Все объекты</option>
              <option v-for="obj in objects" :key="obj.id" :value="obj.id">
                {{ obj.name }}
              </option>
            </select>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Статус
            </label>
            <select
              v-model="filters.filters.value.isPosted"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option :value="null">Все</option>
              <option :value="true">Проведенные</option>
              <option :value="false">Не проведенные</option>
            </select>
          </div>
        </template>

        <template #header-actions>
          <button
            @click="handleCreate"
            class="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            <svg class="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            Создать
          </button>
        </template>

        <template #bulk-actions="{ selected }">
          <button
            @click="handleBulkPost"
            class="px-3 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
          >
            Провести ({{ selected.length }})
          </button>
          <button
            @click="handleBulkUnpost"
            class="px-3 py-2 bg-yellow-600 text-white rounded-md hover:bg-yellow-700"
          >
            Отменить ({{ selected.length }})
          </button>
          <button
            @click="handleBulkDelete"
            class="px-3 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
          >
            Удалить ({{ selected.length }})
          </button>
        </template>

        <template #cell-date="{ value }">
          {{ formatDate(value) }}
        </template>

        <template #cell-is_posted="{ value }">
          <div class="flex items-center justify-center">
            <span
              :class="[
                'inline-flex items-center justify-center w-6 h-6 rounded-full',
                value ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'
              ]"
              :title="value ? 'Проведен' : 'Не проведен'"
            >
              <svg v-if="value" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
              </svg>
              <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <circle cx="10" cy="10" r="3" />
              </svg>
            </span>
          </div>
        </template>

        <template #cell-total_sum="{ value }">
          {{ formatNumber(value) }}
        </template>

        <template #actions="{ row }">
          <button
            @click.stop="handleEdit(row)"
            class="text-blue-600 hover:text-blue-900 mr-4"
          >
            Открыть
          </button>
          <button
            v-if="!row.is_posted"
            @click.stop="handleDelete(row)"
            class="text-red-600 hover:text-red-900"
          >
            Удалить
          </button>
        </template>
      </DataTable>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useTable } from '@/composables/useTable'
import { useFilters } from '@/composables/useFilters'
import { useReferencesStore } from '@/stores/references'
import * as api from '@/api/documents'
import type { Document } from '@/types/models'
import AppLayout from '@/components/layout/AppLayout.vue'
import DataTable from '@/components/common/DataTable.vue'
import DateRangePicker from '@/components/common/DateRangePicker.vue'

const router = useRouter()
const table = useTable()
const referencesStore = useReferencesStore()
const tableRef = ref<InstanceType<typeof DataTable>>()
const selectedItems = ref<Document[]>([])

const filters = useFilters({
  dateFrom: null as string | null,
  dateTo: null as string | null,
  objectId: null as number | null,
  isPosted: null as boolean | null,
})

const objects = ref<any[]>([])

const columns = [
  { key: 'number', label: 'Номер', width: '100px' },
  { key: 'date', label: 'Дата', width: '100px' },
  { key: 'is_posted', label: 'Статус', width: '40px', sortable: false },
  { key: 'object_name', label: 'Объект', width: '250px' },
  { key: 'total_sum', label: 'Сумма', width: '120px' },
  { key: 'author', label: 'Автор', width: '150px' },
]

async function loadReferences() {
  try {
    await referencesStore.fetchConstructionObjects()
    objects.value = referencesStore.constructionObjects
  } catch (error) {
    console.error('Failed to load references:', error)
  }
}

async function loadData() {
  table.loading.value = true
  try {
    const params = {
      ...table.queryParams.value,
      ...filters.getQueryParams()
    }
    const response = await api.getDocuments(params)
    table.data.value = response.data
    table.pagination.value = response.pagination
  } catch (error: any) {
    console.error('Failed to load documents:', error)
    alert(error.response?.data?.detail || 'Ошибка при загрузке')
  } finally {
    table.loading.value = false
  }
}

function handlePageChange(page: number) {
  table.setPage(page)
  loadData()
}

function handleSearch(query: string) {
  table.setSearch(query)
  loadData()
}

function handleSort(sortBy: string, sortOrder: 'asc' | 'desc') {
  table.setSort(sortBy, sortOrder)
  loadData()
}

function handleApplyFilters() {
  filters.applyFilters()
  table.setPage(1)
  loadData()
}

function handleClearFilters() {
  filters.clearAllFilters()
  table.setPage(1)
  loadData()
}

function handleCreate() {
  router.push('/documents/new')
}

function handleEdit(item: Document) {
  router.push(`/documents/${item.id}`)
}

async function handleDelete(item: Document) {
  if (!confirm(`Удалить документ ${item.number}?`)) return

  try {
    await api.deleteDocument(item.id!)
    await loadData()
  } catch (error: any) {
    alert(error.response?.data?.detail || 'Ошибка при удалении')
  }
}

function handleSelectionChange(items: Document[]) {
  selectedItems.value = items
}

async function handleBulkPost() {
  if (selectedItems.value.length === 0) return
  if (!confirm(`Провести выбранные документы (${selectedItems.value.length})?`)) return

  try {
    const ids = selectedItems.value.map(item => item.id!)
    const result = await api.bulkPost(ids)
    
    if (result.errors.length > 0) {
      alert(`${result.message}\n\nОшибки:\n${result.errors.join('\n')}`)
    } else {
      alert(result.message)
    }
    
    tableRef.value?.clearSelection()
    await loadData()
  } catch (error: any) {
    alert(error.response?.data?.detail || 'Ошибка при проведении')
  }
}

async function handleBulkUnpost() {
  if (selectedItems.value.length === 0) return
  if (!confirm(`Отменить проведение (${selectedItems.value.length})?`)) return

  try {
    const ids = selectedItems.value.map(item => item.id!)
    const result = await api.bulkUnpost(ids)
    
    if (result.errors.length > 0) {
      alert(`${result.message}\n\nОшибки:\n${result.errors.join('\n')}`)
    } else {
      alert(result.message)
    }
    
    tableRef.value?.clearSelection()
    await loadData()
  } catch (error: any) {
    alert(error.response?.data?.detail || 'Ошибка при отмене')
  }
}

async function handleBulkDelete() {
  if (selectedItems.value.length === 0) return
  if (!confirm(`Удалить выбранные документы (${selectedItems.value.length})?`)) return

  try {
    const ids = selectedItems.value.map(item => item.id!)
    const result = await api.bulkDelete(ids)
    
    if (result.errors.length > 0) {
      alert(`${result.message}\n\nОшибки:\n${result.errors.join('\n')}`)
    } else {
      alert(result.message)
    }
    
    tableRef.value?.clearSelection()
    await loadData()
  } catch (error: any) {
    alert(error.response?.data?.detail || 'Ошибка при удалении')
  }
}

function formatDate(dateString: string): string {
  if (!dateString) return '—'
  return new Date(dateString).toLocaleDateString('ru-RU')
}

function formatNumber(value: number): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

onMounted(async () => {
  await loadReferences()
  
  // Установить текущий месяц
  const today = new Date()
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1)
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  
  filters.filters.value.dateFrom = formatDate(firstDay)
  filters.filters.value.dateTo = formatDate(lastDay)
  filters.applyFilters()
  
  loadData()
})

function formatDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
</script>
```

---

## Чек-лист для новой формы

- [ ] Импортировать необходимые компоненты и composables
- [ ] Настроить useTable и useFilters
- [ ] Определить колонки с правильными ширинами
- [ ] Добавить фильтры (если нужны)
- [ ] Реализовать loadData с обработкой ошибок
- [ ] Добавить обработчики пагинации, поиска, сортировки
- [ ] Добавить кастомные ячейки (даты, числа, статусы)
- [ ] Добавить массовые операции (если нужны)
- [ ] Добавить действия для строк
- [ ] Загрузить справочники для фильтров
- [ ] Установить период по умолчанию (для документов)
- [ ] Протестировать все функции

---

## Полезные ссылки

- [Требования к формам списков](../docs/ТРЕБОВАНИЯ_К_ФОРМАМ_СПИСКОВ.md)
- [План реализации](./FORMS_REQUIREMENTS_IMPLEMENTATION.md)
- [Краткая сводка](./FORMS_UPDATE_SUMMARY.md)
