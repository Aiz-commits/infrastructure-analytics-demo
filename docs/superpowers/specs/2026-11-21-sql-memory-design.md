# Phase 1.5 — SQL Memory for the AI Controller — Design

Date: 2026-11-21
Builds on: `docs/superpowers/specs/2026-11-21-ai-controller-design.md` (Phase 1, live since PR #4 and #5).
Repo: `C:\Users\newga\projects\infrastructure-analytics-demo`, branch from `main`.

## 1. Intent and why

Phase 1's audit trail lives in the browser session and disappears on restart. Phase 1.5 saves every reviewed run in a real SQL database and shows a **public history** on the live site.

Why: the author (BBA student, Analytics & AI + FinTech) shares the live link on LinkedIn and with the university. A recruiter or professor who opens it at any time should see that the tool has real, persistent activity, and the author shows SQL skills. The same database feeds the Power BI dashboard in Phase 2.5.

The author's internship working file sets the tone: separate FACT from INTERPRETATION, write NEEDS CONFIRMATION instead of guessing, and keep real company data private. The history follows the same rules.

## 2. Goals

1. Every Approve/Reject on a **bundled synthetic example** is saved: the run, the values read, the checks, the AI/template text and the decision.
2. A **"Public history"** section on the AI Controller page shows the latest saved decisions and a few totals to every visitor.
3. The live site is **reachable at any time**: the database never needs a manual restore, and the app is kept awake.
4. The page **never breaks** when the database is down or asleep.
5. Free only: Neon free Postgres, Streamlit Community Cloud, GitHub Actions.
6. Tables are plain and typed so Power BI (Phase 2.5) can read them directly.

## 3. Non-goals (this phase)

- Saving visitor uploads. Only the two bundled examples in `controller_examples/` are saved.
- Accounts, logins or user names. The public history is anonymous.
- Editing or deleting history from the app. The author deletes rows in the Neon SQL console if ever needed.
- The Power BI dashboard itself (Phase 2.5).

## 4. Anti-goals (a failure even if it "works")

- **Real company data in the public database.** No real project names, amounts or files: only synthetic examples are ever written.
- **Visitor-typed text shown in public.** A visitor can edit the memo or email before approving. That edited text is never stored or shown, only a flag `edited = yes/no`. (Otherwise anyone could publish any text on the author's showcase page.)
- **The AI Controller fails because the database fails.** Save errors and read errors become a small notice; checks, memo and approval still work.
- **Raw errors or connection strings on screen.**
- **A paid service, or a secret in the repo.**
- **Spam taking over the history.** Limits in 7.4.

## 5. Constraints

- Keep Phase 1 rules: all money as `Decimal`, rates from `load_policy()`, `scripts/` modules free of Streamlit, tests never call real Gemini or a real database server.
- Dependencies pinned in `requirements.txt` and `requirements.lock`, binary wheels for Linux CPython 3.12 and 3.14 (CI runs both). Check before choosing a driver.
- Connection string from `st.secrets["DATABASE_URL"]`, read only in `app.py` like `GEMINI_API_KEY`. Locally in the git-ignored `.streamlit/secrets.toml`; on the cloud in Streamlit Secrets.
- Neon free plan (checked 2026-11-21): compute suspends after 5 min idle and resumes on the next query (sub-second to a few seconds); no manual restore; 1 GB storage per project. Streamlit Community Cloud sleeps an app after about 12 h without visitors (forum reports, not official docs).
- GitHub disables scheduled workflows in public repos after 60 days without repository activity, and emails the owner first.

## 6. Approaches considered

| | Approach | Trade-off | Decision |
|---|---|---|---|
| A | Neon Postgres + GitHub Actions keep-awake robot for the Streamlit app | One more free account; the robot is a workaround, not an official feature | **Chosen** by the author |
| B | Supabase Postgres + robot that also pings the database | Free projects pause after 1 week idle and need a manual restore if the robot fails | Rejected |
| C | History as a JSON/CSV file committed to GitHub | Not SQL, weak for Power BI, write conflicts between visitors | Rejected |

## 7. Design

### 7.1 When something is saved

- Saving happens **only when the reviewer clicks Approve or Reject**, and only when the current source is a bundled example (`source['example'] is True`). One click = one saved run. Reruns never write.
- Uploaded files: nothing is saved. The page says so next to the uploader: "Uploads are never saved to the public history."
- The save stores what the reviewer approved **as produced by the app** (AI or template text before edits) plus `edited` = whether any of memo / subject / body differs from that text.

### 7.2 Tables (Postgres on Neon; SQLite file locally and in tests)

`controller_runs`: one row per decision.
- `id` (identity primary key), `decided_at` (timestamp, UTC), `decision` (`Approved` / `Rejected`)
- `file_name`, `file_sha256`, `project`, `statement_number`
- `read_method` (`fixed layout` / `found by AI`), `language` (`fr` / `en`)
- `ai_used_text` (bool), `edited` (bool), `review_count` (int), `warning_count` (int), `rule_version`
- `memo`, `email_subject`, `email_body` (app-produced text, never the visitor's edits)

`controller_values`: 7 rows per run. `run_id`, `field`, `value` (numeric 14,2, null when not found), `cell`, `source`, `uncertain` (bool).

`controller_findings`: one row per check. `run_id`, `check_id`, `severity`, `title`, `stated`, `expected`, `difference` (numeric 14,2, nullable), `evidence`.

A view `v_controller_decisions` (one flat row per run with totals) is the entry point for Power BI. Schema is created by the app on first connect (`CREATE TABLE IF NOT EXISTS`), so the author never runs SQL by hand.

### 7.3 What visitors see

New section at the bottom of the AI Controller page:

```
📚 Public history (synthetic examples only)
 Runs saved: 42    Approved: 35    Rejected: 7    Problems flagged: 84
 Date/time (UTC)    File                 Decision   AI text   Problems
 2026-11-22 09:14   DEMO_DP_N5.xlsx      Approved   yes       2
 ...                (latest 20)
```

- Database unreachable → "Public history is temporarily unavailable." and the rest of the page works.
- No `DATABASE_URL` → the section shows "History not configured" locally; the app uses a local SQLite file only if the author sets `DATABASE_URL` to a `sqlite:///` path.
- The session audit trail from Phase 1 stays as it is.

### 7.4 Limits (public site)

- At most **5 saved decisions per browser session**, and one per (file, language) per session. Further clicks still work and still give downloads, with a note: "Not added to the public history (session limit)."
- Connect timeout 5 s, statement timeout 5 s, so a waking Neon compute never blocks the page for long.
- The history query reads at most 20 rows plus one totals query, cached for 60 s.

### 7.5 Keep-awake robot

- `.github/workflows/keep-awake.yml`: scheduled every 6 hours plus manual run. It opens the live app URL in a headless browser, clicks the "wake up" button if the sleep page shows, and waits until the app's title appears. Failure marks the run red (GitHub emails the owner).
- The app URL is a repository variable or written in the workflow; no secrets needed.
- The 60-day GitHub rule is accepted: the README notes "push any commit at least every 60 days, or re-enable the workflow when GitHub emails you".
- Neon needs no robot: it wakes on the next query.

### 7.6 Code layout

- `scripts/history.py`: pure Python, no Streamlit. `connect(url)`, `ensure_schema(conn)`, `save_run(conn, ...) -> int`, `latest_runs(conn, limit=20)`, `totals(conn)`. Works on Postgres and SQLite.
- `app.py`: reads `DATABASE_URL`, calls `save_run` inside the Approve/Reject handler, renders the Public history section; all database errors are caught there.
- `tests/`: `history.py` tested against a temporary SQLite file; AppTest checks that a database error shows the notice and that uploads never save.
- `.github/workflows/keep-awake.yml` and a README section "Public history and uptime".

### 7.7 Builder's calls (settled after the builder check, author can override)

- **Visitor-edited values are never saved.** If the visitor changes any value, the project or the statement number in the "Confirm values" step, the run is not saved (note: "Edited values are not added to the public history"). Same principle as the memo anti-goal: public rows only hold what the app read from the synthetic file.
- **Findings mapping.** Every finding is saved, including OK and SKIPPED (the `Finding.severity` set is already `OK | WARNING | REVIEW | SKIPPED`). `stated` / `expected` come from `Finding.amounts['stated']` / `['expected']` when present, else NULL. `Finding` is not changed.
- **Spam across sessions.** On top of the per-session cap, `save_run` skips a run when an identical (`file_sha256`, `language`, `decision`) was saved in the last 10 minutes, and stops saving after 200 runs per UTC day. Text columns are capped at 5,000 characters. With ~10 KB per run this stays far below 1 GB.
- **Reject then Approve.** The first saved decision per (file, language) per session counts; later clicks still work but are not added. A failed save does not use up the session quota; the notice says "Not saved to the public history (database busy) — click again."
- **One SQL dialect.** SQLAlchemy Core with the `psycopg` driver for Postgres and the standard `sqlite3` for SQLite, so the same code runs on both. Tests run on SQLite. Before merge, a one-off smoke test runs the same `save_run` / `latest_runs` against the author's Neon database locally (author supplies the connection string in `secrets.toml`).
- **Robot unverified in CI.** The workflow uses the live app URL as a repository variable `APP_URL`; its first manual run after merge is the check.

## 8. Success looks like

- Approve on the N5 example on the live site → the row appears in the Public history after a refresh, and is still there the next day.
- With `DATABASE_URL` wrong or Neon down, the AI Controller still runs end to end and shows the notice.
- Opening the live link after a quiet day loads the app without the sleep page (robot working).
- No uploaded file and no visitor-typed text ever appears in the database.
- Power BI Desktop can connect to Neon and read `v_controller_decisions` (checked in Phase 2.5).

## 9. Left to the builder

- Database driver and SQL layer (e.g. `psycopg` 3 or SQLAlchemy Core), within the binary-wheel constraint.
- Exact headless-browser tool for the robot (e.g. Playwright in GitHub Actions) and the wake-button selector.
- Widget layout and wording of notices, consistent with the page.
- Index choices.

## 10. Author steps (cannot be done by Claude)

1. Create a free Neon account and project; copy the connection string.
2. Put `DATABASE_URL = "..."` in local `.streamlit/secrets.toml` and in Streamlit Cloud Secrets.
3. Merge the PR; the robot starts on the next schedule.
