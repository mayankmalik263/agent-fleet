# MCP integration

This document describes how Claude Code talks to Agent Fleet through the Model Context Protocol (MCP), and
how Claude Code hooks add lifecycle events. The server code is in `apps/backend/agent_fleet/mcp/server.py`.

## 1. What MCP is in Agent Fleet

MCP is an **integration protocol**. Claude Code is the MCP client. Agent Fleet is an MCP server that offers
tools. When Claude calls a tool, Agent Fleet validates the arguments and writes records to its database.

MCP is **not** inference. The Agent Fleet MCP server does not call a model, does not run agents and does not
make decisions. All model work happens in Claude Code. The MCP tools only record what Claude reports.

The tools are thin adapters over the same services that the REST API uses. Thus the same validation, state
machines and workspace rules apply on both paths.

## 2. Server entry points

| Entry point | Command | Used by |
|---|---|---|
| Console script | `agent-fleet-mcp` (`agent_fleet.mcp.server:main`) | Project `.mcp.json`, user-scope registration |
| Module | `python -m agent_fleet.mcp` (`mcp/__main__.py`) | Run-bound server that the runner configures, with `-I` |

At start, `main()`:

1. configures logging to stderr,
2. reads `AGENT_FLEET_MCP_TRANSPORT` (default `stdio`) and exits if it is not `stdio`,
3. applies database migrations,
4. reads `AGENT_FLEET_WORKSPACE_ID` and `AGENT_FLEET_RUN_ID`,
5. starts the MCP server over stdio.

The server uses the official MCP Python SDK (`mcp.server.mcpserver.MCPServer`). It sends instructions to the
client that say: report real activity only, and follow the flow
`create_run → register_agent → create_task → ... → complete_run`.

## 3. Project registration (`.mcp.json`)

The repository root contains `.mcp.json`:

```json
{
  "mcpServers": {
    "agent-fleet": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--quiet", "--directory", "apps/backend", "agent-fleet-mcp"],
      "env": {}
    }
  }
}
```

Claude Code reads this file when you start `claude` in the repository folder. The `--directory` path is
relative, so start Claude Code in the repository root.

### 3.1 Approve the server once

Claude Code does not start a project MCP server until you approve it. Do these steps one time:

1. Open a terminal in the repository root.
2. Start Claude Code.

   ```powershell
   claude
   ```

3. Approve the `agent-fleet` server when Claude Code asks.
4. Type `/mcp` in the session.
5. Make sure that the list shows `agent-fleet` as connected with 13 tools.

Before approval, this command shows "Pending approval":

```powershell
claude mcp get agent-fleet
```

### 3.2 Tool permissions

`.claude/settings.json` allows all 13 tools (`mcp__agent-fleet__<tool>`), so Claude Code does not ask for
each call.

### 3.3 Use Agent Fleet from other projects

Register the server in user scope. Change the path to your clone:

```powershell
claude mcp add agent-fleet --scope user -- uv run --quiet --directory D:/Orchestrator/agent-fleet/apps/backend agent-fleet-mcp
```

A user-scope server is available in every folder. The hooks in `.claude/settings.json` apply only in this
repository.

## 4. Free mode and run-bound mode

The same server code runs in two modes. The mode depends on `AGENT_FLEET_RUN_ID`.

| Property | Free mode | Run-bound mode |
|---|---|---|
| `AGENT_FLEET_RUN_ID` | not set | the run id |
| Started by | interactive Claude Code (`.mcp.json` or user scope) | `claude -p` that the runner starts (`data/runs/<run_id>/mcp.json`) |
| Command | `uv run ... agent-fleet-mcp` | `<backend venv python> -I -m agent_fleet.mcp` |
| `create_run` | allowed | refused: `conflict: this session already belongs to run <id>; do not create runs` |
| Other tools | any run of the workspace | only the bound run; another `run_id` gives `not_found: this session may only access run <id>` |
| Purpose | Mode B: Claude records its own work | Mode A: the runner's session reports into its run |

Run-bound mode stops a runner session from creating new runs. This prevents runaway recursive runs
(test `tests/test_mcp.py::test_bound_session_is_confined_to_its_run`).

