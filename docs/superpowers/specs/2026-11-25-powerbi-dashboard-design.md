# Phase 2.5 — Power BI Management Dashboard — Design

Date: 2026-11-25
Builds on: `docs/superpowers/specs/2026-11-21-ai-controller-design.md` (Phase 1) and
`docs/superpowers/specs/2026-11-21-sql-memory-design.md` (Phase 1.5, live since PR #6).
Repo: `infrastructure-analytics-demo` (assumed to be the "Excelium" project in the finance toolkit hub — NEEDS CONFIRMATION).

## 1. Intent and why

Streamlit is the working tool: one controller checks one statement. Phase 2.5 adds the **management view**: a Power BI report that answers "how much has been billed against the contract, where are the problems, and how fast do we decide?"

Why: the author (BBA, Analytics & AI + FinTech) shows a second, recruiter-recognised skill on top of Python and SQL. Power BI is the tool most finance and audit teams actually use. The report reads the same Neon database the live app writes to, so the story is one pipeline: **Excel statement → Python checks → SQL → Power BI**.

## 2. The data problem, stated plainly (FACT)

- The public history only saves the two bundled examples. Both are **statement D5 of `DEMO PROJECT`** (`controller_examples/DEMO_DP_N5*.xlsx`).
- So every row in `controller_runs` is the same statement read again. "Billed vs contract", "by contractor" and "trend over statements" have **one data point**.
- No table has a contractor. The contract value (`contract_ttc` = 5,400,000.00 DH) lives only in `project_config.json`.
- Only `decided_at` is stored. Time to approval cannot be computed.

A dashboard built only on the live history would show activity (runs, decisions, AI vs template, FR vs EN), not management finance. That is honest but thin.

## 3. Approaches considered

| | Approach | Trade-off | Decision |
|---|---|---|---|
| A | Live history only | 100 % real activity; finance pages near-empty (one statement) | Rejected as the only source |
| B | Synthetic portfolio only | Rich finance story; loses the "live app feeds the report" link | Rejected |
| C | **Two sources, two labelled areas.** Page 1 = live app activity (Neon history). Pages 2–4 = a **synthetic portfolio** (several projects, contractors, 6–10 statements each) generated once by Python and checked by the **same** `controller_checks` code | One more seeding script; every page must say which source it uses | **Recommended** (author can override) |

## 4. Goals

1. A Power BI report with 4 pages (7.4), built on SQL views, never on raw tables.
2. Every portfolio number is produced by the existing Python checks (`Decimal`, `load_policy()`), never typed into Power BI or invented by AI. Power BI only sums, counts and filters.
3. Each page shows its data source in a fixed footer: "Live app history — synthetic examples" or "Synthetic portfolio — generated, not real".
4. The live app keeps working exactly as today. Phase 2.5 never writes to the history tables except the new `opened_at` column (7.2).
5. Free only: Neon free plan, Power BI Desktop (free). Sharing per 7.7.

## 5. Non-goals

- Live market data, stock analysis, backtests or trading tools (OpenBB, TradingAgents, Qlib, ML for Trading). This project has no prices or tickers.
- Real company data of any kind (internship rule: real data stays private).
- Editing data from Power BI. Writing back to the database.
- Rebuilding Streamlit pages in Power BI.

## 6. Anti-goals (a failure even if it "works")

- **Synthetic portfolio numbers that look like real results.** Every portfolio page carries the "generated, not real" label; tables use the `portfolio_` prefix.
- **Power BI computing audit results.** A DAX measure that re-derives VAT or retention is a bug. Only totals, counts, ratios and averages.
- **Portfolio rows in the public history.** Portfolio tables are separate; the "Public history" section in the app is unchanged.
- **A read/write password in Power BI.** Power BI connects with a read-only role.
- **Numbers that differ between Streamlit, SQL and Power BI.** Section 8 reconciles them.

## 7. Design

### 7.1 Toolkit roles (from the finance toolkit hub)

| Tool | Role in Phase 2.5 |
|---|---|
| Excelium (this repo) | Source of truth: checks, history, portfolio generator, SQL views |
| Finance plugins | (a) Excel/model check skill: audit the exported portfolio workbook and the Power BI totals against SQL (section 8). (b) Report/memo skill: one-page management commentary for the PDF export. Exact skill names NEEDS CONFIRMATION — the plugins are installed on the author's PC, not in cloud sessions |
| FinceptTerminal | Design reference only: dense dark layout, KPI strip on top, small multiples, one accent colour for alerts. No data link |
| awesome-quant | Not needed unless a library gap appears |
| OpenBB, TradingAgents, Qlib, ML for Trading | Not used (section 5) |

### 7.2 Live history changes (small)

- Add `opened_at` (timestamp, UTC, nullable) to `controller_runs`: when the checks were first shown for that file and language in the session. Saved with the decision. Old rows stay NULL; time-to-approval measures ignore NULLs.
- `metadata.create_all` does not add columns to an existing table, so `ensure_schema` runs `ALTER TABLE controller_runs ADD COLUMN IF NOT EXISTS opened_at ...` on Postgres (and a guarded equivalent on SQLite).
- `opened_at` is a server timestamp, not visitor text, so the public-data rules in Phase 1.5 still hold.

### 7.3 Synthetic portfolio

- `scripts/portfolio.py` (no Streamlit): generates a fixed, seeded portfolio, for example **3 projects × 2–3 contractors × 6–10 statements**, with contract values in DH.
- Each statement is built as a `ControllerStatement` and passed through the **real** `run_checks` with the real policy. About 1 in 5 statements gets a planted problem (continuity gap, VAT off, retention off, missing statement) so findings are produced by Python, not written by hand.
- Decision and timing are simulated with a seeded random generator: `submitted_at`, `opened_at`, `decided_at`, decision (Rejected more likely when a REVIEW finding exists). Labelled simulated.
- Tables: `portfolio_projects` (project, contractor, contract_ttc, start_date), `portfolio_statements` (one row per statement with the 7 values and the timings), `portfolio_findings` (same columns as `controller_findings`).
- Deterministic: the same seed gives the same rows; a test pins the totals.
- Loaded by a command the author runs once: `python -m scripts.portfolio --load` (uses `DATABASE_URL`; replaces only `portfolio_*` tables). Also `--csv outputs/portfolio/` so Power BI can be built offline without Neon.

### 7.4 SQL views (the only thing Power BI reads)

| View | Grain | Feeds |
|---|---|---|
| `v_controller_decisions` (exists) + `opened_at`, `minutes_to_decision` | one live run | Page 1 |
| `v_controller_findings` | one live finding, with run date, decision, language | Page 1 |
| `v_portfolio_statements` | one statement: project, contractor, number, works, cumulative, ttc, contract_ttc, % of contract billed, review_count, decision, days submitted→decided | Pages 2–4 |
| `v_portfolio_findings` | one finding with project, contractor, statement, check type (`check_id` grouped: arithmetic / continuity / sequence / missing value) | Page 3 |

Views live in `scripts/history.py` (live) and `scripts/portfolio.py` (portfolio), created by the same `ensure_schema` pattern. Tested on SQLite.

### 7.5 Report pages

1. **Live app activity** (source: live history) — KPI strip: runs saved, approval rate, problems flagged, AI-text share. Runs per day, decisions by file and language, findings by severity, median minutes to decision (rows with `opened_at`).
2. **Portfolio overview** (synthetic) — KPI strip: contract value, billed TTC to date, % of contract billed, open REVIEW findings. Billed vs contract by project (bullet bars), cumulative billing curve per project.
3. **Findings** (synthetic) — findings by check type × contractor (matrix/heatmap), difference amounts by check type, top statements with problems (drill-through to the finding list with evidence cells).
4. **Approval speed** (synthetic) — days to decision by contractor and decision, trend over statement number, share decided within a target (e.g. 5 days; demo assumption).

Slicers on pages 2–4: project, contractor, period. Theme: a `powerbi/theme.json` (dark, FinceptTerminal-style, one alert colour, colour-blind-safe palette).

### 7.6 Files in the repo

- `powerbi/README.md` — step-by-step build guide for Power BI Desktop: connect to Neon (or the CSVs), load the 4 views, relationships, measures, pages.
- `powerbi/measures.dax` — every measure with a one-line comment (totals, counts, ratios, medians only).
- `powerbi/theme.json` — report theme.
- `powerbi/readonly_role.sql` — `CREATE ROLE powerbi_reader ...; GRANT SELECT` on the views only (run once by the author in the Neon SQL editor).
- `screenshots/powerbi_*.png` and a PDF export, added by the author after building.
- The `.pbix` itself is built on the author's PC. Committing it is optional (binary, ~1 MB); if committed, no credentials are stored in it (Power BI stores them outside the file).

### 7.7 Sharing

- Default: screenshots in the README + PDF export + a short screen recording for LinkedIn.
- If the author's university Microsoft 365 account allows Power BI Service: publish to a workspace and share with the university. "Publish to web" (public link) is often disabled by tenant admins — NEEDS CONFIRMATION with the university account.
- Scheduled cloud refresh from Neon is a nice-to-have, not required (whether the Power BI Service refreshes a cloud Postgres without a gateway: NEEDS CONFIRMATION when tried).

## 8. Reconciliation (how we know the numbers are right)

- A pytest computes, from the generated portfolio in SQLite, the headline numbers: total billed TTC per project, % of contract, count of REVIEW findings per contractor, median days to decision. They are written to `powerbi/expected_totals.json`.
- After building the report, the author (or the finance plugins' Excel check skill on the author's PC) compares the Power BI cards to that file. Any difference above 0.01 DH is a bug in the model or a measure.
- Live page: the Power BI "runs saved / approved / rejected" cards must equal the "Public history" totals in the app at the same moment.

## 9. Success looks like

- `python -m scripts.portfolio --load` fills Neon; re-running it gives identical rows.
- Power BI Desktop connects with `powerbi_reader` and loads only views.
- All four pages show the source footer; portfolio pages say "generated, not real".
- Headline numbers match `expected_totals.json`.
- Approving on the live site and refreshing Power BI adds one run on page 1.
- The live app, its tests and the public history behave exactly as before.

## 10. Constraints

- Keep Phase 1 / 1.5 rules: `Decimal` money, `load_policy()` rates, `scripts/` free of Streamlit, tests never touch a real database or Gemini.
- No new runtime dependency for the app. The portfolio script uses only what is already pinned.
- CI stays green on Python 3.12 and 3.14.

## 11. Left to the builder

- Exact portfolio size, project and contractor names (obviously fictional), and which statements get planted problems.
- Exact view column names and SQL for the median (Postgres `percentile_cont`; SQLite computed in the test instead).
- Wording of the build guide.

## 12. Author steps (cannot be done in a cloud session)

1. Confirm "Excelium" = this repo, and approach C.
2. Run `powerbi/readonly_role.sql` in the Neon SQL editor; keep the reader password in a password manager.
3. Run `python -m scripts.portfolio --load` locally with `DATABASE_URL` in `.streamlit/secrets.toml`.
4. Build the report in Power BI Desktop following `powerbi/README.md`; take screenshots; export PDF.
5. Run the reconciliation (section 8) with the finance plugins on your PC.
6. Optional: try Power BI Service with the university account.
