# Technical specification

This document specifies the interfaces of Agent Fleet as the code implements them: the REST API, the SSE
protocol, the MCP tools, the state machines, the event model and the execution lifecycle.
File paths are relative to `apps/backend/agent_fleet/` unless they start with `apps/`, `docs/` or `.`.

## 1. Conventions

- All ids are UUID strings (36 characters). `repositories/scoped.parse_id()` rejects other values with
  `validation_failed`.
- All times are UTC with a time zone offset (`database/types.py`, `UTCDateTime`).
- JSON field names use `snake_case`.
- Local mode has one fixed user and one fixed workspace:
  - user `00000000-0000-4000-8000-000000000001`
  - workspace `00000000-0000-4000-8000-000000000002`

## 2. REST API

The API is a FastAPI application (`main.py`). It listens on `AGENT_FLEET_API_HOST:AGENT_FLEET_API_PORT`
(default `127.0.0.1:8420`). FastAPI also serves its default OpenAPI pages at `/docs` and `/openapi.json`.

### 2.1 Workspace selection

Every `/api/v1/...` route that reads or writes records depends on `get_workspace_id()` (`api/deps.py`):

- Without a header, the request acts in the local workspace.
- The header `X-Agent-Fleet-Workspace: <uuid>` selects another workspace.
- An unknown workspace gives `404 not_found`. An invalid UUID gives `422 validation_failed`.

This header is **not** authentication. Any local caller can set it. See [SECURITY.md](SECURITY.md).

### 2.2 Endpoints

| Method | Path | Parameters | Response (200 unless noted) | Main errors |
|---|---|---|---|---|
| GET | `/health` | none | `{"status": "ok"}` | none |
| GET | `/api/v1/system/status` | query `refresh` (bool, default false) | `SystemStatus` | 404/422 workspace |
| GET | `/api/v1/system/providers` | query `refresh` (bool) | `ProviderStatus[]` | none |
| GET | `/api/v1/runner/status` | none | `RunnerStatusResponse` | 404/422 workspace |
| GET | `/api/v1/overview` | none | `Overview` | 404/422 workspace |
| POST | `/api/v1/integrations/claude-code/hooks` | body: any JSON object (hook payload) | `{"linked": true, "run_id": "..."}` or `{"linked": false, "reason": "..."}` | 422 body is not an object |
| POST | `/api/v1/runs` | body `RunCreate` | **201** `RunRead` | 422, 503 |
| GET | `/api/v1/runs` | query `limit`, `offset`, `status` (repeatable), `source`, `search`, `sort` | `Page[RunListItem]` | 422 |
| GET | `/api/v1/runs/{run_id}` | path `run_id` | `RunRead` | 404, 422 |
| POST | `/api/v1/runs/{run_id}/cancel` | path `run_id` | `RunRead` | 404, 409, 422 |
| POST | `/api/v1/runs/{run_id}/retry` | body `RunRetry` (`task_id?`, `web_access?`) | `RunRead` (new queued run, `retry_of_run_id` set) | 404, 422 |
| GET | `/api/v1/runs/{run_id}/snapshot` | path `run_id` | `RunSnapshot` | 404, 422 |
| GET | `/api/v1/runs/{run_id}/events` | query `limit` (default 500), `offset`, `after` (int ≥ 0, default 0), `event_type` (repeatable), `agent_id` | `Page[EventRead]` | 404, 422 |
| GET | `/api/v1/runs/{run_id}/events/stream` | query `after` (int ≥ 0); header `Last-Event-ID` | `text/event-stream` (section 3) | 404, 422 (before the stream opens) |
| GET | `/api/v1/runs/{run_id}/agents` | path `run_id` | `AgentRead[]` ordered by `created_at` | 404, 422 |
| GET | `/api/v1/runs/{run_id}/tasks` | query `status` (repeatable) | `TaskRead[]` ordered by `created_at` | 404, 422 |
| GET | `/api/v1/runs/{run_id}/messages` | query `limit` (default 200), `offset`, `agent_id` | `Page[MessageRead]` ordered by `timestamp` | 404, 422 |
| GET | `/api/v1/runs/{run_id}/approvals` | path `run_id` | `ApprovalRead[]` ordered by `created_at` | 404, 422 |
| GET | `/api/v1/agents/{agent_id}` | path `agent_id` | `AgentDetails` | 404, 422 |
| PATCH | `/api/v1/agents/{agent_id}` | body `AgentUpdate` | `AgentRead` | 404, 409, 422, 429 |
| GET | `/api/v1/tasks/{task_id}` | path `task_id` | `TaskRead` | 404, 422 |
| PATCH | `/api/v1/tasks/{task_id}` | body `TaskUpdate` | `TaskRead` | 404, 409, 422 |

