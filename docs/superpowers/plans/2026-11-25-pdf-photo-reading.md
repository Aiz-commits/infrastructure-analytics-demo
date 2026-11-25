# Phase 2 — PDF and Photo Reading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The 🤖 AI Controller reads décomptes from digital PDFs (Python-traced text, AI only maps numbers to fields) and from photos/scans (Gemini vision + mandatory confirm), with live-plus-saved-fallback examples.

**Architecture:** Two new readers (`pdf_reader.py`, `vision_reader.py`) return the same `Statement` the Excel readers return, so checks, memo, email and history are untouched. A small shared module parses printed amounts and checks labels. `app.py` routes uploads by content and adds two example buttons that fall back to committed "saved example answers".

**Tech Stack:** Python 3.12/3.14, Streamlit, `google-genai` (existing), `pypdf` (new runtime, pure Python), `fpdf2` + `Pillow` (new, dev-only, for test and example PDFs/images), pytest with the LLM mocked.

**Spec:** `docs/superpowers/specs/2026-11-25-pdf-photo-reading-design.md`

## Global Constraints

- Money is `Decimal` via `policy.amount()`; the AI never computes or changes a number.
- Tests never call the real AI; CI has no key. Patch `scripts.llm._generate` or pass an `ask=` fake.
- Limits: `.xlsx` unchanged (2 MB); PDF ≤ 2 MB and ≤ 3 pages; image (JPEG/PNG) ≤ 5 MB.
- Same session AI limit (`AI_CALL_LIMIT`, 10) and the same cache by file hash; failures go in `ctrl_ai_failed` and are never retried on rerun.
- Example files only in `controller_examples/`, never `demo_decomptes/`.
- Pinned deps in `requirements.txt` + `requirements.lock` (runtime) and `requirements-dev.txt` (dev); CI installs the lock with `--only-binary=:all:` and runs `pip_audit`.
- D5 example values: works 900000.00, previous 2737700.00, cumulative 3637700.00, retention 90000.00, net 810000.00, vat 163000.00, ttc 973000.00; project `DEMO PROJECT`, number 5 (from `controller_example_values`).
- Source labels (exact): `SOURCE_PDF_TEXT = 'PDF text (AI located)'`, `SOURCE_VISION = 'read by AI from image'`.
- History `read_method` (exact): `'PDF text'`, `'AI vision'`, `'PDF text (saved)'`, `'AI vision (saved)'`.
- Badge copy (exact): `Saved example answer (AI offline)`.
- Vision confirm notice (exact): `These numbers were typed by the AI from the picture. Compare each one with the document before confirming.`
- No privacy tick (exact): `PDF and photo reading uses Gemini. Tick the privacy box above to allow it.`
- No key, own upload (exact): `AI is offline (template mode). PDF and photo reading needs AI; upload an .xlsx instead.`
- Files under 500 lines.

## Review Focus

1. A non-breaking or narrow no-break space inside a printed amount (`2 750 000,00`, `2 750 000,00`, common in French PDFs and in Gemini output) must parse like a normal space. Test in Task 1.
2. An ambiguous `1.000` or `1,000` (one separator, three digits after) means one thousand, not one; a final separator followed by 1–2 digits is the decimal mark. Test in Task 1.
3. A file named `.pdf` that is not a PDF, a corrupt PDF, or an encrypted PDF must give a plain message, never a traceback. Test in Task 2.
4. Gemini returning the same token id for two fields, or ids that don't exist, must not crash; unknown ids are "not found", duplicates are kept but label-checked. Test in Task 4.
5. A photo answer whose `value` holds words or two numbers (`"810 000,00 / 820 000,00"`) is "not found", never the first number guessed. Test in Task 6.

---

### Task 1: Shared amount parser and label check

**Files:**
- Create: `scripts/doc_text.py`
- Modify: `scripts/ai_reader.py` (`_label_ok` calls `label_matches`; behaviour unchanged)
- Test: `tests/test_doc_text.py`

