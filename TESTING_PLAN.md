# Cost Accounting Subsystem — Testing Plan

Scope: backend (`current/api`) + frontend (`current/web-client`) of the **cost accounting**
subsystem. Focus on form behavior as requested.

Проверено повторно: 2026-09-02. Таблицы статусов ниже являются историческим
рабочим журналом и не доказывают прохождение тестов: автоматического backend suite
в репозитории нет. Актуальный gap-анализ и порядок автоматизации находятся в
`SPEC_REVIEW.md` и `DEVELOPMENT_PLAN.md`.

Status legend: ⬜ planned · 🔬 under test · ✅ fixed · ⚠️ known/deferred

---

## 0. Environment / boot blockers (test first — nothing else works if these fail)

| # | Test | Expected | Status |
|---|------|----------|--------|
| B1 | Start backend; DB schema initialized without error | app boots | 🔬 |
| B2 | `GET /api/cost/cost-elements` returns 200 + seeded elements | 6 predefined elements | 🔬 |
| B3 | `GET /api/cost/allocation-bases` returns 200 + seeded bases | 3 bases | 🔬 |
| B4 | `GET /api/cost/audit-logs` returns 200 with valid `pagination` | `page/page_size/total/pages` present | 🔬 |

Root cause under test: **C1 — no DDL** for any cost-accounting table. All endpoints crash with
`sqlite3.OperationalError: no such table` until DDL is added.

---

## 1. Reference data & machines

| # | Test | Expected | Status |
|---|------|----------|--------|
| R1 | Cost elements list (predefined: materials, labor, machinery, subcontract, other_direct, overhead) | 6 rows | ⬜ |
| R2 | Allocation bases list (payroll, direct_costs, labor_days) | 3 rows | ⬜ |
| R3 | Machine CRUD: create → get → update → list (search by name/code) → soft-delete | lifecycle works | ⬜ |
| R4 | Machine list pagination (page/page_size) | correct totals/pages | ⬜ |

---

## 2. Material consumptions (form + lifecycle)

| # | Test | Expected | Status |
|---|------|----------|--------|
| M1 | Create doc with lines | 201, lines saved | ⬜ |
| M2 | **Edit (PUT) existing doc** | 200, no crash | 🔬 C2 |
| M3 | Edit a **posted** doc → rejected | 400 "Cannot edit a posted document" | 🔬 H1 |
| M4 | Post → writes `actual_costs` MATERIALS rows | register rows created | ⬜ |
| M5 | Unpost → deletes those rows; doc `is_posted=0` | clean rollback | ⬜ |
| M6 | Delete → soft delete only | marked_for_deletion=1 | ⬜ |

---

## 3. Machinery usage reports

| # | Test | Expected | Status |
|---|------|----------|--------|
| U1 | CRUD lifecycle | works | ⬜ |
| U2 | Edit posted doc → rejected | 400 | 🔬 H1 |
| U3 | Post → MACHINERY + LABOR (operator) rows when operator_labor>0 | 1–2 rows/line | ⬜ |
| U4 | Unpost clears register | clean | ⬜ |

---

## 4. Subcontract acceptances

| # | Test | Expected | Status |
|---|------|----------|--------|
| S1 | CRUD lifecycle | works | ⬜ |
| S2 | Edit posted doc → rejected | 400 | 🔬 H1 |
| S3 | Post → SUBCONTRACT row, qty=0 | register row | ⬜ |

---

## 5. Overhead expenses & distribution

| # | Test | Expected | Status |
|---|------|----------|--------|
| O1 | CRUD lifecycle; period filter on list | works | ⬜ |
| O2 | Edit distributed doc → rejected | 400 (already guarded) | ✅ |
| O3 | **Distribute** (period + base) — single object | pool fully allocated to that object | 🔬 H2 |
| O4 | Distribute — all objects (object_id=0) | Σ shares == pool total | 🔬 H4 |
| O5 | Distribute with `labor_days` base | uses LABOR quantity only | 🔬 H3 |
| O6 | Cancel distribution → re-distribute allowed | works | ⬜ |
| O7 | UI: "Распределить" / "Отменить" buttons present and wired | reachable | 🔬 FE-M1 |

---

## 6. Cost calculations