Route files: `api/routes_system.py`, `api/routes_runs.py`, `api/routes_entities.py`, `api/stream.py`.

Write routes call `db.commit()` before they return. Thus a client never receives data that is not durable
(`api/deps.py`, `get_write_db`).

### 2.3 Request schemas

All schemas are in `schemas/models.py`.

**`RunCreate`** (body of `POST /api/v1/runs`)

| Field | Type | Default | Rules |
|---|---|---|---|
| `title` | string or null | null | max 200; when empty, the first line of the description (max 80 chars) is used |
| `task_description` | string | required | 1 to 20,000 chars; blank after trim is rejected |
| `execution_provider` | `claude_code_local` \| `anthropic_api` | `claude_code_local` | `anthropic_api` gives **503** `runtime_unavailable` |
| `workspace_path` | string or null | null | max 1,000; absolute; existing folder; inside an allowed root |
| `orchestrator_model` | `sonnet` \| `haiku` | `sonnet` | |
| `permission_policy` | `read_only` \| `workspace_edit` | `read_only` | `workspace_edit` needs `confirm_workspace_edit=true` and a `workspace_path` |
| `max_concurrent_agents` | int or null | null | 1 to 20; null uses `AGENT_FLEET_MAX_CONCURRENT_AGENTS` (default 4) |
| `confirm_workspace_edit` | bool | false | |

The route always sets `source = dashboard`.

**`AgentUpdate`**: `{"status": AgentStatus}`.

**`TaskUpdate`**: `{"status": TaskStatus | null, "progress_percentage": int 0–100 | null}`.
Give at least one field. Otherwise the service returns `validation_failed`.

### 2.4 Response schemas

| Schema | Fields |
|---|---|
| `Page[T]` | `items: T[]`, `total: int`, `limit: int`, `offset: int` |
| `RunRead` | `id`, `workspace_id`, `title`, `task_description`, `source`, `execution_mode`, `provider`, `root_agent_id`, `status`, `workspace_path`, `permission_policy`, `orchestrator_model`, `max_concurrent_agents`, `session_id`, `started_at`, `completed_at`, `created_at`, `updated_at`, `final_summary`, `error_message`, `attempt_count`, `cancel_requested`, `usage_json`, `event_count` |
| `RunListItem` | `RunRead` + `agent_count`, `task_count`, `message_count` |
| `AgentRead` | `id`, `run_id`, `name`, `role`, `model_alias`, `provider`, `parent_agent_id`, `status`, `current_task_id`, `external_ref`, `input_tokens`, `output_tokens`, `tool_call_count`, `started_at`, `completed_at`, `created_at` |
| `TaskRead` | `id`, `run_id`, `title`, `description`, `assigned_agent_id`, `created_by_agent_id`, `parent_task_id`, `priority`, `status`, `progress_percentage`, `result_summary`, `result_payload`, `error_message`, `created_at`, `updated_at`, `started_at`, `completed_at` |
| `MessageRead` | `id`, `run_id`, `sender_agent_id`, `receiver_agent_id`, `task_id`, `message_type`, `content`, `metadata_json`, `timestamp` |
| `EventRead` | `id`, `run_id`, `sequence_number`, `event_type`, `agent_id`, `parent_agent_id`, `task_id`, `timestamp`, `message`, `payload`, `source` |
| `ApprovalRead` | `id`, `run_id`, `requested_by_agent_id`, `action_type`, `description`, `status`, `created_at`, `resolved_at` |
| `RunSnapshot` | `run: RunRead`, `agents: AgentRead[]`, `hierarchy: HierarchyNode[]`, `tasks: TaskRead[]`, `recent_messages: MessageRead[]` (last 50, oldest first), `event_counts: {event_type: int}`, `total_events: int`, `agent_status_counts`, `task_status_counts` |
| `HierarchyNode` | `agent_id`, `name`, `children: HierarchyNode[]` (an agent whose parent is not in the run becomes a root; depth is cut at 50) |
| `AgentDetails` | `agent`, `parent`, `current_task`, `children`, `recent_messages` (last 50), `tool_events` (last 50 events with type `tool.*`), `tasks` (assigned to the agent) |
| `ProviderStatus` | `provider`, `label`, `status` (`ProviderConnectionStatus`), `message`, `local_mode_supported`, `details` |
| `RunnerRead` | `id`, `name`, `runtime_type`, `status`, `last_seen_at`, `details_json`, `online` |
| `RunnerStatusResponse` | `runners: RunnerRead[]`, `any_online`, `queued_runs`, `active_runs` |
| `IntegrationStatus` | `name`, `status`, `message`, `details` |
| `SystemStatus` | `status` (`ok` \| `degraded`), `version`, `mode` (`local`), `database` (`sqlite` \| `postgresql`), `providers`, `runner`, `integrations` |
| `Overview` | `total_runs`, `active_runs`, `total_agents`, `running_agents`, `total_tasks`, `total_messages`, `total_events`, `runs_by_status`, `latest_run_id` |

