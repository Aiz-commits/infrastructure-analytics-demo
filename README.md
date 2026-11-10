# Infrastructure Analytics Demo

A Streamlit demonstration of construction monitoring and financial checks.
**All bundled statements, quantities, contract values and reports are synthetic.**
This public demo is for synthetic uploads only; it is not a production financial approval system.

## Run locally

Supports Python **3.12–3.14**, including the existing Streamlit deployment’s Python 3.14 runtime. No app recreation or Python-setting change is required.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --only-binary=:all: -r requirements.lock
python -m scripts.reports
streamlit run app.py
```

`requirements.txt` pins the direct runtime dependencies. `requirements.lock` pins
the resolved Linux runtime dependencies, tested on Python 3.12 and 3.14. Other platforms may add platform-specific dependencies. The app has no external API keys.
The repository contains regenerated reports so rebuilding is only necessary after
changing source statements, technical input, calculation code or project configuration.

## Pages and data separation

- **Overview:** saved synthetic financial totals, ordered numerically by statement.
- **Financial Audit:** saved continuity and arithmetic checks; only explicit `OK`
  statuses pass. Empty, missing and unknown statuses never constitute success.
- **Technical Monitoring:** quantity arithmetic, contract quantity screening and
  explicitly explained illustrative manual review flags.
- **Document Analysis:** session-only preview and validation of uploaded XLSX files.
  Uploads are not saved to disk, cached globally, sent to AI services or included
  in saved demo reports. Choose the worksheet to use for both preview and single-file
  analysis. Multi-file analysis requires one unambiguous supported DP sheet per file.
- **Report Center:** downloads saved synthetic reports with validated provenance.

Saved reports are deliberately separate from uploaded analysis. The app displays
their generation time and rule version. Every saved report has a `Metadata` sheet;
`outputs/manifest.json` records source, rule and report SHA-256 hashes. Changed,
missing or stale source/report files prevent saved results from being presented
as verified. Upload analysis remains available if saved reports are missing.
This is a consistency check, not a digital signature or evidence of authenticity.

## Financial assumptions

`project_config.json` explicitly defines the demonstration rules:

- Retention: 10% of current-period works HT, with no cap by default.
- Net HT: works HT less retention.
- VAT: 20% of net HT after retention, rounded half up to two decimal places.
- TTC: net HT plus VAT. Allowed discrepancy: at most 0.01 DH.
- Synthetic gross contract value: 5,400,000 DH TTC.

These are demonstration assumptions, **not a tax or contractual opinion**.
The VAT base can be `net_after_retention` or `works_ht`. An optional retention cap
is applied cumulatively, using current and previous cumulative works amounts.
Negative corrections, retention releases, advances, price revisions and mixed tax
rates need additional documented rules and are unsupported by this demonstration.
The overview ratio uses gross works valuation before retention, not net payments
or physical construction progress.

Checks use `Decimal` through calculation and continuity comparison; conversion to
floating point occurs only for presentation/export. Financial cells must be finite,
numeric and no larger than 1 trillion DH in absolute value. Formula cells are read
from saved cached values: openpyxl does not recalculate Excel formulas. Save an
up-to-date recalculated workbook before importing. Missing cached values produce
an actionable error; cache freshness cannot be certified by this app.

The extractor checks current cumulative HT = previous cumulative HT + current
works HT, as well as expected retention/net/VAT/TTC and declared total identities.
A blank opening balance is treated as zero only for a source-identified statement 1;
other missing previous balances remain incomplete.

## Supported statements and identity

Supported summary layouts have `Retenue de Garantie` in A39 or A41. Works totals
are read from row 37 or 39 respectively (B=current cumulative, C=previous cumulative,
D=current-period works); retention is two rows below and net/VAT/TTC are seven,
eight and nine rows below. Results display source worksheet and cell references.

The supplied heading format is `DEMO PROJECT — DECOMPTE D1` in A1. Newly generated
examples also include `Project ID` in A3 / its value in B3 and `Statement number`
in A4 / its integer value in B4. Conflicting heading/metadata numbers are rejected.
Other layouts need an explicit adapter; a filename alone cannot establish identity.

Batch checks require a single identified project, distinct source statement numbers
from 1 to 10000, and at least two consecutive statements. Filename numbers, when
present, must agree with the source. Renamed files with valid source identity are
still checked. All uploaded inputs are accounted for. Invalid, unidentified,
duplicate, missing, mixed-project or discrepant inputs block an overall pass.
A passing subset does not certify statements outside the uploaded interval.
Gap checks compare adjacent numbers without allocating a potentially huge range.

## Upload limits

10 MiB compressed per workbook; 50 MiB expanded; 1024 ZIP entries; 20 worksheets;
10,000 declared rows and 200 declared columns per worksheet; 20 files and 50 MiB
compressed per batch. Preview iteration is bounded to 30 rows and 200 columns.
Encrypted, macro-enabled and invalid XLSX archives are rejected. XML parsing uses
`defusedxml`. Upload errors are reported without tracebacks or document dumps.

This public demo does not provide user/project authorization or certified audit
storage. A confidential production version requires a separate access-control and
retention design before using real records.

## Rebuild synthetic reports

```bash
python -m scripts.reports
```

This regenerates all six saved reports from the bundled statements and
`scripts/demo_technical.csv`, then writes a provenance manifest. The previously
unreconciled D2→D3 report discrepancy is removed: the source previous cumulative
amount is 1,120,000 DH, and all three bundled source transitions reconcile.
The technical CSV preserves the six original synthetic work items and explains
three illustrative manual review flags. It does not supply real D3 evidence.

To explicitly regenerate the four source statements (overwriting those demo files):

```bash
python generate_demo_decomptes.py
python -m scripts.reports
```

Importing the generator is safe and performs no writes. Custom policy changes may
require regenerating the synthetic sources so their stated amounts match the rules.

## Tests and dependency checks

```bash
python -m pip install --only-binary=:all: -r requirements.lock -r requirements-dev.txt
python -m pytest
python -m pip_audit -r requirements.lock
python -m pip check
```

CI installs runtime dependencies as binary wheels and tests Python 3.12 and 3.14, preventing a repeat of the pandas source-build problem on Python 3.14.

Tests cover financial rounding and policy variants, both layouts, cumulative
identities, source selection, missing/duplicate/conflicting identity, gaps, resource
limits, report provenance, safe imports and all five Streamlit pages. GitHub Actions
runs these checks on push and pull requests. Chromium browser checks were also run
locally for the fixes; Playwright is not a runtime dependency.

This remains an academic portfolio demonstration. AI extraction and report drafting
are optional future features; deterministic financial checks remain authoritative.

## Downloaded report design

Excel downloads open on a `Report Overview` tab with summary metrics, an audit
status, a chart, links to the schedules, and the stated demonstration assumptions.
Detailed tables have filters, frozen headers, readable number formats, status
colors and landscape print settings. The technical table retains the duplicate
manual-note source column as a hidden column; its content remains visible in the
combined `Review reason` field. Existing source sheet names, row-one headers,
values and first-sheet access remain unchanged for dashboard compatibility.
Generation times on the overview use Africa/Casablanca; provenance retains UTC.
