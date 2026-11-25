# Development

This document tells you how to set up, run, test and extend Agent Fleet.
Run all commands from the repository root unless a step says otherwise.

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Windows 10/11 with PowerShell (macOS and Linux also work) | | |
| Node.js | 22 or newer (`package.json` `engines`) | `node --version` |
| pnpm | 11 (`packageManager: pnpm@11.20.0`) | `pnpm --version` |
| Python | 3.12 (`apps/backend/.python-version`) | `python --version` |
| uv | current | `uv --version` |
| Claude Code | installed and signed in; needed only to execute runs | `claude auth status` shows `"loggedIn": true` |

Install pnpm if you do not have it:

```powershell
npm install -g pnpm
```

## 2. Setup

### 2.1 Setup script (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

The script:

1. checks `node`, `pnpm` and `uv` (it stops if one is missing),
2. checks `claude` (a warning only),
3. copies `.env.example` to `.env` if `.env` does not exist,
4. creates `data/`,
5. runs `pnpm install`,
6. runs `uv sync --directory apps/backend`,
7. runs `uv run --directory apps/backend agent-fleet-db upgrade`,
8. shows the Claude Code sign-in status.

On macOS, Linux or Git Bash, use `scripts/setup.sh`.

### 2.2 Manual setup

1. Copy the configuration file.

   ```powershell
   Copy-Item .env.example .env
   ```

2. Install the JavaScript packages.

   ```powershell
   pnpm install
   ```

3. Install the Python packages.

   ```powershell
   uv sync --directory apps/backend
   ```

4. Create the database.

   ```powershell
   uv run --directory apps/backend agent-fleet-db upgrade
   ```

The root script `setup` runs steps 2 to 4 in one command. Use `pnpm run setup`, not `pnpm setup`:
`pnpm setup` is a built-in pnpm command, and built-in commands take priority over scripts.

```powershell
pnpm run setup
```

## 3. Run

### 3.1 All components

```powershell
pnpm dev
```

This starts three processes with `concurrently -k`:

| Name | Command | Address |
|---|---|---|
| `api` | `uv run --directory apps/backend agent-fleet-api` | http://127.0.0.1:8420 (OpenAPI page at `/docs`) |
| `runner` | `uv run --directory apps/backend agent-fleet-runner` | no port |
| `web` | `pnpm --filter @agent-fleet/web dev` | http://localhost:3000 |

Press Ctrl+C to stop all three.

`scripts/dev.ps1` (and `scripts/dev.sh`) first runs the database upgrade, then `pnpm dev`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

### 3.2 One component at a time

Start the API:

```powershell
pnpm dev:api
```

Start the runner:

```powershell
pnpm dev:runner
```

Start the dashboard:

```powershell
pnpm dev:web
```

Start the MCP server by hand (normally Claude Code starts it):

```powershell
uv run --directory apps/backend agent-fleet-mcp
```

The dashboard is a Next.js app (`apps/web`, package `@agent-fleet/web`) that reads the REST API and the SSE
stream. Its scripts are `dev`, `build`, `start`, `lint`, `typecheck` and `test`.

| Part | Version |
|---|---|
| Next.js (App Router) | 16.4 |
| React | 19.3 |
| `@xyflow/react` (React Flow) | 13 |
| TanStack Query | 5 |
| Tailwind CSS | 4 |
| Icons | `lucide-react` |
| Test runner | Vitest 5 |

Two dashboard files matter when you debug live updates:

- `apps/web/lib/sse.ts`: the SSE client. It replays from `after=0`, reconnects with exponential backoff and
  `?after=<last sequence number>`, drops duplicate sequence numbers, and stops on `event: end`.
- `apps/web/lib/liveState.ts`: the live run state. The snapshot is the source of truth. New events update it
  in memory until the next (debounced) snapshot fetch.

`apps/web/CLAUDE.md` has more dashboard details.

## 4. Environment variables

The backend reads variables with the prefix `AGENT_FLEET_` from the environment and from `.env` in the
repository root (`apps/backend/agent_fleet/core/config.py`). Environment variables win over `.env`.

