#!/usr/bin/env bash
# Start the API, the local runner and the dashboard together (Ctrl+C stops all three).
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --directory apps/backend agent-fleet-db upgrade
exec pnpm dev
