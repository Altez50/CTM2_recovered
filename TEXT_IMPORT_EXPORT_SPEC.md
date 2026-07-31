# Спецификация обмена данными документов (TSV / JSON / XLSX)

Обновлено: 2026-07-16

---

## 1. Текущее состояние (AS-IS)

### 1.1. Единый модуль обмена данными — РЕАЛИЗОВАН

Модуль [api/text_import_export.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/text_import_export.py)
предоставляет универсальный импорт/экспорт табличной части документов
в форматах **TSV**, **JSON**, **XLSX** с автоматическим созданием
отсутствующих ссылочных типов (материалы, единицы, работы, контрагенты, машины).

Поддерживаемые форматы:

| Формат | Import (загрузка) | Export (выгрузка) | Content-Type |
|---|---|---|---|
| TSV  | да | да | `text/tab-separated-values; charset=utf-8` |
| JSON | да | да | `application/json; charset=utf-8` |
| XLSX | да (через `openpyxl`) | да (через `openpyxl`) | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

### 1.2. Поддерживаемые типы документов (5)

Зарегистрированы в `DOCUMENT_SCHEMAS` (text_import_export.py:356–431)
и в `_DOC_KIND_TO_TYPE` (cost_accounting.py:656–662):

| Документ | `doc_type` (backend) | `doc_kind` (URL) | Роутер | Форма |
|---|---|---|---|---|
| Расход материалов | `material_consumption` | `material-consumptions` | `/api/cost` | MaterialConsumptionFormView |
| Использование машин | `machinery_usage` | `machinery-usage-reports` | `/api/cost` | MachineryUsageFormView |
| Субподряд | `subcontract_acceptance` | `subcontract-acceptances` | `/api/cost` | SubcontractAcceptanceFormView |
| Накладные расходы | `overhead_expense` | `overhead-expenses` | `/api/cost` | OverheadExpenseFormView |
| Дневной отчёт | `daily_report` | `daily-reports` | `/api/cost` | DailyReportFormView |

Все 5 форм имеют:
- Кнопку «⇄ Обмен данными» в тулбаре
- Модалку `DocumentDataExchangeDialog` с вкладками Импорт/Экспорт
- Авто-перезагрузку данных после импорта (`@imported="reload"`)

### 1.3. API-эндпоинты (роутер cost_accounting.py)

```
POST  /api/cost/{doc_kind}/{doc_id}/import-text?format=tsv|json|xlsx&replace=true
GET   /api/cost/{doc_kind}/{doc_id}/export-text?format=tsv|json|xlsx
```

Тело запроса `import-text`:
- raw bytes для XLSX
- raw text для TSV/JSON

Ответ `import-text`:
```json
{
  "data": { "imported": 12, "warnings": [...], "format": "tsv" },
  "message": "Imported 12 lines"
}
```

### 1.4. Авто-создание ссылочных типов

Резолверы в text_import_export.py (get_or_create_*). Поведение по типам справочников:

| Справочник | Lookup | Авто-создание | Функция |
|---|---|---|---|
| `materials` | code → name | **да** | `get_or_create_material` |
| `works` | code → name | **да** | `get_or_create_work` |
| `units` | name (нормализованный) | **да** | `get_or_create_unit` (через `_resolve_unit_id`) |
| `counterparties` | inn → name | **да** | `get_or_create_counterparty` |
| `machines` | code → name | **да** | `get_or_create_machine` |
| `cost_elements` | code → name | **нет** (политика) | `get_or_create_cost_element` |

---

## 2. Статусы остальных типов документов

### 2.1. Документы БЕЗ поддержки единого обмена (4)

