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
- **Repository:** public at https://github.com/mayankmalik263/agent-fleet (MIT license, branch `master`,
  tags `v0.1.0` = milestone-1 prototype, `v0.2.0` = local MVP).
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
  - Read-only policy: `--tools Read,Grep,Glob,Agent` (+ `WebSearch,WebFetch` when the run has `web_access`), `dontAsk`. Workspace edit: `acceptEdits`, Bash allowlist,
    destructive commands denied, needs dashboard confirmation. Never `bypassPermissions`.
  - Agent hierarchy comes from `parent_tool_use_id` of the Agent tool, linked to MCP-registered agents by the
    `AGENT_FLEET_AGENT_ID` marker. Thinking blocks are never stored.
  - The runner's Claude session gets `AGENT_FLEET_RUN_ID`: its MCP tools are confined to that run.
    The run MCP server starts with `python -I` so workspace files cannot shadow modules.
  - The lease check stops Claude Code only on cancel or lost ownership; a run completed via MCP exits normally.
  - The API rejects non-local Host headers (DNS rebinding). The SSE stream ends after `runner.disconnected`.
  - Runs have `web_access` (New Run form, default on; API default `AGENT_FLEET_ALLOW_WEB_TOOLS`) and
    `retry_of_run_id`. `POST /runs/{id}/retry` (optional `task_id`) queues a new run; a session cannot resume.
  - The runner sets `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`: subagents run in the foreground, so the
    orchestrator gets their results and the dashboard sees their real end.
  - The prompt asks for `final_summary` as a full Markdown report (summary, findings, sources, gaps).
  - Migrations on SQLite run with `PRAGMA foreign_keys=OFF` (set in `migrations/env.py`): a batch table
    rebuild with checks on cascade-deletes child rows. `foreign_key_check` runs before commit.
  - Dashboard: Panel B has "Story" (default, plain sentences) and "Lanes" views; Panel D "Final Report".
- **Checks:** backend ruff, mypy, 84 pytest tests (83 pass, 1 opt-in real test skipped); web lint,
  typecheck, 60 Vitest tests, production build. Real Claude Code runs: three on 2026-11-24/25, plus the
  web-research retry `ef58a8db` on 2026-11-25.

## Change log

- 2026-11-25 — Fixed the failed "MCP research papers" run (`3803a288`). Causes: no web tools; Claude Code
  started subagents in the background, so their "Async agent launched" result closed them too early.
  Added per-run `web_access`, foreground subagents, the retry endpoint (run or task), report rules in the
  prompt and migration `0002`. Dashboard: Panel B Story view, Panel D Final Report, Retry run / task, web
  toggle in New Run. Migration `0002` first cascade-deleted all agents, tasks, messages and events of the
  local database; they were restored from the WAL (backup in `D:\Orchestrator\af-recovery`), and
  `migrations/env.py` now turns foreign keys off for migrations. Tests: `test_research_fixes.py`,
  `test_migrations.py`, `apps/web/tests/report.test.tsx`. Committed as 7 commits and pushed. Subagent results now drop Claude Code hand-back
  metadata (`clean_subagent_result`). Real retry run `ef58a8db` completed with web research (about 33 papers).

- 2026-11-25 — Published the repository on GitHub (public, MIT, topics, tags v0.1.0 and v0.2.0). Fixed the
  README contents links (heading emoji changed the anchors). Files: README.md, CLAUDE.md. Why: user request.
- 2026-11-25 — Rewrote README.md as the public project page (diagrams, screenshots, usage, API, security,
  roadmap). Added the MIT LICENSE and production-build screenshots in docs/images/. Why: publish on GitHub.
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

- `next dev` listens on all network interfaces (it prints a Network URL). The API stays on 127.0.0.1.
- Retry starts a new run; it cannot reuse the results of tasks that already succeeded.
- `D:\Orchestrator\af-recovery` holds database backups from the recovery; delete it when no longer needed.

- If a live runner cannot write to the database when it fails a run, recovery waits until its heartbeat is stale.
- `pnpm setup` runs pnpm's own built-in command; use `scripts\setup.ps1` or `pnpm run setup`.
- Approvals beyond the workspace-edit confirmation (`awaiting_approval`, `approval.requested`) are modelled but not used.
- The Graphify integration is untested with a real Graphify installation (not installed here).
- Dashboard: no browser end-to-end tests; graph nodes cannot open the inspector with the keyboard.
- The Anthropic API (BYOK) provider is a documented design only; it does not execute.
- Concurrency limits for subagents are enforced for MCP-registered agents and passed to Claude Code
  (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`); agents seen only in the stream are recorded, not refused.
- Local mode has no authentication. Do not expose the API beyond 127.0.0.1 (see `docs/SECURITY.md`).