**Interfaces:**
- Produces: `AMOUNT_PATTERN: re.Pattern` (finds amount-like tokens in a line); `parse_amount_text(text: str | None) -> Decimal | None` (the whole string must be one amount, optional `DH`/`MAD`; returns `policy.amount()` or `None`); `label_matches(field: str, text: str) -> bool` (keywords from `ai_reader.LABEL_KEYWORDS`, accent/case-insensitive; `cumulative` rejected when a `previous` keyword is present).

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize('text, expected', [
    ('2 750 000,00', '2750000.00'), ('2,750,000.00', '2750000.00'), ('2750000.00', '2750000.00'),
    ('163 000,00 DH', '163000.00'), ('973000 MAD', '973000.00'), ('2 750 000,00', '2750000.00'),
    ('2 750 000,00', '2750000.00'), ('1.000', '1000.00'), ('1,000', '1000.00'), ('90000,5', '90000.50'),
    ('-12 300,00', '-12300.00')])
def test_parse_amount_text(text, expected):
    assert parse_amount_text(text) == Decimal(expected)

@pytest.mark.parametrize('text', ['', 'TVA', '810 000,00 / 820 000,00', '12/03/2026', 'abc 5', None])
def test_parse_amount_text_rejects(text):
    assert parse_amount_text(text) is None

def test_amount_pattern_finds_every_amount_on_a_row():
    found = [m.group() for m in AMOUNT_PATTERN.finditer('3 637 700,00   2 737 700,00   900 000,00')]
    assert found == ['3 637 700,00', '2 737 700,00', '900 000,00']

def test_label_matches():
    assert label_matches('vat', 'TVA 20%')
    assert label_matches('retention', 'Retenue de garantie 10%')
    assert not label_matches('cumulative', 'Cumul précédent HT')
    assert label_matches('previous', 'Cumul précédent HT')
