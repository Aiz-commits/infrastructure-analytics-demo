# Phase 2.5 Power BI Dashboard — Implementation Plan

**Goal:** Feed a 4-page Power BI management report from SQL views: live app activity plus a synthetic portfolio checked by the real Python checks.

**Spec:** `docs/superpowers/specs/2026-11-25-powerbi-dashboard-design.md`

## Global constraints

- Power BI reads views only, never tables. View columns are a contract: append only, pinned by tests.
- Every portfolio finding comes from `run_checks` with `load_policy()`. Power BI never re-derives an audit result.
- Portfolio rows live in `portfolio_*` tables, never in the public history. Every portfolio output says "generated, not real".
- `scripts/` stays free of Streamlit. Tests use SQLite only. No new dependencies.
- Commits authored as `Aiz-commits`, with no Co-Authored-By trailer.

## Tasks

- [x] **1. Live history:** add `opened_at` to `controller_runs` with an in-place migration (Postgres `ADD COLUMN IF NOT EXISTS`, SQLite inspect). Extend `v_controller_decisions` with `opened_at` and `minutes_to_decision`; add `v_controller_findings` with `check_group`. Add a shared `create_views`. Tests: migration of a Phase 1.5 database, minutes, check groups, view contract.
- [x] **2. App:** record the first time the checks are shown per (file, language) and save it with the decision. AppTest: the saved row has `opened_at` ≤ `decided_at`.
- [x] **3. `scripts/portfolio.py`:** fixed projects, a `PLANTED` answer key, seeded timings, tables, views, `load` (delete and re-insert), `view_rows`, `expected_totals`, `export_csv`, CLI. Tests: deterministic output; planted problems found; REVIEW → Rejected; SQL views equal the Python rows; reload is idempotent; committed CSV and JSON are current.
- [x] **4. `powerbi/`:** README build guide, `measures.dax`, `theme.json` (palette validated for colour-blind readers on the dark surface), `readonly_role.sql`, `data/*.csv`, `expected_totals.json`.
- [ ] **5. Author on PC:** load Neon, create the read-only role, build the `.pbix`, reconcile against `expected_totals.json`, add screenshots and a PDF.
