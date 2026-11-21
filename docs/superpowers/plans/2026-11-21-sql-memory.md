# Phase 1.5 SQL Memory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save every Approve/Reject on the bundled synthetic examples to a Postgres database (Neon) and show a public history on the AI Controller page, with the site kept awake.

**Architecture:** New pure module `scripts/history.py` (SQLAlchemy Core, one code path for Postgres and SQLite). `app.py` reads `DATABASE_URL`, saves inside the decision handler under the session rules, and renders a cached "Public history" section. A GitHub Actions workflow keeps the Streamlit app awake.

**Tech Stack:** SQLAlchemy 2.1.8, psycopg[binary] 3.3.8 (Postgres driver), stdlib sqlite3 (tests/local), Streamlit 1.67, Playwright in GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-21-sql-memory-design.md`

## Global Constraints

- Save only when `source['example'] is True` AND no value/project/number was edited in Confirm.
- Never store visitor-typed memo/email text: store the app-produced `Texts` + `edited` bool.
- `scripts/history.py` never imports `streamlit`. Only `app.py` reads `st.secrets["DATABASE_URL"]`.
- Money columns `NUMERIC(14,2)`, written as `Decimal`. Timestamps UTC.
- Text columns capped at 5,000 characters. Dedupe window 10 minutes on (`file_sha256`, `language`, `decision`). Daily cap 200 runs per UTC day.
- Session: max 5 saves; one per (`digest`, `language`); failed save does not consume quota.
- Postgres: connect timeout 5 s, statement timeout 5 s.
- Database failure never breaks the page: notice only, no raw error, no connection string on screen.
- Tests never touch a real database server or real Gemini; SQLite temp files only.
- Pins: `SQLAlchemy==2.1.8`, `psycopg[binary]==3.3.8` in `requirements.txt` + regenerated lock (Linux wheels for 3.12 and 3.14 verified).
- No Co-Authored-By trailer; commit as `Aiz-commits` via `git -c`.

## Review Focus

1. **Neon string as copied** (`postgresql://…?sslmode=require&channel_binding=require`) → must become `postgresql+psycopg://…` or SQLAlchemy picks psycopg2. Test in Task 1.
2. **Neon cold start / wrong password** → save raises, notice "click again", quota untouched; history shows "temporarily unavailable". Tests in Tasks 2 and 3.
3. **Double click / rerun after Approve** → exactly one row. Test in Task 2.
4. **Visitor edits a value in Confirm on the new-layout example** → no row. Test in Task 2.
5. **`ensure_schema` run twice / by two sessions** → idempotent, view created once. Test in Task 1.

---

### Task 1: `scripts/history.py` — schema, save, read

**Files:** Modify `requirements.txt`, `requirements.lock`, `.gitignore` (add `data/*.sqlite`). Create `scripts/history.py`, `tests/test_history.py`.

**Interfaces — Produces:**
- `MAX_TEXT = 5000`, `DAILY_CAP = 200`, `DEDUPE_MINUTES = 10`
- `normalize_url(url: str) -> str` — `postgres://` / `postgresql://` → `postgresql+psycopg://`; `sqlite:///…` unchanged; anything else → `ValueError`.
- `get_engine(url: str) -> sqlalchemy.Engine` — Postgres: `connect_args={'connect_timeout': 5, 'options': '-c statement_timeout=5000'}`, `pool_pre_ping=True`.
- `ensure_schema(engine) -> None` — tables `controller_runs`, `controller_values`, `controller_findings` (columns as spec 7.2) and view `v_controller_decisions` (run columns + `review_count`, `warning_count`); idempotent.
- `@dataclass(frozen=True) RunRecord(decided_at: datetime, decision: str, file_name: str, file_sha256: str, project: str, statement_number: int | None, read_method: str, language: str, ai_used_text: bool, edited: bool, rule_version: str, memo: str, email_subject: str, email_body: str)`
- `save_run(engine, record: RunRecord, statement: Statement, findings: list[Finding]) -> int | None` — one transaction; returns new run id, or `None` when skipped by dedupe or daily cap. `review_count` / `warning_count` computed from findings. `stated`/`expected` from `Finding.amounts` keys when present.
- `latest_runs(engine, limit: int = 20) -> list[dict]` — keys `decided_at, file_name, decision, ai_used_text, review_count`, newest first.
- `totals(engine) -> dict` — keys `runs, approved, rejected, problems` (problems = sum of `review_count`).

- [ ] **Step 1:** Pin deps, regenerate lock with `uv pip compile requirements.txt -o requirements.lock --python-version 3.12 --python-platform linux --no-header`, restore the 2 header lines, verify `pip download --only-binary=:all:` for 3.12 and 3.14 (manylinux x86_64).
- [ ] **Step 2: Failing tests** (`tmp_path / 'h.sqlite'`, N5 statement + findings from `controller_checks`):
  - `test_normalize_url` — `postgresql://u:p@h/db?sslmode=require&channel_binding=require` → `postgresql+psycopg://u:p@h/db?sslmode=require&channel_binding=require`; `postgres://` same; `sqlite:///x.db` unchanged; `mysql://` raises.
  - `test_schema_idempotent` — `ensure_schema` twice, no error, view queryable.
  - `test_save_and_read_back` — `save_run` returns int; 1 run, 7 values (VAT `Decimal('163000.00')`, cell `D45`), findings incl. `continuity` REVIEW with `difference == Decimal('12300.00')`; `totals == {'runs': 1, 'approved': 1, 'rejected': 0, 'problems': 2}`.
  - `test_dedupe_within_10_minutes` — same sha/lang/decision at +5 min → `None`; at +11 min → int; different decision → int.
  - `test_daily_cap` — with `DAILY_CAP` patched to 2, third save same UTC day → `None`.
  - `test_text_capped` — memo of 6,000 chars stored as 5,000.
  - `test_latest_runs_newest_first_and_limited`.
