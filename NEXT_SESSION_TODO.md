# CTM — handoff и TODO для следующей агентной сессии

Актуально: 2026-09-03 (третья сессия P1).

## 1. Цель продолжения

Продолжать [`DEVELOPMENT_PLAN.md`](./DEVELOPMENT_PLAN.md). Схема «Ввод на
основание» и правило труда табеля (раздел 7.4 плана) не утверждены заказчиком —
не реализовывать спорные части автоматически.

Основной контекст:

- [`DEVELOPMENT_PLAN.md`](./DEVELOPMENT_PLAN.md) — roadmap, решения, открытые вопросы (7.2–7.4).
- [`SPEC_REVIEW.md`](./SPEC_REVIEW.md), [`SECURITY_BASELINE_SPEC.md`](./SECURITY_BASELINE_SPEC.md),
  [`TESTING_PLAN.md`](./TESTING_PLAN.md).

## 2. Состояние на конец этой сессии

Все проверки зелёные: backend **50 passed**, `compileall` чист, `vue-tsc` чист,
production build проходит, Playwright **35 passed**.

### Закрыто в этой сессии

- **Обход RBAC вне HTTP (остаток P1):** проверено — sync-runtime не содержит
  cost-сущностей; import-text ограничен admin/manager и отклоняет
  проведённые/распределённые цели; других вызывающих lifecycle-сервисов нет.
  Добавлен отрицательный тест: foreman → 403 на импорт строк.
- **Труд табеля (P1 п. 3, частично):** строки табеля не содержат работы;
  posting в `actual_costs` идёт с `work_id = 0`. Пока правило не выбрано,
  расчёт себестоимости выводит предупреждение
  «Timesheet labor is not attributed to works (work_id=0)…» — диагностика вместо
  молчаливой фантомной строки; суммы не изменены. Варианты правила — в разделе
  7.4 плана (A: работа в строке табеля; B: распределение по planned_labor сметы).
- **Отрицательные UI/E2E:** `web-client/e2e/rbac-cost.spec.ts` (4 теста) —
  прораб: свой черновик удаляем, чужой нет, проведение недоступно, офисный
  список/форма только для чтения; менеджер: полный lifecycle.
- **PostgreSQL parity (инфраструктура):** conftest поддерживает
  `CTM_TEST_DB=postgresql` + `CTM_TEST_PG_*` (временная база на каждый тест,
  DROP … WITH (FORCE) при завершении). Запуск одной командой:
  `docker run -d -p 5433:5432 -e POSTGRES_USER=ctm -e POSTGRES_PASSWORD=ctm postgres:17`
  затем `CTM_TEST_DB=postgresql uv run --with-requirements api/requirements-dev.txt python -m pytest api/tests -q`.
  В текущей среде сервер недоступен: локальная сборка PostgreSQL 1C без
  initdb-файлов (нет postgres.bki), Docker-демон остановлен. Запускать Docker
  Desktop без ведома пользователя не следует.

### Ранее закрыто (сессии 1–2)

RBAC=B для пяти cost-документов (owner-проверки, restore endpoints, guards на
posted/distributed), actor в `audit_logs` для всех lifecycle-операций,
договорная стоимость из сметы (средневзвешенная расценка + предупреждения),
R-REP1 (накладные в карточке, сходимость трёх отчётов), R-REP2/3, state machine
калькуляции.

## 3. Первый шаг следующей сессии — обязательная проверка

```powershell
Set-Location F:\2026f\ctm3\CTM2_recovered
git status --short

Set-Location current
uv run --with-requirements api/requirements-dev.txt python -m pytest api/tests -q
uv run --with-requirements api/requirements-dev.txt python -m compileall -q api

Set-Location web-client
npx vue-tsc --noEmit
npm run build
npx playwright test
```

Дерево dirty; не откатывать чужие изменения, отделять регрессии от старых проблем.

## 4. Оставшиеся задачи

1. **P1 — PostgreSQL parity:** при доступном сервере (или в CI) прогнать suite
   в режиме `CTM_TEST_DB=postgresql`; особое внимание — `SUBSTR`,
   коррелированные подзапросы и runtime-колонка `contract_id`.
2. **P1 — решение 7.4 (труд табеля):** после выбора варианта A/B реализовать и
   снять предупреждение; тест
   `test_calculation_warns_about_unattributed_timesheet_labor` зафиксирует новое
   поведение.
3. **P1 — чтение для прораба:** нужен продуктовый ответ, должен ли foreman
   видеть в list/get только свои полевые документы (сейчас write-only
   ownership).
4. **P2 — обмен/«ввод на основании»/списки:** только после подтверждения графа
   (раздел 7.3 плана); безопасный фундамент (based_on, preview, warnings) можно
   делать заранее.
5. **Техдолг 4.x:** пометка устаревших AS-IS матриц, фиксация SQLite/PostgreSQL
   сценариев в документации.

## 5. Критерий готовности текущего блока

- Backend suite, vue-tsc, build, Playwright — зелёные. ✓ (2026-09-03)
- Отрицательные RBAC-сценарии есть на обоих уровнях (API и UI). ✓
- Диагностика нераспределённого труда табеля включена и покрыта тестом. ✓
- Открытые решения задокументированы (7.4) и не подменены случайным поведением. ✓
