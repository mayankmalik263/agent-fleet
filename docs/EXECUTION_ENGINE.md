# Execution engine

This document describes how Agent Fleet executes a run that a person started in the dashboard (Mode A).
The local runner starts the installed Claude Code CLI, watches it, and turns its output into records.
File paths are relative to `apps/backend/agent_fleet/` unless they start with `.`, `apps/` or `docs/`.

Main code:

| File | Responsibility |
|---|---|
| `runner/main.py` | Entry point `agent-fleet-runner` |
| `runner/worker.py` | `Runner`: poll, claim, prepare, execute, finish |
| `services/queue.py` | `RunQueue`: runner registry, claims, leases, recovery |
| `providers/claude_cli.py` | Detection of Claude Code, child environment |
| `providers/claude_code.py` | `ClaudeCodeLocalRuntime`: argument list, process, stream reading, outcome |
| `runner/policy.py` | Permission policy → CLI options |
| `runner/process.py` | Start and stop the process tree |
| `runner/prompt.py` | Orchestrator prompt |
| `runner/agent_defs.py` | Subagent definitions → `--agents` file |
| `runner/stream_parser.py` | NDJSON parser |
| `runner/event_mapper.py` | `StreamMapper`: stream messages → records |

## 1. Agents

### 1.1 Parent orchestrator

The orchestrator is the main Claude Code session. It has no definition file.

| Property | Value |
|---|---|
| Model | `runs.orchestrator_model`: `sonnet` (default) or `haiku`, passed as `--model` |
| Agent record | registered by the runner before start: name `orchestrator`, role `orchestrator`, `external_ref = root` |
| Tools | set by the permission policy (section 4) |
| Instructions | the prompt from `runner/prompt.build_prompt()` |

### 1.2 Workers

The four workers are official Claude Code subagent files in `.claude/agents/`.

| Name | File | `model` | `disallowedTools` | `maxTurns` | Result payload (from its prompt) |
|---|---|---|---|---|---|
| `researcher` | `.claude/agents/researcher.md` | `haiku` | `Edit, Write, NotebookEdit, Bash, Agent` | 40 | `findings`, `uncertainties`, `open_questions` |
| `analyst` | `.claude/agents/analyst.md` | `haiku` | `Edit, Write, NotebookEdit, Bash, Agent` | 40 | `key_points`, `patterns`, `contradictions`, `confidence` |
| `executor` | `.claude/agents/executor.md` | `sonnet` | `Agent` | 80 | `deliverable`, `changed_files`, `tests`, `limitations` |
| `reviewer` | `.claude/agents/reviewer.md` | `sonnet` | `Edit, Write, NotebookEdit, Bash, Agent` | 40 | `verdict`, `issues`, `missing_requirements`, `unsupported_claims` |

No file sets `tools`. Each worker thus gets the tools of the session, minus its `disallowedTools`. The
session tools come from the run's permission policy. All workers disallow `Agent`, so a worker cannot start
further subagents.

### 1.3 How the definitions reach the CLI

One source serves both modes:

- Interactive Claude Code in this repository reads `.claude/agents/*.md` directly.
- The runner cannot rely on that, because it passes `--setting-sources user` and may run in another folder.
  Thus `runner/agent_defs.py`:
  1. parses the YAML front matter of each `.md` file (`parse_markdown`),
  2. keeps `description`, `tools`, `disallowedTools`, `model`, `maxTurns`, `effort` and the body as
     `prompt`. It never passes `permissionMode`, even when an agent file sets it. The run's permission
     policy decides, so an agent file cannot turn on a permission bypass
     (test `tests/test_review_fixes.py::test_agent_definitions_never_pass_permission_mode`),
  3. writes one JSON object to `data/runs/<run_id>/agents.json` (`agents_json`),
  4. passes the file path as `--agents data/runs/<run_id>/agents.json`.

Test: `tests/test_runner.py::test_agent_definitions_load_with_expected_models`.

## 2. Runtime process

### 2.1 Argument list

`providers/claude_code.build_args()` builds this list. It never uses a shell.

```
<claude executable>
  -p
  --output-format stream-json
  --verbose
  --model <sonnet|haiku>
  --mcp-config data/runs/<run_id>/mcp.json
  --strict-mcp-config
  --agents data/runs/<run_id>/agents.json
  --permission-prompts none
  --setting-sources user
  <policy options from runner/policy.policy_args()>
```

