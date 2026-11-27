# Starts n8n (http://localhost:5678) with the portable Node 24 it needs. Keep this window open while you use it.
# Paths match the setup in docs\phase3-automation-guide.md; change them if you installed n8n elsewhere.
$node = "$env:USERPROFILE\tools\node24"
$n8n = "$env:USERPROFILE\tools\n8n24\n8n.cmd"
$env:Path = "$node;" + $env:Path
& $n8n start