| Документ | Таблица строк | FK документа | Справочники в строках | Импорт/экспорт | Роутер |
|---|---|---|---|---|---|
| **Смета (Estimate)** | `estimate_lines` (database.py:248) | `estimate_id` | `work_id` | **НЕТ** (нет ни своего, ни общего) | `/api/documents` |
| **Табель (Timesheet)** | `timesheet_lines` (database.py:373) | `timesheet_id` | `employee_id`→persons | **свой** (Excel/JSON, только превью) | `/api/documents` |
| **Приходная накладная** | `goods_receipt_lines` (database.py:612) | `receipt_id` | `material_id`, `unit_id`, `object_id` | **свой** (Excel `.xlsx`/`.xls`) | `/api/goods` |
| **Расходная накладная** | `goods_issue_lines` (database.py:672) | `issue_id` | `material_id`, `unit_id`, `object_id` | **свой** (Excel `.xlsx`/`.xls`) | `/api/goods` |
| **Калькуляция затрат** | нет табличной части | — | — | **НЕТ** (и не требуется) | `/api/cost` |

#### 2.1.1. Смета (Estimate)

Таблица строк: `estimate_lines`. Справочники: только `work_id`.
Колонки: `line_number, work_id, quantity, unit, price, labor_rate, sum,
planned_labor, is_group, group_name, is_collapsed, parent_group_id`.

Импорт/экспорт: **полностью отсутствует**. Имеет иерархию строк (группы).
Эндпоинты в documents.py: CRUD + post/unpost + print + copy.

Фронтенд: `EstimateFormView.vue` — без кнопок импорта/экспорта.

#### 2.1.2. Табель (Timesheet)

Таблица строк: `timesheet_lines`. Справочники: `employee_id`→persons.
Колонки: `day_01 … day_31` (часы по дням месяца), `hourly_rate,
total_hours, total_amount`.

Имеет собственную реализацию:
- **Экспорт:** `services.py:3384` `export_timesheet_data()` — JSON/Excel.
- **Импорт (превью):** `services.py:3857` `preview_timesheet_import()` —
  парсит `.xlsx/.json`, сопоставляет сотрудников по `full_name`/
  `personnel_number`, поддерживает создание отсутствующих физлиц.
  Эндпоинт: `POST /api/documents/timesheets/import-preview`.
- Финальное сохранение — через обычный `PUT`.

Фронтенд: `TimesheetFormView.vue` — есть кнопки «Импорт» (`.xlsx,.json`)
и «Заполнить по отчетам» (autofill). Модалка подтверждения импорта с
настройкой ключей автоподбора. Компонент `TimesheetLinesEditor.vue`.

**Гэп:** табель **не интегрирован** в единый `text_import_export.py`.
Имеет собственную логику с 31 колонкой дней, что плохо ложится на TSV.
Создание физлиц происходит на превью, а не на финальном сохранении.

#### 2.1.3. Приходная/расходная накладная (Goods Receipt / Issue)

Таблицы строк: `goods_receipt_lines` / `goods_issue_lines`.
Справочники: `material_id`→materials, `unit_id`→units, `object_id`→objects.
Колонки: `line_number, material_id, name, unit, unit_id, quantity,
price_without_vat, vat_rate, vat_amount, sum_without_vat, sum_with_vat,
drawing_code, note, object_id`.

Имеют собственную реализацию:
- **Экспорт:** `goods_services.py:1762` `export_goods_document_lines()` —
  Excel (SpreadsheetML 2003, `.xls`). Эндпоинты:
  `GET /api/goods/receipts/{id}/lines/export`,
  `GET /api/goods/issues/{id}/lines/export`.
- **Импорт (превью):** `goods_services.py:1876`
  `preview_goods_lines_import()` — парсит `.xlsx` (через `openpyxl`)
  и `.xls` (SpreadsheetML). Гибкое сопоставление заголовков через
  `_goods_header_mapping` с псевдонимами на русском/английском.
  Эндпоинт: `POST /api/goods/{kind}/{id}/lines/import`.
- **Профили импорта:** `api/import_profiles.py` с флагами
  `create_missing_materials`, `create_missing_units` — **задекларированы,
  но не используются** в `preview_goods_lines_import`.