```

- [ ] **Step 2:** Run `python -m pytest tests/test_doc_text.py -v` → FAIL (module missing).
- [ ] **Step 3:** Implement `scripts/doc_text.py`. Normalise ` `/` ` to spaces before matching. `AMOUNT_PATTERN` must not join two amounts separated by 2+ spaces (single spaces are thousands separators, as in the row test).
- [ ] **Step 4:** Run `python -m pytest tests/test_doc_text.py tests/test_controller_reader.py -v` → PASS (old reader tests unchanged).
- [ ] **Step 5:** Commit `feat: shared amount parser and label check for PDF/photo reading`.

### Task 2: File type detection and limits (+ dependencies)

**Files:**
- Create: `scripts/documents.py`
- Modify: `requirements.txt`, `requirements.lock` (add `pypdf`, latest release, pinned); `requirements-dev.txt` (add `fpdf2` and `Pillow`, pinned, binary wheels for 3.12 and 3.14)
- Test: `tests/test_documents.py`

**Interfaces:**
- Produces: `MAX_PDF_BYTES = 2 * 1024 * 1024`, `MAX_PDF_PAGES = 3`, `MAX_IMAGE_BYTES = 5 * 1024 * 1024`; `MIME = {'pdf': 'application/pdf', 'jpeg': 'image/jpeg', 'png': 'image/png'}`; `detect_kind(data: bytes) -> str` returning `'xlsx' | 'pdf' | 'jpeg' | 'png'` by magic bytes (`PK\x03\x04`, `%PDF-`, `\xff\xd8\xff`, `\x89PNG\r\n\x1a\n`), else `ValueError('Unsupported file. Upload an .xlsx, .pdf, .jpg or .png décompte.')`; `check_limits(kind: str, data: bytes) -> None` (raises `ValueError` naming the limit; for PDFs opens `pypdf.PdfReader` and rejects encrypted, unreadable or > 3 pages; `.xlsx` keeps the existing 2 MB message).

- [ ] **Step 1: Write failing tests:** `test_detects_each_kind` (committed `DEMO_DP_N5.xlsx` bytes; a 1-page PDF from `pypdf.PdfWriter().add_blank_page(595, 842)`; minimal JPEG/PNG headers); `test_unknown_bytes_rejected` (`b'hello'` → message contains `.xlsx, .pdf, .jpg or .png`); `test_fake_pdf_rejected_plainly` (`b'%PDF-1.7 garbage'` → `ValueError`, no other exception type); `test_encrypted_pdf_rejected` (writer `.encrypt('x')`); `test_pdf_page_limit` (4 blank pages → message contains `3 pages`); `test_size_limits` (PDF of 2 MB + 1 → `2 MB`; image of 5 MB + 1 → `5 MB`).
- [ ] **Step 2:** Run `python -m pytest tests/test_documents.py -v` → FAIL.
- [ ] **Step 3:** Implement; pin the dependencies; `pip install -r requirements-dev.txt`.
- [ ] **Step 4:** Run the tests → PASS; `python -m pip_audit -r requirements.lock` → no known vulnerabilities.
- [ ] **Step 5:** Commit `feat: detect PDF/image uploads and enforce limits`.

### Task 3: Gemini file input and identity normalisation

**Files:**
- Modify: `scripts/llm.py`, `scripts/controller_checks.py`, `scripts/doc_text.py`
- Test: `tests/test_controller_llm.py`, `tests/test_doc_text.py`

**Interfaces:**
- Produces: `llm.ask_json_file(prompt: str, data: bytes, mime_type: str, schema: dict, api_key: str | None, *, client_factory=None) -> dict | None` (calls `_generate` with `contents=[types.Part.from_bytes(data=data, mime_type=mime_type), prompt]`, temperature 0, JSON schema; `None` on any failure, like `ask_json`). `_generate`'s first parameter becomes `contents`, passed through unchanged (existing callers pass a string).
- Produces: `controller_checks.SOURCE_PDF_TEXT`, `SOURCE_VISION`; `controller_checks.known_projects(folder=HISTORY_DIR) -> tuple[str, ...]` (project names from the history workbooks via `extract_decompte`); `doc_text.normalize_identity(project_text: str | None, number_text: str | int | None, known: tuple[str, ...]) -> tuple[str, int | None]`.

- [ ] **Step 1: Write failing tests:** `test_ask_json_file_sends_file_part` (fake client records `contents`: first item is a Part with mime `image/png`, second is the prompt); `test_ask_json_file_failure_returns_none`; `test_normalize_identity`: `('DEMO PROJECT — DECOMPTE D5', 'D5', ('DEMO PROJECT',)) → ('DEMO PROJECT', 5)`, `('demo project', 'Décompte n° 5', …) → ('DEMO PROJECT', 5)`, `('Other site', '12000', …) → ('Other site', None)`, `(None, None, …) → ('', None)`; `test_known_projects` → `('DEMO PROJECT',)`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Number = first integer in the text, kept only if `statement_number()` accepts it. Project = the known name contained in the text (case-insensitive), else the trimmed text cut to 120 characters.
- [ ] **Step 4:** Run `python -m pytest tests/test_controller_llm.py tests/test_doc_text.py -v` → PASS (existing llm tests still pass).
- [ ] **Step 5:** Commit `feat: Gemini file input and project/number normalisation`.

### Task 4: Digital PDF reader

**Files:**
- Create: `scripts/pdf_reader.py`, `tests/pdf_fixtures.py` (builds test PDFs with `fpdf2`)
- Test: `tests/test_pdf_reader.py`

**Interfaces:**
- Consumes: `doc_text.AMOUNT_PATTERN`, `parse_amount_text`, `label_matches`, `normalize_identity`; `controller_checks.known_projects`, `SOURCE_PDF_TEXT`, `ReadValue`, `Statement`, `FIELDS`; `ai_reader.FIELD_HINTS`; `llm.ask_json`.
- Produces: `Token(id: str, value: Decimal, page: int, line: str, x0: float, x1: float, y: float)` (frozen dataclass); `Line(page: int, y: float, text: str, chunks: tuple[tuple[str, float, float], ...])`; `extract_tokens(data: bytes) -> tuple[list[Token], list[Line]]` (positions from `page.extract_text(visitor_text=…)`, ids `T1…` in reading order); `MIN_TOKENS = 3`; `trace_pdf(data: bytes, answer: dict) -> Statement`; `read_pdf_with_ai(data: bytes, api_key: str | None, ask=llm.ask_json) -> Statement | None` (raises `ValueError('NO_TEXT')` when fewer than `MIN_TOKENS` tokens, so the app switches to vision).
- `tests/pdf_fixtures.py` produces `d5_table_pdf() -> bytes` (the layout described in Task 5) and `blank_pdf() -> bytes`; Task 5's generator reuses the same drawing function, so the bundled PDF and the test PDF are identical.
- Cell column text: `f'page {page} · line "{line[:40]}"'`.

- [ ] **Step 1: Write failing tests** (on `d5_table_pdf()`; the test maps fields to ids by finding each D5 value in `extract_tokens`): `test_traces_all_seven` (all seven D5 values, source `SOURCE_PDF_TEXT`, none uncertain, `('DEMO PROJECT', 5)`); `test_table_row_values_pass_column_header_check` (cumulative, previous and works sit on one line and are not uncertain); `test_wrong_token_is_uncertain` (vat mapped to the retention token → 90000.00, uncertain True); `test_unknown_and_duplicate_ids` (`{'works': 'T999', 'net': 'T1', 'vat': 'T1'}` → works not found, no exception); `test_blank_pdf_raises_no_text`; `test_prompt_lists_tokens_not_bytes` (fake `ask` receives a string containing `T1 | p1 |` and no `%PDF`).
- [ ] **Step 2:** Run `python -m pytest tests/test_pdf_reader.py -v` → FAIL.
- [ ] **Step 3:** Implement. Label check: pass if `label_matches(field, token.line)`, or a `Line` above it on the same page has a chunk overlapping `[x0, x1]` (±10 pt) whose text `label_matches(field, …)`. Prompt: return token ids only, never compute, null when unsure.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: digital PDF reader with traced tokens`.

