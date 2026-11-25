# Agent Fleet

Agent Fleet is a local-first **multi-agent orchestration and observability platform**. You start a complex
task. A Claude Code orchestrator (Sonnet) delegates work to specialized subagents (Haiku and Sonnet).
Agent Fleet records every step and shows it live: which agents run, which model each one uses, who
delegated what, which tools ran, what the agents said to each other, and how the run progressed.

It uses **your installed, signed-in Claude Code** (for example with a Claude Pro subscription).
Local mode needs **no Anthropic API key**.

> Local development / self-hosted connector. Agent Fleet does not bundle, modify or redistribute Claude Code.
> Commercial use of the local Claude Code connector stays disabled until provider terms are reviewed.

## Main features

- **Two ways to start work, one data model.**
  - *Dashboard:* type a task in **New Run**. The local runner starts `claude -p` and records the session.
  - *Claude Code:* in a Claude Code session, ask Claude to use the `agent-fleet` MCP tools. The run appears
    in the dashboard because both paths write the same database and events.
- **Real observability only.** Every number comes from stored records. Missing values show "Not available".
  Cost from Claude Code is shown as a client-side estimate, never as a charge. Hidden reasoning is never stored.
- **Agent network** (React Flow), **cross-agent timeline**, **task board**, **agent inspector**, **run history**,
  live updates over **Server-Sent Events** with replay and reconnect.
- **Safe execution:** read-only by default; "Workspace edit" needs explicit confirmation; no permission bypass.
- **Optional Graphify** code-graph integration (detected, never required).

## Technology

| Part | Technology |
|---|---|
| Dashboard | Next.js (App Router), TypeScript, Tailwind CSS, React Flow (`@xyflow/react`), TanStack Query, Lucide |
| Control plane | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| MCP server | Official MCP Python SDK (`MCPServer`), stdio transport |
| Local runner | asyncio subprocess management of the official Claude Code CLI |
| Storage | SQLite in WAL mode (PostgreSQL-compatible schema) |
| Tooling | uv (Python), pnpm (Node), PowerShell scripts |

## Architecture in one picture

```
 Dashboard (Next.js :3000) ──REST/SSE──► API (FastAPI 127.0.0.1:8420) ─┐
                                                                     │  services + EventService
 Claude Code (you) ──stdio MCP──► agent-fleet MCP server ─────────────┼──► SQLite (data/agent_fleet.sqlite3)
                                                                     │
 Local runner ──claims queued runs──► claude -p (stream-json) ───────┘
                  └─ run-specific MCP config ──► agent-fleet MCP server (confined to that run)
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Requirements

- Windows 10/11 with PowerShell (macOS and Linux also work)
- Node.js 22 or newer and pnpm (`npm install -g pnpm`)
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Claude Code, installed and signed in: `claude auth status` must show `"loggedIn": true`

## Install (Windows)

```powershell
cd D:\Orchestrator\agent-fleet
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

The script checks the tools, creates `.env` from `.env.example`, installs packages, creates the database
and shows your Claude Code sign-in status.

## Run

```powershell
pnpm dev
```

This starts three processes: the API (http://127.0.0.1:8420, docs at `/docs`), the local runner, and the
dashboard (http://localhost:3000). Press Ctrl+C to stop all three.

Start the parts one by one for debugging:

```powershell
pnpm dev:api
```

```powershell
pnpm dev:runner
```

```powershell
pnpm dev:web
```

## Connect Claude Code (MCP)

The project file `.mcp.json` registers the `agent-fleet` server for Claude Code sessions in this folder.

1. Open a terminal in the repository and run `claude`.
2. Approve the `agent-fleet` server when Claude Code asks (project servers need your approval once).
3. Type `/mcp`. The list shows `agent-fleet` as connected with 13 tools.

Check from the command line:

```powershell
claude mcp get agent-fleet
```

To use Agent Fleet from **other** projects too, register it for your user (adjust the path):

```powershell
claude mcp add agent-fleet --scope user -- uv run --quiet --directory D:/Orchestrator/agent-fleet/apps/backend agent-fleet-mcp
```

More: [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md).

## Your first orchestration run

**From the dashboard:** open http://localhost:3000, click **New Run**, describe the task, keep
**Read-only**, and submit. The runner claims the run and starts Claude Code. Watch the network, the timeline
and the tasks update live. To let a run read a project folder, add its parent folder to
`AGENT_FLEET_ALLOWED_WORKSPACE_ROOTS` in `.env` and give the folder as the workspace path.

**From Claude Code:** in this repository, ask for example:

> Use the Agent Fleet tools: create a run for "Compare the README with the docs folder", delegate the
> reading to the researcher and the check to the reviewer, then complete the run.

## Tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

This runs backend lint (ruff), types (mypy) and tests (pytest), then frontend lint, types, tests (Vitest)
and the production build. The test suite never calls a real model; it uses a fake Claude Code executable.
An optional real smoke test uses your subscription and runs only when you ask for it:

```powershell
$env:AGENT_FLEET_REAL_CLAUDE_SMOKE="1"; uv run --directory apps/backend pytest -m real_claude
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Providers page shows "Claude Code was not found" | Install Claude Code, or set `AGENT_FLEET_CLAUDE_PATH` in `.env` to `claude.exe` |
| "Claude Code is not signed in" | Run `claude auth login` |
| Run stays **queued** | Start the runner (`pnpm dev:runner`); check **Providers** for the runner status |
| "workspace_path is outside the allowed workspace roots" | Add the parent folder to `AGENT_FLEET_ALLOWED_WORKSPACE_ROOTS` in `.env` |
| Run failed with "usage or rate limit reached" | Wait until your Claude usage limit resets, then start a new run |
| `/mcp` shows agent-fleet as failed | Run `uv sync --directory apps/backend`; see [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md) |
| A Python process stays alive after you stop a terminal | `taskkill /IM agent-fleet-runner.exe /T /F` (or `agent-fleet-api.exe`) |
| Dashboard says the API is unreachable | Start the API (`pnpm dev:api`) and check port 8420 is free |

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Design](docs/DESIGN.md) · [Technical specification](docs/TECHNICAL_SPECIFICATION.md)
· [Database](docs/DATABASE.md) · [MCP integration](docs/MCP_INTEGRATION.md) · [Execution engine](docs/EXECUTION_ENGINE.md)
· [Graphify](docs/GRAPHIFY_INTEGRATION.md) · [Security](docs/SECURITY.md) · [Development](docs/DEVELOPMENT.md)
· [Agents](AGENTS.md)

## Status

This is a local MVP. It is **not production-ready**: local mode has no authentication and is meant for one
user on one computer. See [docs/SECURITY.md](docs/SECURITY.md) for what production needs.