Why each special option is there:

| Option | Reason |
|---|---|
| `-p` (print mode) | Unattended run; one session, then exit |
| `--output-format stream-json --verbose` | Newline-delimited JSON events that the runner can parse |
| `--mcp-config` + `--strict-mcp-config` | Use only the run-bound Agent Fleet MCP server. `-p` loads the `.mcp.json` of the working folder otherwise, and an untrusted workspace could add servers. |
| `--setting-sources user` | Do not load project settings of the workspace. An untrusted repository cannot add hooks or permission rules. Your user settings still apply. |
| `--permission-prompts none` | Never wait for an approval. A denied tool appears as a `permission_denied` system message and in `permission_denials` of the result. |
| `--agents <file>` | The four worker definitions (section 1.3) |

Agent Fleet does **not** use `--bare`, because bare mode skips the subscription (OAuth) login. It never uses
`--dangerously-skip-permissions` or `bypassPermissions`
(test `tests/test_runner.py::test_cli_arguments_are_safe`).

### 2.2 Executable

`providers/claude_cli.find_executable()` selects the executable:

1. `AGENT_FLEET_CLAUDE_PATH`, if set. The file must exist.
2. `claude` on `PATH`. On Windows, if this is a `.cmd`, `.bat`, `.ps1` or extension-less shim, use
   `node_modules/@anthropic-ai/claude-code/bin/claude.exe` next to it, or `claude.exe` on `PATH`.
   A `.cmd` shim sends arguments through `cmd.exe`, which is not safe for free text.
3. `~/.local/bin/claude.exe` (Windows) or `~/.local/bin/claude`.

Before each run, the runner calls `detect()` again (`claude --version`, `claude --help`,
`claude auth status --json`). It checks that `--help` lists all 13 flags in `REQUIRED_FLAGS`.

### 2.3 Prompt on stdin

The prompt goes to stdin. The runtime writes it, then closes stdin. This avoids command-line length and
quoting limits. The prompt contains (`runner/prompt.py`):

- `run_id`, the root `agent_id`, the policy text and the subagent limit,
- the work rules: do simple tasks alone, call `register_agent` and `create_task` before each delegation,
  start the subagent prompt with `AGENT_FLEET_RUN_ID`, `AGENT_FLEET_AGENT_ID` and `AGENT_FLEET_TASK_ID`,
  start independent subagents in one message, check results with `get_run_snapshot`, finish with
  `complete_run` or `fail_run`, do not call `create_run`,
- the list of subagents with model and description,
- the task title and the task description.

### 2.4 Child environment

`providers/claude_cli.child_env()` copies the runner environment and then:

| Change | Reason |
|---|---|
| Removes `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` (unless `AGENT_FLEET_KEEP_API_KEY_ENV=true`) | The run uses your Claude subscription login, not API-key billing |
| Removes `CLAUDE_CODE_DANGEROUSLY_SKIP_PERMISSIONS` | The child never inherits a permission bypass |

`ClaudeCodeLocalRuntime.execute()` adds `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS = runs.max_concurrent_agents`.

### 2.5 Working folder and run files

| Item | Location |
|---|---|
| Working folder | `runs.workspace_path`, or `data/workspaces/<run_id>/` (an empty folder) when the run has none |
| MCP configuration | `data/runs/<run_id>/mcp.json` |
| Agent definitions | `data/runs/<run_id>/agents.json` |

### 2.6 MCP isolation

