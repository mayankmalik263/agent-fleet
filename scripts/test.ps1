# Run every check: backend lint, types and tests; frontend lint, types, tests and production build.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\test.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$failed = @()

function Invoke-Step($name, [scriptblock]$command) {
    Write-Host "== $name ==" -ForegroundColor Cyan
    & $command
    if ($LASTEXITCODE -ne 0) { $script:failed += $name; Write-Host "FAILED: $name" -ForegroundColor Red }
}

Invoke-Step "backend lint" { uv run --directory apps/backend ruff check agent_fleet tests }
Invoke-Step "backend types" { uv run --directory apps/backend mypy }
Invoke-Step "backend tests" { uv run --directory apps/backend pytest }
Invoke-Step "web lint" { pnpm --filter @agent-fleet/web lint }
Invoke-Step "web types" { pnpm --filter @agent-fleet/web typecheck }
Invoke-Step "web tests" { pnpm --filter @agent-fleet/web test }
Invoke-Step "web build" { pnpm --filter @agent-fleet/web build }

if ($failed.Count -gt 0) {
    Write-Host ("Failed steps: " + ($failed -join ", ")) -ForegroundColor Red
    exit 1
}
Write-Host "All checks passed." -ForegroundColor Green