Фронтенд: `GoodsDocumentFormView.vue` (views/goods/) — есть кнопки
«Загрузить из Excel…», «Выгрузить в Excel», «Создать материалы»
(`createMissingMaterials` — по строкам без `material_id`),
«Движения по регистрам». Компонент `GoodsLinesEditor.vue`.

**Гэпы:**
- Материалы **не создаются автоматически** при импорте — только lookup
  по коду; если не найден → warning. Кнопка «Создать материалы» работает
  постфактум, отдельно.
- `unit_id` всегда `None` при импорте (стр. 1945 goods_services.py).
- Профили импорта с `create_missing_*` не подключены.
- Товарные накладные **не интегрированы** в единый `text_import_export.py`.
- Файлы форм находятся в `views/goods/`, а не в `views/documents/`.

#### 2.1.4. Калькуляция затрат (Cost Calculation)

**Не имеет табличной части.** Структура `cost_calculations` содержит
только шапку (номер, дата, период, объект). Результаты расчёта пишутся
в регистр `completed_works_cost` (database.py:990), а не в редактируемые
строки. Импорт/экспорт строк **не применим**.

Фронтенд: `CostCalculationFormView.vue` — только шапка + кнопки
«Рассчитать / Провести / Отменить».

---

## 3. Формат данных

### 3.1. Общие правила

- **Делимитер (TSV):** TAB (`\t`)
- **Перенос строк:** `\n`
- **Кодировка:** UTF-8
- **Первая строка:** заголовок с **русскими метками** колонок
- **Пустые строки:** игнорируются
- **Заголовки TSV:** используют `label` из схемы (человеко-читаемые),
  например: `Код материала`, `Материал`, `Ед.`, `Лимит`, `Списано`,
  `Цена`, `Сумма`

### 3.2. JSON-формат

Экспорт возвращает:
```json
{
  "doc_type": "material_consumption",
  "doc_id": 42,
  "lines": [
    { "material_code": "М001", "material_name": "Бетон М100", "unit": "м³",
      "work_code": "Р-001", "work_name": "Бетонные работы",
      "planned_quantity": 10, "actual_quantity": 8, "price": 3500, "sum": 28000 }
  ]
}
```

Импорт принимает:
- Массив объектов `[ {field: value, ...}, ... ]`
- Или объект `{ "lines": [ ... ] }`

### 3.3. XLSX-формат

Первая строка листа = заголовки (те же `label`), далее строки данных.
Пустые строки игнорируются. Требует `openpyxl` (указан в requirements).

### 3.4. Маппинг колонок по типам документов

Каждая колонка в `DOCUMENT_SCHEMAS` описывается dict'ом:
```python
{ "field": "material_code", "label": "Код материала", "type": "text",
  "ref": "material", "create": True, "maps": "material_id" }
```

- `type`: `text` | `float` | `int`
- `ref`: `material` | `work` | `unit` | `counterparty` | `machine` |
  `cost_element` | `None`
- `create`: создавать справочник, если не найден
- `maps`: колонка в БД, куда пишется resolved ID
- `ref_helper`: вспомогательное текстовое поле (snapshot имени)

Полные схемы всех 5 типов — в `DOCUMENT_SCHEMAS` (text_import_export.py:356–431).

---

## 4. Семантика загрузки

Для каждой строки:

1. Резолвятся все справочные ссылки (по коду → по имени).
2. Если `create=True` и запись не найдена → выполняется `INSERT` с
   минимальным набором полей (name/code), создаваемая запись логируется.
3. Если `create=False` и запись не найдена → строка сохраняется с null,
   в `warnings` добавляется предупреждение.
4. При `replace=True` существующие строки документа удаляются перед
   импортом; при `replace=False` — добавляются к существующим.
5. Ответ: `{ "imported": N, "warnings": [...], "format": "tsv" }`.