`mcp.json` starts the MCP server as `<runner python> -I -m agent_fleet.mcp` with `AGENT_FLEET_RUN_ID` set.
`-I` (isolated mode) keeps the working folder off `sys.path`. Without it, a workspace folder named `mcp/`
shadowed the MCP SDK in a real run and could inject code. Regression test:
`tests/test_runner.py::test_mcp_server_starts_from_a_hostile_workspace`. Details:
[MCP_INTEGRATION.md](MCP_INTEGRATION.md#41-why--i-isolated-mode).

### 2.7 Process start and stop

`runner/process.py`:

- `start()` uses `asyncio.create_subprocess_exec` with pipes for stdin, stdout and stderr. On Windows it sets
  `CREATE_NEW_PROCESS_GROUP`. Elsewhere it sets `start_new_session=True`.
- `kill_tree()` stops the process and its children (MCP server, tool processes). On Windows:
  `taskkill /PID <pid> /T /F`. Elsewhere: `SIGTERM` to the group, `SIGKILL` after 5 s.

`providers/claude_code.ClaudeCodeLocalRuntime` supervises the process:

- **Interruption.** `execute()` wraps the supervision in `try/except BaseException`. On any interruption
  (runner shutdown, task cancellation, an unexpected error) it runs `kill_tree()` inside `asyncio.shield()`
  and then re-raises. The shield lets the kill finish while the task is being cancelled. Claude Code thus
  never keeps running without its runner (test `tests/test_review_fixes.py::test_runner_shutdown_kills_claude_process`).
- **Watch loop.** The loop runs until the process has exited **and** the output readers are done. Every
  2 seconds it checks the timeout and calls `keep_going()`. If the readers end while the process still runs,
  the loop keeps polling the exit, so the timeout and cancel checks still work.
- **Output readers.** stdout is read in 64 KiB chunks. stderr is also read in 64 KiB chunks, not line by
  line. A very long stderr line thus cannot stop the reader (`readline()` has a 64 KiB limit). The runtime
  keeps the last 60 stderr lines, each redacted and cut at 500 chars, for error messages
  (test `tests/test_review_fixes.py::test_long_stderr_line_keeps_timeout_working`).

## 3. Delegation and hierarchy

### 3.1 Owner of a stream message

Claude Code puts `parent_tool_use_id` on the messages of a subagent. Its value is the id of the `Agent`
tool call that started the subagent. `StreamMapper._owner()` uses it:

```
message.parent_tool_use_id
   ├─ null / missing                → root agent (orchestrator)
   ├─ in mapper.delegations          → the subagent of that Agent call
   └─ unknown                        → root agent
```

Nesting works the same way, because each delegation adds one entry to `delegations`.

### 3.2 Linking an Agent tool call to an agent record

The subagent tool is `Agent` (alias `Task`; both are in `DELEGATION_TOOLS`). When the mapper sees a
`tool_use` block with one of these names, `_delegate()` runs:

1. It searches the `prompt` input for `AGENT_FLEET_AGENT_ID: <uuid>`.
2. **Marker found, agent exists in this run:** it reuses the MCP-registered agent. It sets
   `external_ref = tool:<tool_use_id>` if the field is empty. It sets the agent to `running` if it is not
   running or terminal.
3. **No marker, or unknown agent:** it registers a new agent:
   - name and role = `subagent_type` (made safe; default `general-purpose`),
   - model = the `model` input, else the model of that definition, else `inherit`,
   - parent = the owner of the message,
   - status `running`, `external_ref = tool:<tool_use_id>`, no capacity check.
4. It stores `delegations[tool_use_id] = agent id`.
5. It records an `instruction` message from the owner to the subagent. The content is the `description`
   and the first 1,500 chars of the prompt (redacted). It links the task if `AGENT_FLEET_TASK_ID: <uuid>`
   names a task of this run.

When the matching `tool_result` arrives, `_user()`:

1. emits `tool.completed` or `tool.failed`,
2. sets the subagent to `completed` or `failed` (if it is not terminal yet),
3. records a `result` message from the subagent to the owner with the first 500 chars of the output.

The marker link prevents duplicate agents. A real run confirmed this: the orchestrator (sonnet) delegated to
`researcher` (haiku) and `reviewer` (sonnet). The MCP tools registered the agents, and the mapper linked
the `Agent` calls to them. Test: `tests/test_runner.py::test_e2e_fake_claude_through_real_mcp_server`
(5 agents, no duplicates).

## 4. Permission policies

`runner/policy.policy_args()` turns `runs.permission_policy` into CLI options.
`MCP` below means the 12 rules `mcp__agent-fleet__<tool>` for every tool except `create_run`.
`web` means `WebSearch,WebFetch`, added only when `AGENT_FLEET_ALLOW_WEB_TOOLS=true`.

| Option | `read_only` (default) | `workspace_edit` |
|---|---|---|
| `--tools` | `Read,Grep,Glob,Agent[,web]` | `Read,Grep,Glob,Agent,Edit,Write,Bash[,web]` |
| `--permission-mode` | `dontAsk` | `acceptEdits` |
| `--allowedTools` | `Read,Grep,Glob,Agent[,web],MCP` | `Read,Grep,Glob,Agent,Edit,Write[,web],Bash(<pattern>)...,MCP` |
| `--disallowedTools` | `Bash,Edit,Write,NotebookEdit` | `Bash(rm *)`, `Bash(rmdir *)`, `Bash(del *)`, `Bash(git push *)`, `Bash(git reset *)`, `Bash(git clean *)`, `Bash(git checkout *)`, `Bash(curl *)`, `Bash(wget *)`, `Bash(sudo *)`, `Bash(chmod *)`, `Bash(chown *)`, `Bash(Remove-Item *)`, `Bash(format *)`, `Bash(shutdown *)`, `Bash(git diff --output*)`, `Bash(git log --output*)` |

- `dontAsk` denies anything that is not pre-approved. It never prompts.
- The Bash patterns come from `AGENT_FLEET_EDIT_BASH_ALLOWLIST`. The default is
  `git status,git diff *,git log *`. Test runners are not in the default, because commands such as
  `pytest *` or `npm test *` run project code with your user rights. `.env.example` has a warning about this.
  Add them only for folders that you trust.
- The deny list also blocks `git diff --output...` and `git log --output...`, because `--output` writes a file.
- `workspace_edit` needs `confirm_workspace_edit=true` and a `workspace_path` when the run is created
  (`RunService.create`). The service records an `approved` approval request.
- **Never used:** `bypassPermissions`, `--dangerously-skip-permissions`.

## 5. Event collection

The runtime reads stdout in chunks of 64 KiB. `NdjsonParser` splits complete lines and parses each line.
For each message, `StreamMapper.handle()` opens **one transaction**. A failure in one message rolls back only
that message and is logged. The run continues.

| Stream message | Records |
|---|---|
| `system/init` | `runs.session_id`; `execution.session_started` (model, permission mode, version, tool count, MCP servers, agents); `execution.notice` when the `agent-fleet` MCP server is not `connected`; run `planning → running` (`run.started`) |
| `system/api_retry` | `execution.notice` with attempt and error category; the category is kept for the failure message |
| `system/permission_denied` | `tool.failed` with `denied: true` |
| `system/hook_*`, `plugin_install`, `status`, `compact_boundary` | ignored (quiet subtypes) |
| other `system/<subtype>` | counted in `unknown_message_types` as `system/<subtype>` |
| `assistant`, text block | `message.sent` (type `note`) from the owner; skipped when the run is terminal |
| `assistant`, `tool_use` block | `tool.started` with a short input summary; `tool_call_count + 1`; delegation for `Agent`/`Task` (section 3) |
| `assistant`, `thinking` / `redacted_thinking` | never read, never stored |
| `assistant`, `usage` | token counts of the owner (section 6) |
| `user`, `tool_result` block | `tool.completed` or `tool.failed` with a 500-char output preview; subagent end for a delegation |
| `result` | `runs.usage_json`; `execution.usage_reported`; `tool.failed` for each entry in `permission_denials` |
| `stream_event`, `rate_limit_event`, `prompt_suggestion` | ignored |
| any other `type` | counted in `unknown_message_types` |

Real Claude Code 2.1.330 also emits the system subtypes `task_started`, `task_progress`, `task_updated` and
`task_notification`. Agent Fleet does not map them. It counts them in `unknown_message_types`, which appears
in the payload of `execution.session_ended`, and otherwise ignores them. A newer Claude Code with new message
types thus does not break a run.

## 6. Usage accounting

### 6.1 Per agent

`StreamMapper._record_usage()` reads `message.usage` of each `assistant` message:

- **Input tokens** = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
- **Output tokens** = `output_tokens`.
- One API message can arrive as several stream messages with the same `message.id`. The mapper keeps the
  **latest** value per message id. It does not add them up.
- `agents.input_tokens` and `agents.output_tokens` are the sums over all message ids of that agent.
- The owner comes from `parent_tool_use_id` (section 3.1). Subagent tokens go to the subagent.

### 6.2 Per run

The `result` message gives the run totals. `runs.usage_json` holds:

| Key | Source |
|---|---|
| `usage` | `result.usage` (sanitized) |
| `num_turns`, `duration_ms`, `duration_api_ms`, `subtype` | `result` |
| `estimated_cost_usd` | `result.total_cost_usd` |
| `cost_is_estimate` | always `true` |
| `cost_note` | "Client-side estimate from Claude Code. Not an invoice." |
| `model_usage` | `result.modelUsage` (sanitized) |

`total_cost_usd` is a client-side estimate from Claude Code. With a subscription it is not a charge.

## 7. Queue, claims, leases, recovery and retry

### 7.1 Runner loop

`Runner.run_forever()`:

1. Refuses to start when `AGENT_FLEET_COMMERCIAL_MODE=true`.
2. Detects Claude Code and registers the runner (`runner_devices`, name `<runner_name>@<host name>`).
3. Every 10 s: runs `RunQueue.recover()`.
4. Every `AGENT_FLEET_RUNNER_POLL_SECONDS` (default 2): `tick()` sends a heartbeat (`online` or `busy`) and
   claims one run if fewer than `AGENT_FLEET_RUNNER_MAX_CONCURRENT_RUNS` runs are active.
5. On stop: cancels active run tasks, marks the runner `offline`. For each active run, the runtime kills
   the Claude Code process tree and the run fails with "The runner was stopped while the run was active."

### 7.2 Claim

`RunQueue.claim_next()`:

1. Selects the oldest run with `status = queued`, `source != claude_code` and
   `attempt_count < AGENT_FLEET_RUN_MAX_ATTEMPTS`.
2. Runs `UPDATE runs SET status='planning', runner_device_id, claimed_at, lease_expires_at = now + lease,
   attempt_count = attempt_count + 1, started_at WHERE id = :id AND status = 'queued'`.
3. If the update changed 0 rows, another runner was faster. The claim returns nothing.
4. Emits `runner.connected` and `run.status_changed` (queued → planning).

Two runners can never claim the same run (test `test_two_runners_never_claim_the_same_run`). Mode B runs
are never claimed (test `test_claude_code_runs_are_never_claimed`).

### 7.3 Lease

The lease length is `AGENT_FLEET_RUNNER_LEASE_SECONDS` (default 90). While Claude Code runs, the runtime
calls `keep_going()` every 2 seconds. This calls `RunQueue.renew_lease()`:

| Run state | `renew_lease()` result | Effect |
|---|---|---|
| Run missing, or `runner_device_id` is another runner | `False` | Runtime stops the process tree |
| `cancel_requested = true` or status `cancelled` | `False` | Runtime stops the process tree |
| Status `completed` or `failed` (the orchestrator called `complete_run` / `fail_run`) | `True`, lease not extended | Claude Code keeps running and exits normally |
| Any other status | `True`, lease extended to now + lease length | Normal case |

Why a completed run keeps going: after `complete_run`, Claude Code still writes its final `result` message
with usage and the estimated cost. In a real run, an earlier version killed Claude Code right after
`complete_run`, and the usage was lost. Now the runner waits until Claude Code exits by itself. The run
timeout still applies. Regression test: `tests/test_runner.py::test_e2e_fake_claude_through_real_mcp_server`
with `FAKE_CLAUDE_RESULT_DELAY=5` (longer than the 2-second watch interval).

### 7.4 Recovery

`RunQueue.recover(skip_run_ids)` runs every 10 s in each runner. The runner passes the ids of its own active
runs as `skip_run_ids`, so it never recovers a run that it is still executing.

A run in `planning`, `running` or `awaiting_approval` is a recovery candidate only when **both** are true:

1. Its lease has expired (`lease_expires_at < now`).
2. Its runner is stale: the `runner_devices` row is missing, has no `last_seen_at`, or `last_seen_at` is
   older than one lease period (`AGENT_FLEET_RUNNER_LEASE_SECONDS`).

Thus a runner that was only paused (for example while the computer was asleep) keeps its runs. Its next
heartbeat proves that it is alive (test `tests/test_review_fixes.py::test_recover_keeps_runs_of_a_live_runner`).

| Case | Action |
|---|---|
| Candidate with status `planning`, no `session_id`, attempts left | Re-queue: `planning → queued` ("Runner lease expired before the session started; re-queued") |
| Any other candidate | Fail: "The runner stopped before the run finished (lease expired)."; open agents and tasks → `cancelled` |
| Run `queued` with `attempt_count >= AGENT_FLEET_RUN_MAX_ATTEMPTS` | Fail: "Run gave up after N attempts." |

If a runner loses a run and a new runner takes it, the first runner does not change the run any more.
When its Claude Code process ends, `Runner._finish()` only emits the `execution.notice` "A previous runner
attempt ended after it lost the run". `Runner._fail()` does nothing for a run that another runner owns.

Test: `tests/test_runner.py::test_expired_lease_recovery`.

### 7.5 Retry rule

A run is retried **only** when no Claude Code session started (`session_id` is NULL). A session can have
side effects (tool calls, file edits). Thus a run with a session is never run again.

`RunQueue.release()` implements a "give back the claim" path for start-up errors, but no code calls it
today. Start-up errors in `Runner.execute()` fail the run instead, because they need a person (for example
"Claude Code is not ready").

## 8. Concurrency limits

| Limit | Setting | Enforced by |
|---|---|---|
| Runs per runner | `AGENT_FLEET_RUNNER_MAX_CONCURRENT_RUNS` (1–8, default 1) | `Runner.tick()` |
| Active subagents per run | `runs.max_concurrent_agents` (1–20; when a request gives no value, `AGENT_FLEET_MAX_CONCURRENT_AGENTS`, default 4) | 1. `AgentService._check_capacity()` for MCP and REST status changes (HTTP 429 / `limit_exceeded`). 2. `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` in the child environment. 3. The prompt text. |
| Run duration | `AGENT_FLEET_RUN_TIMEOUT_SECONDS` (≥ 30, default 1,800) | `ClaudeCodeLocalRuntime.execute()` |

Agents that the runner sees only in the stream, or that hooks report, are recorded without a capacity
check. They already run. Agent Fleet records them and does not refuse them.

The subagents run inside your own Claude Code session. They share its subscription usage and limits.

## 9. Failure handling

| Failure | Detection | Run result | User message (`runs.error_message`) | Code |
|---|---|---|---|---|
| Claude Code not installed | `detect()`: no executable | `failed` | "Claude Code is not ready. Claude Code was not found. Install it ... or set AGENT_FLEET_CLAUDE_PATH ..." | `claude_cli.detect`, `Runner.execute` |
| Claude Code too old | `--help` lacks a required flag | `failed` | "... lacks options Agent Fleet needs: ... Run `claude update`." | `claude_cli.detect` |
| Not signed in (before start) | `auth status` has `loggedIn: false` | `failed` | "... Claude Code is not signed in. Run `claude auth login` ..." | `claude_cli.detect` |
| Not signed in / account blocked (during run) | `api_retry` error in `authentication_failed`, `oauth_org_not_allowed`, `account_on_hold` | `failed` | "Claude Code is not signed in or the account cannot be used. Run `claude auth login`." | `worker.explain_failure` |
| MCP server failed or missing | `system/init` lists `agent-fleet` with a status other than `connected`, or not at all | run continues | `execution.notice` "Agent Fleet MCP server status in Claude Code: <status>" | `StreamMapper._system` |
| Invalid MCP configuration | Claude Code exits non-zero without a result | `failed` | "Claude Code exited with code N without a result. <stderr tail>" | `ClaudeCodeLocalRuntime._error_text` |
| Model not available | `api_retry` error `model_not_found` | `failed` | "The selected model is not available for this Claude account." | `explain_failure` |
| Rate or usage limit | `api_retry` error `rate_limit` | `failed` | "Claude usage or rate limit reached. Wait for the limit to reset, then start a new run." | `explain_failure` |
| Billing problem | `api_retry` error `billing_error` | `failed` | "Claude reported a billing problem for this account." | `explain_failure` |
| Error result | `result.is_error` or `subtype != success` | `failed` | "Claude Code ended with '<subtype>'. <text>" | `_error_text` |
| Timeout | deadline passed (checked every 2 s until the process exits, also when the output readers stopped early) | `failed`; process tree killed | "Claude Code did not finish within N seconds and was stopped." | `_supervise`, `kill_tree` |
| Crash | non-zero exit and no `result` | `failed` | "Claude Code exited with code N without a result. <last 8 stderr lines>" | `_error_text` |
| Process cannot start | `OSError` | `failed` | "Claude Code could not be started: <reason>" | `Runner.execute` |
| Cancel | `POST /runs/{id}/cancel` sets `cancelled` at once; next `renew_lease()` returns `False` | `cancelled`; process tree killed | none (`run.cancelled` event message "Cancelled by the user") | `RunService.cancel`, `renew_lease` |
| Runner stopped | `asyncio.CancelledError` | `failed`; process tree killed (`asyncio.shield(kill_tree)`) | "The runner was stopped while the run was active." | `ClaudeCodeLocalRuntime.execute`, `Runner.execute` |
| Runner crashed | lease expired **and** no runner heartbeat for one lease period | re-queued or `failed` (section 7.4) | "The runner stopped before the run finished (lease expired)." | `RunQueue.recover` |
| Run taken by another runner | `runs.runner_device_id` is no longer this runner | not changed by this runner | `execution.notice` "A previous runner attempt ended after it lost the run" | `Runner._finish`, `Runner._fail` |
| Very long, blank or whitespace-only result text | successful `result` | `completed` | none; the summary is stripped, a blank text becomes "Claude Code finished without a final text result.", and a long text is cut to fit the 20,000-char limit | `Runner._finish` |
| Database write fails for one stream message | exception in `StreamMapper.handle` | run continues; that message's records are rolled back and logged | none | `StreamMapper.handle` |
| Database write fails when the runner marks a failure | exception in `Runner._fail` | logged; the run stays open until recovery (see note below) | "... (lease expired)." | `Runner._fail`, `recover` |
| Malformed JSON line | `json.JSONDecodeError` or non-object JSON | run continues | count in `parse_issues` of `execution.session_ended` | `NdjsonParser`, `note_parse_issue` |
| Line longer than 32 MiB | buffer limit | line dropped; run continues | count in `parse_issues` | `NdjsonParser.feed` |
| Unknown message type or system subtype | not in the mapping | run continues | count in `unknown_message_types` | `StreamMapper.handle`, `_system` |
| Other runner error | any exception | `failed` | "Runner error: <redacted text>" | `Runner.execute` |

Each run that ends after the process exits, and that this runner still owns, gets
`execution.session_ended` with `exit_code`, `timed_out`, `cancelled`, `parse_issues` and
`unknown_message_types`, then `runner.disconnected`.

Note on the last row: recovery needs a stale runner heartbeat (section 7.4). While the runner that failed
to write keeps running, its heartbeat stays fresh, so recovery does not touch the run. The run is repaired
after that runner stops for one lease period.

Tests in `tests/test_runner.py`: `test_process_crash_fails_run`, `test_authentication_error_is_explained`,
`test_timeout_stops_process_and_fails_run`, `test_cancellation_stops_process`,
`test_not_ready_claude_fails_with_setup_message`, `test_malformed_and_unknown_stream_lines_are_tolerated`.
Tests in `tests/test_review_fixes.py`: `test_runner_shutdown_kills_claude_process`,
`test_long_stderr_line_keeps_timeout_working`, `test_successful_run_with_unusual_result_text_completes`,
`test_recover_keeps_runs_of_a_live_runner`.

## 10. How the runner decides the final run status

`Runner._finish()` runs after Claude Code exits. First it checks ownership. If `runs.runner_device_id` is no
longer this runner, it emits only an `execution.notice` and stops (section 7.4).

The runtime sets `success` only when **all** of these are true (`ClaudeCodeLocalRuntime._supervise`):

- no timeout and no cancel,
- exit code 0,
- a `result` message exists,
- `result.is_error` is false,
- `result.subtype` is `success`.

Then:

| Run status at exit | `success` | Action |
|---|---|---|
| open (`planning` or `running`) | true | The orchestrator did not call `complete_run`. Complete the run with `result.result` as `final_summary`. The text is stripped. A blank text becomes "Claude Code finished without a final text result.". A long text is redacted and cut to 19,900 chars plus a truncation note, so it fits the 20,000-char limit. Emit `execution.notice` "The orchestrator did not call complete_run; the final Claude Code result was used". |
| open | false | Fail the run with the message from section 9. |
| `completed` | false, not cancelled | Keep `completed`. Emit `execution.notice` "The run was completed by the orchestrator, but the Claude Code process ended with an error: ...". |
| any other terminal status | any | Do not change the status. |

Rules that follow from this:

- The runner never completes a run when the process failed, timed out, was cancelled, or gave no successful
  `result`.
- The runner never changes a terminal status.
- When a run completes, open agents are closed as `completed` with `implicit: true` in the event payload
  (except the root agent). The dashboard can thus show that the agent did not report its own end.
- `RunService.complete()` does **not** close open tasks. A task that never got a result keeps its status
  (for example `pending` or `in_progress`) in a completed run. It is not marked as completed.
- After a run is terminal, the mapper stops writing assistant text, new delegations and subagent status
  changes. It still writes tool events and the usage report.
