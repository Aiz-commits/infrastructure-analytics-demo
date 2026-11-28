# Phase 3 — AI agent + email automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A décompte emailed to a demo inbox is read, checked by an AI agent with a Python guard, and sent to the reviewer's phone as an ntfy alert whose link opens a PIN-protected approve/reject page.

**Architecture:** Pure `scripts/` modules (intake, agent, settings, store) under a small FastAPI app in `api/`; n8n (local) does IMAP → API → ntfy. Python computes every amount; Gemini only chooses tools and drafts text; every AI failure has a non-AI path.

**Tech Stack:** Python 3.14 (`.venv`), google-genai 2.34 function calling, FastAPI + uvicorn + python-multipart (separate `requirements-api.txt`), SQLite (stdlib `sqlite3`), SQLAlchemy history (existing), n8n 2.49.8, ntfy.sh.

**Spec:** `docs/superpowers/specs/2026-11-27-agent-automation-design.md`

## Global Constraints

- No Streamlit import in `scripts/` or `api/`. Files under 500 lines.
- Python does every calculation; tool calls take **no arguments** that reach a check (any `args` from the model are ignored).
- Every Gemini failure returns None → fallback (all core checks; template texts; saved answer for bundled examples).
- `run_checks` output unchanged byte-for-byte; the Streamlit app behaviour unchanged; all existing tests stay green (`.venv\Scripts\python.exe -m pytest -q -p no:warnings`).
- Secrets only in `.streamlit/secrets.toml` (git-ignored): `GEMINI_API_KEY`, `DATABASE_URL`, `REVIEWER_PIN` (6 digits), `AGENT_API_KEY`, `ALLOWED_SENDERS` (list), `REVIEW_BASE_URL`. Never in code, docs, tests, n8n export.
- Review token: `secrets.token_urlsafe(32)`, SHA-256 stored, valid 48 h, single use. 5 wrong PINs lock a run.
- GET never changes state. Errors are JSON `{"error": "<plain sentence>"}`, never a stack trace.
- Public history only for bundled example files (`controller_examples/`, `demo_decomptes/`), optional findings stripped, read_method suffixed `" via email"`.
- Commits: `git -c user.name=Aiz-commits -c user.email=312724055+Aiz-commits@users.noreply.github.com commit`, no Co-Authored-By. git at `C:\Program Files\Git\cmd\git.exe`.

## Review Focus

1. Email signature logos / unrelated images as attachments → must not produce a review alert with invented numbers: a read where **all 7 values are None** is rejected with 422 "No décompte values found in this file." (Task 4)
2. `From` header in `Name <Addr@Gmail.com>` form → allowlist compares the parsed address lower-cased. (Task 5)
3. PIN typed with spaces or wrong → spaces stripped; wrong PIN counts toward the 5-try lock; correct PIN after lock still refused. (Task 6)
4. Link opened again after a decision, on another device, or after API restart → read-only page with the decision; state survives restart (SQLite). (Task 6)
5. Model sends tool calls with invented amounts in `args`, or calls the same tool twice → args ignored, duplicate call runs once. (Task 3)

---

### Task 1: Per-check functions, contract ceiling, AI_SOURCES

**Files:**
- Modify: `scripts/controller_checks.py` (split `_arithmetic`; add ceiling; add `AI_SOURCES`, `CORE_CHECKS`)
- Modify: `app.py:137` (import `AI_SOURCES` from scripts instead of defining it)
- Test: `tests/test_controller_checks.py`

**Interfaces:**
- Produces: `AI_SOURCES = (SOURCE_AI, SOURCE_PDF_TEXT, SOURCE_VISION)`; `CORE_CHECKS = ('retention', 'net', 'vat', 'ttc', 'cumulative', 'history')`; `OPTIONAL_CHECKS = ('contract_ceiling',)`; `value_warnings(current) -> (list[Finding], Statement)` (missing/uncertain warnings + statement with every field filled); `run_one_check(name: str, current: Statement, policy, previous: Statement | None) -> list[Finding]` (`'history'` returns continuity+sequence; arithmetic names return one finding; `'contract_ceiling'` returns the ceiling finding); `check_contract_ceiling(current, policy) -> Finding` (id `'contract_ceiling'`); `CHECK_ORDER` = finding-id order of `run_checks` + `'contract_ceiling'` last.