| # | Test | Expected | Status |
|---|------|----------|--------|
| C1 | Create → list → get → **edit (PUT)** → delete | edit persists | 🔬 FE-H1 |
| C2 | List **search** by number/period | filters results | 🔬 FE-H2 |
| C3 | Calculate (single object) → `completed_works_cost` per work, correct object_id | works | 🔬 H5 |
| C4 | Calculate (all objects, object_id=0) → each work keeps its own object_id | no collapse to 0 | 🔬 H5 |
| C5 | Post requires `calculated`; Unpost → returns to `calculated` (not draft) | consistent status | 🔬 FE-M3 |
| C6 | Role gating: admin/manager can calculate/post/unpost; UI matches backend | consistent | 🔬 FE-M4 |

---

## 7. Reports

### 7.0 Что улучшить в тестировании отчётов

Текущие тесты P1–P4 проверяют только **факт наличия строк** («elements + works rows», «rows»).
Это качественная проверка — она не ловит ошибки математики и не воспроизводима без данных.
Добавить:

1. **Детерминированный сид-сценарий** (раздел 7A). Без него любой тест отчёта — слепой.
   Сценарий даёт заранее вычисленные ожидаемые числа для всех 4 отчётов.
2. **Количественные assertion'ы** (Q-тесты): сверка конкретных сумм, а не «есть строки».
3. **Межотчётная сверка (reconciliation)** (X-тесты). Отчёты черпают из пересекающихся
   таблиц (`actual_costs`, `completed_works_cost`, `overhead_distribution`) — их числа
   должны быть согласованы. Именно здесь всплывают реальные баги (см. R-REP1).
4. **Матрица фильтров**: period-only / object-only / оба / ничего — для каждого отчёта.
5. **Граничные условия**: входящее сальдо (нужны ≥2 периода), граница `threshold_pct`
   (`pct == threshold` должно входить), `object_id=0` vs один объект (регрессия H5).
6. **Покрытие известных мёртвых зон**: `outflow` (всегда 0 — M1), элемент overhead в
   карточке (всегда 0 — R-REP1), `profit == −deviation` (M3).

### 7.1 Базовые проверки

| # | Test | Expected | Status |
|---|------|----------|--------|
| P1 | Cost card (object + period) | elements + works rows | ⬜ |
| P2 | Cost turnover (period) | opening/inflow/outflow/closing | ⬜ |
| P3 | Cost deviations (period + threshold) | rows | ⬜ |
| P4 | Cost profitability (period) | per-object rows | ⬜ |
| P5 | Null/zero guard on `profitability_pct` / `deviation_pct` in tables | no JS crash | 🔬 FE-L5 |
| P6 | All 4 reports consistent initial-load behavior | parity | 🔬 FE-M9 |

### 7.2 Количественные тесты (на сценарии 7A — ожидаемые числа там же)

| # | Test | Expected | Status |
|---|------|----------|--------|
| Q1 | Cost card: суммы по элементам совпадают с расчётными | точное совпадение | ⬜ |
| Q2 | Cost card: `total_deviation == Σ(deviation по элементам) == total_actual − total_planned` | сходится | ⬜ |
| Q3 | Turnover: `closing == opening + inflow − outflow` в каждой строке | сходится | ⬜ |
| Q4 | Turnover: входящее сальдо (period=2025-02) включает факт 2025-01 | opening ≠ 0 | ⬜ |
| Q5 | Deviations: граница threshold — `pct == threshold` входит; `pct > threshold` — входит; `pct < threshold` — нет | 2/3/1 строка | ⬜ |
| Q6 | Profitability: Σ profit и `profitability_pct` совпадают с расчётом; `object_id` сохранён (регрессия H5) | сходится | ⬜ |

### 7.3 Межотчётная сверка (reconciliation) — ловит реальные баги

| # | Test | Expected | Status |
|---|------|----------|--------|
| X1 | Σ `actual_cost` (profitability) − Σ element `actual` (cost card, все объекты) == распределённый пул overhead | == pool | ⚠️ R-REP1 |
| X2 | Σ `deviation` (deviations) == Σ actual − Σ planned (profitability, тот же период) | сходится | ⬜ |
| X3 | Profitability по объекту == totals карточки по тому же объекту/периоду | дивергенция = overhead | ⚠️ R-REP1 |

### 7.4 Матрица фильтров и граничные условия

| # | Test | Expected | Status |
|---|------|----------|--------|
| FR1 | Каждый отчёт: period-only / object-only / оба / ничего — без 500 | 200 + корректный срез | ⬜ |
| FR2 | Cost card с `object_id`, у которого нет данных | пустые elements (0), works=[] | ⬜ |
| FR3 | Turnover для периода без факта | все строки 0, не падает | ⬜ |
| FR4 | Deviations `threshold_pct = 0` → все строки | все | ⬜ |

---

## 7A. Сквозной пример учёта (детерминированный сценарий)

