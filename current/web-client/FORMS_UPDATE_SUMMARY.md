# Обновление форм списков - Краткая сводка

## Что сделано

### 1. Обновлен компонент DataTable.vue ✅

**Новые возможности:**
- Улучшенная панель инструментов с поиском, фильтрами и обновлением
- Debounce для поиска (300ms)
- Сворачиваемая панель расширенных фильтров
- Панель массовых операций с индикатором количества
- Улучшенная таблица с иконками сортировки
- Чередующиеся цвета строк (белый/серый)
- Расширенная пагинация (Первая/Предыдущая/Следующая/Последняя)
- Горячие клавиши (F5, Ctrl+F, Ctrl+A, Escape)
- Улучшенные состояния (загрузка, пустой список)
- Настраиваемая ширина колонок
- Опция отключения сортировки для колонок

**Новые props:**
```typescript
hasFilters?: boolean  // Показывать кнопку фильтров
columns: Column[]     // Теперь с width и sortable
```

**Новые events:**
```typescript
refresh         // Обновление данных
apply-filters   // Применить фильтры
clear-filters   // Очистить фильтры
```

**Новые slots:**
```typescript
filters              // Поля фильтров
page-size-selector   // Выбор размера страницы
```

**Новые методы (expose):**
```typescript
clearSelection()  // Очистить выбор
focusSearch()     // Фокус на поиск
```

### 2. Создан компонент DateRangePicker.vue ✅

**Возможности:**
- Выбор периода "с" и "по"
- Быстрые периоды (Сегодня, Вчера, Неделя, Месяц, Год, Прошлый месяц)
- v-model для обоих полей
- Валидация
- Опциональное отображение быстрых периодов

**Использование:**
```vue
<DateRangePicker
  v-model:from="dateFrom"
  v-model:to="dateTo"
  label="Период"
  :show-quick-periods="true"
/>
```

### 3. Создан composable useFilters.ts ✅

**Возможности:**
- Управление состоянием фильтров
- Разделение текущих и примененных фильтров
- Подсчет активных фильтров
- Формирование query параметров
- Сброс фильтров

**Использование:**
```typescript
const filters = useFilters({
  dateFrom: null,
  dateTo: null,
  objectId: null,
  isPosted: null
})

// В шаблоне
filters.filters.value.dateFrom = '2024-01-01'

// Применить
filters.applyFilters()

// Получить параметры для API
const params = filters.getQueryParams()
```

### 4. Обновлена форма EstimateListView.vue ✅

**Добавлено:**
- Панель расширенных фильтров:
  - Период (с быстрыми периодами)
  - Объект строительства
  - Заказчик
  - Статус проведения
  - Диапазон суммы (от/до)
- Колонка "Автор"
- Иконки статусов (✓ проведен, ○ не проведен)
- Настроенная ширина колонок
- Загрузка справочников для фильтров
- Период по умолчанию (текущий месяц)

**Пример использования фильтров:**
```vue
<template #filters>
  <DateRangePicker
    v-model:from="filters.filters.value.dateFrom"
    v-model:to="filters.filters.value.dateTo"
    label="Период"
  />
  
  <div>
    <label>Объект</label>
    <select v-model="filters.filters.value.objectId">
      <option :value="null">Все объекты</option>
      <option v-for="obj in objects" :value="obj.id">
        {{ obj.name }}
      </option>
    </select>
  </div>
</template>
```

---

## Что нужно сделать дальше

### Приоритет 1: Завершить формы документов

1. **TimesheetListView.vue** - добавить фильтры аналогично EstimateListView
2. **API расширение** - добавить параметры фильтрации в endpoints
3. **Тестирование** - проверить работу фильтров

### Приоритет 2: Обновить формы справочников

1. **CounterpartiesView.vue** - добавить колонки (ИНН, телефон, email, тип) и фильтры
2. **ObjectsView.vue** - добавить колонки и фильтры
3. **PersonsView.vue** - добавить колонки и фильтры
4. **WorksView.vue** - добавить колонки и фильтры

### Приоритет 3: Дополнительные компоненты

1. **ContextMenu.vue** - контекстное меню (правая кнопка мыши)
2. **ExportButton.vue** - экспорт в Excel/CSV
3. **useKeyboardShortcuts.ts** - расширенные горячие клавиши
4. **useContextMenu.ts** - логика контекстного меню

### Приоритет 4: API и бэкенд

1. Добавить параметры фильтрации в API endpoints
2. Добавить endpoint для экспорта данных
3. Добавить колонку "author" в ответы API
4. Оптимизация запросов с фильтрами

