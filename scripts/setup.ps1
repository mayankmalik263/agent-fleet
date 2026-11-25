# Agent Fleet setup for Windows PowerShell.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Test-Tool($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host "MISSING: $name. $hint" -ForegroundColor Red
        return $false
    }
    Write-Host ("ok: {0} {1}" -f $name, (& $name --version 2>$null | Select-Object -First 1))
    return $true
}

Write-Host "== Checking tools ==" -ForegroundColor Cyan
$ok = $true
$ok = (Test-Tool "node" "Install Node.js 22 or newer from https://nodejs.org") -and $ok
$ok = (Test-Tool "pnpm" "Run: npm install -g pnpm") -and $ok
$ok = (Test-Tool "uv" "Install uv: https://docs.astral.sh/uv/getting-started/installation/") -and $ok
if (-not $ok) { exit 1 }
$claudeFound = Test-Tool "claude" "Install Claude Code: https://code.claude.com/docs/en/setup (needed to execute runs)"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}
New-Item -ItemType Directory -Force "data" | Out-Null

Write-Host "== Installing JavaScript packages ==" -ForegroundColor Cyan
pnpm install
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== Installing Python packages ==" -ForegroundColor Cyan
uv sync --directory apps/backend
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== Creating / upgrading the database ==" -ForegroundColor Cyan
uv run --directory apps/backend agent-fleet-db upgrade
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($claudeFound) {
    Write-Host "== Claude Code sign-in status ==" -ForegroundColor Cyan
    $status = claude auth status --json 2>$null | ConvertFrom-Json
    if ($status.loggedIn) {
        Write-Host ("Signed in ({0}, {1})." -f $status.authMethod, $status.subscriptionType) -ForegroundColor Green
    } else {
        Write-Host "Claude Code is not signed in. Run: claude auth login" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Setup complete. Start everything with: pnpm dev" -ForegroundColor Green
Write-Host "Dashboard: http://localhost:3000   API: http://127.0.0.1:8420/docs"
