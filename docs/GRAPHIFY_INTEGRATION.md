# Graphify integration

This document describes the optional connector between Agent Fleet and Graphify
(<https://github.com/Graphify-Labs/graphify>). The connector code is in
`apps/backend/agent_fleet/integrations/graphify.py`.

> **Status.** The connector is implemented and covered by unit tests with a fake setup
> (`tests/test_units.py::test_graphify_status_and_query_guards`). It was **not** tested with a real Graphify
> installation. Graphify is not installed on the development computer. Agent Fleet works fully without it.

## 1. Purpose

Graphify builds a knowledge graph of a code base. Agents can ask the graph questions, for example "which
module calls X", instead of reading many files. Agent Fleet lets a run's agents ask the graph of the run
workspace through one read-only MCP tool, `query_code_graph`.

## 2. Two different graphs

Agent Fleet shows two kinds of graph. Do not mix them up.

| | Agent graph | Code graph |
|---|---|---|
| What it shows | Agents of a run and who delegated to whom | Files, symbols and relations of a code base |
| Built by | Agent Fleet, from `agents.parent_agent_id` | Graphify, from the source code |
| Stored in | Agent Fleet database (`agents` table) | `<workspace>/graphify-out/graph.json` |
| Shown in | Dashboard agent network | Graphify output (`graph.html`, `GRAPH_REPORT.md`) |
| Required | Yes | No (optional) |

## 3. Ways to use Graphify

Graphify offers three access paths. Agent Fleet uses only the first.

| Path | What it is | Data location | Used by Agent Fleet |
|---|---|---|---|
| CLI `graphify` | Local commands: `graphify query`, `graphify path`, `graphify explain` | Local `graphify-out/` folder | **Yes**, through `query_code_graph` |
| Local MCP server `graphify-mcp` | Optional stdio MCP server from `graphifyy[mcp]` | Local | No. You can add it to Claude Code yourself. |
| Graphify Cloud MCP | Hosted MCP server at `https://api.graphify.com/mcp` | Stored by the hosted service | **No.** Agent Fleet never sends code there. |

## 4. Setup

These steps use the official Graphify commands. Agent Fleet never installs Graphify for you.

1. Install the Graphify CLI. The PyPI package name is `graphifyy` (two "y").

   ```powershell
   uv tool install graphifyy
   ```

2. Install the Graphify integration for Claude Code in your user configuration.

   ```powershell
   graphify install
   ```

   To install it only for one project, run this command in that project folder instead.

   ```powershell
   graphify install --project
   ```

3. Open Claude Code in the workspace folder of your run.

   ```powershell
   claude
   ```

4. Type `/graphify .` in Claude Code. Graphify writes `graphify-out/` with `graph.json`, `graph.html` and
   `GRAPH_REPORT.md`.
5. Make sure that `graphify-out/graph.json` exists in the workspace folder.
6. Add the parent folder of the workspace to `AGENT_FLEET_ALLOWED_WORKSPACE_ROOTS` in `.env`.
7. Start a run with that folder as the workspace path.

Optional: install the local Graphify MCP server, if you want Claude Code to call Graphify directly.

```powershell
uv tool install "graphifyy[mcp]"
```

The server command is `graphify-mcp`. Agent Fleet does not configure or use it.

## 5. What Agent Fleet does

### 5.1 Detection

`graphify.status(workspace)`:

1. finds `graphify` on `PATH` (`shutil.which`),
2. checks for `<workspace>/graphify-out/graph.json`,
3. returns `installed`, `executable`, `graph_path`, `graph_present` and a message.

| State | Message |
|---|---|
| CLI missing | "Graphify is not installed (optional). See docs/GRAPHIFY_INTEGRATION.md." |
| CLI found, no graph | "Graphify is installed. No graph yet: run `/graphify .` in Claude Code inside the workspace." |
| CLI and graph found | "Graphify is installed and a local graph is available." |

### 5.2 Status reporting

`GET /api/v1/system/status` contains one entry in `integrations` (`api/routes_system._graphify_status`):

| Field | Value |
|---|---|
| `name` | `graphify` |
| `status` | `available` (CLI and graph), `installed` (CLI only), `not_installed` |
| `message` | the message from section 5.1 |
| `details` | `{"optional": true, "graph_path": "..."}` |

This status checks the **repository root** of Agent Fleet (`REPO_ROOT`), not the workspace of a run. A run
workspace can have a graph while this status says `installed`, and the other way round.
`query_code_graph` always checks the run workspace.

### 5.3 The `query_code_graph` MCP tool

| Argument | Values |
|---|---|
| `run_id` | the run; in run-bound mode it must be the bound run |
| `command` | `query`, `path` or `explain` |
| `arguments` | `query`: `["question"]`; `path`: `["A", "B"]`; `explain`: `["Name"]` |

Steps (`mcp/server.py`, `graphify.run_query`):

1. Read `runs.workspace_path`. If it is empty, fail with `unavailable: this run has no workspace_path`.
2. Check that `command` is one of the three values.
3. Check each argument: a non-empty string, max 500 chars, not starting with `-`. Option-like arguments are
   refused, so an agent cannot pass Graphify options.
4. Check that the CLI and the graph exist. Otherwise fail with the status message.
5. Refuse a `.cmd` or `.bat` executable. Such shims pass arguments through `cmd.exe`.
6. Run `graphify <command> <arg1> [<arg2>]` in the workspace folder. No shell is used. The timeout is 60 s.
   The child environment has API keys removed (`child_env()`). stdin is closed.
7. Return the result.

Result:

| Field | Meaning |
|---|---|
| `exit_code` | Graphify exit code |
| `outcome` | `answer` (0), `ambiguous` (3), `no_match` (4), else `error` |
| `output` | last 20,000 chars of stdout |
| `error` | last 2,000 chars of stderr, only for an unknown exit code |

All errors reach Claude as `unavailable: <reason>`.

## 6. What Agent Fleet does not do

- It does not install, update or configure Graphify.
- It does not build the graph. You run `/graphify .` yourself.
- It does not parse code or read `graph.json` itself.
- It does not write to `graphify-out/`.
- It does not use the hosted Graphify Cloud MCP.
- It does not start `graphify-mcp`.
- It does not copy code graph data into the Agent Fleet database. Only the MCP tool call and its result
  appear as normal tool events in the run.

## 7. Privacy notes

- Graphify parses code locally with tree-sitter.
- Documents and images can go to an AI backend for analysis. Set `GRAPHIFY_BACKEND=none` if you do not want
  this. Read the Graphify documentation for the current behaviour.
- The hosted Graphify Cloud MCP stores your data on its servers. Agent Fleet does not use it.
- `query_code_graph` output can contain code text. It returns to Claude Code like any tool output. The
  runner stores at most a 500-char redacted preview of a tool result in the event log.

## 8. Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Status `not_installed` | `graphify` is not on `PATH` | Install with `uv tool install graphifyy`; restart the API so it sees the new `PATH` |
| Status `installed`, never `available` | No graph in the Agent Fleet repository root | Expected if you only built graphs in run workspaces; the tool checks the run workspace |
| `unavailable: this run has no workspace_path` | Run without a workspace | Start the run with a workspace path |
| `unavailable: Graphify is installed. No graph yet ...` | No `graphify-out/graph.json` in the workspace | Run `/graphify .` in Claude Code in that folder |
| `unavailable: Graphify resolved to a .cmd/.bat shim ...` | CLI installed through a batch shim | Install with `uv tool install graphifyy` |
| `unavailable: arguments must be 1-2 non-empty strings ...` | Empty, too long or option-like argument | Pass plain text, max 500 chars, not starting with `-` |
| `outcome: ambiguous` | Exit code 3 | Use a more exact name |
| `outcome: no_match` | Exit code 4 | Check the name or ask a broader question |
| Tool is denied in a runner session | Tool not allowed | It is allowed by default (`runner/policy.py` `MCP_TOOLS`); check your user settings for a deny rule |
