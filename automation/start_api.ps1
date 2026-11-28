# Starts the AI Controller API (Phase 3) on port 8000. Keep this window open while you use it.
# Needs: .streamlit\secrets.toml with AGENT_API_KEY, REVIEWER_PIN, ALLOWED_SENDERS, REVIEW_BASE_URL (see docs\phase3-automation-guide.md).
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& "$root\.venv\Scripts\python.exe" -m uvicorn api.main:app --host 0.0.0.0 --port 8000
