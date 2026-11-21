# AI Controller — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "🤖 AI Controller" page that reads a décompte, checks it with Python, drafts a memo + contractor email with Gemini, and waits for a human Approve/Reject.

**Architecture:** Fixed pipeline (approach A). Pure-Python modules in `scripts/` (no Streamlit inside): checks, AI reader, AI writer, review files, thin Gemini wrapper. `app.py` only wires UI, secrets, cache and session limits. AI never does math: it returns cell addresses (Python reads the cells) and writes text (Python guards every number).

**Tech Stack:** Python 3.12/3.14, Streamlit 1.67, openpyxl, `Decimal`, `google-genai` (new), pytest + `streamlit.testing.v1.AppTest`.

**Spec:** `docs/superpowers/specs/2026-11-21-ai-controller-design.md`

## Global Constraints

- All money is `Decimal` via `policy.amount()`. Float only at display (`audit.display_frame`).
- Rates, tolerance, contract come from `load_policy()` (`demo-finance-v1`: retention 0.10, no cap, VAT 0.20 on net after retention, tolerance 0.01 DH). Never hardcode them.
- Open workbooks only via `workbooks.workbook_bytes` / `open_workbook`.
- Do not change `extract_decompte()`, `audit.py`, existing pages, or anything in `demo_decomptes/` / `outputs/`.
- New example files go in `controller_examples/`, never `demo_decomptes/`.
- `scripts/*` modules never import `streamlit`. Only `app.py` reads `st.secrets["GEMINI_API_KEY"]`.
- Tests never call real Gemini. Every AI entry point takes an `ask` callable so tests pass a fake.
- `google-genai` pinned in `requirements.txt` and `requirements.lock`, binary wheels for 3.12 and 3.14.
- Wording: "requires justification". Never "fraud" or "error confirmed".
- No email is ever sent. Approve = downloadable files only.
- Files stay under 500 lines.

## Review Focus

1. **Gemini returns junk cell addresses** (`"Sheet2!A1"`, `"Z99999"`, `"hello"`, a text cell, an empty cell) → that field = "not found". No crash. Test in Task 4.
2. **Amounts stored as text** in an uploaded file (`"900 000,00"`) → "not found", never guessed. Test in Task 4.
3. **Gemini slow / quota / bad key** → `None` → template text + badge. No raw error. Tests in Tasks 1 and 5.
4. **French number spacing in AI text** (no-break space U+00A0, narrow U+202F, `12 300,00 DH`) → number guard still matches. Test in Task 5.
5. **Random xlsx that is not a décompte** (empty sheet, > 2,000 non-empty cells, > 2 MB) → friendly message, no AI call. Tests in Tasks 4 and 7.

---

## File map

| File | Job |
|---|---|
| `scripts/llm.py` | Gemini wrapper. `MODEL` constant, timeout, returns `None` on any failure. |
| `scripts/controller_checks.py` | Dataclasses + all checks. Pure. |
| `scripts/ai_reader.py` | Cell text → Gemini → trace rule + label check → `Statement`. |
| `scripts/ai_writer.py` | Findings → prompt → number guard → retry → templates. |
| `scripts/controller_review.py` | Memo `.md`, email `.eml`, audit-trail row. |
| `generate_demo_decomptes.py` | + `generate_controller_examples()`. |
| `controller_examples/*.xlsx` | 2 generated example files (committed). |
| `app.py` | Sidebar entry + page block. |
| `tests/test_controller_*.py` | One test file per module + one AppTest file. |

---

### Task 1: Gemini wrapper + dependency

**Files:**
- Modify: `requirements.txt`, `requirements.lock`
- Create: `scripts/llm.py`
- Test: `tests/test_controller_llm.py`

**Interfaces:**
- Produces:
  - `MODEL: str` (e.g. `'gemini-2.5-flash'`; confirm on build day it is on the free tier)
  - `TIMEOUT_MS = 20_000`
  - `ask_json(prompt: str, schema: dict, api_key: str | None, *, client_factory=None) -> dict | None`
  - `ask_text(prompt: str, api_key: str | None, *, client_factory=None) -> str | None`
  - `client_factory(api_key) -> client` defaults to `genai.Client(api_key=..., http_options=types.HttpOptions(timeout=TIMEOUT_MS))`. Tests inject a fake.