Derived values:

- `event_count` equals `runs.event_seq`. Sequence numbers have no gaps.
- A runner is `online` when its status is not `offline` and `last_seen_at` is younger than
  `max(15 s, 5 × AGENT_FLEET_RUNNER_POLL_SECONDS)` (`routes_system.runner_status`).
- `SystemStatus.status` is `ok` only when a provider is `connected` **and** a runner is online.
- `active_runs` counts runs in `planning`, `running` or `awaiting_approval` (`ACTIVE_RUN_STATUSES`).
- The Graphify entry in `integrations` checks the repository root, not a run workspace (`_graphify_status`).

### 2.5 Pagination, filters and sorting

| Rule | Value | Source |
|---|---|---|
| `limit` | 1 to 500 | `api/pagination.py` (`Limit`) |
| `offset` | ≥ 0 | `api/pagination.py` (`Offset`) |
| `total` | count of all matching rows before `limit`/`offset` | `paginate()` |
| Run `status` filter | repeat the parameter: `?status=queued&status=running` | `list_runs` |
| Run `source` filter | one of `dashboard`, `claude_code`, `api` | `list_runs` |
| Task `status` filter | repeatable; each value must be a `TaskStatus` value; an unknown value gives `422 validation_failed` | `list_tasks` |
| Run `search` | case-insensitive substring of `title`, max 200 chars | `list_runs` |
| Run `sort` | `created_at`, `updated_at`, `title`, `status`; prefix `-` for descending; default `-created_at` | `apply_sort()` |
| Unknown sort field | `422 validation_failed` | `apply_sort()` |
| Events order | always by `sequence_number` ascending | `list_events` |
| Events `after` | only events with `sequence_number > after` | `list_events` |
| Messages `agent_id` | messages where the agent is sender **or** receiver | `list_messages` |

### 2.6 Error envelope

Every error has the same shape (`api/errors.py`):

```json
{"error": {"code": "not_found", "message": "run not found", "details": {"run_id": "..."}}}
```

| HTTP status | `code` | Cause |
|---|---|---|
| 404 | `not_found` | Record missing or in another workspace (`NotFoundError`) |
| 422 | `validation_failed` | Domain validation (`ValidationFailedError`) or request validation; for request validation `details.errors` is a list of `{loc, msg, type}` |
| 409 | `invalid_transition` | State machine refused the change (`InvalidTransitionError`) |
| 409 | `conflict` | `ConflictError` (defined; no REST route raises it today) |
| 429 | `limit_exceeded` | Too many active subagents (`LimitExceededError`) |
| 503 | `runtime_unavailable` | Provider not available, for example `anthropic_api` (`RuntimeUnavailableError`) |
| any | `http_error` | Starlette HTTP errors, for example an unknown route |
| 500 | `internal_error` | Unexpected exception; the message is always "internal server error" |

One error does not use the envelope. A request with a `Host` header that is not allowed gets **HTTP 400**
with the plain-text body `Invalid host header` from Starlette's `TrustedHostMiddleware` (section 2.7).

The request log contains method, path, status and duration only. It never contains query strings or bodies
(`install_request_logging`; test `test_request_log_never_contains_query_strings`).

### 2.7 Host check and CORS

`TrustedHostMiddleware` (`main.create_app`) accepts only these `Host` values: `127.0.0.1`, `localhost`,
`[::1]`, `testserver` (the test client) and the configured `AGENT_FLEET_API_HOST`. Any other host gets HTTP
400. This blocks DNS rebinding: a web page cannot reach the local API through a domain name that resolves
to `127.0.0.1`. Test: `tests/test_review_fixes.py::test_untrusted_host_header_is_rejected`.

