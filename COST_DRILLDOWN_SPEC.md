# Спецификация механизма Drilldown — расшифровка итоговых записей отчётов себестоимости

Версия: 0.2
Обновлено: 2026-09-02
Статус реализации: **частично**. Три endpoint'а, диалог и точки входа в четырёх
отчётах существуют; составной факт с накладными, экспорт, индексы и acceptance-
тесты не закрыты. Проверено по коду: 2026-09-02 (`SPEC_REVIEW.md`).

---

## 1. Цель и область применения

### 1.1. Назначение

Drilldown — механизм последовательной расшифровки итоговых (агрегированных)
записей отчётов подсистемы «Себестоимость» до уровня исходных документов-
регистраторов. Пользователь кликает на итоговую строку (или ячейку) и видит
составляющие её движения, а из движения переходит к исходному документу.

### 1.2. Принцип

```
Отчёт (итоговая строка/ячейка)
  │  клик
  ▼
Список проводок (actual_costs / planned_costs / overhead_distribution)
  │  двойной клик
  ▼
Исходный документ-регистратор (смета, наряд, акт расхода ТМЦ, рапорт машин, ...)
```

### 1.3. Двухуровневая модель

| Уровень | Что показывает | Источник данных |
|---|---|---|
| **L1: Итог → Проводки** | Список движений регистра, составляющих итог | `actual_costs`, `planned_costs`, `overhead_distribution` |
| **L2: Проводка → Документ** | Переход к карточке исходного документа | `registrar_type` + `registrar_id` |

---

## 2. Отчёты и их drilldown-точки

### 2.1. Карточка себестоимости (`/reports/cost-card`)

**Параметры отчёта:** `object_id`, `period_from`, `period_to`.

#### Таблица 1 — «По элементам затрат» (CostElementSummary)

| Итоговая ячейка | L1-фильтр проводок | Регистр |
|---|---|---|
| `actual_amount` элемента X (кроме overhead) | `cost_element_id=X`, `object_id`, `period BETWEEN from AND to` | `actual_costs` |
| `actual_amount` элемента `kind=overhead` | `object_id`, `period BETWEEN from AND to` | `overhead_distribution` |
| `planned_amount` элемента X | `cost_element_id=X`, `object_id`, `period BETWEEN from AND to` | `planned_costs` |
| `deviation` (вычисляется) | не drilldown — разница | — |

#### Таблица 2 — «Детализация по работам» (WorkCostRow, из `completed_works_cost`)

| Итоговая ячейка | L1-фильтр проводок | Регистр |
|---|---|---|
| `actual_cost` работы X | `work_id=X`, `object_id`, `period` | `actual_costs` + `overhead_distribution` |
| `planned_cost` работы X | `work_id=X`, `object_id`, `period` | `planned_costs` |
| `contract_value`, `profit` | не drilldown — из `completed_works_cost` | — |

#### Итоговые карточки (total_*)

| Карточка | L1-фильтр | Регистр |
|---|---|---|
| `total_planned` | `object_id`, `period` | `planned_costs` |
| `total_actual` | `object_id`, `period` | `actual_costs` + `overhead_distribution` |
| `total_deviation` | не drilldown | — |

### 2.2. Оборотно-сальдовая ведомость (`/reports/cost-turnover`)

**Параметры отчёта:** `period_from`, `period_to`, `object_id`.

**Особенность:** drilldown на уровне **ячейки**, а не строки.

| Ячейка | L1-фильтр проводок | Регистр |
|---|---|---|
| `opening_balance` элемента X | `cost_element_id=X`, `period < period_from` | `actual_costs` |
| `inflow` элемента X | `cost_element_id=X`, `period BETWEEN from AND to`, `amount > 0` | `actual_costs` |
| `outflow` элемента X | `cost_element_id=X`, `period BETWEEN from AND to`, `amount < 0` | `actual_costs` |
| `closing_balance` | не drilldown — вычисляется | — |

### 2.3. Отчёт по отклонениям (`/reports/cost-deviations`)

**Параметры отчёта:** `period`, `threshold`, `object_id`.