Воспроизводимый сценарий «от справочников до отчётов». Все числа просчитаны вручную и
являются эталоном для Q/X-тестов. Источники: `actual_costs`, `planned_costs`,
`overhead_distribution`, `completed_works_cost` (см. `cost_accounting_services.py`).

### Каталоги (предопределённые)
CE1 Материалы · CE2 Оплата труда · CE3 Эксплуатация машин · CE4 Субподряд ·
CE5 Прочие прямые · CE6 Накладные расходы.
Базы распределения: B1 payroll (оплата труда) · B2 direct_costs · B3 labor_days.

### Мастер-данные
| Сущность | id | Наименование |
|----------|----|--------------|
| Объект | O1 | Объект А |
| Объект | O2 | Объект Б |
| Работа | W1 | Кладка (O1) |
| Работа | W2 | Монтаж (O1) |
| Работа | W3 | Отделка (O2) |
| Машина | M1 | Кран |

### Плановые затраты `planned_costs` (period = 2025-01)
| object | work | element | planned_amount |
|--------|------|---------|----------------|
| O1 | W1 | CE1 Материалы | 100 000 |
| O1 | W1 | CE2 Оплата труда | 30 000 |
| O1 | W2 | CE3 Эксплуатация машин | 40 000 |
| O2 | W3 | CE1 Материалы | 60 000 |

### Фактические затраты `actual_costs`
Период **2025-01**:
| object | work | element | amount | quantity |
|--------|------|---------|--------|----------|
| O1 | W1 | CE1 Материалы | 90 000 | 100 |
| O1 | W1 | CE2 Оплата труда | 30 000 | 30 |
| O1 | W2 | CE3 Эксплуатация машин | 44 000 | 40 |
| O2 | W3 | CE1 Материалы | 60 000 | 60 |
| O2 | W3 | CE2 Оплата труда | 20 000 | 20 |

Период **2025-02** (только для проверки входящего сальдо в оборотке):
| object | work | element | amount | quantity |
|--------|------|---------|--------|----------|
| O1 | W1 | CE1 Материалы | 10 000 | 10 |
| O1 | W1 | CE2 Оплата труда | 5 000 | 5 |

### Накладные и распределение `overhead_distribution`
Пул `overhead_expense_lines` за 2025-01 = **20 000**. Распределение по базе B1 (оплата труда), `object_id = 0`.
База труда за период: O1/W1 = 30 000, O2/W3 = 20 000 → итого 50 000.

| object | work | base | share |
|--------|------|------|-------|
| O1 | W1 | 30 000 | 12 000 |
| O2 | W3 | 20 000 | 8 000 |
| | | **Σ** | **20 000** |

### Калькуляция `completed_works_cost` (period = 2025-01, object_id = 0)
`actual_cost = actual_direct + overhead`; `contract_value = planned`; `profit = contract_value − actual_cost`.

| object | work | qty | planned | actual | deviation | contract | profit |
|--------|------|-----|---------|--------|-----------|----------|--------|
| O1 | W1 | 130 | 130 000 | 132 000 | +2 000 | 130 000 | −2 000 |
| O1 | W2 | 40 | 40 000 | 44 000 | +4 000 | 40 000 | −4 000 |
| O2 | W3 | 80 | 60 000 | 88 000 | +28 000 | 60 000 | −28 000 |

### Эталонные результаты отчётов

**P1 — Карточка себестоимости (object = O1, period = 2025-01)**
Элементы (факт берётся только из `actual_costs`, поэтому CE6 = 0 — см. R-REP1):

| element | planned | actual | deviation |
|---------|---------|--------|-----------|
| CE1 Материалы | 100 000 | 90 000 | −10 000 |
| CE2 Оплата труда | 30 000 | 30 000 | 0 |
| CE3 Эксплуатация машин | 40 000 | 44 000 | +4 000 |
| CE4/CE5/CE6 | 0 | 0 | 0 |

Totals: planned **170 000**, actual **164 000**, deviation **−6 000**,
contract **170 000**, profit **−6 000**, profitability_pct **−3.7**.
Works (сорт. по deviation DESC): W2 (+4 000, pft −9.1), W1 (+2 000, pft −1.5).

**P2 — Оборотная ведомость (period = 2025-02, object = 0)**
opening = Σ факт за period < 2025-02 (т.е. 2025-01); inflow = факт 2025-02.

| element | opening | inflow | outflow | closing |
|---------|---------|--------|---------|---------|
| CE1 Материалы | 150 000 | 10 000 | 0 | 160 000 |
| CE2 Оплата труда | 50 000 | 5 000 | 0 | 55 000 |
| CE3 Эксплуатация машин | 44 000 | 0 | 0 | 44 000 |
| CE4/CE5/CE6 | 0 | 0 | 0 | 0 |