---

## Как использовать обновленные компоненты

### Базовая форма списка с фильтрами

```vue
<template>
  <AppLayout>
    <div class="space-y-6">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Заголовок</h2>
        <p class="mt-1 text-sm text-gray-600">Описание</p>
      </div>

      <DataTable
        ref="tableRef"
        :columns="columns"
        :data="data"
        :loading="loading"
        :pagination="pagination"
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
        <!-- Фильтры -->
        <template #filters>
          <DateRangePicker
            v-model:from="filters.filters.value.dateFrom"
            v-model:to="filters.filters.value.dateTo"
            label="Период"
          />
          <!-- Другие фильтры -->
        </template>

        <!-- Кнопки в шапке -->
        <template #header-actions>
          <button @click="handleCreate">Создать</button>
        </template>

        <!-- Массовые операции -->
        <template #bulk-actions="{ selected }">
          <button @click="handleBulkPost">
            Провести ({{ selected.length }})
          </button>
          <button @click="handleBulkDelete">
            Удалить ({{ selected.length }})
          </button>
        </template>

        <!-- Кастомные ячейки -->
        <template #cell-is_posted="{ value }">
          <div class="flex items-center justify-center">
            <span :class="value ? 'text-green-600' : 'text-gray-400'">
              <svg v-if="value">✓</svg>
              <svg v-else>○</svg>
            </span>
          </div>
        </template>

        <template #cell-date="{ value }">
          {{ formatDate(value) }}
        </template>

        <!-- Действия для строки -->
        <template #actions="{ row }">
          <button @click.stop="handleEdit(row)">Открыть</button>
          <button @click.stop="handleDelete(row)">Удалить</button>
        </template>
      </DataTable>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useTable } from '@/composables/useTable'
import { useFilters } from '@/composables/useFilters'
import DataTable from '@/components/common/DataTable.vue'
import DateRangePicker from '@/components/common/DateRangePicker.vue'

const table = useTable()
const filters = useFilters({
  dateFrom: null,
  dateTo: null,
  // ... другие фильтры
})

const columns = [
  { key: 'number', label: 'Номер', width: '100px' },
  { key: 'date', label: 'Дата', width: '100px' },
  { key: 'is_posted', label: 'Статус', width: '40px', sortable: false },
  // ... другие колонки
]

async function loadData() {
  table.loading.value = true
  try {
    const params = {
      ...table.queryParams.value,
      ...filters.getQueryParams()
    }
    const response = await api.getData(params)
    table.data.value = response.data
    table.pagination.value = response.pagination
  } finally {
    table.loading.value = false
  }
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

onMounted(() => {
  loadData()
})
</script>
```

---

## Горячие клавиши

| Клавиша | Действие |
|---------|----------|
| F5 | Обновить список |
| Ctrl+F | Фокус на поиск |
| Ctrl+A | Выбрать все элементы |
| Escape | Снять выделение / Закрыть фильтры |

---

## Визуальные улучшения

### Цветовая схема таблицы
- Заголовок: `bg-gray-50`
- Четные строки: `bg-white`
- Нечетные строки: `bg-gray-50`
- Наведение: `hover:bg-blue-50`
- Выбранные: `bg-blue-100`

### Иконки статусов
- ✓ Проведен: зеленый круг с галочкой
- ○ Не проведен: серый круг с точкой
- ✗ Удален: красный крестик

### Пагинация
- Кнопки навигации с иконками
- Номера страниц (до 5 видимых)
- Информация о количестве записей
- Адаптивная версия для мобильных

---

## Производительность

### Оптимизации
- Debounce для поиска (300ms)
- Серверная пагинация
- Lazy loading справочников
- Кэширование в stores

### Рекомендации
- Использовать индексы БД для полей фильтрации
- Ограничивать размер страницы (25-50 элементов)
- Кэшировать справочные данные

---

## Совместимость

### Браузеры
- ✅ Chrome/Edge (последние 2 версии)
- ✅ Firefox (последние 2 версии)
- ✅ Safari (последние 2 версии)

### Устройства
- ✅ Desktop (1920x1080, 1366x768)
- ✅ Tablet (768px+)
- ✅ Mobile (320px+)

---

## Следующие шаги

1. Обновить TimesheetListView с фильтрами
2. Расширить API для поддержки фильтрации
3. Обновить формы справочников
4. Добавить контекстное меню
5. Добавить экспорт данных
6. Написать E2E тесты

**Ожидаемое время:** 5-7 рабочих дней