- [ ] **Step 1: Write failing tests**
  - `test_run_checks_equals_sum_of_single_checks`: for the fixtures already used in the file, `run_checks(c, p, policy) == warnings + sum((run_one_check(n, filled, policy, p) for n in CORE_CHECKS), [])` where `warnings, filled = value_warnings(c)`.
  - `test_contract_ceiling`: policy contract 5 400 000, VAT 0.20: cumulative 4 500 000 → `OK` (100.00 % exactly, not REVIEW); 4 500 001 → `REVIEW`; 3 636 000 → `OK` and evidence contains `'80.80 %'`; cumulative None → `SKIPPED`.
  - `test_ai_sources_constant`: `AI_SOURCES == (SOURCE_AI, SOURCE_PDF_TEXT, SOURCE_VISION)`.
- [ ] **Step 2:** Run `.venv\Scripts\python.exe -m pytest tests/test_controller_checks.py -q -p no:warnings` → new tests FAIL (ImportError).
- [ ] **Step 3: Implement.** `_arithmetic` becomes a dict of the five `(title, inputs, expected, stated_field)` specs keyed by check id; `run_one_check` runs one; `run_checks` = warnings + each core check in `CORE_CHECKS` order (history last), same output. Ceiling: `ratio = cumulative * (1 + vat_rate) / contract_ttc`; title `'Contract ceiling (cumulative TTC ≤ contract)'`; evidence = percentage with two decimals and a space before `%` (`'80.80 %'`) plus the cumulative cell via `_cells`; `difference` = amount above the contract TTC, `None` when OK. `app.py` imports `AI_SOURCES`.
- [ ] **Step 4:** Full suite green.
- [ ] **Step 5:** Commit `feat: per-check functions and contract ceiling check`.

### Task 2: Gemini tool-calling wrapper

**Files:** Modify `scripts/llm.py`; Test `tests/test_controller_llm.py`

**Interfaces:**
- Produces: `ask_with_tools(contents: list, declarations: list[dict], api_key, *, client_factory=None) -> tuple[content, list[tuple[str, dict]]] | None` — one model turn; returns the model's `candidates[0].content` (appended unchanged next turn) and `[(name, args)]` from `response.function_calls` (empty list = model answered in text). None on no key / any exception / no candidate. Config: `tools=[types.Tool(function_declarations=declarations)]`, `automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)`, `temperature=0`.
- Produces: `function_response(name: str, payload: dict) -> types.Part` (wraps `types.Part.from_function_response`).

- [ ] **Step 1:** Tests with a fake client: returns `(content, [('check_vat', {})])`; passes `tools` and disabled AFC in config (assert on captured kwargs); exception → None; no key → None without building a client; response without candidates → None.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Pass. **Step 5:** Commit `feat: Gemini tool-calling wrapper`.

### Task 3: Agent loop with guard

**Files:** Create `scripts/agent.py`; Test `tests/test_agent.py`

**Interfaces:**
- Consumes: Task 1 functions, Task 2 `ask_with_tools`, `function_response`, `previous_from_history`.
- Produces: `@dataclass(frozen=True) TraceStep(who: str, action: str, check_id: str | None, reason: str)` (`who` ∈ `'AI'|'guard'|'Python'`); `@dataclass(frozen=True) AgentResult(findings: list[Finding], trace: list[TraceStep], ai_used: bool)`; `run_agent(statement, policy, api_key, *, ask=llm.ask_with_tools, previous_lookup=previous_from_history, max_turns=8) -> AgentResult`; `TOOL_DECLARATIONS: list[dict]` (7 checks named `check_<id>` + `finish` with one string param `reason`; check tools have **no parameters**).