| Строка | L1-фильтр проводок | Регистр |
|---|---|---|
| Работа X, `actual_amount` | `work_id=X`, `object_id`, `period` | `actual_costs` |
| Работа X, `planned_amount` | `work_id=X`, `object_id`, `period` | `planned_costs` |
| `deviation` | не drilldown — разница | — |

### 2.4. Рентабельность по объектам (`/reports/cost-profitability`)

**Параметры отчёта:** `period` (необязательный).

| Строка | L1-фильтр проводок | Регистр |
|---|---|---|
| Объект X, `actual_cost` | `object_id=X`, `period` | `actual_costs` + `overhead_distribution` |
| Объект X, `planned_cost` | `object_id=X`, `period` | `planned_costs` |
| `contract_value`, `profit` | не drilldown — из `completed_works_cost` | — |

---

## 3. Регистры и их структура

### 3.1. `actual_costs` — фактические затраты

```sql
CREATE TABLE actual_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,           -- YYYY-MM
    date TEXT,                      -- YYYY-MM-DD
    registrar_type TEXT NOT NULL,   -- тип документа-регистратора
    registrar_id INTEGER NOT NULL,  -- ID документа-регистратора
    object_id INTEGER,
    estimate_id INTEGER,
    work_id INTEGER,
    cost_element_id INTEGER NOT NULL,
    quantity REAL DEFAULT 0,
    amount REAL NOT NULL,
    created_at TEXT NOT NULL
);
```

**Поля для drilldown:**
- `registrar_type` + `registrar_id` — связь с исходным документом
- `cost_element_id` — фильтр по элементу затрат
- `work_id` — фильтр по работе
- `object_id` — фильтр по объекту
- `period` — фильтр по периоду

### 3.2. `planned_costs` — плановые затраты

```sql
CREATE TABLE planned_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    estimate_id INTEGER,
    object_id INTEGER,
    work_id INTEGER,
    cost_element_id INTEGER NOT NULL,
    planned_quantity REAL DEFAULT 0,
    planned_amount REAL NOT NULL,
    created_at TEXT NOT NULL
);
```

**Особенность:** нет `registrar_type`/`registrar_id` —源头 всегда смета.
Drilldown L2 для плана ведёт к смете (estimate) по `estimate_id`.

### 3.3. `overhead_distribution` — распределённые накладные расходы

```sql
CREATE TABLE overhead_distribution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    object_id INTEGER,
    estimate_id INTEGER,
    work_id INTEGER,
    amount REAL NOT NULL,
    allocation_base_id INTEGER,
    base_value REAL,
    created_at TEXT NOT NULL
);
```

**Особенность:** нет связи с конкретным документом — это результат распределения.
Drilldown L2 не применяется (уровень L1 — финальный).

### 3.4. `completed_works_cost` — себестоимость по работам (результат расчёта)

```sql
CREATE TABLE completed_works_cost (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    calculation_id INTEGER,
    object_id INTEGER,
    work_id INTEGER,
    completed_quantity REAL,
    planned_cost REAL,
    actual_cost REAL,
    deviation REAL,
    contract_value REAL,
    profit REAL,
    created_at TEXT NOT NULL
);
```

**Особенность:** это материализованный результат, не регистр.
Drilldown ведёт **к** `actual_costs`/`planned_costs` по `work_id` + `object_id` + `period`.

---

## 4. Связь проводок с исходными документами (L2)

### 4.1. Реестр регистраторов `actual_costs`

| `registrar_type` | Исходный документ | Маршрут фронтенда | API |
|---|---|---|---|
| `MaterialConsumption` | Акт расхода ТМЦ | `/documents/material-consumptions/{id}` | `GET /api/cost/material-consumptions/{id}` |
| `MachineryUsageReport` | Рапорт о работе машин | `/documents/machinery-usage/{id}` | `GET /api/cost/machinery-usage-reports/{id}` |
| `SubcontractAcceptance` | Акт приёмки субподряда | `/documents/subcontract-acceptances/{id}` | `GET /api/cost/subcontract-acceptances/{id}` |
| `Timesheet` | Табель | `/documents/timesheets/{id}` | `GET /api/documents/timesheets/{id}` |
| `DailyReport` | Наряд (дневной отчёт) | `/documents/daily-reports/{id}` | `GET /api/documents/daily-reports/{id}` |