- [ ] **Step 3:** Run `pytest tests/test_history.py -q` → FAIL (module missing).
- [ ] **Step 4:** Implement with SQLAlchemy Core `MetaData`/`Table` (`Numeric(14, 2)`, `DateTime(timezone=True)`, `Identity()` primary key) and `metadata.create_all`; view via `text()` using `CREATE VIEW IF NOT EXISTS` on SQLite and `CREATE OR REPLACE VIEW` on Postgres (`engine.dialect.name`).
- [ ] **Step 5:** Run full `pytest -q` → PASS. Commit `feat: add SQL history store`.

### Task 2: App — save on decision under the session rules

**Files:** Modify `app.py`. Create `tests/test_history_app.py`.

**Interfaces — Consumes:** Task 1 API; `Texts`, `Statement`, `SOURCE_EDITED`.
- `database_url() -> str | None` in `app.py` (same pattern as `gemini_key()`).
- `@st.cache_resource history_engine(url)` → `get_engine` + `ensure_schema`.
- Session keys: `ctrl_saved: set[tuple]` of (`digest`, `language`), `ctrl_values_edited: set[str]` of digests.
- In `confirm_values`: if `apply_edits` changed any value, project or number → add digest to `ctrl_values_edited`.
- In `review_texts`, on a new click: try save when example, not edited-values, `len(ctrl_saved) < 5`, key not in `ctrl_saved`. On `int` → add key, `st.caption('Added to the public history.')`; on `None` → caption "Not added (duplicate or daily limit)"; on exception → caption "Not saved to the public history (database busy) — click again." and do NOT add key. Uploads → caption "Uploads are never saved to the public history."
- `edited` = memo/subject/body differ from the app-produced `Texts`; store the app-produced text.

- [ ] **Step 1: Failing AppTests** (secrets `DATABASE_URL = f'sqlite:///{tmp_path}/h.sqlite'`, `_generate` patched to `None`):
  - `test_approve_example_saves_one_row` — example → Approve → 1 row; extra `run()` ×2 → still 1.
  - `test_reject_then_approve_saves_first_only`.
  - `test_upload_never_saved` — upload N5 bytes via patched uploader → Approve → 0 rows, caption shown.
  - `test_edited_values_not_saved` — fake AI reader returns traced statement; confirm with an edited value → Approve → 0 rows.
  - `test_db_failure_keeps_page_working` — `DATABASE_URL = 'postgresql://x:y@127.0.0.1:1/none'` → Approve works, "click again" caption, no exception, no `postgresql://` text on page.
  - `test_edited_memo_stores_app_text` — change memo text area, Approve → stored memo equals app text, `edited` true.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Full `pytest -q` → PASS. Commit `feat: save reviewed example runs to the public history`.

### Task 3: App — Public history section

**Files:** Modify `app.py`, `tests/test_history_app.py`.

- `@st.cache_data(ttl=60) public_history(url) -> tuple[dict, list[dict]]` (`totals`, `latest_runs`); cleared after a successful save.
- Section at page bottom, also shown before any example is loaded: header `📚 Public history (synthetic examples only)`, 4 `st.metric` (Runs saved, Approved, Rejected, Problems flagged), table (Date/time UTC, File, Decision, AI text yes/no, Problems).
- No URL → `st.caption('Public history not configured.')`. Exception → `st.info('Public history is temporarily unavailable.')`.

- [ ] **Step 1: Failing AppTests:** `test_history_shows_saved_run` (after Approve, section lists `DEMO_DP_N5.xlsx`, metric Runs saved = 1); `test_history_unavailable_notice` (bad URL → info text, no exception); `test_history_not_configured` (no secret → caption).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Full `pytest -q` → PASS. Commit `feat: show public history on the AI Controller page`.

### Task 4: Keep-awake robot + README

**Files:** Create `.github/workflows/keep-awake.yml`. Modify `README.md`.

- Workflow: `on: schedule: cron '17 */6 * * *'` + `workflow_dispatch`; `permissions: contents: read`; job on `ubuntu-latest`: setup Python 3.12, `pip install playwright==<pinned, ≥2 weeks old>` + `playwright install --with-deps chromium`, run inline script: open `${{ vars.APP_URL }}`; if a button whose text contains "get this app back up" exists, click it; wait up to 180 s for text "Infrastructure Analytics Demo" in any frame; exit 1 if not found. Skip with a notice when `APP_URL` is empty.
- README: section "Public history and uptime" — what is saved/never saved, `DATABASE_URL` secret, Neon free plan behavior, robot + `APP_URL` repo variable, the 60-day GitHub rule.

- [ ] **Step 1:** Write workflow; validate YAML parses. **Step 2:** README. **Step 3:** Full `pytest -q` → PASS. Commit `ci: keep the live app awake; docs: public history`.

### Task 5: Neon smoke test + live check (needs the author)

- [ ] **Step 1:** Author pastes the Neon string into `.streamlit/secrets.toml` (`DATABASE_URL`). Run a local script that reads it (never prints it), calls `get_engine` → `ensure_schema` → `save_run` with the N5 record → `latest_runs` → deletes that smoke row. Expected: id int, row read back, cleanup ok, timing printed.
- [ ] **Step 2:** `streamlit run app.py` locally, Approve N5, history shows the row.
- [ ] **Step 3:** Push branch, PR (author creates and merges), author adds `DATABASE_URL` to Streamlit Secrets and `APP_URL` repo variable, runs the workflow once manually.