### Task 5: Example PDF, photo and saved answers

**Files:**
- Modify: `generate_demo_decomptes.py`
- Create (generated, committed): `controller_examples/DEMO_DP_N5.pdf`, `controller_examples/DEMO_DP_N5_PHOTO.jpg`, `controller_examples/DEMO_DP_N5.pdf.answer.json`, `controller_examples/DEMO_DP_N5_PHOTO.jpg.answer.json`
- Test: `tests/test_controller_examples.py`

**Interfaces:**
- Consumes: `controller_example_values(policy)`; `pdf_reader.extract_tokens`; the drawing function behind `tests/pdf_fixtures.d5_table_pdf` (move it into the generator; the fixture imports it from there).
- Produces: `generate_document_examples(folder, policy=None) -> list[Path]` (the four files); `--controller-dir` also writes them. PDF answer: `{"works": "T<n>", …, "project": "DEMO PROJECT", "number": "5"}`. Photo answer: `{"works": {"value": "900 000,00", "label": "Travaux du mois HT"}, …, "project": "DEMO PROJECT", "number": "5"}`.

- [ ] **Step 1: Write failing tests:** `test_document_examples_generated(tmp_path)` (4 files; PDF starts `%PDF`; JPEG starts `\xff\xd8\xff`); `test_committed_document_answers_match_generator(tmp_path)` (both `.answer.json` equal as JSON; committed PDF text equals generated PDF text; the photo is not compared byte-for-byte).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. PDF (`fpdf2`, A4, French): heading `DEMO PROJECT — DECOMPTE D5`, the line `SYNTHETIC DATA — FOR DEMONSTRATION ONLY`, a header row `Cumul actuel HT | Cumul précédent HT | Travaux du mois HT` with the three amounts under it, then one labelled line each for `Retenue de garantie 10%`, `Net HT`, `TVA 20%`, `Total TTC`; amounts in French format (`2 737 700,00`). Photo (Pillow, `random.Random(5)`): the same content, light paper tint, 2–3° rotation, soft shadow, JPEG quality 85. PDF answer ids come from `extract_tokens` on the generated PDF matched to the known values.
- [ ] **Step 4:** Run `python generate_demo_decomptes.py --controller-dir`, then `python -m pytest tests/test_controller_examples.py tests/test_pdf_reader.py -v` → PASS (Excel example tests unchanged).
- [ ] **Step 5:** Commit `feat: synthetic PDF and photo examples with saved answers`.

### Task 6: Vision reader

**Files:**
- Create: `scripts/vision_reader.py`
- Test: `tests/test_vision_reader.py`

**Interfaces:**
- Consumes: `doc_text.parse_amount_text`, `label_matches`, `normalize_identity`; `controller_checks.known_projects`, `SOURCE_VISION`; `llm.ask_json_file`; `ai_reader.FIELD_HINTS`.
- Produces: `SCHEMA` (per field nullable `{"value": string, "label": string}`, plus `project`, `number`); `parse_vision_answer(answer: dict, cell_text: str) -> Statement` (`cell_text` is `'image'` or `'scanned PDF'`); `read_with_vision(data: bytes, mime_type: str, api_key: str | None, ask=llm.ask_json_file) -> Statement | None`.