- [ ] **Step 1: Add dependency.** Add `google-genai==<latest>` to `requirements.txt`. Regenerate lock with uv (keep the existing header comment lines). Check wheels: `python -m pip download --only-binary=:all: -r requirements.lock -d %TEMP%\wheels --python-version 3.14` and same for `3.12`. Expected: no "no matching distribution".
- [ ] **Step 2: Write failing tests**

```python
def test_no_key_returns_none():
    assert ask_text('hi', None) is None
    assert ask_json('hi', {}, '') is None

def test_any_exception_returns_none():
    def boom(key): raise RuntimeError('quota')
    assert ask_text('hi', 'k', client_factory=boom) is None

def test_json_parsed():
    fake = fake_client(text='{"vat": "H15"}')       # helper in test file
    assert ask_json('p', {}, 'k', client_factory=lambda k: fake) == {'vat': 'H15'}

def test_bad_json_returns_none():
    fake = fake_client(text='not json')
    assert ask_json('p', {}, 'k', client_factory=lambda k: fake) is None
```
`fake_client` returns an object whose `.models.generate_content(...)` returns `SimpleNamespace(text=...)`.

- [ ] **Step 3: Run** `python -m pytest tests/test_controller_llm.py -v` → FAIL (module missing).
- [ ] **Step 4: Implement `scripts/llm.py`.** `ask_json` uses `types.GenerateContentConfig(response_mime_type='application/json', response_schema=schema)`; `json.loads(response.text)`; must be a `dict`, else `None`. `ask_text` returns stripped text or `None` if empty. Wrap the whole call in `except Exception: return None`.
- [ ] **Step 5: Run** full `python -m pytest` → all PASS (old tests too).
- [ ] **Step 6: Commit** `feat: add Gemini wrapper with safe fallback`

---

### Task 2: Demo example files

**Files:**
- Modify: `generate_demo_decomptes.py`
- Create: `controller_examples/DEMO_DP_N5.xlsx`, `controller_examples/DEMO_DP_N5_NEW_LAYOUT.xlsx`
- Test: `tests/test_controller_examples.py`

**Interfaces:**
- Produces: `generate_controller_examples(folder, policy=None) -> list[Path]` (standard file first). CLI flag `--controller-dir` (default `controller_examples/`); running the script with no flags still only writes `demo_decomptes/`.
- `EXAMPLES_DIR = ROOT / 'controller_examples'` lives in `scripts/controller_checks.py` (Task 3) — here just use the path.

N5 numbers (D4 cumulative is 2,750,000.00):

| Field | Value | Standard cell | New-layout cell (label in F) |
|---|---|---|---|
| works | 900,000.00 | D37 | H10 `Travaux du mois HT` |
| previous | 2,737,700.00 (= D4 − 12,300) | C37 | H11 `Cumul précédent HT` |
| cumulative | 3,637,700.00 | B37 | H12 `Cumul actuel HT` |
| retention | 90,000.00 | D39 | H13 `Retenue de garantie 10%` |
| net | 810,000.00 | D44 | H14 `Net HT` |
| vat | 163,000.00 (= 162,000 + 1,000) | D45 | H15 `TVA 20%` |
| ttc | 973,000.00 | D46 | H16 `Total TTC` |

Both files: A1 `DEMO PROJECT — DECOMPTE D5`, A2 synthetic note, A3:B4 `Project ID`/`DEMO PROJECT`, `Statement number`/5. Standard file: sheet `DP`, A39 `Retenue de Garantie`. New layout: sheet `Situation`, nothing in A39/A41.

- [ ] **Step 1: Failing tests**