`CORSMiddleware` allows the origins in `AGENT_FLEET_CORS_ORIGINS`, the methods `GET`, `POST`, `PATCH`, and
the headers `Content-Type`, `Last-Event-ID`, `X-Agent-Fleet-Workspace`. Credentials are not allowed.

## 3. SSE protocol

Endpoint: `GET /api/v1/runs/{run_id}/events/stream` (`api/stream.py`).

1. The server checks the run first. A missing run gives `404` with the error envelope.
2. The start cursor is `after` (default 0). If `Last-Event-ID` is a number, the cursor is
   `max(after, Last-Event-ID)`.
3. The first frame is `retry: 2000`. A browser waits 2 seconds before it reconnects.
4. The server reads up to 500 events with `sequence_number > cursor`. It sends one frame per event:

   ```
   id: 17
   data: {"id":"...","run_id":"...","sequence_number":17,"event_type":"tool.started",...}

   ```

   `data` is one `EventRead` object as JSON.
5. When a batch had events, the server reads again at once. Otherwise it waits 0.5 seconds.
6. After 15 seconds without events, the server sends the comment `: keep-alive`.
7. When the stream is finished, the server sends:

   ```
   event: end
   data: {"run_id": "...", "last_sequence": 42}

   ```

   Then it closes the stream.
8. When the client disconnects, the loop stops.

The stream is finished only when all of these are true (`_stream_finished`):

1. The run status is terminal.
2. The cursor has reached `runs.event_seq` (all stored events were sent).
3. One of these is true:
   - the run has no `runner_device_id` (a Mode B run, or a run cancelled before a runner claimed it),
   - a `runner.disconnected` event exists for the run,
   - `completed_at` is more than `END_GRACE_SECONDS` (90 s) in the past.