> outflow всегда 0 — нет пути, создающего отрицательные `actual_costs` (известно как M1).

**P3 — Отклонения (period = 2025-01, threshold = 0, object = 0)**
Сорт. по `ABS(deviation)` DESC; `deviation_pct = |deviation| / planned * 100`.

| object | work | planned | actual | deviation | pct |
|--------|------|---------|--------|-----------|-----|
| O2 | W3 | 60 000 | 88 000 | +28 000 | 46.7 |
| O1 | W2 | 40 000 | 44 000 | +4 000 | 10.0 |
| O1 | W1 | 130 000 | 132 000 | +2 000 | 1.5 |

threshold=10 → W3 (46.7) + W2 (10.0, на границе — входит); threshold=11 → только W3.
> `cost_element_name` берётся через `LIMIT 1` без `ORDER BY` — недетерминирован (R-REP2).

**P4 — Рентабельность (period = 2025-01)**
Группировка `completed_works_cost` по `object_id`; сорт. по profit DESC.

| object | planned | actual | contract | profit | profitability_pct |
|--------|---------|--------|----------|--------|-------------------|
| O1 | 170 000 | 176 000 | 170 000 | −6 000 | −3.4 |
| O2 | 60 000 | 88 000 | 60 000 | −28 000 | −31.8 |

### Межотчётная сверка (эталон для X-тестов)
- **X1**: Σ actual (profitability) = 264 000; Σ element actual (cost card, все объекты:
  O1 164 000 + O2 80 000) = 244 000. Разница **20 000** == пул overhead → подтверждает R-REP1
  (накладные есть в рентабельности, но отсутствуют в карточке).
- **X2**: Σ deviation (P3) = 34 000 == Σ actual 264 000 − Σ planned 230 000. ✓
- **X3**: Profitability O1 actual 176 000 ≠ Cost card O1 actual 164 000. Разрыв **12 000** ==
  распределённый overhead O1/W1 (его нет в карточке, но есть в калькуляции/рентабельности).

---

## 8. Form-behavior (frontend) — cross-cutting

| # | Test | Expected | Status |
|---|------|----------|--------|
| F1 | Cost calc form: edit fields → Save → persists (PUT) | saved | 🔬 FE-H1 |
| F2 | Cost calc list: type in search → results filter | filters | 🔬 FE-H2 |
| F3 | Unsaved changes → navigate away → confirm prompt | warning shown | 🔬 FE-H3 |
| F4 | Distributed overhead: grid locked AND Save disabled | consistent lock | 🔬 FE-M2 |
| F5 | Calculate button visible only to admin/manager | role-correct | 🔬 FE-M4 |

---

## Issue register (severity)

**Critical**
- C1 — cost-accounting DDL missing → every endpoint crashes
- C2 — `PUT /material-consumptions/{id}` crashes (`connection.fetchone()` AttributeError)
- C3 — `GET /audit-logs` malformed pagination → response-model validation failure

**High (backend)**
- H1 — no posted-document edit guard on material/machinery/subcontract
- H2 — per-object overhead distribution mis-allocates + locks rest
- H3 — `labor_days` base sums wrong column
- H4 — no penny balancing in distribution
- H5 — all-objects cost calculation collapses object_id to 0
- H8 — weak authz on writes (deferred — design decision)

**High (frontend)**
- FE-H1 — cost calculation edit Save is a no-op (no PUT endpoint either side)
- FE-H2 — cost calculation list search never sent to backend
- FE-H3 — no dirty-flag / unsaved-changes protection in cost forms

**Reports (найдено при ревью раздела 7)**
- R-REP1 — Карточка себестоимости не учитывает распределённые накладные: элемент
  «Накладные расходы» всегда 0, т.к. `get_cost_card` суммирует только `actual_costs`,
  а накладные лежат в `overhead_distribution`. Факт в карточке занижен на сумму пула,
  и не сходится с рентабельностью/калькуляцией (см. X1, X3). High.
- R-REP2 — В отчёте отклонений `cost_element_name` берётся подзапросом `LIMIT 1` без
  `ORDER BY` → недетерминирован и отражает лишь один элемент на работу. Low/Medium.
- R-REP3 — `get_cost_card` / `get_profitability` не фильтруют `cost_elements.marked_for_deletion`,
  а `get_turnover_balance` — фильтрует. Несогласованное поведение при удалении элемента. Low.

**Medium** — see PROGRESS_LOG.md