```python
def test_standard_example_reads_with_fixed_extractor(tmp_path):
    std, _ = generate_controller_examples(tmp_path)
    r = extract_decompte(std)
    assert (r['Statement number'], r['Previous cumulative HT'], r['VAT']) == (5, Decimal('2737700.00'), Decimal('163000.00'))

def test_new_layout_is_rejected_by_fixed_extractor(tmp_path):
    _, new = generate_controller_examples(tmp_path)
    with pytest.raises(ValueError):
        extract_decompte(new)

def test_committed_examples_match_generator(tmp_path):
    # same cell values as the committed files in controller_examples/
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**, then run `python generate_demo_decomptes.py --controller-dir controller_examples`.
- [ ] **Step 4: Run** full `python -m pytest` + `python -m scripts.reports` → PASS, and `git status outputs/ demo_decomptes/` shows no new changes from this task.
- [ ] **Step 5: Commit** `feat: add AI Controller example decomptes`

---

### Task 3: Python checks

**Files:**
- Create: `scripts/controller_checks.py`
- Test: `tests/test_controller_checks.py`

**Interfaces:**
- Produces:
  - `FIELDS = ('works', 'previous', 'cumulative', 'retention', 'net', 'vat', 'ttc')`
  - `SOURCE_FIXED = 'fixed layout'`, `SOURCE_AI = 'found by AI'`, `SOURCE_EDITED = 'edited by reviewer'`
  - `EXAMPLES_DIR`, `HISTORY_DIR = ROOT / 'demo_decomptes'`
  - `@dataclass(frozen=True) ReadValue(field: str, value: Decimal | None, cell: str | None, source: str, uncertain: bool = False)`
  - `@dataclass(frozen=True) Statement(project: str, number: int | None, values: dict[str, ReadValue])`
  - `@dataclass(frozen=True) Finding(id: str, severity: str, title: str, amounts: dict[str, Decimal], difference: Decimal | None, evidence: str)` — severity in `OK | WARNING | REVIEW | SKIPPED`
  - `from_extractor(record: dict) -> Statement` — maps `extract_decompte()` keys; row from `Source cells` (`!B(\d+)`); cells B/C/D{row}, D{row+2}, D{row+7..9}.
  - `apply_edits(statement: Statement, edits: dict[str, Decimal | None]) -> Statement` — changed values get `SOURCE_EDITED`, `uncertain=False`.
  - `previous_from_history(current: Statement, folder=HISTORY_DIR) -> Statement | None` — same project (casefold), number − 1.
  - `run_checks(current: Statement, previous: Statement | None, policy: Policy) -> list[Finding]`
  - `review_count(findings) -> int`

Rules (stated values, one step each, `abs(diff) > policy.tolerance` → REVIEW):

| id | Compare |
|---|---|
| `retention` | stated retention vs `expected_amounts(works, cumulative, previous, policy)['Retention']` |
| `net` | stated net vs stated works − stated retention |
| `vat` | stated vat vs `amount(base × vat_rate)`; base = stated net (or stated works if `vat_base == 'works_ht'`) |
| `ttc` | stated ttc vs stated net + stated vat |
| `cumulative` | stated cumulative vs stated previous + stated works |
| `continuity` | stated previous vs previous statement's stated cumulative |
| `sequence` | previous.number must be current.number − 1 |
| `missing:<field>` | value is `None` → WARNING |
| `uncertain:<field>` | `uncertain=True` → WARNING |

- A check whose inputs are missing → `SKIPPED`, title says which field.
- `previous is None` → `continuity` and `sequence` = SKIPPED, evidence `"skipped — no previous décompte"`.
- Different project → `continuity` REVIEW, title "different project".
- Gap → `sequence` REVIEW, `continuity` SKIPPED.

- [ ] **Step 1: Failing tests** (build `Statement`s with a small helper `stmt(**values)`):

```python
def test_n5_gives_exactly_two_reviews():          # standard example + DEMO_DP_N4 history
    f = run_checks(cur, previous_from_history(cur), policy)
    reviews = {x.id: x.difference for x in f if x.severity == 'REVIEW'}
    assert reviews == {'continuity': Decimal('12300.00'), 'vat': Decimal('1000.00')}