- [ ] **Step 1: Failing tests** (scripted `ask` fakes, no network):
  - `test_all_core_called_no_guard`: AI calls 6 core + `finish` → no `guard` steps; findings == `run_checks` output.
  - `test_guard_adds_skipped_history`: AI calls 5 arithmetic + finish → trace has `TraceStep('guard', 'added', 'history', 'the AI did not run this core check')`; findings still == `run_checks` output.
  - `test_optional_ceiling_kept_and_ordered_last`: AI calls ceiling first → `contract_ceiling` finding is the last finding; the rest == `run_checks`.
  - `test_args_ignored_and_duplicates_run_once` (Review Focus 5): calls `check_vat` twice with `{'vat': 999}` → one VAT finding identical to `run_checks`.
  - `test_unknown_tool_logged`: call `delete_everything` → trace step `('AI', 'unknown tool ignored', None, 'delete_everything')`, guard covers all.
  - `test_ai_offline`: `ask` returns None on first turn → `ai_used is False`, first trace step `('Python', 'AI planner offline — all core checks run', None, '')`, findings == `run_checks`.
  - `test_turn_limit`: fake never calls finish → stops after 8 asks; guard completes.
  - `test_finish_reason_recorded`: finish `reason` stored as `('AI', 'finished', None, reason)`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.** Prompt: values (field: amount or "missing"), project, number, one-line tool descriptions, instruction "Choose the checks this décompte needs, call them, then call finish. Never compute amounts." Each turn: append returned content unchanged, then one user `Content` with a `function_response` per call; payload `{'severity': ..., 'title': ...}` per finding (no amounts). Findings assembled at the end: `value_warnings` + results sorted by `CHECK_ORDER`.
- [ ] **Step 4:** Pass. **Step 5:** Commit `feat: AI agent picks checks, Python guard completes them`.

### Task 4: Pure intake (file bytes → statement)

**Files:** Create `scripts/intake.py`; Modify `ui/document_section.py` (`cached_document_read` calls `read_document_with_ai`); Test `tests/test_intake.py`

**Interfaces:**
- Produces: `class IntakeError(ValueError)` with `.status: int` (413/415/422/503); `@dataclass(frozen=True) IntakeRead(statement: Statement, read_method: str, needs_confirmation: bool)`; `read_document_with_ai(data, kind, api_key) -> tuple[Statement | None, str]` (moved logic: pdf text → vision on `NO_TEXT`); `saved_answer_for(data: bytes) -> tuple[str, dict] | None` (SHA-256 match against `SAVED_ANSWER_FILES` in `EXAMPLES_DIR`); `bundled_hashes() -> frozenset[str]` (all `controller_examples/*.xlsx|pdf|jpg` + `demo_decomptes/*.xlsx`); `read_file(data: bytes, api_key: str | None) -> IntakeRead`.
- Routing: `detect_kind` error → 415, `check_limits` error → 413; xlsx fixed → read_method `'fixed layout'`; xlsx other → `read_with_ai` (`'found by AI'`); pdf/image → `read_document_with_ai`, falling back to `saved_answer_for` (`'PDF text (saved)'` / `'AI vision (saved)'`); nothing read → 503 "AI reading is unavailable right now. Try again later."; all seven values None → 422 "No décompte values found in this file." `needs_confirmation = any(v.source in AI_SOURCES ...)`.

- [ ] **Step 1: Failing tests:** fixed xlsx (`make_workbook`) → `needs_confirmation False`; bundled photo with `api_key=None` → saved answer, `needs_confirmation True`; renamed copy of bundled PDF still matches by hash; PNG with patched vision returning all None → `IntakeError` status 422 (Review Focus 1); `.txt` bytes → 415; oversize PDF → 413; unknown-layout xlsx with no key → 503.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** Full suite green (document_section tests unchanged). **Step 5:** Commit `feat: pure intake reader shared by app and API`.

### Task 5: Settings and run store