- [ ] **Step 1: Write failing tests** (with the committed photo answer): `test_saved_photo_answer_parses` (all seven D5 values, source `SOURCE_VISION`, cell `'image'`, `('DEMO PROJECT', 5)`); `test_two_numbers_in_value_not_found`; `test_wrong_label_uncertain` (vat with label `'Net HT'` → uncertain); `test_junk_answer_shapes` (`{'vat': 'abc'}`, `{'vat': {'value': None}}`, `{'vat': 5}` → not found, no exception); `test_none_from_ai_returns_none`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Prompt: transcribe digits exactly as printed with their printed label, never compute, null when unsure.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: vision reader for photos and scanned PDFs`.

### Task 7: App routing, examples, fallback and confirm screen

**Files:**
- Modify: `app.py`, `scripts/controller_checks.py`
- Test: `tests/test_controller_app.py`

**Interfaces:**
- Produces: `controller_checks.load_saved_answer(name: str) -> dict | None` (reads `EXAMPLES_DIR / f'{name}.answer.json'`, only for `DEMO_DP_N5.pdf` and `DEMO_DP_N5_PHOTO.jpg`). Buttons `ctrl_example_pdf` (`▶ Try example: PDF`) and `ctrl_example_photo` (`▶ Try example: photo`). `read_values` returns `(statement, problem, read_method)`; Excel paths keep `'fixed layout'` / `'found by AI'`.
- Routing: `detect_kind` + `check_limits` first (their message shown as the problem). `pdf` → `read_pdf_with_ai`; on `ValueError('NO_TEXT')` → `read_with_vision(data, 'application/pdf', …)` with cell text `'scanned PDF'`. `jpeg`/`png` → `read_with_vision`. Own upload without the privacy tick → exact no-tick copy; own upload without a key → exact offline copy. Bundled example with no key, limit reached or AI failure → parse `load_saved_answer(name)` through `trace_pdf` / `parse_vision_answer`, show the exact badge, and add ` (saved)` to `read_method`. Live reads use `ai_call_allowed`, `ctrl_ai_failed`, and cached functions keyed by digest like `cached_ai_read`.
- Confirm: PDF and vision statements always go through `confirm_values`; for `SOURCE_VISION` also the exact vision notice and `st.image(data)` (JPEG/PNG) or the caption `PDF page sent to AI` (scanned PDF). Uploader types `['xlsx', 'pdf', 'jpg', 'jpeg', 'png']`, label `Or upload your own synthetic décompte (.xlsx, .pdf, .jpg, .png)`.

- [ ] **Step 1: Write failing tests:** `test_pdf_example_offline_uses_saved_answer` (no key → badge shown, `ctrl_confirm` present, no `REVIEW` before confirm; after confirm → `REVIEW` count ≥ 2 and `12,300.00` or `12 300,00` shown); `test_photo_example_offline_uses_saved_answer` (same, plus an image element); `test_photo_example_live` (patch `scripts.llm._generate` to return the saved photo JSON when `contents` is a list → no badge, `read by AI from image` shown); `test_own_pdf_needs_privacy_tick` (example PDF bytes uploaded as `x.pdf` → no-tick copy); `test_own_photo_offline_message` (privacy ticked, no key → offline copy); `test_not_a_pdf_upload` (`b'hello'` as `x.pdf` → unsupported-file message, no exception); existing `test_upload_too_big_is_rejected` still passes.
- [ ] **Step 2:** Run `python -m pytest tests/test_controller_app.py -v` → new tests FAIL, old ones PASS.
- [ ] **Step 3:** Implement in `app.py`; the Excel path's behaviour and copy stay unchanged.
- [ ] **Step 4:** Run `python -m pytest -q` → all PASS.
- [ ] **Step 5:** Commit `feat: AI Controller reads PDFs and photos`.

### Task 8: Docs and final verification

**Files:**
- Modify: `README.md` (AI Controller section)

- [ ] **Step 1:** Add to the README the new example buttons, the privacy/offline behaviour, and the sentence: "The controller now reads PDFs and phone photos too, and tells you which numbers it read itself and which ones a human must confirm."
- [ ] **Step 2:** Run `python -m pytest -q`, `python -m scripts.reports`, `python -m pip_audit -r requirements.lock` → all succeed; this work changes nothing under `demo_decomptes/` or `outputs/`.
- [ ] **Step 3:** Run the app locally (`streamlit run app.py`); click both new examples with and without a key; check the badge, the image preview and the 2 REVIEW findings.
- [ ] **Step 4:** Commit `docs: describe PDF and photo reading`.