def test_one_wrong_cell_gives_one_finding():      # only ttc off by 5 → only 'ttc' REVIEW
def test_tolerance_edge():                        # diff 0.01 → OK, 0.02 → REVIEW
def test_no_previous_is_skipped_not_review():
def test_gap_d3_to_d5_is_sequence_review():
def test_different_project_is_review():
def test_missing_vat_skips_vat_and_ttc():          # missing:vat WARNING, vat+ttc SKIPPED
def test_uncertain_value_is_warning():
def test_apply_edits_marks_source():
```

- [ ] **Step 2: Run** `python -m pytest tests/test_controller_checks.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: add stated-value controller checks`

---

### Task 4: AI reader (trace rule + label check)

**Files:**
- Create: `scripts/ai_reader.py`
- Test: `tests/test_controller_reader.py`

**Interfaces:**
- Consumes: `Statement`, `ReadValue`, `FIELDS`, `SOURCE_AI` (Task 3); `llm.ask_json` (Task 1); `statement_number`, `identity`, `amount`, `open_workbook`.
- Produces:
  - `MAX_UPLOAD_BYTES = 2 * 1024 * 1024`, `MAX_AI_CELLS = 2000`
  - `AI_FIELDS = FIELDS + ('project', 'number')`
  - `LABELS: dict[str, tuple[str, ...]]` — accent-free lowercase: works `('travaux','works')`, previous `('precedent','anterieur','previous')`, cumulative `('cumul','cumulative')` and must NOT contain a previous keyword, retention `('retenue','retention')`, net `('net',)`, vat `('tva','vat')`, ttc `('ttc',)`
  - `cell_text(data: bytes) -> str` — first sheet, `"A1: value"` per non-empty cell; raises `ValueError` past `MAX_AI_CELLS`.
  - `trace(data: bytes, cells: dict) -> Statement` — Python reads each cell itself.
  - `read_with_ai(data: bytes, api_key: str | None, ask=llm.ask_json) -> Statement | None` — `None` if `ask` returns `None`.

Trace rule details:
- Address must match `^[A-Z]{1,3}[1-9][0-9]{0,4}$` and be inside the sheet's dimensions, else "not found".
- Amount = `amount(cell.value)`; `ValueError` or bool/str → `value=None` (not found). Never parse text.
- Label check: text cells in the same row, or in the same column above it. No keyword hit → `uncertain=True`.
- `number` → `statement_number()`; `project` → stripped str ≤ 120 chars. If `identity(sheet)` gives values, they win; AI cells are only the fallback.

- [ ] **Step 1: Failing tests** (fake `ask` returns a fixed dict):

```python
def test_new_layout_traced(new_layout_bytes):
    s = read_with_ai(new_layout_bytes, 'k', ask=lambda *a, **k: GOOD_CELLS)   # H10..H16
    assert s.values['vat'] == ReadValue('vat', Decimal('163000.00'), 'H15', SOURCE_AI, False)
    assert (s.project, s.number) == ('DEMO PROJECT', 5)