## 5. Семантика выгрузки

Для каждого документа:

1. Строки читаются из БД с упорядочиванием по `line_number`.
2. Справочные ID резолвятся обратно в коды/имена (JOIN materials, works,
   counterparties, machines, cost_elements).
3. `unit` берётся из work → material → line.unit (cascade).
4. Формируется тело ответа согласно запрошенному формату.
5. Content-Disposition: `attachment; filename="{doc_type}_{doc_id}.{ext}"`.

---

## 6. Фронтенд-компоненты

### DocumentDataExchangeDialog.vue

Модалка с вкладками «Импорт» / «Экспорт»:
- Выбор формата: TSV / JSON / XLSX
- Import: textarea (для TSV/JSON) или file input (для XLSX)
- Чекбокс «Заменить существующие строки»
- После успешного импорта эмитит `imported` → форма перезагружает данные
- Export: кнопка «Скачать» → blob download

API-клиент (`api/costAccounting.ts`):
- `importDocumentText(kind, docId, format, body, replace)` → POST
- `exportDocumentText(kind, docId, format)` → GET (blob)
- `DocDataExchangeKind` = union литералов всех 5 `doc_kind`

---

## 7. Оставшиеся гэпы и рекомендации

### 7.1. Смета — нет обмена данными

Смета (`estimate_lines`) не поддерживается ни единым модулем, ни
собственным импортом/экспортом. Рекомендуется добавить схему в
`DOCUMENT_SCHEMAS` и эндпоинты в `documents.py`. Сложность: иерархия
строк (`parent_group_id`, `is_group`) требует расширения формата.

### 7.2. Табель — собственная реализация, не унифицирована

Табель имеет работающий импорт/экспорт (Excel/JSON), но через отдельный
код (`services.py`). 31 колонка дней плохо ложится на TSV — но JSON
можно интегрировать. Создание физлиц происходит только на превью.

### 7.3. Товарные накладные — материалы не создаются при импорте

`preview_goods_lines_import` в `goods_services.py:1876` только делает
lookup материалов по коду. Кнопка «Создать материалы» работает отдельно.
Профили импорта (`create_missing_materials`, `create_missing_units`)
задекларированы, но **не используются**. Рекомендуется подключить
`get_or_create_material` из `text_import_export.py` в goods-импорт.

### 7.4. Несоответствие размещения файлов

`GoodsDocumentFormView.vue` и `GoodsDocumentListView.vue` находятся в
`views/goods/`, а не в `views/documents/` вместе с остальными документами.

### 7.5. Калькуляция затрат — без обмена (by design)

Не имеет редактируемой табличной части. Импорт/экспорт строк не применим.

---

## 8. Сводная матрица поддержки

| Документ | Единый модуль | Собственный | UI-кнопка | Авто-создание справочников |
|---|---|---|---|---|
| Расход материалов | ✅ TSV/JSON/XLSX | — | ✅ | ✅ materials, units, works |
| Использование машин | ✅ TSV/JSON/XLSX | — | ✅ | ✅ machines, units, works |
| Субподряд | ✅ TSV/JSON/XLSX | — | ✅ | ✅ counterparties, units, works |
| Накладные расходы | ✅ TSV/JSON/XLSX | — | ✅ | ✅ counterparties (cost_elements — нет) |
| Дневной отчёт | ✅ TSV/JSON/XLSX | — | ✅ | ✅ units, works |
| Смета | ❌ | ❌ | ❌ | — |
| Табель | ❌ | ✅ Excel/JSON | ✅ | persons (на превью) |
| Приходная накладная | ❌ | ✅ Excel | ✅ | ❌ (отдельная кнопка) |
| Расходная накладная | ❌ | ✅ Excel | ✅ | ❌ (отдельная кнопка) |
| Калькуляция затрат | ❌ | ❌ | ❌ | — (нет строк) |
