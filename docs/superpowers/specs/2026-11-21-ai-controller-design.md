# AI Project Controller — Design

Date: 2026-11-21
Project: Infrastructure Analytics Demo (public portfolio version, synthetic data)
Repo: github.com/Aiz-commits/infrastructure-analytics-demo, deployed on Streamlit Community Cloud. Local working copy: `C:\Users\newga\projects\infrastructure-analytics-demo`.

## 1. Intent and why

Add an AI "digital junior auditor" to the public demo. A new construction payment statement (décompte) comes in. The app reads it, checks it, explains the problems in plain French or English, drafts an email to the contractor, and waits for a human to approve.

Why: the author is a BBA student (Analytics & AI for Business + FinTech) who wants the project to impress their university and help their career (internships, a US master's). It must show AI applied to a real finance problem in a way a professor or recruiter understands in about 1 minute. It extends a real internship project at EXCELIUM STD. The public version uses only synthetic data.

## 2. Goals

1. New page **"🤖 AI Controller"** in the existing Streamlit app.
2. A visitor can click **"Try example"** and, in under ~30 seconds, see:
   - the values read from the décompte,
   - the checks that passed and failed,
   - an AI audit memo (FR or EN),
   - an AI draft email to the contractor,
   - Approve / Reject buttons, with an audit trail.
3. It reads décomptes whose layout differs from the 2 fixed layouts the current extractor supports (AI-assisted reading).
4. It still works with no AI available (no key, or quota used up), using template text.
5. It runs free: Gemini API free tier plus Streamlit Community Cloud.

## 3. Non-goals (this version)

- Really sending emails. Approve produces downloadable files only.
- Reading PDFs or phone photos (phase 2).
- An agent that chooses its own checks (approach B, phase 3).
- Changing the private internship app or using real company data.
- Comparing many projects or prices across projects.

## 4. Anti-goals (a failure even if it "works")

- **The AI calculates or changes any amount.** All math is Python. The AI only locates values and writes text.
- The AI writes a number in the memo or email that the Python checks didn't produce.
- Anything is "sent" or marked final without a human click.
- The page crashes or shows a raw error when the AI is down or slow.
- Real company data or a real API key ends up in the public repo.
- Any paid service.

## 5. Constraints

- Work happens in `C:\Users\newga\projects\infrastructure-analytics-demo`, a fresh clone of the GitHub repo at commit 837cefe (version 0.2.0). The older Desktop copy is 3 commits behind and is not used.
- Python + Streamlit, inside the existing `app.py`. Existing pages and their tests stay as they are.
- Reuse what the repo already has. Do not duplicate it:
  - `scripts/policy.py`: `amount()`, `load_policy()` and `expected_amounts()`. All rates, tolerance and contract total come from `project_config.json`, never hardcoded.
  - `scripts/workbooks.py`: `open_workbook` / `workbook_bytes`, which bound file size and cells.
  - `scripts/decompte_extractor.py`: `identity()` (project and statement number from A1 / A3:B4), `layout_row()`, `extract_decompte()`.
  - `scripts/audit.py`: continuity rules (same project, no duplicates, consecutive numbers).
- Dependencies are pinned in `requirements.txt` and `requirements.lock`. CI (`.github/workflows/checks.yml`) runs pytest on Python 3.12 and 3.14, regenerates reports and runs pip-audit. New: the official Google Gen AI SDK (`google-genai`), pinned in both files with a binary wheel for 3.12 and 3.14. Tests must never call the real AI (mock it); CI has no key.
- Reports and `outputs/manifest.json` are built from `demo_decomptes/*.xlsx`. New example files must not go in that folder, or the existing reports change.
- API key from `st.secrets["GEMINI_API_KEY"]`. Locally it lives in `.streamlit/secrets.toml`, which is already in `.gitignore`. On the cloud it goes in Streamlit's Secrets settings.
- Public site: anyone can click, so AI calls must be limited and cached (see 7.6).
- Money uses `Decimal` via `policy.amount()`. Convert to float only for display, like `audit.display_frame`.
- Demo rules (from `project_config.json`, version `demo-finance-v1`): retention 10%, no cap, VAT 20% on net after retention, tolerance 0.01 DH, contract 5,400,000.00 DH TTC.

## 6. Approaches considered

| | Approach | Trade-off | Decision |
|---|---|---|---|
| A | Fixed pipeline: Python does every check; Gemini only (1) locates values in unknown layouts and (2) writes memo and email | Reliable, free, runs on the live site; the AI doesn't "decide" the steps | **Chosen** by the author |
| B | Tool-calling agent: the AI chooses which Python checks to run | More "autonomous"; harder to build, and it may skip a check on money data | Later upgrade (phase 3) |
| C | Local model on the user's PC | Private; can't run on Streamlit Cloud, and the 6 GB GPU limits quality | Rejected for the public demo |

## 7. Design

### 7.1 Flow (5 steps shown on the page as a progress list)

1. **Receive.** The visitor uploads a `.xlsx` décompte or clicks "Try example".
   - **Previous décompte (builder's call):** for the bundled examples, it comes from the bundled demo history (`demo_decomptes/DEMO_DP_N1..N4.xlsx`), matched by project and statement number. For a visitor's own upload, continuity and gap checks run only if they also upload the previous décompte. Otherwise those checks show "skipped — no previous décompte", never a false finding.
   - **Privacy (builder's call):** the bundled examples always use AI. A visitor's own upload is sent to Gemini only after they tick: "This file contains no confidential data. It will be sent to Google Gemini (free tier), which may use it to improve its products." Without the tick, the page uses the fixed layout and template text only.
2. **Read.**
   - First try the existing extractor (`extract_decompte`).
   - If the layout is unsupported, use AI reading: send Gemini the non-empty cells of the first sheet as `coordinate: value` text. Ask for JSON with the cell address of each field: works HT (month), cumulative HT, previous cumulative HT, retention, net HT, VAT, TTC.
   - **Trace rule:** Python reopens the workbook and reads each returned cell itself. Only those values are used. Any field whose cell is empty or not numeric becomes "not found" and is never invented.
   - The UI shows each value with its cell and its source: "fixed layout" or "found by AI".
   - **Label check (builder's call):** for AI-read values, Python also checks that the row or column of each chosen cell contains an expected label keyword (e.g. "TVA" for VAT, "Retenue" for retention, "Cumul" for cumulative). A mismatch marks that value "uncertain".
   - **Confirm step (builder's call):** when any value was read by AI, the page shows an editable values table and a **"Confirm values"** button. Steps 3–5 run only after the click. Values from the fixed layout skip this step, so "Try example" stays fast. This keeps a human in control before any finding or email exists.
   - **Project and décompte number (builder's call):** use the existing `identity()` (A1 heading, or A3:B4). The filename number (`filename_number()`) is only cross-checked, never trusted alone, as `audit.py` already does. AI reading also returns the cells holding project and number, traced like the amounts. If none is found, the visitor types them in.
3. **Check (Python only).** Produce a list of findings, each with: id, severity (OK / WARNING / REVIEW), title, amounts involved, difference, evidence (cells / décompte numbers). Checks:
   - retention = 10% of works
   - net = works − retention
   - VAT = 20% of net
   - TTC = net + VAT
   - continuity: this "previous cumulative" = last décompte's cumulative
   - cumulative = previous cumulative + works of the month
   - sequence gap (e.g. D5 arrives but D4 is missing)
   - missing fields from step 2
   - **Stated values (builder's call):** each check compares the values as written in the file, one step at a time (e.g. TTC check = stated net + stated VAT). It does not recompute the whole chain from works. So one wrong cell gives one finding, not a cascade. Rates and tolerance come from `load_policy()`. The existing `extract_decompte()` keeps its own behavior for the other pages; it is not changed.
   - The same check function runs on values from the fixed layout and on AI-read values, so both paths follow identical rules.
4. **Explain (AI).** Gemini receives **only** the findings list as JSON, never the raw file. It returns (a) a short audit memo and (b) a polite email to the contractor asking for justification of each REVIEW item. Language toggle: Français / English.
   - **Number guard:** Python extracts every number from the AI text. Each must match a number in the findings (normalized for spaces, commas, dots and "DH"). On a mismatch, retry once. If it still fails, use the template text.
5. **Human review.** Memo and email are shown in editable text boxes, with Approve and Reject buttons. Approve marks it "Approved by reviewer" with a timestamp and offers downloads: memo `.md` and email `.eml` (or `.txt`). An audit-trail table for the session records file, date/time, AI used yes/no, decision. Nothing is emailed.

### 7.2 What the page looks like

```
🤖 AI Controller                         Language: [Français ▾]

📥 New décompte  [Upload .xlsx]  or  [▶ Try example: DEMO_DP_N5]

Step 1 Receive ✅  Step 2 Read ✅  Step 3 Check ⚠️  Step 4 Explain ✅  Step 5 Review ⏳

Values read                         source
 Works of month HT   900,000.00     D37 (fixed layout)
 Previous cumul HT 2,737,700.00     C37 (fixed layout)
 ...

Checks
 ✅ Retention 10%          OK
 ⚠️ Continuity D4 → D5     REVIEW   gap 12,300.00 DH
 ⚠️ VAT 20%                REVIEW   diff 1,000.00 DH

📝 Audit memo (AI)        [editable]
✉️ Email to contractor (AI) [editable]

[✅ Approve]  [❌ Reject]      ⬇ memo.md  ⬇ email.eml

Audit trail (this session)
```

### 7.3 Code layout

- `scripts/controller_checks.py`: pure Python. Findings dataclass and all checks, built on `policy.py`. No Streamlit, no AI. Fully unit-tested.
- `scripts/ai_reader.py`: opens the file with `workbooks.open_workbook`, builds the cell text, calls the LLM, applies the trace rule and the label check.
- `scripts/ai_writer.py`: builds the prompt from findings, calls the LLM, applies the number guard, falls back to templates.
- `scripts/llm.py`: thin Gemini wrapper. Reads the key, sets the model name in one constant, applies a timeout, returns `None` on any failure so callers fall back.
- `app.py`: adds "🤖 AI Controller" to the sidebar list and a page block that calls the modules above.
- `generate_demo_decomptes.py`: extended (see 7.5).
- `tests/`: pytest for checks, trace rule and number guard, with the LLM mocked.

### 7.4 AI details

- Model: the current free-tier Gemini Flash model, set in one constant in `llm.py` (builder picks the exact name at build time).
- Ask for JSON output (structured response) for reading. Use plain text with a fixed section format for writing.
- Prompts are in English and ask for the chosen output language. Tone: neutral auditor, "requires justification", never "fraud" or "error confirmed" (matches the app's existing wording).

### 7.5 Demo data

Add a separate generator function in `generate_demo_decomptes.py` that writes into a new folder **`controller_examples/`** (not `demo_decomptes/`, so the existing reports and manifest don't change). Same identity cells as N1–N4 (A1 heading, A3:B4 project and number = 5). It creates:
- `DEMO_DP_N5.xlsx`, standard layout, with exactly 2 planted problems, so exactly 2 REVIEW findings:
  - Continuity: stated previous cumulative = D4 cumulative − 12,300.00 DH. Stated cumulative = stated previous + works, so it is internally consistent and only the continuity check fails.
  - VAT: stated VAT = 20% of net + 1,000.00 DH. Stated TTC = net + stated VAT, so only the VAT check fails.
- `DEMO_DP_N5_NEW_LAYOUT.xlsx`, the same numbers placed at different rows and columns with labels, so the fixed extractor fails and AI reading is shown.

N1–N4 stay unchanged.

### 7.6 Public-site safety

- Cache AI results by file hash plus language (`st.cache_data`), so repeat demo clicks cost no AI calls.
- Limit of 10 AI calls per browser session. After that, use template text with a notice.
- Upload limit: `.xlsx` only, max ~2 MB, first sheet only, max ~2,000 non-empty cells sent to the AI.
- If the key is missing, show a small "AI offline — template mode" badge. Everything else still works.

## 8. Success looks like

- "Try example" works on the live site in under ~30 seconds and catches both planted problems.
- The new-layout file is read correctly by AI, with every value traced to a cell.
- No number in the memo or email is unsupported by the findings.
- With the key removed, the page still runs in template mode.
- Tests pass for the checks, trace rule and number guard.
- README and LinkedIn can describe it in one sentence: "An AI controller that reads construction payment statements, checks them with Python, and drafts the audit memo and contractor email for human approval."

## 9. Left to the builder

- Exact Gemini model name and SDK call style.
- Prompt wording, within the rules above.
- Streamlit widget details and styling, consistent with `.streamlit/config.toml`.
- Template text wording for offline mode.
- How the 0.01 DH tolerance is applied in the number guard (e.g. rounding to 2 decimals).

## 10. Later phases (roadmap, each gets its own design)

Design rule for phase 1, so these fit later: keep checks and AI calls in `scripts/` modules with plain inputs and outputs (no Streamlit inside). Then a database, an API and n8n can reuse them.

- **Phase 1.5 — SQL memory.** Save décomptes, extracted values, findings, memos and approval decisions in a database. SQLite locally; a free hosted Postgres (e.g. Supabase) for the live site, since Streamlit Cloud storage is not permanent. The audit trail survives restarts.
- **Phase 2 — PDF and photo reading** with Gemini vision. No cell trace is possible, so the visitor must confirm the extracted values before checks run.
- **Phase 2.5 — Power BI management dashboard** reading the SQL database: total billed vs contract, findings by type and contractor, time to approval. Streamlit stays the working tool; Power BI is the management report. Sharing online may need a university Microsoft 365 account; otherwise share screenshots or a video.
- **Phase 3 — Agent + automation.** Approach B (the AI chooses checks through tool calls). A small API (e.g. FastAPI) exposes the controller. n8n watches an email inbox, sends new décomptes to the API, and sends a phone notification (ntfy/Telegram) with the result and an approve link.
- **Phase 4 — Contract price list (BPU) checks** on quantities and unit prices.
- **Phase 5 — "Billed vs Built"**: site photos compared with billed quantities, shown as "check this zone", never as proof.
- **Phase 6 — Startup pitch**: multi-project price comparison and contractor risk score, as a business plan.
