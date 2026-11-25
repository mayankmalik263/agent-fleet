#!/usr/bin/env bash
# Agent Fleet setup for macOS, Linux and Git Bash.
set -euo pipefail
cd "$(dirname "$0")/.."

for tool in node pnpm uv; do
  command -v "$tool" >/dev/null || { echo "MISSING: $tool"; exit 1; }
  echo "ok: $tool $($tool --version | head -1)"
done
command -v claude >/dev/null && echo "ok: claude $(claude --version)" || echo "Claude Code not found (needed to execute runs)."

[ -f .env ] || { cp .env.example .env; echo "Created .env from .env.example"; }
mkdir -p data
pnpm install
uv sync --directory apps/backend
uv run --directory apps/backend agent-fleet-db upgrade
command -v claude >/dev/null && claude auth status --text || true
echo "Setup complete. Start everything with: pnpm dev"
