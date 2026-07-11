# План выравнивания web ↔ desktop (ТМЦ + взаиморасчеты)

Версия: 1.0 (2026-07-09). Источник: сравнительный анализ desktop (эталон) ↔ web.

## Базовые факты
- **API готов на ~90%**: `/api/goods/receipts|issues` (CRUD + post/unpost + экспорт/импорт строк), `/api/goods/inventory/balances|movements`, `/api/settlements/balance|ledger|overdue`, `/api/goods/import-profiles`, `/api/payments/schedules/preview/goods-receipts|goods-issues`.
- **API-пробелы (Phase 0)**: нет `/api/settlements/turnover` (ОСВ); `contracts` в `REFERENCE_CONFIG` не join-ит организацию и не сортирует по новым полям.
- **Web**: Vue 3 + TS + Pinia + native `fetch` + MDI-табы (5 точек регистрации каждой формы). Нет ТМЦ; из взаиморасчетов — только generic-«Договоры» и ранее существовавший платёжный модуль.
- **Desktop** — эталон.

---

## Phase 0 — пробелы API (фундамент)

| Задача | Файл | Детали |
|---|---|---|
| 0.1 ОСВ-эндпоинт | `api/goods_services.py` + `api/routers/settlements.py` | `settlements_turnover`: сальдо нач. (period<date_from), обороты ([date_from,date_to]), сальдо кон. по `accrual`/`payment`, Дт(receivable)/Кт(payable). `GET /api/settlements/turnover`. |
| 0.2 Расширить contracts reference | `api/services.py` `REFERENCE_CONFIG["contracts"]` | join `organizations` → `organization_name`; `sortable` += `kind, payment_deferral_days, vat_rate, organization_id`; проверить `save_reference` для новых полей. |
| 0.3 Тесты | `api/tests/test_settlements_turnover.py` | ОСВ: сальдо + обороты + фильтр. |

## Phase 1 — фундамент web: типы + API-модули
`types/models.ts`: `GoodsLine`, `GoodsDocument`, `GoodsReceipt/Issue`, `InventoryBalanceItem`, `InventoryMovementItem`, `SettlementBalanceRow/TurnoverRow/OverdueRow`, `ImportProfile`; расширить `PaymentCategory` (`supplier_invoice`, `customer_invoice`), `PaymentSourceKind` (`goods_receipt`, `goods_issue`), `ContractRecord`.
Новые `api/goods.ts`, `api/settlements.ts`; расширить `api/payments.ts` (suggest из ТМЦ).

## Phase 2 — документы ТМЦ (ядро)
Образец: `views/payments/PaymentScheduleListView/FormView.vue`.
- `views/goods/GoodsDocumentListView.vue` (generic, `kind`).
- `views/goods/GoodsDocumentFormView.vue` (generic, `kind`) + `components/documents/GoodsLinesEditor.vue`.
- Excel: загрузка (`<input file>` → `previewGoodsLinesImport`/профиль), выгрузка (`exportGoodsLines` → Blob).
- **MDI 5 точек**: `router/index.ts` (6 маршрутов) → `stores/workspace.ts` → `WorkspaceContent.vue` → `AppSidebar.vue` (новый раздел `goods`).

## Phase 3 — отчёты (3 формы)
Образец: `views/payments/PaymentCalendarView.vue`, `views/registers/WorkExecutionView.vue`.
- `views/reports/InventoryBalancesReport.vue`
- `views/reports/SettlementsTurnoverReport.vue` (нужен API 0.1)
- `views/reports/OverdueReport.vue`
Фильтры → `loadRegister` → `DataTable` + `.metric-grid` итоги + Excel (Blob или SpreadsheetML).

## Phase 4 — Договоры (обогащение) + профили импорта
- 4a: `composables/referenceFields.ts` `mapping['contracts']` += `organization_id/kind/vat_rate/payment_deferral_days/currency/agreement_date/valid_until`.
- 4b: `views/admin/ImportProfilesView.vue` (CRUD профилей через `/api/goods/import-profiles`).
- 4c: кнопка «Загрузить из Excel…» в форме ТМЦ → Modal выбора профиля + предпросмотр.
- Синхронизация desktop↔API профилей (последний пробел).

## Phase 5 — платёжный календарь: связь с ТМЦ
- `PaymentScheduleFormView.vue`: кнопки suggest «Из поступлений/реализаций ТМЦ».
- `PaymentCalendarView.vue`: пометка источника `goods_receipt|goods_issue`.

---

## Сквозной MDI 5-точечный чек-лист (каждая новая форма)
1. `router/index.ts` — маршрут(ы).
2. `stores/workspace.ts` — `DocumentKind` + `specFromRoute` + `singletonKinds`.
3. `components/layout/WorkspaceContent.vue` — `componentMap`.
4. `components/layout/AppSidebar.vue` — пункт меню.
5. `composables/referenceFields.ts` — только для references.
Плюс во view: `useHeaderBar(tabId, title, actions)` + `useDirtyFlag` для форм.

## Матрица паритета (цель)
| Возможность | Desktop | Web сейчас | Web после |
|---|:---:|:---:|:---:|
| Поступление ТМЦ | ✅ | ❌ | ✅ Ph2 |
| Списание ТМЦ | ✅ | ❌ | ✅ Ph2 |
| Договоры (тип/отсрочка/НДС) | ✅ | ⚠️ | ✅ Ph4a |
| Остатки ТМЦ | ✅ | ❌ | ✅ Ph3 |
| ОСВ взаиморасчетов | ✅ | ❌ | ✅ Ph3 (API 0.1) |
| Просрочки | ✅ | ❌ | ✅ Ph3 |
| Профили импорта + диалог | ✅ | ❌ | ✅ Ph4b/c |
| Импорт строк ТМЦ из Excel | ✅ | ❌ | ✅ Ph2 |
| Выгрузка строк в Excel | ✅ | ❌ | ✅ Ph2 |
| Авто-подсказки оплат из ТМЦ | API | ❌ | ✅ Ph5 |
| Синхронизация профилей desktop↔API | ❌ | ❌ | ✅ Ph4b |

## Оценки
- Ph0 ~0.5д, Ph1 ~0.5д, Ph2 ~2–3д, Ph3 ~1д, Ph4 ~1–1.5д, Ph5 ~0.5д. **Итого ~6–7 чел-дней** + E2E.

## Риски
1. MDI 5-точечная регистрация — пропуск = форма не работает.
2. `save_reference` whitelist — новые поля contracts могут теряться (проверить в 0.2).
3. Excel client-side без библиотеки — предпочесть серверный Blob (`/api/goods/.../export` есть).
4. ОСВ `func.iif` — на Postgres нет; использовать `CASE WHEN`.
5. Schema-runtime: `ensure_runtime_schema` уже обновлён; web-сборка идёт с актуальным API.
