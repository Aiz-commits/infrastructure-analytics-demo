# Phase 3 — AI agent + email automation (design)

Date: 2026-11-27. Status: approved choices 1B, 2, 3A, 4A (user, 2026-11-27). Builds on
`2026-11-21-ai-controller-design.md` (section 10 roadmap) and Phase 2 (`2026-11-25-pdf-photo-reading-design.md`).

## 1. Intent

Today a person opens the Streamlit app, uploads a décompte, and clicks Approve. Phase 3 shows the same controller
working **by itself**: a décompte arrives by email, an AI agent decides which checks to run, Python runs them, and the
reviewer gets a phone alert with a link to approve or reject. A human still makes every decision.

Why: a portfolio / LinkedIn demo for the Excelium internship that shows "agent + automation" done safely on money
data. Success = a short screen recording where an email goes in and an approve link arrives on the phone, plus a
plain-language guide a client (a project owner or site accountant, not a developer) can read and understand.

## 2. Goals, non-goals, anti-goals

Goals
1. AI agent picks checks through tool calls (Gemini function calling); a Python guard makes sure no core check is
   ever skipped, and records what the AI skipped.
2. A small local FastAPI service runs the whole controller: read → agent checks → memo/email → pending review →
   approve/reject.
3. n8n (local, http://localhost:5678) watches a demo Gmail inbox and posts each décompte attachment to the API, then
   sends a phone alert through ntfy with the result and a review link.
4. Clear explanation for clients: a guide, a "what happened" timeline on the review page, and a README section.

Non-goals
- No public hosting of the API or n8n (local demo, approach A). Visitors keep using the Streamlit app.
- No change to how the Streamlit app checks décomptes (it keeps `run_checks`).
- No sending of the contractor email. Approve still means "approved by the reviewer"; nothing is emailed out.
- No BPU / price list checks (Phase 4).

Anti-goals (a failure even if it "works")
- A core money check silently missing from a result.
- A décompte approved without a human seeing the values and findings (including link-preview bots "clicking").
- Values read by AI (PDF/photo/unknown layout) approved without the reviewer confirming them (Phase 2 rule).
- Anyone who sees or receives the alert link, or guesses a URL, being able to approve without the reviewer PIN;
  anyone outside the sender allowlist being able to push files into the API.
- Real company data or secrets in the repo, the alert, or the public history.

## 3. Constraints

- Windows PC, Python `.venv` (3.14), n8n 2.49.8 on Node 24 (`C:\Users\newga\tools`), no Docker.
- Gemini `gemini-3.1-flash-lite` free tier: rate limits, sometimes returns nothing. Every AI call must have a
  non-AI fallback (existing rule: failures return None).
- Python does every calculation; the AI never produces an amount that ends up in a finding.
- Reuse `scripts/` modules; no Streamlit imports in new code. Files under 500 lines.
- Public history rule (Phase 1.5) stays: only bundled example files go to the public Neon history.
- Synthetic data only.

## 4. Approaches considered

| | Approach | Trade-off | Decision |
|---|---|---|---|
| 1A | Fixed 7 core checks + AI only adds extras | Safest, but not really an agent | Rejected |
| **1B** | **AI chooses checks via tools; Python guard adds any skipped core check and logs it** | Real agent, nothing missed, the guard is visible | **Chosen** |
| **2** | **Local FastAPI wrapping existing `scripts/`** | Only sensible option for a local demo | **Chosen** |
| **3A** | **ntfy push (free, no account) with a review link** | Link works on the same Wi-Fi as the PC | **Chosen** |
| 3B | Telegram bot | Nicer, but buttons need the PC reachable from the internet | Rejected |
| **4A** | **New demo Gmail read by n8n over IMAP (app password)** | Keeps real mail out; quick setup | **Chosen** |
| 4B | Own Gmail through Google OAuth | Slow Google Cloud setup | Rejected |

## 5. How it works (end to end)

```
Demo Gmail ──IMAP──> n8n "Décompte inbox" workflow
                       │ 1. for each attachment (.xlsx .pdf .jpg .png)
                       │ 2. POST /intake  (header X-API-Key)            ┌───────────────────────────┐
                       └──────────────────────────────────────────────> │ FastAPI on the PC :8000   │
                                                                        │  read values (Phase 1/2)  │
                       ┌── JSON: summary + review_url ───────────────── │  agent picks checks (AI)  │
                       │ 3. POST to ntfy topic (title, summary, link)   │  guard adds missed checks │
                       v                                                │  memo + email (Phase 1)   │
                  Phone (ntfy app) ── tap "Review" ──> GET /review/... ─>│  pending run (SQLite)     │
                                                     POST approve/reject│  → public history if      │
                                                                        │    bundled example        │
                                                                        └───────────────────────────┘
```

### 5.1 Reading (reuse)

New pure module `scripts/intake.py` (no Streamlit) that turns file bytes into a `Statement` and a read method, using
exactly the Phase 1/2 paths: `detect_kind` + `check_limits`; xlsx → `extract_decompte` (fixed layout) else
`read_with_ai`; pdf → `read_pdf_with_ai` (vision fallback for scans as in Phase 2); jpg/png → `read_with_vision`.
The Streamlit `ui/document_section.py` logic is moved here where it is not UI-specific; the app keeps working the same
(its tests must stay green). Bundled examples keep the saved-answer fallback (`load_saved_answer`) so the demo works
when Gemini is rate-limited.

`needs_confirmation = True` when any value came from AI (sources in `AI_SOURCES`). This flag drives the review page
(section 5.5). `AI_SOURCES` moves from `app.py` into `scripts/controller_checks.py` (app imports it from there).
Bundled examples live in `controller_examples/` (with `*.answer.json` saved answers) and `demo_decomptes/`; saved
answers are matched by file SHA-256, not file name.

### 5.2 Agent: the AI picks checks (approach 1B)

New module `scripts/agent.py`.

Tools exposed to Gemini (function declarations). Each tool is a thin wrapper over the existing check code, so results
are identical to `run_checks`:

| Tool | Core? | Runs |
|---|---|---|
| `check_retention` | core | retention finding |
| `check_net` | core | net HT finding |
| `check_vat` | core | VAT finding |
| `check_ttc` | core | TTC finding |
| `check_cumulative` | core | cumulative finding |
| `check_history` | core | continuity + sequence (looks up the previous décompte itself via `previous_from_history`) |
| `check_contract_ceiling` | optional (new) | contract progress = cumulative HT × (1 + VAT rate) ÷ `policy.contract_ttc` — the same formula as the live app's "Indicative Contract Valuation" metric (`app.py`, saved page), before retention. REVIEW when strictly above 100 %, OK otherwise; SKIPPED if cumulative missing. Evidence states the percentage |
| `finish` | — | AI says it is done, with a one-sentence reason per check it chose not to run |

To make tool results identical, `_arithmetic` in `controller_checks.py` is split into one function per check
(same titles, ids, evidence, severities); `run_checks` keeps its output byte-for-byte (existing tests prove it).

Loop
1. Prompt = the values read (field → number or "missing"), project, statement number, and the list of tools with
   plain descriptions. Instruction: choose the checks this décompte needs, call them, then call `finish`.
2. Gemini call with `tools=[...]`, automatic function calling **off**, temperature 0. For each function call returned,
   Python runs the tool and sends back a short result (`severity` + `title`, never asks the AI to compute).
3. Stop at `finish`, or after **8 turns**, or on any AI failure. Each turn sends back the model's previous content
   unchanged (Gemini 3 requires its thought signatures to be returned) plus the function responses.
4. Guard: every core tool not called is run by Python and logged as `added by guard`. Missing/uncertain value
   warnings are always produced by Python (same as `run_checks`), not by the AI.
5. If the AI is unavailable from the start: run all core checks, trace says "AI planner offline — all core checks run".

Output: `AgentResult(findings, trace)`. `trace` is a list of steps, each `{who: 'AI'|'guard'|'Python', action,
check_id, reason}` — shown to the reviewer as the "what happened" timeline and stored with the run. Findings order:
warnings, then checks in the standard `run_checks` order (so memo text is stable whatever order the AI used).

Memo and email: existing `write_texts` (number-checked AI text, template fallback), language `fr` by default.

### 5.3 API (FastAPI, local)

Package `api/` (`api/main.py` app factory, small helpers in `scripts/`). Run with
`uvicorn api.main:app --host 0.0.0.0 --port 8000`. Dependencies in a separate `requirements-api.txt`
(fastapi, uvicorn, python-multipart, pinned) so Streamlit Cloud is not affected.

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | none | `{"status":"ok"}` |
| `POST /intake` | header `X-API-Key` + sender allowlist | multipart file + required `sender` (+ optional `subject`). Sender not in `ALLOWED_SENDERS` → 403, nothing read, no AI call. Reads, runs agent, writes texts, stores a pending run. Returns `{run_id, project, number, review_count, warning_count, needs_confirmation, summary, review_url}` |
| `GET /review/{run_id}?t=TOKEN` | review token | HTML page (section 5.5). Never changes state |
| `POST /review/{run_id}/decision` | review token + reviewer PIN (form fields) | `decision=Approved|Rejected`, `pin`, plus `confirmed_values=on` when required for Approve. Single use |
| `GET /runs/{run_id}` | header `X-API-Key` | JSON of the run (for n8n / debugging) |

Security rules
- `X-API-Key` = `AGENT_API_KEY` from `.streamlit/secrets.toml` (same file as the Gemini key; gitignored). Compared with
  `hmac.compare_digest`. Missing key in config → API refuses to start.
- Review token: `secrets.token_urlsafe(32)` per run; only its SHA-256 is stored; valid 48 h; after a decision the
  token is spent and the page shows the decision read-only.
- GET never approves (link previews and chat apps open links automatically). Approve is a POST from a button.
- Reviewer PIN (user decision 2026-11-27): `REVIEWER_PIN` (6 digits) in `secrets.toml`, required for both Approve and
  Reject, compared with `hmac.compare_digest`. The link alone only lets someone *read* the review page. 5 wrong PINs
  on a run lock that run (page says "locked — re-send the email"). Missing/invalid PIN in config → API refuses to start.
- Sender allowlist (user decision 2026-11-27): `ALLOWED_SENDERS` (list of emails, compared lower-case) in
  `secrets.toml`. n8n drops other senders before calling the API (no alert); `/intake` checks again (defence in depth).
  Empty list → API refuses to start.
- File limits from `documents.py` (`check_limits`), plus a 10 MB request cap; unknown types → 415 with a clear message.
- Errors return JSON `{error: "<plain sentence>"}`; never a stack trace.

### 5.4 Storage

- Pending runs: local SQLite `data/agent_runs.sqlite` (gitignored), table `agent_runs` (id, created_at, file_name,
  file_sha256, sender, subject, statement JSON, findings JSON, trace JSON, texts, language, read_method,
  needs_confirmation, token_hash, token_expires_at, decision, decided_at). Original file kept in
  `data/agent_files/<sha256>` so the review page can show/download it.
- On decision: if `file_sha256` is one of the bundled example files (`controller_examples/` + `demo_decomptes/`) and
  `DATABASE_URL` is set, save to the public Neon history with `save_run` (read_method suffixed `" via email"`,
  e.g. `fixed layout via email`). Otherwise local only. A database failure never undoes the decision.
  Optional findings (`check_contract_ceiling`) are **removed before `save_run`**, so the public history and the Power
  BI views get exactly the same findings as a Streamlit approval of the same file (no view or Power BI change).

### 5.5 Review page (what the reviewer sees on the phone)

Plain HTML, mobile-first, no JavaScript framework, French/English labels matching the memo language. Top to bottom:
1. Status line: project, D-number, "2 points to review / 0 warnings", received from <sender> at <time>.
2. **What happened** timeline (from the trace), e.g. "Email received → values read (fixed layout) → AI chose 6
   checks: retention, net, VAT, TTC, cumulative, contract ceiling → Guard added 1 the AI skipped: history → Memo
   drafted (AI, number-checked)".
3. Values read table (field, value, where it was found, source; uncertain marked).
4. Findings table (OK / REVIEW / WARNING / SKIPPED with the difference and evidence).
5. Memo and email draft (read-only).
6. Link to open the original file.
7. If `needs_confirmation`: a required checkbox "I compared these values with the attached document". Without it the
   server rejects Approve with a clear message. Values cannot be edited on this page (user decision 2026-11-27):
   a wrong value means Reject, fix the file, email it again — the page says this next to the checkbox.
8. PIN field + buttons Approve / Reject. After a decision: a confirmation line, the page becomes read-only.

### 5.6 n8n workflow "Décompte inbox"

Built in the local n8n through the n8n MCP (validated there), exported to `automation/n8n/decompte_inbox.json` with no
secrets (credentials referenced by name; ntfy topic and API key as placeholders documented in the guide).

1. **Email Trigger (IMAP)** on the demo Gmail, unread mail only, download attachments, mark as read.
   Then a **sender filter**: only `From` addresses in the allowlist continue; others stop silently.
2. **Split attachments**; keep `.xlsx .pdf .jpg .jpeg .png`; others → ntfy "ignored attachment <name>".
3. **HTTP Request** POST `http://localhost:8000/intake` (multipart, `X-API-Key` from an n8n credential).
4. **HTTP Request** POST `https://ntfy.sh/<topic>` with title "Décompte D5 — 2 to review", message = `summary`,
   click/action = `review_url`, priority high when `review_count > 0`.
5. Error path (API down, read failed): ntfy "Could not process <file>: <plain reason>".

ntfy topic: a long random name (it acts as the password for the channel). The alert contains summary counts and
project / D-number only — no amounts.

### 5.7 Phone link reachability

`REVIEW_BASE_URL` in secrets = `http://<PC LAN IP>:8000`. Works when the phone is on the same Wi-Fi. Windows
Firewall must allow inbound TCP 8000 on the Private profile — the user runs that one command (a security setting), the
guide shows it. Remote access (tunnel) is out of scope.

## 6. Making it understandable for clients

1. `docs/phase3-automation-guide.md`: plain language, numbered, for a non-developer. Sections: what it does in one
   paragraph; the picture above; what you receive on your phone and what each word means (OK, REVIEW, WARNING,
   SKIPPED, "added by guard"); what the AI decides and what it never decides; what Approve does and does not do;
   how to set it up (Gmail app password, ntfy app + topic, start n8n, start API, firewall); troubleshooting
   (no alert, link does not open, "AI offline").
2. The review page timeline (5.5 #2) explains every run in words.
3. README: a short "Phase 3 — email automation (local demo)" section linking the guide.
4. Startup scripts `automation/start_api.ps1` and `automation/start_n8n.ps1` so setup is two commands.

## 7. Error handling

| Situation | Result |
|---|---|
| Gemini down / rate-limited | Reading: saved answer for bundled examples, else clear "could not read" error. Agent: all core checks run, trace says so. Texts: template |
| Unsupported or too-big file | 415/413 with a plain message; n8n sends an ntfy error alert |
| AI calls an unknown tool or bad arguments | Ignored and logged in the trace; guard still covers core checks |
| Token expired / used / wrong | Page says so plainly; no state change |
| Neon down | Decision saved locally; page notes "public history not updated" |
| Same file emailed twice | New pending run each time (each email deserves a review); public history keeps its own 10-min dedupe |

## 8. Testing

TDD for all Python. Fake Gemini client returning scripted function calls (no network in tests).
- Split checks: `run_checks` output unchanged on all existing fixtures.
- Agent: AI calls all → no guard steps; AI skips history → guard adds it and trace says so; unknown tool / bad args
  ignored; AI offline → all core; turn limit; findings order stable.
- Contract ceiling check: under, equal, above 100 %, missing.
- Intake: each file kind routes to the right reader; needs_confirmation set for AI sources.
- API (FastAPI TestClient): auth required on intake/runs; size/type limits; review GET never changes state; POST
  approve works once; expired/wrong token; confirmation required for AI-read values; public-history save only for
  bundled examples.
- n8n workflow validated with the n8n MCP validator, then one real end-to-end run with a bundled example emailed to
  the demo inbox (manual, recorded in the PR).

## 9. What the user must do (cannot be automated)

1. Create the demo Gmail, turn on 2-step verification, create an app password, enter it in n8n's IMAP credential.
2. Install the ntfy app on the phone and subscribe to the topic.
3. Run the firewall command once.
4. Choose the 6-digit reviewer PIN and the allowed sender emails, and put them in `.streamlit/secrets.toml`
   (the guide shows the exact lines).

## 10. Decisions log (builder check, 2026-11-27)

User decisions: reviewer PIN required; no value editing on the review page (reject + resend); sender allowlist.
Builder-side calls (Claude): contract ceiling uses the live app's formula, strictly above 100 % = REVIEW; optional
findings stripped before public-history save; `AI_SOURCES` moved to `scripts/`; saved answers matched by SHA-256.

## 11. Left to the builder

Exact prompt wording; HTML/CSS of the review page; module split inside `api/`; SQLite schema details beyond 5.4;
n8n node versions (use what the local n8n validator accepts).
