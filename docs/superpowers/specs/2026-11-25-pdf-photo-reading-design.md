# Phase 2 — Reading PDF and photo décomptes — Design

Date: 2026-11-25
Project: Infrastructure Analytics Demo (public portfolio version, synthetic data)
Builds on: `2026-11-21-ai-controller-design.md` (Phase 1), `2026-11-21-sql-memory-design.md` (Phase 1.5).

## 1. Intent and why

Today the 🤖 AI Controller only reads `.xlsx` décomptes. On real construction sites, statements also arrive as PDFs exported from software, as signed paper scans, and as phone photos. Phase 2 lets the controller read all three, then run the same Python checks, memo, email and human review as today.

Why: it closes the gap between the demo and real work (the author's internship at Excelium), and it shows a professor or recruiter that the tool knows the difference between a number it read from a file and a number an AI read from a picture. That judgment is the story.

## 2. Goals

1. The upload accepts `.xlsx`, `.pdf`, `.jpg`/`.jpeg` and `.png`.
2. **Digital PDF path:** for a PDF that contains text, Python pulls the text out and numbers every amount it finds. Gemini only says which numbered amount is which field (like it names cells today). Python takes each value from its own extracted text. The AI never types a number.
3. **Vision path:** for a photo, or a PDF with no usable text (a scan), Gemini reads the values from the image. The visitor must confirm them before any check runs.
4. The app picks the path by itself. The values table shows where each value came from.
5. Two new "Try example" buttons: a digital PDF and a phone-style photo of the same synthetic statement (D5). Both lead to the same 2 REVIEW findings as the Excel example.
6. Everything after "Read" (checks, memo, email, approve/reject, public history) is unchanged.

## 3. Non-goals

- Reading the previous décompte from a PDF or photo. The "previous décompte" upload stays `.xlsx` only; bundled examples keep using `demo_decomptes/` history.
- HEIC/HEIF photos, multi-statement PDFs, batch upload, handwriting quality guarantees.
- Image cleanup (deskew, contrast). Gemini gets the file as uploaded.
- Any change to the private Excelium app or use of real company documents.
- Phase 3 (agent, API, n8n).

## 4. Anti-goals (a failure even if it "works")

- A value read by AI from an image reaches the checks without a human click on **Confirm values**.
- An AI-read image value is shown as if it were traced to a cell or to PDF text.
- The AI calculates, corrects or "fixes" a number. It transcribes what is printed; Python does all math.
- An uploaded PDF or photo, or any value from it, is stored anywhere (history keeps saving bundled examples only).
- A PDF or photo is sent to Gemini without the privacy tick (bundled examples excepted, as today).
- A crash or raw error when the AI is offline, slow, or returns junk.
- Any paid service or new paid dependency.

## 5. Constraints

- Same repo, Python + Streamlit in `app.py`, free Gemini tier via the existing `google-genai` SDK and `scripts/llm.py`. Model stays the one constant in `llm.py` (it must accept image and PDF input; builder confirms at build time and changes the constant only if needed).
- All Phase 1 constraints still apply: `Decimal` money via `policy.amount()`, rates from `project_config.json`, tests never call the real AI, CI runs Python 3.12 and 3.14 with `pip-audit`, pinned `requirements.txt` + `requirements.lock`.
- New runtime dependency: **`pypdf`** (pure Python, no binary wheel issues) for PDF text. Generators of the example files may use dev-only libraries pinned in `requirements-dev.txt`; the app must not need them.
- Limits (public site): PDF ≤ 2 MB and ≤ 3 pages; image ≤ 5 MB (phone photos are larger than spreadsheets); `.xlsx` limit unchanged. Same 10-AI-calls-per-session limit and the same cache by file hash.
- Example files go in `controller_examples/` (never `demo_decomptes/`, which feeds the reports).

## 6. Approaches considered

| | Approach | Trade-off | Decision |
|---|---|---|---|
| A | Digital PDFs only: Python extracts text, AI only maps numbers to fields | Keeps the "AI never types a number" rule; cannot read scans or photos | Part of C |
| B | Photos and scans only, via Gemini vision + mandatory confirm | Best demo moment; the AI transcribes digits, so trust depends on the human check | Part of C |
| C | Both, routed automatically, with the source shown per value | More work; covers every real case and shows the trust difference | **Chosen** by the author |

## 7. Design

### 7.1 Flow changes (5 steps stay the same)

1. **Receive.** File type is decided by content, not only extension: `.xlsx` (zip), `.pdf` (`%PDF` header), JPEG/PNG (magic bytes). Anything else is refused with a plain message. Size and page limits from §5 are checked here.
2. **Read.**
   - `.xlsx` → unchanged (fixed layout, then AI cell reading).
   - `.pdf` → try the **digital PDF path** (7.2). If the PDF has no usable text, use the **vision path** (7.3) on the PDF itself (Gemini accepts PDF input).
   - image → **vision path**.
   - Without the privacy tick, PDF and photo uploads stop here with: "PDF and photo reading uses Gemini. Tick the privacy box above to allow it." Without an API key: "AI is offline (template mode). PDF and photo reading needs AI; upload an .xlsx instead."
   - Any value not found stays "not found" and becomes a WARNING finding, as today.
3. **Confirm.** Every PDF and photo read goes through the existing **Confirm values** screen (editable table, project and number inputs). For vision reads, the screen also shows the uploaded image (or "PDF page sent to AI") next to the table and a stronger notice: "These numbers were typed by the AI from the picture. Compare each one with the document before confirming."
4. **Check, Explain, Review** → unchanged.

### 7.2 Digital PDF path (`scripts/pdf_reader.py`)

- Open with `pypdf`, max 3 pages, extract text page by page. "Usable text" = at least 3 amounts found (builder's call on the exact threshold, documented in code).
- Python finds every amount-like token with a regex that understands French and English formats (`2 750 000,00`, `2,750,000.00`, `2750000.00`, optional `DH`/`MAD`), parses it with `policy.amount()`, and gives it an id: `T1, T2, …` with its full line of text and page number.
- Gemini receives the numbered list (`T7 | p1 | "TVA 20% ...... 125 000,00"`) plus the field hints already in `ai_reader.FIELD_HINTS`, and returns JSON: the token id for each field (or null), plus the project name and statement number as text.
- **Trace rule, PDF version:** Python looks up each returned id in its own token list. Unknown ids → "not found". The value used is always Python's parse of that token.
- **Tokens keep their position (builder's call, from the review):** real exported décomptes are tables, with several amounts on one row and the labels in a header line. So each token also stores its x/y position (via pypdf's text visitor), not just its line.
- **Label check (builder's call):** the field keyword from `ai_reader.LABEL_KEYWORDS` must appear either on the token's own line, or in a header line above it whose text overlaps the token's column (same horizontal span, small tolerance). Otherwise the value is "uncertain" (WARNING), same as cells. The cumulative/previous exclusion from `ai_reader._label_ok` applies here too.
- The bundled `DEMO_DP_N5.pdf` uses the same table layout as the Excel example (cumulative, previous and works side by side under column headers), so this rule is exercised on the demo.
- Display: the "Cell" column shows `page 1 · line "TVA 20% …"` (truncated), source **"PDF text (AI located)"**.
- Project and number: Python cross-checks the AI's answers against the text (the project string must appear in the text; the number must be an integer 1–10000). Otherwise left blank for the visitor to type.

### 7.3 Vision path (`scripts/vision_reader.py`)

- Gemini receives the file bytes with their MIME type and the same field hints. It returns JSON per field: `{"value": "<digits exactly as printed>", "label": "<the printed label next to it>"}` or null, plus project and number.
- Python parses each `value` string with the same amount parser as 7.2. Unparseable → "not found". Values are never rounded or adjusted.
- **Label check:** the returned `label` must contain the field keyword; otherwise "uncertain".
- **Project and number, normalised by Python (builder's call, from the review):** the statement number is the first integer in the AI's text (`"D5"`, `"Décompte n° 5"` → 5), kept only if 1–10000. For the project, if the AI's text contains a project name known from `demo_decomptes/` history (case-insensitive), that exact name is used; otherwise the AI text is trimmed and shown for the visitor to correct. This keeps the continuity lookup working on the photo example. The same normalisation applies to the PDF path's project/number answers.
- History rule unchanged: a visitor correction on the Confirm screen (values, project or number) still blocks saving that run to the public history, as in Phase 1.5.
- Display: "Cell" column shows `image` (or `scanned PDF`), source **"read by AI from image"**.
- `llm.py` gets one new function, `ask_json_file(prompt, data, mime_type, schema, api_key)`, built like `ask_json` (temperature 0, JSON schema, returns `None` on any failure).

### 7.4 What changes in shared code

- `controller_checks.py`: two new source constants (`SOURCE_PDF_TEXT`, `SOURCE_VISION`). `run_checks` is unchanged. The existing "uncertain" and "missing" findings cover both new paths.
- `app.py`: upload types, routing by content, two example buttons, the confirm notice and image preview for vision reads, `read_method` saved to history as `'PDF text'` or `'AI vision'` (fits the existing `String(32)` column; Power BI is unaffected).
- `ai_reader.py`: the shared amount regex/parser and label check move to a small helper both new readers import, so there is one parser.
- History: unchanged rules. Only bundled examples are saved, and not if the visitor edited values.

### 7.5 Demo data

`generate_demo_decomptes.py` gets a third generator writing into `controller_examples/`, from the same numbers as `DEMO_DP_N5.xlsx` (so the same 2 planted problems):
- `DEMO_DP_N5.pdf`: a clean one-page digital statement in French, amounts in French format.
- `DEMO_DP_N5_PHOTO.jpg`: the same page rendered as an image with a light tilt, shadow and paper tint, so it looks like a phone photo but stays readable.
The generated files are committed. The libraries used to draw them are dev-only.

**Live + saved fallback (decided by the author):**
- The PDF and photo example buttons call Gemini for real, like the new-layout Excel example.
- If there is no key, the session limit is reached, or the call fails, they use a **saved example answer** committed next to each file (`DEMO_DP_N5.pdf.answer.json`, `DEMO_DP_N5_PHOTO.jpg.answer.json`). Each one has the same JSON shape Gemini returns: token ids for the PDF, transcribed strings and labels for the photo.
- The saved answer goes through exactly the same Python trace, parse and label checks as a live answer. The page shows a clear badge: "Saved example answer (AI offline)".
- The generator writes the saved answers from its own known values, so they are correct by construction. They are labelled "saved example answer", never "AI".
- The fallback applies to the bundled examples only. A visitor's own PDF or photo with the AI offline still gets the offline message.
- History `read_method`: `'PDF text'` or `'AI vision'` for live reads, `'PDF text (saved)'` or `'AI vision (saved)'` for fallback runs.
- Tests use the saved answers to prove that both examples produce exactly the 2 planted REVIEW findings, with no AI call.

### 7.6 Safety and cost

- Same cache by file hash (and path), same 10-call session limit, same failure handling (`ctrl_ai_failed`, no retry loops).
- Uploads stay in memory only. The image preview is shown from memory and never written to disk.
- Prompt says: transcribe only, never compute, return null when unsure.

## 8. Success looks like

- "Try example: PDF" reads all 7 values, each traced to a PDF line, and finds exactly the 2 planted REVIEW findings.
- "Try example: photo" shows the image beside the values; after Confirm, the same 2 REVIEW findings appear.
- With no key, `.xlsx` still works, the PDF and photo examples still work from their saved answers (with the badge), and a visitor's own PDF/photo shows the clear offline message.
- Tests (LLM mocked) cover: file-type detection, amount parser on FR/EN formats, PDF token trace rule and label check, vision parsing including junk answers, routing (text PDF vs scanned PDF vs image), and the confirm gate.
- LinkedIn/README sentence: "The controller now reads PDFs and phone photos too, and tells you which numbers it read itself and which ones a human must confirm."

## 9. Left to the builder

- Exact regex and the "usable text" threshold.
- Prompt wording within the rules above.
- How the photo example is made to look realistic.
- Widget layout of the image preview.
- Whether the PDF path also sends page images when text is partial (default: no; text or vision, not both).
