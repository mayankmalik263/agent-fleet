# Start the API, the local runner and the dashboard together (Ctrl+C stops all three).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
uv run --directory apps/backend agent-fleet-db upgrade
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
pnpm dev
exit $LASTEXITCODE
