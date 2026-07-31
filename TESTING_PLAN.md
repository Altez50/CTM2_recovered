# Cost Accounting Subsystem — Testing Plan

Scope: backend (`current/api`) + frontend (`current/web-client`) of the **cost accounting**
subsystem. Focus on form behavior as requested.

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

| # | Test | Expected | Status |
|---|------|----------|--------|
| P1 | Cost card (object + period) | elements + works rows | ⬜ |
| P2 | Cost turnover (period) | opening/inflow/outflow/closing | ⬜ |
| P3 | Cost deviations (period + threshold) | rows | ⬜ |
| P4 | Cost profitability (period) | per-object rows | ⬜ |
| P5 | Null/zero guard on `profitability_pct` / `deviation_pct` in tables | no JS crash | 🔬 FE-L5 |
| P6 | All 4 reports consistent initial-load behavior | parity | 🔬 FE-M9 |

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

**Medium** — see PROGRESS_LOG.md
