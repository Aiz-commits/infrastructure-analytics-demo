# Demo fixes prepared for review

Base repository: Aiz-commits/infrastructure-analytics-demo
Base commit: cf60efd32b3ba1a28b3e285f68c0925fa4bcfed7

This package changes only the public synthetic demo. It does not contain or claim
to fix the separate Excelium STD project. No GitHub commit, push or deployment was
performed while preparing these changes.

## Corrected behavior

- Missing balances, duplicates, conflicting/missing source identity, mixed projects,
  invalid files and gaps cannot produce an overall batch pass.
- Current cumulative = previous cumulative + current works is checked per statement.
- Decimal arithmetic continues through continuity comparisons and declared identities.
- DP sheets after cover sheets are detected; preview selection is used for single-file
  extraction. Ambiguous summary sheets require explicit selection.
- Filename numbers are bounded and cross-checked against source identities. Adjacent
  gap checks avoid allocating a potentially enormous statement-number range.
- Numeric values, workbook archives, worksheets, previews and upload batches are bounded.
- Unknown and missing status labels never produce a saved-report pass.
- All six reports are regenerated from the bundled statements and an explicit synthetic
  technical CSV. The unsupported 20,000 DH continuity alert is removed.
- Report metadata and a manifest track source/rule/artifact hashes and generation time.
  Stale or missing reports fail safely without blocking session-only upload analysis.
- Demonstration retention/VAT/base/cap/tolerance/contract settings are explicit.
  Formula cache limitations and unsupported negative corrections are explained.
- Generator imports perform no writes. No uploaded document is persisted by app code.
- Pinned dependencies, a runtime lock, Python version declaration, tests and CI are added.
- Deprecated width arguments, obsolete extraction messages and fixed D1–D4 filtering are removed.

## Verification

59 automated tests passed in a clean Python 3.12 environment installed from the runtime
lock and pinned development requirements. pip check found no broken requirements.

Chromium checks passed for all five pages, report download, single upload, selecting a
DP summary after a cover sheet, four-statement continuity, and rejection of misleading
success for missing previous balances and duplicate statement numbers. No captured
JavaScript errors occurred. These browser checks used a local server and synthetic data.

The runtime vulnerability scan found no known vulnerabilities in the audited versions.
This is a point-in-time advisory check, not a security certification.

## Use

See README.md for installation, tests and report regeneration commands. Python 3.12–3.14 is
supported. Existing bundled source statements were preserved. Do not reuse this public
demo for confidential records without a separate authorization and retention design.

The included patch is intended for the exact base commit above. Apply on a separate
branch and review before merging; a merge to a watched Streamlit branch may deploy.

## Python 3.14 deployment recovery

The earlier pandas 2.2.3 pin lacked a CPython 3.14 wheel and caused the existing
Streamlit deployment to attempt a source build. Pandas is now pinned to 3.1.1,
which supplies CPython 3.14 wheels. The runtime lock is regenerated and CI tests
binary-only runtime installation on both Python 3.12 and 3.14. Existing app URLs
and financial rules are preserved; creating another Streamlit app is unnecessary.