### 4.2. Реестр регистраторов `planned_costs`

Источник — всегда смета (`estimate_id`).

| Параметр | Маршрут | API |
|---|---|---|
| `estimate_id` | `/documents/estimates/{id}` | `GET /api/documents/estimates/{id}` |

---

## 5. Требования к бэкенду

### 5.1. Endpoint drilldown L1 (список проводок)

```
GET /api/cost/drilldown/actual-costs
```

**Параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `period_from` | str (YYYY-MM) | Начало периода |
| `period_to` | str (YYYY-MM) | Конец периода |
| `period_before` | str (YYYY-MM) | Периоды ДО указанного (для opening_balance) |
| `object_id` | int | Объект |
| `cost_element_id` | int | Элемент затрат |
| `work_id` | int | Работа |
| `estimate_id` | int | Смета |
| `amount_sign` | str | Фильтр по знаку суммы: `positive` / `negative` |
| `registrar_type` | str | Фильтр по типу регистратора |
| `page` | int | Страница (default 1) |
| `page_size` | int | Размер страницы (default 50, max 500) |

**Ответ:**

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "period": "2026-01",
        "date": "2026-01-15",
        "registrar_type": "MaterialConsumption",
        "registrar_id": 42,
        "registrar_number": "М-0001",
        "object_id": 1,
        "object_name": "Объект А",
        "work_id": 3,
        "work_name": "Кладка стен",
        "cost_element_id": 1,
        "cost_element_name": "Материалы",
        "quantity": 100.0,
        "amount": 50000.0
      }
    ],
    "totals": {
      "quantity": 100.0,
      "amount": 50000.0
    }
  }
}
```

### 5.2. Endpoint drilldown для плановых затрат

```
GET /api/cost/drilldown/planned-costs
```

Те же параметры, кроме `amount_sign` и `registrar_type`.
Добавляется поле `registrar_number` = номер сметы.

### 5.3. Endpoint drilldown для накладных

```
GET /api/cost/drilldown/overhead
```

Параметры: `period_from`, `period_to`, `object_id`, `work_id`.

### 5.4. Реализация

Сервисные функции (в `cost_accounting_services.py`):

```python
def get_actual_costs_drilldown(
    connection, *, period_from, period_to, object_id=None,
    cost_element_id=None, work_id=None, estimate_id=None,
    amount_sign=None, registrar_type=None, page=1, page_size=50,
) -> tuple[list[dict], Pagination, dict[str, float]]:
    ...

def get_planned_costs_drilldown(
    connection, *, period_from, period_to, object_id=None,
    cost_element_id=None, work_id=None, estimate_id=None,
    page=1, page_size=50,
) -> tuple[list[dict], Pagination, dict[str, float]]:
    ...

def get_overhead_drilldown(
    connection, *, period_from, period_to, object_id=None,
    work_id=None, page=1, page_size=50,
) -> tuple[list[dict], Pagination, dict[str, float]]:
    ...
```

SQL-запрос `actual_costs` drilldown (базовый):

```sql
SELECT
    ac.*,
    o.name AS object_name,
    w.name AS work_name,
    ce.name AS cost_element_name,
    CASE ac.registrar_type
        WHEN 'MaterialConsumption' THEN mc.number
        WHEN 'MachineryUsageReport' THEN mu.number
        WHEN 'SubcontractAcceptance' THEN sa.number
        WHEN 'Timesheet' THEN ts.number
        WHEN 'DailyReport' THEN dr.number
    END AS registrar_number
FROM actual_costs ac
LEFT JOIN objects o ON o.id = ac.object_id
LEFT JOIN works w ON w.id = ac.work_id
LEFT JOIN cost_elements ce ON ce.id = ac.cost_element_id
LEFT JOIN material_consumptions mc
    ON ac.registrar_type = 'MaterialConsumption' AND mc.id = ac.registrar_id
LEFT JOIN machinery_usage_reports mu
    ON ac.registrar_type = 'MachineryUsageReport' AND mu.id = ac.registrar_id
LEFT JOIN subcontract_acceptances sa
    ON ac.registrar_type = 'SubcontractAcceptance' AND sa.id = ac.registrar_id
