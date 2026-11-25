# Agent Fleet — project instructions

## Using the Agent Fleet MCP tools (orchestration)

The `agent-fleet` MCP server (see `.mcp.json`) records multi-agent work. The dashboard shows it live.
Report real activity only. Do not invent progress, counts or results.

When the user asks you to run or record an orchestration:

1. Call `create_run(task_description, source="claude_code", session_id=<your session id>)`.
   A SessionStart hook gives you the session id. Skip this step if you already have a run_id.
2. Register yourself: `register_agent(run_id, name="orchestrator", role="orchestrator", model_alias=<your model alias>)`.
3. For simple requests, do the work yourself. Do not delegate only to make the graph bigger.
4. For complex requests, split the work into independent tasks. For each subagent:
   - `register_agent(..., parent_agent_id=<your agent_id>)`, then `create_task(..., assigned_agent_id=<its id>)`.
   - Start the subagent with the Agent tool (`researcher`, `analyst`, `executor` or `reviewer`, see `.claude/agents/`).
   - Put these lines at the top of its prompt: `AGENT_FLEET_RUN_ID: ...`, `AGENT_FLEET_AGENT_ID: ...`, `AGENT_FLEET_TASK_ID: ...`.
   - Start independent subagents in the same message. Keep at most 4 active at the same time.
5. Record coordination with `send_agent_message`. Report progress percentages only when you can measure them.
6. Make sure every task has a result (`submit_task_result`). Ask the reviewer to check important results.
7. Finish with `complete_run(run_id, final_summary)`, or `fail_run(run_id, error_message)`.
8. Never put secrets or hidden reasoning in tool arguments.

## Current state

- **What it is:** Agent Fleet, a local-first multi-agent orchestration and observability platform (MVP).
- **Stack:** Python 3.12 + uv (FastAPI 0.165, SQLAlchemy 2.1, Alembic 1.20, Pydantic 2, MCP SDK 2.3), SQLite (WAL);
  dashboard in `apps/web`: Next.js 16.4, React 19.3, @xyflow/react 13, TanStack Query 5, Tailwind 4, Vitest 5
  (pnpm 11, Node 22+). `apps/web/CLAUDE.md` has the dashboard details.
- **Run everything:** `pnpm dev` (API on 127.0.0.1:8420, runner, dashboard on localhost:3000).
  Setup: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`. All checks: `scripts\test.ps1`.
- **Main folders:**
  - `apps/backend/agent_fleet/` — `core/` (config, enums, errors, state machine, redaction), `models/` (ORM),
    `database/` (engine, migrations runner), `repositories/` (workspace-scoped lookups), `services/`
    (runs, agents, tasks, messages, events, queue, hooks), `api/` (REST + SSE), `mcp/` (stdio MCP server),
    `runner/` (worker, stream parser, event mapper, prompt, policy, process), `providers/` (interfaces,
    Claude Code detection and runtime, Anthropic API design stub), `integrations/` (Graphify, hook relay).
  - `apps/backend/migrations/` — Alembic. `apps/backend/tests/` — pytest (fake Claude CLI in `tests/fixtures`).
  - `apps/web/` — dashboard (`app/` routes, `features/` panels, `lib/` API client, SSE client, layout, timeline).
  - `.claude/agents/` — subagent definitions. `docs/` — 9 documents (architecture, design, spec, database, MCP,
    execution engine, Graphify, security, development).
  - `legacy/milestone1/` — the first milestone (single-file MCP store), kept for reference only.
- **Decisions:**
  - REST API, MCP server and runner share one service layer. EventService is the only writer of run_events
    (per-run sequence numbers, idempotency keys). SSE polls persisted events (works across processes).
  - SQLite: write sessions use `BEGIN IMMEDIATE`, read sessions `BEGIN DEFERRED`.
  - Runner: database queue with conditional-UPDATE claims, leases, recovery, retry only before a session
    starts. Claude Code runs as `claude -p --output-format stream-json --verbose --model <alias>
    --mcp-config <run file> --strict-mcp-config --agents <run file> --permission-prompts none
    --setting-sources user` plus policy flags. Prompt goes on stdin. API keys are removed from the child env.
  - Read-only policy: `--tools Read,Grep,Glob,Agent`, `dontAsk`. Workspace edit: `acceptEdits`, Bash allowlist,
    destructive commands denied, needs dashboard confirmation. Never `bypassPermissions`.
  - Agent hierarchy comes from `parent_tool_use_id` of the Agent tool, linked to MCP-registered agents by the
    `AGENT_FLEET_AGENT_ID` marker. Thinking blocks are never stored.
  - The runner's Claude session gets `AGENT_FLEET_RUN_ID`: its MCP tools are confined to that run.
    The run MCP server starts with `python -I` so workspace files cannot shadow modules.
  - The lease check stops Claude Code only on cancel or lost ownership; a run completed via MCP exits normally.
  - The API rejects non-local Host headers (DNS rebinding). The SSE stream ends after `runner.disconnected`.
- **Checks:** `scripts\test.ps1` passes: backend ruff, mypy, 75 pytest tests (1 opt-in real test skipped);
  web lint, typecheck, 49 Vitest tests, production build. Three real Claude Code runs completed on 2026-11-25.

## Change log

- 2026-11-25 — Fixed 13 findings of an independent backend review (process kill on runner shutdown, stderr
  reader limit, long/blank result text, Host header check, lease recovery and run ownership, safer Bash allowlist,
  SSE end timing, typed task filter, result on cancelled task, hook root agent, permissionMode pass-through,
  redaction patterns) plus the agent-limit default. Tests: `tests/test_review_fixes.py`. Added `docs/DESIGN.md`.
- 2026-11-25 — Real Claude Code tests found and fixed two bugs: workspace `mcp/` folder shadowed the MCP SDK
  (now `python -I`), and the runner killed Claude Code after `complete_run` (lost usage). Regression tests added.
- 2026-11-25 — Built the full MVP: monorepo (`apps/backend`, `apps/web`), relational schema with Alembic,
  services, REST API + SSE, 13 MCP tools, local runner with Claude Code runtime, 4 subagent definitions,
  hooks, Graphify adapter, scripts and docs. Moved milestone-1 code to `legacy/milestone1/`. Why: the
  user's MVP specification.
- 2026-11-19 — Milestone 1: single MCP server with `runs` / `run_events` in SQLite (now in `legacy/`).

## Open items

- If a live runner cannot write to the database when it fails a run, recovery waits until its heartbeat is stale.
- `pnpm setup` runs pnpm's own built-in command; use `scripts\setup.ps1` or `pnpm run setup`.
- Approvals beyond the workspace-edit confirmation (`awaiting_approval`, `approval.requested`) are modelled but not used.
- The Graphify integration is untested with a real Graphify installation (not installed here).
- Dashboard: no browser end-to-end tests; graph nodes cannot open the inspector with the keyboard.
- The Anthropic API (BYOK) provider is a documented design only; it does not execute.
- Concurrency limits for subagents are enforced for MCP-registered agents and passed to Claude Code
  (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`); agents seen only in the stream are recorded, not refused.
- Local mode has no authentication. Do not expose the API beyond 127.0.0.1 (see `docs/SECURITY.md`).