The runner writes this environment for the run-bound server (`runner/worker.py`, `Runner._prepare`):

| Variable | Value |
|---|---|
| `AGENT_FLEET_DATABASE_URL` | the runner's database URL |
| `AGENT_FLEET_WORKSPACE_ID` | the runner's workspace id |
| `AGENT_FLEET_RUN_ID` | the run id |
| `AGENT_FLEET_LOG_LEVEL` | `WARNING` |

### 4.1 Why `-I` (isolated mode)

Claude Code starts the run-bound server with the run workspace as its working folder. Without `-I`, Python
puts the current folder on `sys.path`. A workspace folder with a package named, for example, `mcp/` then
shadows the MCP SDK. It could also inject code into the server. This bug occurred in a real run.
`-I` keeps the working folder off `sys.path` and ignores `PYTHON*` environment variables.
Regression test: `tests/test_runner.py::test_mcp_server_starts_from_a_hostile_workspace`.

## 5. Workspace binding

The server acts in one workspace:

- `AGENT_FLEET_WORKSPACE_ID` selects it. The default is the local workspace
  `00000000-0000-4000-8000-000000000002`.
- Every lookup uses `repositories/scoped.py`. A record of another workspace is "not found".
- `create_run` with a `workspace_id` argument that differs from the bound workspace fails with
  `not_found: cross-workspace access is not allowed`.

The server does not check at start that the workspace exists. A wrong id makes each tool call fail with
`not_found`.

## 6. Tool reference