LEFT JOIN timesheets ts
    ON ac.registrar_type = 'Timesheet' AND ts.id = ac.registrar_id
LEFT JOIN daily_reports dr
    ON ac.registrar_type = 'DailyReport' AND dr.id = ac.registrar_id
WHERE ac.period >= ? AND ac.period <= ?
  AND (? IS NULL OR ac.object_id = ?)
  AND (? IS NULL OR ac.cost_element_id = ?)
  AND (? IS NULL OR ac.work_id = ?)
  AND (? IS NULL OR ac.registrar_type = ?)
  AND (? IS NULL OR ac.amount > 0 OR ac.amount < 0)
ORDER BY ac.period DESC, ac.id DESC
LIMIT ? OFFSET ?
```

---

## 6. Требования к фронтенду

### 6.1. Компонент `CostDrilldownDialog.vue`

Универсальное модальное окно для отображения проводок любого регистра.

**Props:**

```ts
interface DrilldownProps {
  open: boolean
  title: string           // «Расшифровка: Материалы — Объект А»
  register: 'actual' | 'planned' | 'overhead'
  filters: {              // L1-фильтры, вычисленные из контекста клика
    period_from?: string
    period_to?: string
    period_before?: string
    object_id?: number
    cost_element_id?: number
    work_id?: number
    estimate_id?: number
    amount_sign?: 'positive' | 'negative'
    registrar_type?: string
  }
}
```

**Поведение:**
1. При открытии загружает проводки через соответствующий drilldown endpoint.
2. Таблица: Период, Дата, Регистратор, Работа, Элемент затрат, Количество, Сумма.
3. Колонка «Регистратор» — кликабельная ссылка на документ (L2).
4. Пагинация серверная.
5. Итоги внизу (сумма количества и суммы).
6. Для итогов, включающих прямые и накладные затраты, диалог показывает обе
   составляющие (две секции либо единый список с `source_register`). Сумма строк
   обязана совпадать со значением ячейки, из которой открыт drilldown.
7. Ошибка загрузки показывается пользователю и не маскируется как пустой результат.

### 6.2. Интерактивность в отчётах

**Кликабельные элементы:**

| Отчёт | Элемент | Действие |
|---|---|---|
| CostCard | Ячейка `actual_amount` (таблица элементов) | Открыть drilldown actual_costs с фильтрами |
| CostCard | Ячейка `planned_amount` (таблица элементов) | Открыть drilldown planned_costs |
| CostCard | Ячейка `actual_cost` (таблица работ) | Открыть drilldown actual_costs (с work_id) |
| CostTurnover | Ячейка `opening_balance` | Drilldown actual_costs, `period_before` |
| CostTurnover | Ячейка `inflow` | Drilldown actual_costs, `amount_sign=positive` |
| CostTurnover | Ячейка `outflow` | Drilldown actual_costs, `amount_sign=negative` |
| CostDeviations | Ячейка `actual_amount` | Drilldown actual_costs (с work_id) |
| CostProfitability | Ячейка `actual_cost` | Drilldown actual_costs (с object_id) |

**Визуальный отклик:**
- Кликабельные ячейки подчёркнуты пунктиром или выделены цветом (hover).
- Курсор `pointer`.
- Tooltip: «Расшифровать».

### 6.3. Переход к документу (L2)

Двойной клик по строке проводки (или клик на ссылке в колонке «Регистратор»):

```ts
function openRegistrar(row: DrilldownItem) {
  const routeMap: Record<string, string> = {
    MaterialConsumption: '/documents/material-consumptions/',
    MachineryUsageReport: '/documents/machinery-usage/',
    SubcontractAcceptance: '/documents/subcontract-acceptances/',
    Timesheet: '/documents/timesheets/',
    DailyReport: '/documents/daily-reports/',
  }
  const base = routeMap[row.registrar_type]
  if (base) router.push(base + row.registrar_id)
}
```

### 6.4. API-клиент

Добавить в `api/costAccounting.ts`:

```ts
export function getActualCostsDrilldown(params: DrilldownQuery) {
  return apiRequest<ApiResponse<DrilldownResponse>>('/api/cost/drilldown/actual-costs', { params })
}
export function getPlannedCostsDrilldown(params: DrilldownQuery) {
  return apiRequest<ApiResponse<DrilldownResponse>>('/api/cost/drilldown/planned-costs', { params })
}
export function getOverheadDrilldown(params: DrilldownQuery) {
  return apiRequest<ApiResponse<DrilldownResponse>>('/api/cost/drilldown/overhead', { params })
}
```

### 6.5. Типы

```ts
export interface DrilldownQuery {
  period_from?: string
  period_to?: string
  period_before?: string
  object_id?: number
  cost_element_id?: number
  work_id?: number
  estimate_id?: number
  amount_sign?: 'positive' | 'negative'
  registrar_type?: string
  page?: number
  page_size?: number
}