| Variable | Default | Rules | Purpose |
|---|---|---|---|
| `AGENT_FLEET_DATA_DIR` | `<repo>/data` | | Run files (`runs/<id>/`) and default workspaces (`workspaces/<id>/`) |
| `AGENT_FLEET_DATABASE_URL` | `sqlite:///<repo>/data/agent_fleet.sqlite3` | | Database URL; not derived from `AGENT_FLEET_DATA_DIR` |
| `AGENT_FLEET_SQLITE_BUSY_TIMEOUT_MS` | `15000` | | SQLite lock wait time |
| `AGENT_FLEET_API_HOST` | `127.0.0.1` | keep local | API bind address; also the hook relay target |
| `AGENT_FLEET_API_PORT` | `8420` | | API port |
| `AGENT_FLEET_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | comma or `;` separated | Allowed browser origins |
| `AGENT_FLEET_LOG_LEVEL` | `INFO` | | Log level (logs go to stderr) |
| `AGENT_FLEET_RUNNER_NAME` | `local-runner` | | Runner name prefix (`<name>@<host>`) |
| `AGENT_FLEET_RUNNER_POLL_SECONDS` | `2.0` | | Runner loop interval |
| `AGENT_FLEET_RUNNER_LEASE_SECONDS` | `90` | | Claim lease length |
| `AGENT_FLEET_RUNNER_MAX_CONCURRENT_RUNS` | `1` | 1–8 | Parallel runs per runner |
| `AGENT_FLEET_RUN_TIMEOUT_SECONDS` | `1800` | ≥ 30 | Maximum duration of one Claude Code session |
| `AGENT_FLEET_RUN_MAX_ATTEMPTS` | `2` | 1–5 | Claims per run before it gives up |
| `AGENT_FLEET_MAX_CONCURRENT_AGENTS` | `4` | 1–20 | Default subagent limit for a new run when the request gives no value (REST and MCP) |
| `AGENT_FLEET_CLAUDE_PATH` | empty (search `PATH`) | must be an existing file | Claude Code executable |
| `AGENT_FLEET_CLAUDE_DETECT_TIMEOUT_SECONDS` | `20.0` | | Timeout of each detection command |
| `AGENT_FLEET_ALLOWED_WORKSPACE_ROOTS` | empty | `;` or `,` separated | Folders that runs may use (besides `data/workspaces`) |
| `AGENT_FLEET_ALLOW_WEB_TOOLS` | `false` | | Add `WebSearch` and `WebFetch` to runner sessions |
| `AGENT_FLEET_EDIT_BASH_ALLOWLIST` | `git status,git diff *,git log *` | comma separated | Bash patterns for `workspace_edit` runs. Test runners (`pytest *`, `npm test *`) run project code; add them only for trusted folders |
| `AGENT_FLEET_KEEP_API_KEY_ENV` | `false` | | Keep `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` for Claude Code |
| `AGENT_FLEET_COMMERCIAL_MODE` | `false` | | `true` stops the runner |

Variables outside `config.py`:

| Variable | Read by | Purpose |
|---|---|---|
| `AGENT_FLEET_WORKSPACE_ID` | MCP server | Workspace of the server (default: the local workspace) |
| `AGENT_FLEET_RUN_ID` | MCP server | Run-bound mode |
| `AGENT_FLEET_MCP_TRANSPORT` | MCP server | Must be `stdio` (default) |
| `NEXT_PUBLIC_AGENT_FLEET_API_URL` | dashboard | API base URL (default `http://127.0.0.1:8420`) |
| `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | Claude Code | Set by the runner for each run |
| `AGENT_FLEET_REAL_CLAUDE_SMOKE` | tests | `1` enables the real smoke test |
| `FAKE_CLAUDE_SCENARIO`, `FAKE_CLAUDE_RESULT_DELAY` | tests | Control the fake Claude Code |

## 5. Tests, lint and types

### 5.1 All checks

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

The script runs these steps and lists the failed steps at the end:

1. backend lint: `ruff check agent_fleet tests`
2. backend types: `mypy`
3. backend tests: `pytest`
4. web lint
5. web types
6. web tests (Vitest)
7. web production build

### 5.2 Backend

Run the tests:

```powershell
pnpm test:backend
```

Run lint:

```powershell
uv run --directory apps/backend ruff check agent_fleet tests
```

Run the type check:

```powershell
uv run --directory apps/backend mypy
```

Run one test file:

```powershell
uv run --directory apps/backend pytest tests/test_runner.py
```

Test files:

| File | Covers |
|---|---|
| `tests/test_units.py` | NDJSON parser, redaction, state machine, hook relay, Graphify guards |
| `tests/test_services.py` | Run, agent, task, message and event services; validation; workspace isolation |
| `tests/test_api.py` | REST routes, error envelope, pagination, SSE replay, hooks, request log |
| `tests/test_mcp.py` | All 13 tools, errors, run binding, workspace scope, real stdio server |
| `tests/test_runner.py` | Runner with the fake Claude Code, queue, leases, recovery, CLI arguments, detection |
| `tests/test_review_fixes.py` | Regression tests for the review fixes (12 tests): process kill on runner shutdown, long stderr lines, unusual result text, Host header check, recovery with a live runner, task status filter, result on a cancelled task, hook root agent, no `permissionMode`, redaction patterns, SSE end timing |

The backend suite has 76 tests: 75 pass and 1 is skipped (the opt-in real Claude test, section 7).
The web suite has 49 Vitest tests.

Each test gets a new SQLite file in a temporary folder and runs all migrations (`tests/conftest.py`).
`conftest.py` sets `AGENT_FLEET_CLAUDE_PATH` to a missing file, so no test can start a real Claude by
accident.

### 5.3 Web

Run the tests:

```powershell
pnpm test:web
```

Run lint:

```powershell
pnpm --filter @agent-fleet/web lint
```

Run the type check:

```powershell
pnpm --filter @agent-fleet/web typecheck
```

Build for production:

```powershell
pnpm build
```

`pnpm lint` and `pnpm typecheck` in the root run the backend and the web checks together.

## 6. The fake Claude Code executable

`apps/backend/tests/fixtures/fake_claude.py` replaces Claude Code in tests. It never calls a model. It reads
the prompt from stdin and writes stream-json like `claude -p --output-format stream-json --verbose`.

`FAKE_CLAUDE_SCENARIO` selects the behaviour:

| Scenario | Behaviour |
|---|---|
| `e2e` (default) | Starts the real Agent Fleet MCP server from `--mcp-config` as an MCP client. Registers 4 agents, creates tasks, sends messages, submits results and completes the run. Emits matching `Agent` tool_use and tool_result messages. Waits `FAKE_CLAUDE_RESULT_DELAY` seconds before the final `result`. |
| `no_complete` | Ends with success but never calls `complete_run` |
| `malformed` | Mixes partial writes, invalid JSON, non-object JSON and unknown message types |
| `crash` | Writes `init`, writes to stderr, exits with code 3 |
| `hang` | Writes `init`, then sleeps (timeout and cancel tests) |
| `auth` | Reports an authentication `api_retry`, then an error result |

Tests start it as `[sys.executable, "tests/fixtures/fake_claude.py"]` through `Runner(claude_command=...)`.

## 7. Real smoke test (opt-in)

`tests/test_runner.py::test_real_claude_smoke` starts your installed Claude Code. It uses your subscription.
It asks Claude to reply with the single word "OK". It skips unless you enable it, and it skips when Claude Code
is not ready.

1. Set the switch in the current PowerShell session.

   ```powershell
   $env:AGENT_FLEET_REAL_CLAUDE_SMOKE="1"
   ```

2. Run the marked test.

   ```powershell
   uv run --directory apps/backend pytest -m real_claude
   ```

## 8. Extend Agent Fleet

### 8.1 Add a migration

1. Change the models in `apps/backend/agent_fleet/models/`.
2. Generate a revision in `apps/backend`.

   ```powershell
   uv run --directory apps/backend alembic revision --autogenerate -m "describe the change"
   ```

3. Read and correct the new file in `apps/backend/migrations/versions/`.
4. Apply it.

   ```powershell
   uv run --directory apps/backend agent-fleet-db upgrade
   ```

5. Run the backend tests.

More details: [DATABASE.md, section 10](DATABASE.md#10-migrations).

### 8.2 Add an event type

1. Add a member to `EventType` in `apps/backend/agent_fleet/core/enums.py`. Use the form `<area>.<verb>`.
2. Decide who may write it:
   - A state change: emit it only from the service that changes the state, with `EventService.emit()`.
   - An observation that agents may report: also add it to `FREEFORM_EVENT_TYPES`.
3. Emit it in the same transaction as the related change.
4. Give it an idempotency key if the same write can repeat (for example from the stream).
5. No migration is needed. `run_events.event_type` has no CHECK constraint.
6. Update the dashboard if it must show the type, and update the event table in
   [TECHNICAL_SPECIFICATION.md](TECHNICAL_SPECIFICATION.md#82-event-types).
7. Add a test.

### 8.3 Add an MCP tool

1. Put the business rule in a service in `apps/backend/agent_fleet/services/`, not in the tool.
2. Add a function in `build_server()` in `apps/backend/agent_fleet/mcp/server.py` with `@mcp.tool()` and
   `@_tool_errors`.
3. Call `ctx.check_run(run_id)` for every run id, so run-bound mode works.
4. Open the database with `with ctx.session() as s:`.
5. Write a clear docstring. Claude Code shows it as the tool description.
6. Return a Pydantic model or a JSON-safe dict.
7. If runner sessions may use the tool, add its name to `MCP_TOOLS` in `apps/backend/agent_fleet/runner/policy.py`.
8. If interactive sessions may use it without a prompt, add `mcp__agent-fleet__<name>` to
   `.claude/settings.json`.
9. Add the name to `ALL_TOOLS` in `apps/backend/tests/test_mcp.py` and add a test.
10. Never write to stdout in the tool. Use `logging`.

### 8.4 Add a subagent

1. Create `.claude/agents/<name>.md` with YAML front matter. Use one `key: value` per line. Give at least
   `name` and `description`. Usual keys: `model`, `disallowedTools` (comma separated), `maxTurns`.
2. Write the body as the subagent's system prompt. Tell it to read `AGENT_FLEET_RUN_ID`,
   `AGENT_FLEET_AGENT_ID` and `AGENT_FLEET_TASK_ID` from its prompt and to report with the MCP tools.
3. Put `Agent` in `disallowedTools`, so the subagent cannot start further subagents.
4. Check that the file parses. The runner reads it with `runner/agent_defs.parse_markdown()`, a simple
   parser. Lists must be on one line.
5. Update `test_agent_definitions_load_with_expected_models` in `apps/backend/tests/test_runner.py`.
6. Update the table in `AGENTS.md`.

The runner passes the new definition to every new run. The orchestrator prompt lists it automatically.

## 9. Windows notes

- **Stray processes.** If you close only a parent terminal, `agent-fleet-runner.exe` or `agent-fleet-api.exe`
  can stay alive. A stray runner keeps claiming runs. Stop it:

  ```powershell
  taskkill /IM agent-fleet-runner.exe /T /F
  ```

  Stop a stray API:

  ```powershell
  taskkill /IM agent-fleet-api.exe /T /F
  ```

- **Port 8420 in use.** A stray API holds the port. Stop it as above, or set `AGENT_FLEET_API_PORT` and
  `NEXT_PUBLIC_AGENT_FLEET_API_URL` to another port.
- **Claude Code not found.** The npm shim `claude.cmd` is bypassed in favour of
  `node_modules/@anthropic-ai/claude-code/bin/claude.exe`. If detection still fails, set
  `AGENT_FLEET_CLAUDE_PATH` to `claude.exe` in `.env`.
- **Paths in `.env`.** Use forward slashes, for example `D:/Projects`. Separate several roots with `;`.
- **Execution policy.** Run the scripts with `powershell -ExecutionPolicy Bypass -File ...`.
- **Database locks.** The API, the runner and each MCP server open the same SQLite file. Do not open it in a
  tool that holds a write lock for a long time.
- **Project MCP server.** Approve `agent-fleet` once in an interactive `claude` session
  ([MCP_INTEGRATION.md](MCP_INTEGRATION.md#31-approve-the-server-once)).

## 10. Troubleshooting

| Symptom | Action |
|---|---|
| Run stays `queued` | Start the runner (`pnpm dev:runner`). Check `GET /api/v1/runner/status`. |
| Run fails with "Claude Code is not ready" | Read the problems text. Install or update Claude Code, or run `claude auth login`. |
| "workspace_path is outside the allowed workspace roots" | Add the parent folder to `AGENT_FLEET_ALLOWED_WORKSPACE_ROOTS` and restart the API. |
| Run fails with "usage or rate limit reached" | Wait until your Claude usage limit resets. |
| Dashboard cannot reach the API | Start the API and check that port 8420 is free. |
| Tests start a real Claude | They cannot: `conftest.py` points `AGENT_FLEET_CLAUDE_PATH` to a missing file. |