**Files:** Create `scripts/agent_settings.py`, `scripts/agent_store.py`; Modify `.gitignore` (add `data/agent_files/`); Test `tests/test_agent_store.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) Settings(api_key, pin, allowed_senders: frozenset[str], review_base_url, gemini_key, database_url, data_dir: Path)`; `load_settings(path=ROOT/'.streamlit/secrets.toml', data_dir=ROOT/'data') -> Settings` raising `ValueError` with a plain message when `AGENT_API_KEY` missing/short (<24 chars), `REVIEWER_PIN` not 6 digits, `ALLOWED_SENDERS` empty, `REVIEW_BASE_URL` not http(s); `sender_address(raw: str) -> str` (`email.utils.parseaddr`, lower-cased).
- Produces store: `RunStore(db_path: Path)` with `create(*, file_name, data, sender, subject, statement, findings, trace, texts, language, read_method, needs_confirmation, ai_used_agent, now) -> tuple[int, str]` (id, raw token); `get(run_id) -> dict | None`; `check_token(run, token, now) -> str | None` ('This link is not valid.' / 'This link has expired.' / None); `record_wrong_pin(run_id) -> int` (attempts; locks at 5); `decide(run_id, decision, now) -> bool` (False if decided or locked); file saved at `data_dir/agent_files/<sha256>`. Statement/findings/trace/texts stored as JSON (Decimals as strings) and restored to `Statement`, `Finding`, `TraceStep`, `Texts`.

- [ ] **Step 1: Failing tests:** settings happy path + each invalid case message; `sender_address('Ilyass <A@Gmail.com>') == 'a@gmail.com'` (Review Focus 2); store round-trip equality of statement/findings/trace/texts; token hash stored, not raw; expired after 48 h; decide twice → second False; 5 wrong PINs → `locked`; new `RunStore` on same file sees the run (Review Focus 4).
- [ ] **Step 2:** FAIL. **Step 3:** Implement (stdlib `sqlite3`, table `agent_runs` per spec 5.4 + `pin_attempts`, `locked`). **Step 4:** Pass. **Step 5:** Commit `feat: agent settings and SQLite run store`.

### Task 6: FastAPI app and review page

**Files:** Create `api/__init__.py`, `api/main.py`, `api/review_page.py`, `requirements-api.txt`; Test `tests/test_api.py`

**Interfaces:**
- Consumes: Tasks 3–5, `write_texts`, `save_run`, `get_engine`, `RunRecord`.
- Produces: `create_app(settings: Settings, *, agent=run_agent, reader=read_file, writer=write_texts, history_saver=save_public, policy=load_policy()) -> FastAPI`; module-level `app` in `api/main.py` built from `load_settings()` for uvicorn (tests import `create_app` only); `save_public(settings, run) -> str` ('Added to the public history.' / 'Kept on this PC (not a bundled example).' / 'Public history not updated (database unavailable).'); `render_review(run, *, token, message=None) -> str` in `review_page.py` (pure HTML string, FR/EN labels by `run['language']`, HTML-escaped values).
- Endpoints exactly as spec 5.3. `/intake` form fields `file`, `sender`, `subject`; summary `f'{project} D{number}: {review} to review, {warnings} warnings'` (FR: `'à vérifier'`, `'alertes'`); `review_url = f'{REVIEW_BASE_URL}/review/{id}?t={token}'`. Body > 10 MB → 413. Language `'fr'`.
- Decision POST: strip spaces from `pin`; wrong → count + message "Wrong PIN (n of 5)."; locked → "Locked — re-send the email."; Approve with `needs_confirmation` and no `confirmed_values` → message, no decision.

