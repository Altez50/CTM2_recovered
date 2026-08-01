# Cost Accounting Subsystem — Testing & Fixes Progress Log

Generated: 2026-07-14

## Environment note

The sandbox's Python installation (`D:\ptn313`) is corrupted: all stdlib `.py` files in
`Lib\encodings\` have been renamed to `.py.Ares`, causing `Fatal Python error:
init_fs_encoding: failed to get the Python codec of the filesystem encoding`. Backend
runtime smoke test could not be executed; verification was performed via static code
review + frontend `vue-tsc` typecheck (passed with 0 errors).

---

## Issues Found & Fix Status

### CRITICAL — all fixed

#### C1 — Cost-accounting DDL missing
**Problem:** No `CREATE TABLE` for any of the 14 cost-accounting tables existed anywhere.
Every endpoint in the subsystem crashed with `sqlite3.OperationalError: no such table`.

**Fix:** Added DDL for all 14 tables + 20 indexes to `SCHEMA_TABLES_SQL` and
`SCHEMA_INDEXES_SQL` in [database.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/database.py).
Wired `_seed_cost_accounting_catalogs()` into `ensure_runtime_schema()` to seed
predefined cost elements and allocation bases at DB init time.

Tables added: `allocation_bases`, `cost_elements`, `machines`, `material_consumptions`,
`material_consumption_lines`, `machinery_usage_reports`, `machinery_usage_lines`,
`subcontract_acceptances`, `subcontract_acceptance_lines`, `overhead_expenses`,
`overhead_expense_lines`, `cost_calculations`, `planned_costs`, `actual_costs`,
`overhead_distribution`, `completed_works_cost`.

**Status:** ✅ Fixed (static-verified)

---

#### C2 — `PUT /material-consumptions/{id}` always crashes
**Problem:** `save_material_consumption()` used `connection.fetchone()` on line 264 —
but `sqlite3.Connection` has no `fetchone()` method (it's a `Cursor` method). Every
update call raised `AttributeError`.

**Fix:** Replaced with a proper `connection.execute(...).fetchone()` pattern and added
the missing posted-document edit guard (H1) + `modified_at` update.
File: [cost_accounting_services.py:261-274](file:///f:/2026f/ctm3/CTM2_recovered/current/api/cost_accounting_services.py)

**Status:** ✅ Fixed (static-verified)

---

#### C3 — `GET /audit-logs` malformed pagination
**Problem:** Router returned `{"total":..., "limit":..., "offset":...}` but the
`ApiResponse.pagination` field requires `{page, page_size, total, pages}`. Every call
caused a response-model validation error.

**Fix:** Converted limit/offset to page/page_size/pages in the router endpoint.
File: [cost_accounting.py:622-632](file:///f:/2026f/ctm3/CTM2_recovered/current/api/routers/cost_accounting.py)

**Status:** ✅ Fixed (static-verified)

---

### HIGH (backend) — all fixed

#### H1 — No posted-document edit guards
**Problem:** `save_material_consumption`, `save_machinery_usage_report`,
`save_subcontract_acceptance` allowed editing of already-posted documents without
unposting, leaving stale `actual_costs` registers.

**Fix:** Added `is_posted` check + 400 error to all three update paths. Also added
`modified_at = ?` to every UPDATE statement (was missing on 4 of 5 document types).
File: [cost_accounting_services.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/cost_accounting_services.py)

**Status:** ✅ Fixed

---

#### H2 — Per-object overhead distribution mis-allocates + locks rest
**Problem:** The "already distributed" check was always global (all objects), and all
overhead docs were marked `is_distributed=1` regardless of scope. Distributing
object-by-object was impossible.

**Fix:** Guard is now scoped: checks `object_id` when specified. `is_distributed` flag
is only set on a full (all-objects, `object_id=0`) distribution. DELETE before insert
is also scoped per object.

**Status:** ✅ Fixed

---

#### H3 — `labor_days` base sums wrong column
**Problem:** `labor_days` allocation base summed `quantity` across ALL `actual_costs`
(mixing material units, machine hours, labor hours).

**Fix:** Now filters to `cost_element_id = labor_ce` for `labor_days` base, matching
the `payroll` pattern.

**Status:** ✅ Fixed

---

#### H4 — No penny balancing in distribution
**Problem:** Each share was `round(share, 2)` independently; `Σ shares` could drift
from the pool total by cents.

**Fix:** Last written row absorbs the rounding residual: `share = round(total - allocated, 2)`
so `Σ shares == pool` exactly.

**Status:** ✅ Fixed

---

#### H5 — All-objects calculation collapses object_id to 0
**Problem:** When `object_id == 0` (all objects), `calculate_cost` grouped only by
`work_id` and wrote `object_id = calc["object_id"] = 0` for every row. The profitability
report then collapsed every object into `object_id = 0`.

**Fix:** All three aggregation queries (actual_costs, overhead_distribution,
planned_costs) now `GROUP BY COALESCE(object_id, 0), work_id`, and the INSERT uses the
per-row `object_id` instead of the calculation header's `object_id`.

**Status:** ✅ Fixed

---

#### H6 — Cost calc list has no search (backend side)
**Problem:** `list_cost_calculations` accepted no `search` parameter; the router didn't
expose one.

**Fix:** Added `search` parameter to service + router, matching by number or period
(LIKE pattern), consistent with other list endpoints.

**Status:** ✅ Fixed

---

#### H7 — No PUT endpoint for cost calculations
**Problem:** No `CostCalculationUpdate` schema, no `PUT /cost-calculations/{id}` route.
Editing a calculation's header was impossible from the UI.

**Fix:** Added `CostCalculationUpdate` schema (identical to Create). Added
`PUT /api/cost/cost-calculations/{calc_id}` endpoint. The service `save_cost_calculation`
already supported `calc_id` updates with a posted-guard.

**Status:** ✅ Fixed

---

### HIGH (frontend) — all fixed

#### FE-H1 — Cost calculation edit Save is a no-op
**Problem:** `save()` did `isEdit.value ? null : await createCostCalculation(...)`. In
edit mode, nothing happened — no update call, no feedback. No `updateCostCalculation`
existed in the API client; no PUT endpoint on the backend.

**Fix:** Added `updateCostCalculation(id, payload)` to [costAccounting.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/api/costAccounting.ts).
Rewrote `save()` in [CostCalculationFormView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/CostCalculationFormView.vue)
to call PUT on edit. Save button now disabled when posted.

**Status:** ✅ Fixed (vue-tsc: 0 errors)

---

#### FE-H2 — Cost-calculation list search never sent to backend
**Problem:** The search ref had a 300ms debounce watcher calling `loadItems()`, but
`loadItems` passed `{ page, page_size, sort_order: 'desc' }` — `search` was never
included. The backend also didn't accept search.

**Fix:** `loadItems` now passes `search: search.value`. Removed unsupported `sort_order`
param. Backend now accepts and filters by search (see H6 above).

**Status:** ✅ Fixed (vue-tsc: 0 errors)

---

#### FE-H3 — No dirty-flag / unsaved-changes protection
**Problem:** `useDirtyFlag.ts` composable existed but was referenced nowhere. Editing
fields then navigating away silently discarded changes.

**Fix:** Implemented lightweight inline dirty-tracking in both
CostCalculationFormView and OverheadExpenseFormView via `savedSnapshot` comparison +
`onBeforeRouteLeave` confirm prompt.

**Status:** ✅ Fixed (vue-tsc: 0 errors)

---

#### FE-M1 — Overhead distribution UI missing (MEDIUM, promoted)
**Problem:** `distributeOverhead()` and `cancelOverheadDistribution()` existed in the
API client but were called from no view. The entire distribution lifecycle was
unreachable from the UI.

**Fix:** Added a distribution toolbar to
[OverheadExpenseListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/OverheadExpenseListView.vue):
period input, allocation-base dropdown, "Распределить" and "Отменить распределение"
buttons. Visible only to admin/manager (`auth.canManageCost`).

**Status:** ✅ Fixed (vue-tsc: 0 errors)

---

#### FE-M2 — Overhead form: Save stays enabled while grid is locked
**Problem:** When `is_distributed`, all line inputs were disabled but the Save button
remained active.

**Fix:** Save button now `:disabled="form.is_distributed || saving"`.

**Status:** ✅ Fixed

---

#### FE-M3 — Cost calc status mutated optimistically without re-fetch
**Problem:** `calculate()` hardcoded `form.value.status = 'calculated'`, `post()` set
`'posted'`, `unpost()` set `'draft'` — all without reloading. If the server's resulting
status differed, the UI drifted.

**Fix:** All three lifecycle actions now call `reload()` which re-fetches the document
from the server and updates `form.value` + `markSaved()`.

**Status:** ✅ Fixed

---

#### FE-M4 — Role gating mismatches backend
**Problem:** Calculate button had no role check (any user sees it, gets 403 on click).
Post/Unpost checked `auth.isAdmin` only — managers (allowed by backend) were excluded.

**Fix:** Added `canManageCost` getter to [auth.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/stores/auth.ts)
(`role === 'admin' || role === 'manager'`). All three action buttons in both the form
and list views now use `auth.canManageCost` instead of `auth.isAdmin`.

**Status:** ✅ Fixed

---

## Files Changed

### Backend (`current/api/`)
| File | Changes |
|------|---------|
| [database.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/database.py) | +14 cost-accounting tables DDL, +20 indexes, `_seed_cost_accounting_catalogs()` |
| [cost_accounting_services.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/cost_accounting_services.py) | C2 fetchone fix, H1 posted guards (3 doc types), H2 scoped distribution, H3 labor_days fix, H4 penny balancing, H5 object identity, H6 list search, modified_at on all updates |
| [routers/cost_accounting.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/routers/cost_accounting.py) | C3 audit pagination, H6 search param, H7 PUT cost-calculations endpoint |
| [models/cost_accounting.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/models/cost_accounting.py) | H7 `CostCalculationUpdate` schema |

### Frontend (`current/web-client/src/`)
| File | Changes |
|------|---------|
| [api/costAccounting.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/api/costAccounting.ts) | FE-H1 `updateCostCalculation()` |
| [stores/auth.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/stores/auth.ts) | FE-M4 `canManageCost` getter |
| [views/documents/CostCalculationFormView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/CostCalculationFormView.vue) | FE-H1 edit save (PUT), FE-H3 dirty flag, FE-M3 re-fetch after lifecycle, FE-M4 role gating |
| [views/documents/CostCalculationListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/CostCalculationListView.vue) | FE-H2 search wired, FE-M4 role gating, dropped sort_order |
| [views/documents/OverheadExpenseFormView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/OverheadExpenseFormView.vue) | FE-M2 Save disabled when distributed, FE-H3 dirty flag |
| [views/documents/OverheadExpenseListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/OverheadExpenseListView.vue) | FE-M1 distribution UI, dropped sort_order |

---

## Verification

| Check | Method | Result |
|-------|--------|--------|
| Frontend TypeScript | `npx vue-tsc --noEmit` | ✅ 0 errors |
| Backend DDL syntax | Static review of SQL strings | ✅ Consistent with existing patterns |
| Backend Python syntax | Static review | ✅ No syntax errors, correct sqlite3 API usage |
| Backend smoke test | — (Python install corrupted) | ⚠️ Not executed |

---

## Known/Deferred Issues (not fixed — see TESTING_PLAN.md for full list)

- **H8** — Weak authz on writes: create/update/delete for cost documents only requires
  authentication, not admin/manager role. This is a design decision; deferred.
- **H9** — Audit logs never record the actor (`user_id`/`username` always null/empty).
  The router has `current_user` available; needs plumbing through all `_audit_log` calls.
- **M1** — `get_turnover_balance` outflow is permanently 0 (no code path creates
  negative `actual_costs.amount`). Functional but the outflow column is dead.
- **M3** — `profit` equals `−deviation` because `contract_value` is hardcoded to
  `planned_cost`. Needs a real contract-value source.
- **M8** — Timesheet labor posts with `work_id = 0`, distorting per-work cost.
- **L1–L9** — Various low-severity items (validation gaps, dead params, missing
  print/export, etc.) — see TESTING_PLAN.md.

---

## Summary

| Severity | Found | Fixed | Deferred |
|----------|-------|-------|----------|
| Critical | 3 | 3 | 0 |
| High (backend) | 7 | 7 | 0 |
| High (frontend) | 3 | 3 | 0 |
| Medium | 9 | 4 | 5 |
| Low | 9 | 0 | 9 |
| **Total** | **31** | **17** | **14** |

---

# Document List Framework — DOCUMENT_LIST_SPEC.md Implementation

Date: 2026-08-01
Spec: [DOCUMENT_LIST_SPEC.md](file:///f:/2026f/ctm3/CTM2_recovered/DOCUMENT_LIST_SPEC.md)

## Goal

Unify all 11 document list views to match 1C 8.3 thin-client dynamic list behavior:
server-side sorting, quick filter row, user-saved column settings, unified command bar,
context menu with submenus, and "Create on basis" (Ввод на основании).

## What was done

### Backend — server-side sort + quick filter + user settings + based_on columns

| Area | Files | Changes |
|------|-------|---------|
| Sort/filter helpers | [list_query.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/list_query.py) (new) | `resolve_sort` (whitelist), `order_by_clause` (tiebreaker by id), `apply_quick_filters` (field→sql_col map), `parse_quick_filters` (extracts `f_*` from query) |
| Cost-accounting lists | [cost_accounting_services.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/cost_accounting_services.py) | 5 list functions got `sort_by/sort_order/filters` params |
| Goods lists | [goods_services.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/goods_services.py) | `_list_documents` extended with sort/filter |
| Payment lists | [payment_services.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/payment_services.py) | schedules + transactions got sort/filter |
| Document lists | [services.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/services.py) | list_estimates, list_daily_reports, list_timesheets got `filters` (sort was already there) |
| Routers | [cost_accounting.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/routers/cost_accounting.py), [goods.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/routers/goods.py), [payments.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/routers/payments.py), [documents.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/routers/documents.py) | All list endpoints accept `sort_by/sort_order` + `Request`, parse `f_*` via `parse_quick_filters` |
| User settings API | [system.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/routers/system.py) | GET/PUT/DELETE `/api/system/user-settings/{form_name}[/{key}]` with upsert via `ON CONFLICT` |
| based_on columns | [database.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/database.py) | `_ensure_based_on_columns` — adds `based_on_type/id/number` to 7 result tables via ALTER |

### Frontend — unified declarative list framework

| Component / module | File | Purpose |
|--------------------|------|---------|
| DataTable | [DataTable.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/components/common/DataTable.vue) | Rewritten: sortable headers (▲▼ cycle asc→desc→null), filter row (text/number/date/month/select), marked-for-deletion row styling |
| ContextMenu | [ContextMenu.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/components/common/ContextMenu.vue) | Rewritten: unified item interface with `type:'separator'` + one-level `submenu`, viewport-clamped positioning |
| ListCommandBar | [ListCommandBar.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/components/documents/ListCommandBar.vue) (new) | Unified command panel: Create/Open/Copy/Post/Unpost/Delete, "Ввод на основании" dropdown, Filter/Settings/Refresh |
| ListSettingsDialog | [ListSettingsDialog.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/components/documents/ListSettingsDialog.vue) (new) | Column visibility checkboxes, Up/Down order, Reset to default |
| useDocumentList | [useDocumentList.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/composables/useDocumentList.ts) (new) | State, server load (sort+filters), sort cycle with settings save, selection, posting/delete commands, `openBaseOn()` |
| useListSettings | [useListSettings.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/composables/useListSettings.ts) (new) | `effectiveColumns`, `effectiveSort`, `saveColumns/saveSort/resetColumns` with debounce, load on mount |
| useDocumentListContextMenu | [useDocumentListContextMenu.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/composables/useDocumentListContextMenu.ts) (new) | Builds menu with submenu + separators, dispatches `based_on/<kind>` |
| Config types | [documentListTypes.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/config/documentListTypes.ts) (new) | `DocListConfig`, `DocListColumn`, `DocListApi`, `BaseOnTarget`, predicates |
| 11 list configs | [documentLists.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/config/documentLists.ts) (new) | One config per doc kind: columns, API, routes, baseOn registry |
| System API | [system.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/api/system.ts) | `getUserSettings/putUserSettings/deleteUserSetting` |

### Frontend — 11 ListView views converted

All use the unified template: `page-shell → panel → search-row → ListCommandBar → DataTable → pagination → ListSettingsDialog → ContextMenu`.

| View | Special features preserved |
|------|---------------------------|
| [EstimateListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/EstimateListView.vue) | Print (estimate + act), PrintFormatDialog |
| [DailyReportListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/DailyReportListView.vue) | Print |
| [TimesheetListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/TimesheetListView.vue) | Print, role-based `canManagePosting` for foreman |
| [MaterialConsumptionListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/MaterialConsumptionListView.vue) | — |
| [MachineryUsageListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/MachineryUsageListView.vue) | — |
| [SubcontractAcceptanceListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/SubcontractAcceptanceListView.vue) | — |
| [OverheadExpenseListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/OverheadExpenseListView.vue) | Distribution block (`distributeOverhead`/`cancel`) |
| [CostCalculationListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/documents/CostCalculationListView.vue) | Status state-machine, "Calculate" button |
| [GoodsDocumentListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/goods/GoodsDocumentListView.vue) | computed config from `props.kind` |
| [PaymentScheduleListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/payments/PaymentScheduleListView.vue) | formatNumber totals |
| [PaymentTransactionListView.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/views/payments/PaymentTransactionListView.vue) | `canOpen:false`, inline create form |

### "Create on basis" (Ввод на основании) — section 3.6

| Part | File | What |
|------|------|------|
| Navigation | useDocumentList.`openBaseOn()` | router.push with `based_on_type/id/number` query |
| Prefill composable | [useBasedOnPrefill.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/composables/useBasedOnPrefill.ts) (new) | Reads query params, loads source doc by kind, normalizes common requisites |
| Prefill in forms | DailyReportFormView, TimesheetFormView, MaterialConsumptionFormView, MachineryUsageFormView, PaymentScheduleFormView, GoodsDocumentFormView | onMounted prefill of header requisites + `based_on_*` fields into payload |
| Model types | [models.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/types/models.ts), [costAccounting.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/types/costAccounting.ts) | `based_on_type/id/number` optional fields on 7 result types |

### AppHeader fix

[AppHeader.vue](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/components/layout/AppHeader.vue) — header toolbar now renders actions via `<component :is>` with visible labels and glyphs instead of bare icon squares.

### Router fix

[index.ts](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/src/router/index.ts) — `/goods/issues` now passes `props: { kind: 'issue' }` (previously rendered as receipt).

## Verification

| Check | Command | Result |
|-------|---------|--------|
| Frontend types | `npx vue-tsc --noEmit` | ✅ 0 errors |
| Frontend build | `npx vite build` | ✅ built in 4.34s |
| Backend syntax | `py_compile` on all changed .py | ✅ 0 errors |

## Deferred (spec section 8)

- О1 Multiple sort (Shift+click) — out of scope
- О2 Filter persistence — not saved by default
- О3 Full "Selection & Sort" dialog — separate iteration
- О4 Column resize — separate iteration
- О6 Tabular part transfer on "Create on basis" — header only; lines remain manual