def test_junk_addresses_are_not_found():           # 'Sheet2!A1', 'Z99999', 'hello', None, empty cell
def test_text_amount_is_not_found():               # cell holds '900 000,00'
def test_wrong_label_is_uncertain():               # vat → H13 (row says Retenue) → uncertain
def test_cumul_precedent_not_accepted_for_cumulative():
def test_ai_down_returns_none():                    # ask returns None
def test_too_many_cells_raises():                  # 2001 filled cells
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** Prompt: English, lists `AI_FIELDS`, says "return the cell address only, or null; do not compute anything". **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: add traced AI reader for unknown layouts`

---

### Task 5: AI writer (number guard + templates)

**Files:**
- Create: `scripts/ai_writer.py`
- Test: `tests/test_controller_writer.py`

**Interfaces:**
- Consumes: `Finding` (Task 3), `llm.ask_text` (Task 1), `Policy`.
- Produces:
  - `@dataclass(frozen=True) Texts(memo: str, email_subject: str, email_body: str, ai_used: bool)`
  - `findings_json(findings) -> str` — amounts as `"12300.00"` strings. This is the ONLY thing Gemini sees.
  - `format_amount(value: Decimal, language: str) -> str` — `'en'` → `12,300.00`; `'fr'` → `12 300,00` (U+202F).
  - `extract_numbers(text: str) -> list[Decimal]`
  - `allowed_numbers(findings, policy) -> set[Decimal]` = every number in `findings_json(findings)` + `retention_rate×100` + `vat_rate×100`.
  - `unsupported_numbers(text, allowed, tolerance) -> list[Decimal]` — round each to 2 dp; match if `abs(x − a) <= tolerance` for some `a`.
  - `template_texts(findings, language) -> Texts` (`ai_used=False`)
  - `write_texts(findings, language, policy, api_key, ask=llm.ask_text) -> Texts`

AI output format (prompt asks for it, parser requires it):
```
### MEMO
...
### EMAIL
Subject: ...
...
```
Flow: ask → parse → guard. Parse fail or guard fail → retry once → still bad → `template_texts`. `ask` returns `None` → template right away (no retry).

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.parametrize('text,expected', [
    ('12 300,00 DH', [Decimal('12300.00')]),
    ('12 300,00 DH', [Decimal('12300.00')]),
    ('12,300.00', [Decimal('12300.00')]),
    ('1.000,00', [Decimal('1000.00')]),
    ('162 000', [Decimal('162000')]),
    ('TVA 20%', [Decimal('20')]),
    ('D4 → D5', [Decimal('4'), Decimal('5')]),
])
def test_extract_numbers(text, expected): ...

def test_invented_number_triggers_retry_then_template():   # ask returns '... 99,999.00 ...' twice → ai_used False, 2 calls
def test_good_text_first_try():                             # 1 call, ai_used True
def test_bad_then_good_uses_second():                       # 2 calls, ai_used True
def test_ai_down_uses_template_no_retry():                  # ask returns None → 1 call
def test_templates_pass_their_own_guard():                  # fr + en, N5 findings
def test_template_never_says_fraud():                       # 'fraud'/'fraude'/'error confirmed' absent
def test_prompt_contains_no_raw_cells():                    # prompt built from findings_json only
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** Prompt rules: neutral auditor, "requires justification", one bullet per REVIEW item, no numbers that are not in the JSON, no cell addresses, no dates, `-` bullets (no numbered lists). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: add guarded AI memo and email writer`

---

### Task 6: Review files + audit trail

**Files:**
- Create: `scripts/controller_review.py`
- Test: `tests/test_controller_review.py`

**Interfaces:**
- Consumes: `Texts` (Task 5).
- Produces:
  - `memo_markdown(texts, project: str, number: int | None, decision: str, decided_at: datetime) -> bytes` — top line `Approved by reviewer — <ISO time>` (or `Rejected by reviewer`).
  - `email_eml(texts, decided_at: datetime) -> bytes` — `email.message.EmailMessage`, `Subject` + `Date`, no `To` (reviewer fills it in), UTF-8.
  - `trail_row(filename: str, decided_at: datetime, ai_used: bool, decision: str) -> dict` — keys `File, Date/time, AI used, Decision`.