The full argument, return and error tables are in
[TECHNICAL_SPECIFICATION.md, section 5](TECHNICAL_SPECIFICATION.md#5-mcp-tools).

| Tool | Short description |
|---|---|
| `create_run` | Create a run. `source=claude_code` (default) starts a run for this session; `dashboard` or `api` queues it for the runner |
| `register_agent` | Register an agent. Without a parent: root, `running`. With a parent: `queued` |
| `update_agent_status` | Change an agent status; terminal statuses are final |
| `create_task` | Record a delegated task |
| `update_task_status` | Change a task status and/or progress (0–100) |
| `submit_task_result` | Store the public result and complete the task (refused for a `failed` or `cancelled` task) |
| `send_agent_message` | Record a message between agents |
| `append_run_event` | Append an observational event (only `FREEFORM_EVENT_TYPES`) |
| `get_run_snapshot` | Read the run, agents, hierarchy, tasks, recent messages and counts |
| `get_agent_details` | Read one agent with parent, children, messages, tool events, tasks |
| `complete_run` | Complete the run with a final summary |
| `fail_run` | Fail the run with an error message |
| `query_code_graph` | Optional read-only Graphify query in the run workspace |

Errors reach Claude as a tool result with `is_error = true` and the text `<code>: <message>`. Claude can
read the text and correct the call.

## 7. Hooks

Hooks let Agent Fleet see subagent lifecycle events in Mode B, also when Claude does not report them.
`.claude/settings.json` runs one relay for five hook events:

| Hook | Mode | What the relay does |
|---|---|---|
| `SessionStart` | synchronous, timeout 20 s | Prints `additionalContext` with the session id |
| `SubagentStart` | `async: true` | Sends ids and names to the API |
| `SubagentStop` | `async: true` | Sends ids and names to the API |
| `PostToolUseFailure` | `async: true` | Sends ids and the tool name to the API |
| `SessionEnd` | `async: true` | Sends the session id and reason to the API |

The relay command is `uv run --quiet --directory ${CLAUDE_PROJECT_DIR}/apps/backend agent-fleet-hook`
(`integrations/claude_hooks.py`).

### 7.1 Flow

```
SessionStart ──► agent-fleet-hook ──► stdout: {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                "additionalContext": "... session id of this session is <id> ..."}}
Claude ──► create_run(..., session_id=<id>)           (MCP; stored in runs.session_id)

SubagentStart / SubagentStop / PostToolUseFailure / SessionEnd
   └─► agent-fleet-hook ──► POST http://<API host>:<port>/api/v1/integrations/claude-code/hooks
                              body: only hook_event_name, session_id, agent_id, agent_type,
                                    tool_name, tool_use_id, reason
         └─► services/hooks.record_hook_event(): find the newest run with this session_id
```

### 7.2 What the API records

`record_hook_event()` (`services/hooks.py`) finds the newest run of the workspace with the same
`session_id`. If there is no such run, or the run is terminal, it returns `{"linked": false}` and stores
nothing.

| Hook event | Record |
|---|---|
| `SubagentStart` | Registers an agent with `external_ref = hook:<agent_id>`, name and role from `agent_type` (made safe, for example `plugin:rev` → `plugin-rev`), model `inherit`, parent = root agent, status `running`. Capacity is not enforced. The agent never becomes the run's root agent, also when the run has none yet (`may_become_root=False`). |
| `SubagentStop` | Sets that agent to `completed` |
| `PostToolUseFailure` | Emits `tool.failed` with the tool name and tool use id |
| `SessionEnd` | Emits `execution.session_ended` with the reason |

Tool inputs and outputs are never sent or stored. Repeated hook calls are idempotent
(test `tests/test_api.py::test_hook_events_attach_to_session_run`).

### 7.3 The relay never blocks Claude Code

- It reads at most 1,000,000 bytes from stdin.
- The HTTP call has a 2-second timeout.
- It ignores network and parse errors.
- It always exits with code 0.

If the API is not running, Claude Code continues and the hook events are lost.

## 8. stdout and stderr rule

The stdio transport uses stdout for JSON-RPC messages. Any other text on stdout breaks the protocol.

- `core/logging.configure_logging()` sends all log output to stderr.
- `alembic.ini` sends Alembic logs to stderr, and `migrate.py` keeps the application logging setup.
- Test `tests/test_mcp.py::test_stdout_carries_only_json_rpc` starts the server with `DEBUG` logging and
  checks that every stdout line is a JSON-RPC message.

Rule for contributors: never `print()` in code that the MCP server imports. Use `logging`.

## 9. Transport

Only the local **stdio** transport is enabled.

`main()` reads `AGENT_FLEET_MCP_TRANSPORT`. Any value other than `stdio` stops the server with the message
"Only the local stdio transport is enabled. Remote MCP needs authentication and is not enabled."

The tools are defined in `build_server(ctx)`, separate from the transport. A remote transport (for example
streamable HTTP) could reuse them. It needs these items first:

1. Real authentication of the client (for example OAuth) and per-user authorization.
2. A workspace from the authenticated identity, not from an environment variable.
3. TLS, rate limiting and audit logging.

None of these items exist today. Do not expose the MCP server to a network.

## 10. Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `claude mcp get agent-fleet` shows "Pending approval" | Project server not approved | Start `claude` in the repository root and approve `agent-fleet` |
| `/mcp` shows `agent-fleet` as failed | Python packages missing, or `uv` not on `PATH` | Run `uv sync --directory apps/backend`, then restart Claude Code |
| `/mcp` does not list `agent-fleet` | Claude Code started in another folder | Start Claude Code in the repository root, or use the user-scope registration |
| Tool error `not_found: this session may only access run ...` | Run-bound session used another run id | Use the run id from the prompt header |
| Tool error `conflict: this session already belongs to run ...` | `create_run` in a runner session | Do not call `create_run`; the run exists |
| Tool error `limit_exceeded: ...` | Too many active subagents | Wait until a subagent is `completed`, `failed` or `cancelled` |
| Tool error `invalid_transition: run is already completed` | Write after the run ended | Start a new run |
| Tool error `not_found: ...` for every call | Wrong `AGENT_FLEET_WORKSPACE_ID` | Remove the variable or set an existing workspace id |
| Hook events do not appear | API not running, or `create_run` had no `session_id` | Start the API (`pnpm dev:api`); pass the session id from the SessionStart context |
| Run-bound server fails with an import error | Old run file without `-I` | Start a new run; the runner writes a new `mcp.json` for each run |
| Server exits at once with "Only the local stdio transport is enabled" | `AGENT_FLEET_MCP_TRANSPORT` is set | Remove the variable |
| Protocol errors in Claude Code | Something writes to stdout | Remove the `print()`; log to stderr |