- [ ] **Step 1: Failing tests** (`fastapi.testclient.TestClient`, fake agent/reader/writer/history, tmp data dir): health; intake without/with wrong API key → 401; sender not allowed → 403 and reader never called; `Name <allowed@x>` accepted; reader `IntakeError(422)` → 422 JSON error; happy intake returns fields + review_url; GET review twice → no state change; POST with spaced correct PIN approves; second POST → read-only "already decided"; wrong PIN ×5 then correct → still locked (Review Focus 3); AI-read run Approve without checkbox → refused; Reject works without checkbox; history saver called once, only on decision; expired token page; new `create_app` on same data dir shows the decided run (Review Focus 4); `/runs/{id}` needs API key; unexpected reader exception → 500 JSON plain error, no traceback text.
- [ ] **Step 2:** `pip install -r requirements-api.txt` (pin fastapi, uvicorn, python-multipart, httpx to versions that install on 3.14); run → FAIL.
- [ ] **Step 3:** Implement. `save_public` strips `OPTIONAL_CHECKS` findings; saves only when `sha256 in bundled_hashes()` and `database_url` set; wraps all DB errors.
- [ ] **Step 4:** Full suite green. **Step 5:** Commit `feat: local API with PIN-protected review page`.

### Task 7: Start scripts, secrets, live smoke test

**Files:** Create `automation/start_api.ps1`, `automation/start_n8n.ps1`; local-only edit of `.streamlit/secrets.toml` (never committed)

- [ ] **Step 1:** Add to secrets: `AGENT_API_KEY` (generated `secrets.token_urlsafe(32)`), `ALLOWED_SENDERS = ["<user's sending address>"]`, `REVIEW_BASE_URL = "http://<LAN IPv4>:8000"`.
- [ ] **Step 2:** `start_api.ps1` runs `.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000` from repo root; `start_n8n.ps1` prepends `C:\Users\newga\tools\node24` and runs `C:\Users\newga\tools\n8n24\n8n.cmd start`.
- [ ] **Step 3:** Smoke: start API; `/health` → ok; POST `controller_examples/DEMO_DP_N5.xlsx` with the real key and live Gemini → JSON with review_url; open it in the browser pane; approve with the PIN; confirm the decision and the history note. Commit `chore: start scripts for API and n8n`.

### Task 8: n8n workflow "Décompte inbox"

**Files:** Create `automation/n8n/decompte_inbox.json` (export, placeholders only)

- [ ] **Step 1:** `get_user_preferences`, `get_workflow_sdk_reference`, best practices; build via n8n MCP: IMAP Email Trigger (credential "Demo Gmail IMAP", unread, attachments, mark read) → sender allowlist filter → split binary attachments, keep xlsx/pdf/jpg/jpeg/png → HTTP POST `http://localhost:8000/intake` multipart with header credential "Agent API key" → HTTP POST `https://ntfy.sh/<topic>` (headers `Title`, `Click`, `Priority`, `Tags`); error branch → ntfy "Could not process <file>: <error>".
- [ ] **Step 2:** `validate_workflow` passes; test with pinned data against the running API.
- [ ] **Step 3:** Export JSON with topic/API key as `REPLACE_WITH_...` placeholders; commit `feat: n8n inbox workflow`.

### Task 9: Client guide and README

**Files:** Create `docs/phase3-automation-guide.md`; Modify `README.md`

- [ ] **Step 1:** Guide per spec section 6 (plain words, numbered): what it does; the picture; the alert and the words OK/REVIEW/WARNING/SKIPPED/"added by guard"/"contract ceiling"; what the AI decides and never decides; what Approve does (no email sent); PIN and lock; why values can't be edited (reject + resend); setup (demo Gmail + 2-step + app password, ntfy app + topic, secrets lines with placeholders, `start_n8n.ps1`, `start_api.ps1`, firewall `New-NetFirewallRule -DisplayName "AI Controller API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Profile Private -Action Allow`); troubleshooting table.
- [ ] **Step 2:** README section "Phase 3 — email automation (local demo)" linking the guide. Commit `docs: Phase 3 client guide`.

### Task 10: End-to-end with the user

- [ ] User creates demo Gmail + app password, installs ntfy, runs firewall command (guide steps).
- [ ] Email `DEMO_DP_N5.xlsx` and the photo example from the allowed address → alerts arrive → approve one, reject one with PIN on the phone. Record results in the PR.