- [ ] **Step 1: Failing tests**: `.eml` parses back with `email.message_from_bytes` and keeps French accents; memo starts with the approval line; trail row has the 4 keys.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: add approval files and audit trail rows`

---

### Task 7: Streamlit page

**Files:**
- Modify: `app.py`
- Test: `tests/test_controller_app.py`, `tests/test_app.py` (add page to `test_pages_load`)

**Interfaces:**
- Consumes: everything above.
- Session keys: `ctrl_ai_calls: int`, `ctrl_ai_seen: set[tuple]`, `ctrl_statement`, `ctrl_confirmed: bool`, `ctrl_trail: list[dict]`.
- `AI_CALL_LIMIT = 10` (in `app.py`).
- Widget keys: `ctrl_example` (button), `ctrl_example_new`, `ctrl_upload`, `ctrl_prev_upload`, `ctrl_privacy` (checkbox), `ctrl_lang` (`Français` / `English`), `ctrl_confirm`, `ctrl_approve`, `ctrl_reject`.

Page logic, in order:
1. `api_key()` in `app.py`: `try: return st.secrets.get('GEMINI_API_KEY') or None` / `except Exception: return None`. No key → badge "AI offline — template mode".
2. Receive: `ctrl_example` loads `EXAMPLES_DIR/DEMO_DP_N5.xlsx`; `ctrl_example_new` loads `..._NEW_LAYOUT`. Upload: `.xlsx`, reject > `MAX_UPLOAD_BYTES` with a message. Privacy tick text copied from spec 7.1. AI allowed = example OR ticked.
3. Read: `workbook_bytes` → `extract_decompte` → `from_extractor`. `ValueError` → if AI allowed and under limit → `read_with_ai`; else message "Layout not supported — AI reading needs the privacy tick" or "AI offline".
4. Any `SOURCE_AI` value → `st.data_editor` table (value, cell, source, uncertain) + "Confirm values" button. Steps 3–5 wait for it.
5. Previous: example → `previous_from_history`; upload → optional `ctrl_prev_upload`, else `None`.
6. Check → findings table with ✅/⚠️ icons.
7. Explain → `write_texts` through a `@st.cache_data` wrapper keyed by `(sha256, language, findings_json)`. Count a call only when the `(sha256, language)` pair is new in `ctrl_ai_seen`. Past 10 → template + notice.
8. Review → editable memo/email `st.text_area`, Approve/Reject → `trail_row` appended, download buttons for memo `.md` and `.eml` after Approve.
9. Progress line: 5 steps with ✅ / ⚠️ / ⏳.
10. Any unexpected exception in the page → `st.error('Cannot analyze this workbook…')`, never a traceback.

Branching: add `'🤖 AI Controller'` to the sidebar radio; `if page == '🤖 AI Controller': controller_page()` before the existing `if page != 'Document Analysis'`. Keep `app.py` under 500 lines; if it gets close, move the page to `controller_page.py` beside `app.py` and say so in the commit.

- [ ] **Step 1: Failing AppTests** (no secrets in CI = template mode):

```python
def test_try_example_template_mode():
    at = open_page('🤖 AI Controller'); at.button(key='ctrl_example').click().run(timeout=30)
    assert not at.exception
    assert 'AI offline — template mode' in all_text(at)
    assert all_text(at).count('REVIEW') >= 2                 # continuity + VAT

def test_new_layout_without_ai_asks_for_values():          # no key → no crash, clear message
def test_approve_adds_trail_row():
def test_fake_ai_reader_needs_confirm():                    # patch scripts.ai_reader.read_with_ai → confirm button shown, no findings yet
def test_upload_too_big_is_rejected():                      # 2 MB + 1 byte
def test_unexpected_error_shows_message():                  # patch run_checks to raise RuntimeError
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** full `python -m pytest` → PASS. Local manual check: `streamlit run app.py`, with a real key in `.streamlit/secrets.toml`, click both examples, time it (< 30 s).
- [ ] **Step 5: Commit** `feat: add AI Controller page`

---

### Task 8: README + live deploy

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Add a short "AI Controller" section with the spec's one sentence, the fixed-pipeline rule (AI never calculates), and the privacy note.
- [ ] **Step 2:** Run `python -m pytest` + `python -m scripts.reports` + `python -m pip_audit -r requirements.lock` → all PASS.
- [ ] **Step 3: Commit** `docs: describe AI Controller`. Push + PR only with the author's OK.
- [ ] **Step 4 (author does it):** Streamlit Cloud → app → Settings → Secrets → `GEMINI_API_KEY = "..."`. Then on the live site: both examples work, both problems caught, < 30 s; remove the key once → template mode still works.