Condition 3 makes the stream wait for the runner's last events. The runner writes
`execution.usage_reported`, `execution.session_ended` and `runner.disconnected` after the orchestrator
called `complete_run`, so these events reach the client before `event: end`. The 90-second grace period
ends the stream if the runner never writes `runner.disconnected` (for example after a runner crash).
Test: `tests/test_review_fixes.py::test_sse_waits_for_runner_final_events`.

Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`,
`Connection: keep-alive`.

Guarantees (test `tests/test_api.py::test_sse_replay_cursor_and_end`):

- Sequence numbers in one stream are strictly increasing with no gaps.
- A reconnect with `Last-Event-ID: N` sends events `N+1 ...` only.
- `event: end` comes after the last event that the run can produce.

## 4. Runtime abstraction

The interfaces are in `providers/base.py`.

| Type | Kind | Members |
|---|---|---|
| `ProviderHealth` | dataclass | `provider`, `label`, `status: ProviderConnectionStatus`, `message`, `local_mode_supported`, `details` |
| `ExecutionRequest` | dataclass | `run_id`, `workspace_id`, `prompt`, `cwd: Path`, `model`, `permission_policy`, `mcp_config_path`, `agents_path`, `timeout_seconds`, `max_concurrent_agents` |
| `ExecutionOutcome` | dataclass | `exit_code`, `success`, `session_id`, `result_text`, `error`, `timed_out`, `cancelled`, `usage` |
| `MessageSink` | callable | `async (dict) -> None`; called for each parsed stream message; must not raise |
| `KeepGoing` | callable | `async () -> bool`; `False` means "stop the process" |
| `ProviderHealthCheck` | Protocol | `check(*, refresh=False) -> ProviderHealth` |
| `ExecutionRuntime` | Protocol | `name`; `async execute(request, on_message, keep_going) -> ExecutionOutcome` |
| `AgentExecutor` | Protocol | `async run_agent_task(*, run_id, agent_id, task_id, model, instructions) -> dict` |
| `ModelProvider` | Protocol | `name`, `label`, `model_aliases`; `health(*, refresh=False)`; `runtime() -> ExecutionRuntime` |

## 5. MCP tools

The MCP server (`mcp/server.py`) has 13 tools. Each tool opens one write transaction. Each tool maps domain
errors to an MCP `ToolError` with the text `"<code>: <message>"`, for example
`"validation_failed: run_id is not a valid UUID"`. The MCP client receives a tool result with
`is_error = true`.

Scope rules for every tool:

- The server acts in the workspace from `AGENT_FLEET_WORKSPACE_ID` (default: the local workspace).
- In run-bound mode (`AGENT_FLEET_RUN_ID` set), every `run_id` must equal the bound run. Otherwise the tool
  fails with `not_found: this session may only access run <id>`.

| Tool | Arguments | Returns | Specific errors |
|---|---|---|---|
| `create_run` | `task_description` (str), `source` (`claude_code` \| `dashboard` \| `api`, default `claude_code`), `workspace_id` (str, optional), `title` (str, optional), `session_id` (str, optional) | `{run_id, status, created_at}` | `conflict` in run-bound mode; `not_found: cross-workspace access is not allowed` when `workspace_id` differs; `validation_failed` for empty text |
| `register_agent` | `run_id`, `name`, `role`, `model_alias`, `parent_agent_id` (optional) | `{agent_id, status}` | `validation_failed` (name/role: letters, digits, space, `.`, `_`, `-`, max 120; model alias: lower case, max 64); `invalid_transition` when the run is terminal; `limit_exceeded` |
| `update_agent_status` | `run_id`, `agent_id`, `status` (AgentStatus) | `{agent_id, status}` | `invalid_transition` for a terminal agent; `limit_exceeded` |
| `create_task` | `run_id`, `title`, `description`, `assigned_agent_id`, `parent_task_id` (optional), `priority` (`low` \| `normal` \| `high` \| `critical`, default `normal`), `created_by_agent_id` (optional) | `{task_id, status, progress_percentage}` | `not_found` for agents or tasks of another run |
| `update_task_status` | `run_id`, `task_id`, `status` (TaskStatus), `progress_percentage` (0–100, optional) | `{task_id, status, progress_percentage}` | `validation_failed` for bad progress; `invalid_transition` |
| `submit_task_result` | `run_id`, `task_id`, `agent_id`, `result_summary`, `result_payload` (object, optional) | `TaskRead` | `validation_failed` when the agent is not the assignee, the delegating agent or the root agent; `invalid_transition` when the task is `failed` or `cancelled` |
| `send_agent_message` | `run_id`, `sender_agent_id`, `content`, `message_type` (default `note`), `receiver_agent_id` (optional), `task_id` (optional) | `{message_id, timestamp}` | `validation_failed` for an unknown type |
| `append_run_event` | `run_id`, `event_type`, `message`, `agent_id` (optional), `task_id` (optional), `payload` (object, optional) | `EventRead` | `validation_failed` when `event_type` is not in `FREEFORM_EVENT_TYPES` |
| `get_run_snapshot` | `run_id` | `RunSnapshot` | `not_found` |
| `get_agent_details` | `run_id`, `agent_id` | `AgentDetails` | `not_found` |
| `complete_run` | `run_id`, `final_summary` | `{run_id, status, completed_at}` | `invalid_transition` when the run is already terminal or still `queued` |
| `fail_run` | `run_id`, `error_message` | `{run_id, status, completed_at}` | `invalid_transition` when terminal |
| `query_code_graph` | `run_id`, `command` (`query` \| `path` \| `explain`), `arguments` (list of str) | `{exit_code, outcome, output, error}` | `unavailable: ...` when the run has no `workspace_path`, Graphify is missing, the graph is missing, or the arguments are invalid |

Notes:

- `create_run` from MCP always uses `permission_policy = read_only`.
- `create_run` with `source = claude_code` creates a run in status `running` for this session.
  `source = dashboard` or `api` creates a `queued` run for the local runner.
- `register_agent` without a parent starts as `running` and becomes the run's `root_agent_id` if the run
  has none. With a parent it starts as `queued`. An agent that a hook registers never becomes the root
  agent (`AgentService.register(..., may_become_root=False)` in `services/hooks.py`).
- `submit_task_result` sets the task to `completed` and progress to 100. A task that is already
  `completed` accepts a new result and keeps its status. A `failed` or `cancelled` task refuses a result
  with `invalid_transition`.
- The runner's permission rules allow 12 of these tools. `create_run` is not in `runner/policy.py`
  `MCP_TOOLS`, and the run-bound server refuses it in any case.
- `query_code_graph` details: [GRAPHIFY_INTEGRATION.md](GRAPHIFY_INTEGRATION.md).

## 6. Database summary

Ten application tables plus `alembic_version`. Full details: [DATABASE.md](DATABASE.md).

| Table | Purpose |
|---|---|
| `users` | Local user (one seed row) |
| `workspaces` | Local workspace (one seed row); every record belongs to a workspace |
| `runs` | One orchestration run; queue and lease fields; `event_seq` counter |
| `agents` | Agents of a run; hierarchy by `parent_agent_id` |
| `tasks` | Delegated tasks and results |
| `agent_messages` | Messages between agents |
| `run_events` | Append-only event log |
| `approval_requests` | Workspace-edit confirmations |
| `runner_devices` | Local runners and heartbeats |
| `provider_connections` | Reserved for future bring-your-own-key credentials; no code writes it |

## 7. State machines

Source: `core/state_machine.py`.

### 7.1 Run

| From | Allowed targets |
|---|---|
| `queued` | `planning`, `running`, `failed`, `cancelled` |
| `planning` | `queued`, `running`, `awaiting_approval`, `completed`, `failed`, `cancelled` |
| `running` | `awaiting_approval`, `completed`, `failed`, `cancelled` |
| `awaiting_approval` | `running`, `failed`, `cancelled` |
| `completed`, `failed`, `cancelled` | none (terminal) |

```
            claim                session init
 queued ───────────► planning ──────────────► running ──► completed
   │  ▲                 │  │                     │   ├──► failed
   │  └── re-queue ─────┘  └──► completed/failed │   └──► cancelled
   │   (no session yet)        /cancelled        ▼
   └──► failed / cancelled                 awaiting_approval ──► running / failed / cancelled