export interface DrilldownItem {
  id: number
  period: string
  date?: string
  registrar_type: string
  registrar_id: number
  registrar_number?: string
  object_id?: number
  object_name?: string
  work_id?: number
  work_name?: string
  cost_element_id: number
  cost_element_name: string
  quantity: number
  amount: number
}

export interface DrilldownResponse {
  items: DrilldownItem[]
  totals: { quantity: number; amount: number }
}
```

Пагинация передаётся в стандартном верхнеуровневом поле `ApiResponse.pagination`,
а не внутри `DrilldownResponse`.

---

## 7. Предопределённые элементы затрат

Из `COST_ELEMENT_KINDS` в `services.py`:

| `kind` | Наименование | Источник факта |
|---|---|---|
| `materials` | Материалы | `MaterialConsumption` |
| `labor` | Основная заработная плата | `Timesheet` / `DailyReport` |
| `machinery` | Эксплуатация машин и механизмов | `MachineryUsageReport` |
| `subcontract` | Субподрядные работы | `SubcontractAcceptance` |
| `overhead` | Накладные расходы | `overhead_distribution` |
| `other_direct` | Прочие прямые затраты | (различные) |

---

## 8. Критерии приёмки

1. В отчёте «Карточка себестоимости» клик на ячейке `actual_amount` элемента
   затрат открывает модальное окно со списком проводок `actual_costs` для этого
   элемента, объекта и периода.
2. В отчёте «Оборотно-сальдовая ведомость» клик на ячейке `inflow` открывает
   список проводок с положительными суммами; клик на `outflow` — с
   отрицательными; клик на `opening_balance` — проводки до начала периода.
3. Двойной клик на проводке открывает исходный документ (акт расхода ТМЦ,
   рапорт машин и т.д.).
4. Drilldown корректно работает при фильтрации отчёта по объекту.
5. Пагинация drilldown работает серверно.
6. Колонка «Регистратор» показывает номер документа и является ссылкой.
7. Drilldown фактической себестоимости работы/объекта включает прямые затраты и
   распределённые накладные; сумма расшифровки точно равна исходной ячейке.
8. Ошибка API отображается как ошибка, а не как «нет данных».
9. Регресс: существующие функции отчётов не сломаны.

---

## 9. Открытые вопросы

| № | Вопрос | Варианты / предложение |
|---|---|---|
| О1 | Drilldown для `completed_works_cost.contract_value` и `profit` | Нет источника в actual_costs — перейти к списку расчётов? |
| О2 | Индексы для производительности | Добавить индексы на `actual_costs(cost_element_id, period)`, `actual_costs(work_id, period)` |
| О3 | Множественный drilldown (несколько уровней) | Текущая модель — 2 уровня. Расширение — отдельная итерация. |
| О4 | Экспорт drilldown в Excel | Переиспользовать механизм экспорта из Регистра работ |
| О5 | Drilldown из Регистра работ → actual_costs | Регистр работ сейчас не связан с actual_costs напрямую |

---

## 10. История изменений

| Версия | Дата | Изменения |
|---|---|---|
| 0.1 | 2026-08-01 | Первичная спецификация: двухуровневая модель, 4 отчёта, 3 drilldown-endpoint'а, CostDrilldownDialog. |
| 0.2 | 2026-09-02 | Зафиксирован частичный статус; устранено противоречие по overhead, добавлены reconciliation и error-state требования. |