```

- `planning → queued` is used only to give back a claim that never started a session
  (`RunQueue.recover()`, `RunQueue.release()`).
- A Mode B run starts directly in `running`.
- No code sets `awaiting_approval` today.
- A transition that is not in the table raises `invalid_transition` (HTTP 409).

### 7.2 Agent

Statuses: `idle`, `queued`, `running`, `waiting`, `reviewing`, `completed`, `failed`, `cancelled`.

- A non-terminal agent may move to any status.
- `completed`, `failed` and `cancelled` are terminal. A change to a different status raises
  `invalid_transition`. A change to the same status is a no-op.
- `running` and `reviewing` are "active" (`AGENT_ACTIVE`). Entering an active status checks the subagent
  limit (section 7.4).

### 7.3 Task

Statuses: `pending`, `in_progress`, `blocked`, `review`, `completed`, `failed`, `cancelled`.

- A non-terminal task may move to any status.
- `completed`, `failed` and `cancelled` are terminal, with the same rule as agents.

### 7.4 Subagent limit

`AgentService._check_capacity()` counts agents of the run that have a parent and are `running` or
`reviewing`. When this count is equal to `runs.max_concurrent_agents`, a new active subagent raises
`limit_exceeded` (HTTP 429). Agents that the runner or a hook observes are registered with
`enforce_capacity=False`. They already run, so Agent Fleet records them and does not refuse them.

### 7.5 Side effects of run end

| Call | Run | Open agents | Open tasks |
|---|---|---|---|
| `RunService.complete()` | `completed`, `final_summary` | → `completed` (payload `implicit: true`, except the root agent) | not changed |
| `RunService.fail()` | `failed`, `error_message` | → `cancelled` | → `cancelled` (`implicit: true`) |
| `RunService.cancel()` | `cancelled`, `cancel_requested = true` | → `cancelled` | → `cancelled` |

## 8. Event model

### 8.1 Event record

| Field | Meaning |
|---|---|
| `sequence_number` | Per-run number, starts at 1, no gaps |
| `event_type` | One value from `EventType` (`core/enums.py`) |
| `agent_id`, `parent_agent_id`, `task_id` | Optional references |
| `timestamp` | UTC time of the write |
| `message` | Human-readable text, redacted, max 2,000 chars |
| `payload` | JSON object, sanitized (`core/redaction.sanitize`) |
| `source` | `api`, `mcp`, `runner`, `hook` or `system` |
| `idempotency_key` | Optional; unique per run |

### 8.2 Event types

"Freeform" means that `append_run_event` accepts the type (`FREEFORM_EVENT_TYPES`).

| Event type | Written by | Freeform |
|---|---|---|
| `run.created` | `RunService.create` | no |
| `run.queued` | `RunService.create` (runner-managed runs); transition to `queued` | no |
| `run.started` | `RunService.create` (Mode B); transition from `queued`/`planning` to `running` | no |
| `run.status_changed` | `RunQueue.claim_next` (queued → planning); other transitions | no |
| `run.completed` | transition to `completed` | no |
| `run.failed` | transition to `failed` | no |
| `run.cancelled` | transition to `cancelled` | no |
| `agent.created` | `AgentService.register` | no |
| `agent.started` | `register` with an active status; first change to an active status | no |
| `agent.status_changed` | other agent changes; `close_agents` with `cancelled` | no |
| `agent.completed` | change to `completed`; `close_agents` with `completed` | no |
| `agent.failed` | change to `failed` | no |
| `agent.waiting` | change to `waiting` | **yes** |
| `task.created` | `TaskService.create` | no |
| `task.started` | first change to `in_progress` | no |
| `task.progress` | progress-only update | **yes** |
| `task.blocked` | change to `blocked` | no |
| `task.review_requested` | change to `review` | no |
| `task.completed` | change to `completed`; `submit_result` | no |
| `task.failed` | change to `failed` | no |
| `task.status_changed` | other task changes; `close_tasks` | no |
| `message.sent` | `MessageService.send` | no |
| `message.received` | only through `append_run_event` | **yes** |
| `tool.started` | stream mapper (`tool_use` block) | **yes** |
| `tool.completed` | stream mapper (`tool_result`) | **yes** |
| `tool.failed` | stream mapper (`is_error`, `permission_denied`, `permission_denials`); hook `PostToolUseFailure` | **yes** |
| `runner.connected` | `RunQueue.claim_next` | no |
| `runner.disconnected` | `RunQueue.release`; `Runner._finish` | no |
| `execution.session_started` | stream mapper (`system/init`) | no |
| `execution.session_ended` | `Runner._finish`; hook `SessionEnd` | no |
| `execution.usage_reported` | stream mapper (`result`) | no |
| `execution.notice` | stream mapper (MCP status, `api_retry`); `Runner._finish` | **yes** |
| `approval.requested` | defined; not emitted | no |
| `approval.approved` | `RunService.create` with `confirm_workspace_edit=true` | no |
| `approval.rejected` | defined; not emitted | no |

### 8.3 Redaction

`core/redaction.py` runs on every stored message, payload and result:

- Keys that look like secrets get the value `[redacted]`. The key test is case-insensitive. It matches
  `api_key`, `secret`, `password`, `passwd`, `authorization`, `cookie`, `credential`, `session_key`,
  `private_key`, and any key that ends in `token` (for example `token`, `access_token`, `accessToken`,
  `idToken`). Usage counters that end in `tokens` (for example `input_tokens`) are kept.
- Values that look like credentials become `[redacted]`: Anthropic keys (`sk-ant-...`), other `sk-...`
  keys, `Bearer ...` values, GitHub tokens (`ghp_...` and similar), JWTs (`eyJ...` with three parts),
  AWS access key ids (`AKIA...`) and Slack tokens (`xox...-...`).
- Keys `thinking`, `redacted_thinking`, `reasoning`, `signature` are removed.
- Strings are cut at 4,000 chars, lists and objects at 200 items, nesting at depth 8.

## 9. Execution lifecycle (Mode A)

| Step | What happens | Code |
|---|---|---|
| 1 | The dashboard sends `POST /api/v1/runs`. | `api/routes_runs.create_run` |
| 2 | The service validates text, model alias, provider, agent limit, workspace path and edit confirmation. | `services/runs.RunService.create`, `services/workspace_paths.py` |
| 3 | The service inserts the run as `queued`, emits `run.created`, optional `approval.approved`, `run.queued`, and the route commits. | `RunService.create` |
| 4 | The runner loop sends a heartbeat every `runner_poll_seconds` and runs recovery every 10 s. | `runner/worker.Runner.run_forever`, `tick` |
| 5 | The runner claims the oldest queued run with a conditional `UPDATE` to `planning`, sets the lease and adds 1 to `attempt_count`. It emits `runner.connected` and `run.status_changed`. | `services/queue.RunQueue.claim_next` |
| 6 | The runner detects Claude Code again. If it is not ready, the run fails with the problems text. | `Runner.execute`, `providers/claude_cli.detect` |
| 7 | The runner creates `data/runs/<run_id>/` and the working folder (`workspace_path`, or `data/workspaces/<run_id>`). | `Runner._prepare` |
| 8 | The runner registers the root agent `orchestrator` (`external_ref = "root"`). | `Runner._prepare` |
| 9 | The runner writes `mcp.json` (run-bound MCP server, `python -I -m agent_fleet.mcp`) and `agents.json` (from `.claude/agents/*.md`). | `Runner._prepare`, `runner/agent_defs.py` |
| 10 | The runner builds the orchestrator prompt with run id, root agent id, policy, limit, subagents and task. | `runner/prompt.build_prompt` |
| 11 | The runtime builds the argument list and the child environment, then starts Claude Code. It writes the prompt to stdin and closes stdin. | `providers/claude_code.build_args`, `ClaudeCodeLocalRuntime.execute`, `runner/process.start` |
| 12 | Claude Code starts the run-bound MCP server from `mcp.json`. | Claude Code |
| 13 | The runtime parses stdout as NDJSON and calls the stream mapper once per message, in its own transaction. | `runner/stream_parser.NdjsonParser`, `runner/event_mapper.StreamMapper.handle` |
| 14 | `system/init` stores `session_id`, emits `execution.session_started`, and moves the run from `planning` to `running`. | `StreamMapper._system` |
| 15 | The orchestrator registers subagents and tasks through MCP. The mapper links each `Agent` tool call to its subagent and records tools, messages and usage. | `mcp/server.py`, `StreamMapper._assistant`, `_delegate`, `_user` |
| 16 | Every 2 s, until the process exits, the runtime checks the timeout and calls `keep_going` (lease renewal). A timeout, a cancel or a lost claim stops the process tree. A runner interruption also stops it. | `ClaudeCodeLocalRuntime.execute`, `_supervise`, `RunQueue.renew_lease`, `process.kill_tree` |
| 17 | The `result` message gives usage and an estimated cost (`execution.usage_reported`) and permission denials (`tool.failed`). | `StreamMapper._result` |
| 18 | After exit, if the run still belongs to this runner, the runner emits `execution.session_ended`, completes or fails the run if it is still open, and emits `runner.disconnected`. If another runner took the run, it only emits an `execution.notice`. | `Runner._finish` |

Mode B has no runner steps. Claude Code calls the MCP tools directly, and hooks add subagent lifecycle
events (`services/hooks.py`).

<a id="provider-abstraction"></a>

## 10. Provider abstraction

Agent Fleet separates "who runs the model" from "what Agent Fleet records". The core uses only the
interfaces in section 4. The runner uses `ExecutionRuntime`. The status endpoints use the health checks in
`providers/registry.py`.

### 10.1 Implemented: local Claude Code

| Item | Value |
|---|---|
| Provider name | `claude_code_local` |
| Label | "Local Claude Code" |
| Health | `connected` when found, signed in and all required flags exist; `authentication_required` when found with all flags but not signed in; otherwise `disconnected` |
| Detection | `claude --version`, `claude --help` (checks 13 flags in `REQUIRED_FLAGS`), `claude auth status --json`; cached for 60 s; `refresh=true` forces a new check |
| Runtime | `ClaudeCodeLocalRuntime` |
| Health details | `version`, `executable`, `auth` (4 safe fields), `missing_flags`, `integration`, `commercial_mode` |

### 10.2 Designed, not implemented: Anthropic API

`providers/anthropic_api.py` holds the design. Nothing in it executes.

- Health is always `unsupported_in_local_mode` with `local_mode_supported = false`.
- `AnthropicApiProvider.runtime()` raises `RuntimeUnavailableError`.
- `RunService.create()` refuses any provider other than `claude_code_local` with HTTP 503. It never
  falls back to another provider.
- The planned design:
  1. Store credentials only as ciphertext in `provider_connections.encrypted_credentials`.
  2. Get the key-encryption key from a secret manager (for example a cloud KMS), never from the database
     or `.env`.
  3. Decrypt in memory at execution time. Call the official `anthropic` SDK (Messages API with tool use)
     through an `AgentExecutor`.
  4. Map each response to the same Agent Fleet events that the Claude Code runtime produces.
  5. Take usage from the API `usage` field. Label costs as estimates until they match the invoice.

### 10.3 How to add a provider

1. Add a value to `ProviderName` (`core/enums.py`) and a migration for the CHECK constraint.
2. Implement `ModelProvider` and `ExecutionRuntime` (or `AgentExecutor`).
3. Add its health to `providers/registry.all_providers()`.
4. Allow it in `RunService.create()` and teach the runner to select the runtime.
5. Emit the same event types as the Claude Code runtime, so the dashboard needs no change.
