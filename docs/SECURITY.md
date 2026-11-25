# Security

This document describes the security model of Agent Fleet in local mode, the controls that the code
implements, and what a production deployment needs. The short policy is in the root `SECURITY.md`.
File paths are relative to `apps/backend/agent_fleet/` unless they start with `.`, `apps/` or `docs/`.

> **Local mode is not a production multi-tenant SaaS.** It is a development MVP for one person on one
> computer. It has no authentication. Do not expose the API or the MCP server to a network.

## 1. Scope and assumptions

Local mode assumes:

- One trusted user on one computer.
- The API listens on `127.0.0.1` only.
- The user installed and signed in to Claude Code.
- The dashboard runs on `localhost:3000`.

## 2. Threat model (local mode)

| Asset | Threat | Main controls |
|---|---|---|
| Claude credentials | Agent Fleet reads, copies or leaks them | No credential access; safe detection fields only (3.2) |
| API key billing | A run uses an API key instead of the subscription by accident | API key variables removed from the child environment (3.3) |
| Files on the computer | An agent edits or deletes files outside the intended folder | Workspace roots, read-only default, permission policy, deny list (3.4, 3.5) |
| The unattended runner session | An untrusted workspace injects hooks, MCP servers, settings or Python modules | `--strict-mcp-config`, `--setting-sources user`, `python -I` (3.6) |
| Command execution | Prompt text breaks out of an argument | Argument arrays, no shell, native binary instead of `.cmd` shim (3.7) |
| Stored data | Secrets or hidden reasoning end up in the database or logs | Redaction and sanitizing (3.8) |
| Run integrity | A runner session creates runs or writes into other runs | Run-bound MCP mode (3.9) |
| Cross-workspace data | One workspace reads another workspace's records | Scoped lookups (3.10) |
| The local API | A web page in the browser calls the API, directly or through DNS rebinding | Host header check, CORS limited to the dashboard origin (3.1) |
| Availability | A run never ends; a crashed runner leaves runs open | Timeout, leases, recovery (3.11) |

Threats that local mode does **not** address: other users or malware on the same computer, a hostile process
that calls `127.0.0.1:8420` directly, network attackers if you bind the API to another interface, and
the content that Claude Code itself sends to Anthropic.

## 3. Implemented controls

### 3.1 Network exposure

- The API binds to `AGENT_FLEET_API_HOST`, default `127.0.0.1` (`core/config.py`).
- `main.run()` logs a warning when the host is not `127.0.0.1`, `localhost` or `::1`. It does not stop.
- Starlette's `TrustedHostMiddleware` accepts only the `Host` values `127.0.0.1`, `localhost`, `[::1]`,
  `testserver` (test client) and the configured `AGENT_FLEET_API_HOST` (`main.create_app`). Another host
  gets HTTP 400 "Invalid host header". This blocks DNS rebinding: a web page cannot reach the API through
  its own domain name that resolves to `127.0.0.1`
  (test `tests/test_review_fixes.py::test_untrusted_host_header_is_rejected`).
- CORS allows only `AGENT_FLEET_CORS_ORIGINS` (default `http://localhost:3000,http://127.0.0.1:3000`), the
  methods `GET`, `POST`, `PATCH`, and no credentials (`main.create_app`).
- The MCP server supports only stdio. Another `AGENT_FLEET_MCP_TRANSPORT` value makes it exit
  (`mcp/server.main`).
- The hook relay posts only to `AGENT_FLEET_API_HOST:AGENT_FLEET_API_PORT` from settings
  (`integrations/claude_hooks.py`).

CORS does not stop a non-browser program on the same computer. Such a program can call the API.

### 3.2 Claude credential handling

Agent Fleet does not read, store, copy or log Claude credentials. It does not open Claude credential files,
tokens or cookies.

- Detection runs only `claude --version`, `claude --help` and `claude auth status --json`
  (`providers/claude_cli.detect`).
- From the auth status it keeps only `loggedIn`, `authMethod`, `apiProvider` and `subscriptionType`
  (`_SAFE_AUTH_FIELDS`). It drops email, organisation and account ids.
- Runs use the official Claude Code login of the user. Agent Fleet does not use `--bare`, because bare mode
  skips that login.
- Agent Fleet does not bundle, modify or redistribute Claude Code.

### 3.3 API key isolation

`providers/claude_cli.child_env()` removes `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` from the
environment of every Claude Code and Graphify child process. Thus runs use the subscription login.
Set `AGENT_FLEET_KEEP_API_KEY_ENV=true` only if you want API-key billing on purpose.
Test: `tests/test_runner.py::test_child_env_removes_api_keys`.

Local mode stores no API key. The `provider_connections` table is reserved and no code writes it.

### 3.4 Workspace roots

`services/workspace_paths.resolve_workspace_path()` checks every `workspace_path`:

1. The path must be absolute.
2. `Path.resolve()` follows symbolic links and removes `..`.
3. The result must be an existing folder.
4. The result must be inside `data/workspaces/` or inside a folder in `AGENT_FLEET_ALLOWED_WORKSPACE_ROOTS`.

A link or a `..` cannot escape a root (test `tests/test_services.py::test_workspace_path_cannot_escape_allowed_roots`).
A run without a workspace uses an empty folder `data/workspaces/<run_id>/`.

### 3.5 Permission policies

Every runner session gets an explicit policy (`runner/policy.py`). Details:
[EXECUTION_ENGINE.md, section 4](EXECUTION_ENGINE.md#4-permission-policies).

- `read_only` (default): tools `Read`, `Grep`, `Glob`, `Agent` (plus web tools only when
  `AGENT_FLEET_ALLOW_WEB_TOOLS=true`). Mode `dontAsk`. `Bash`, `Edit`, `Write`, `NotebookEdit` are denied.
- `workspace_edit`: adds `Edit`, `Write` and allowlisted `Bash` patterns in mode `acceptEdits`. A deny list
  blocks destructive commands such as `rm`, `git push`, `git reset`, `curl`, `Remove-Item`, and the
  file-writing options `git diff --output` and `git log --output`.
- The default Bash allowlist is `git status,git diff *,git log *`. It has no test runners, because
  `pytest`, `npm test` and similar commands run project code with your user rights. `.env.example` warns
  about this.
- Agent definition files cannot change the permission mode. `runner/agent_defs.py` never passes
  `permissionMode` to the CLI (test `tests/test_review_fixes.py::test_agent_definitions_never_pass_permission_mode`).
- `workspace_edit` needs `confirm_workspace_edit=true` and a `workspace_path` (`RunService.create`).
  The confirmation is stored as an `approved` row in `approval_requests`.
- `--permission-prompts none`: an unattended run never waits for an approval; denials are recorded as
  `tool.failed` events.
- Never used: `bypassPermissions`, `--dangerously-skip-permissions`. `child_env()` also removes
  `CLAUDE_CODE_DANGEROUSLY_SKIP_PERMISSIONS`.

Limit: Bash patterns are prefix rules of Claude Code. If you add a command such as `pytest *` to the
allowlist, the run can execute project code. Use `workspace_edit` only for folders that you trust.

For Mode B runs (inside your own Claude Code session), the run's `permission_policy` is informational only.
Your Claude Code permission settings govern that session.

### 3.6 Isolation of the unattended session from the workspace

| Option | Effect |
|---|---|
| `--strict-mcp-config` with a run-specific `--mcp-config` | The workspace `.mcp.json` cannot add MCP servers |
| `--setting-sources user` | The workspace `.claude/settings.json` cannot add hooks or permission rules |
| `python -I -m agent_fleet.mcp` | Python modules in the workspace cannot shadow the MCP SDK or inject code |

The last row fixes a real bug. Regression test:
`tests/test_runner.py::test_mcp_server_starts_from_a_hostile_workspace`.

### 3.7 Safe process execution

- Every child process uses an argument array. No code uses `shell=True` (`runner/process.py`,
  `providers/claude_cli._run`, `integrations/graphify.run_query`).
- The prompt goes to stdin, not to the command line.
- On Windows, the native `claude.exe` replaces the npm `.cmd` shim, because `cmd.exe` would parse the
  arguments (`find_executable`).
- Graphify refuses `.cmd` and `.bat` executables and refuses arguments that start with `-`.
- Each run has a timeout. A timeout or a cancel kills the whole process tree.
- A runner shutdown or an unexpected runner error also kills the process tree, so Claude Code never runs
  without supervision (`ClaudeCodeLocalRuntime.execute`).

### 3.8 Redaction of stored and logged data

`core/redaction.py` runs before data is stored:

- Values that look like credentials become `[redacted]`: `sk-ant-...`, `sk-...`, `Bearer ...`, GitHub
  tokens (`ghp_...` and similar), JWTs (`eyJ...`), AWS access key ids (`AKIA...`) and Slack tokens (`xox...`).
- Values under secret-like keys become `[redacted]`: `api_key`, `secret`, `password`, `authorization`,
  `cookie`, `credential`, `session_key`, `private_key`, and any key that ends in `token` in any letter case
  (`access_token`, `accessToken`, `idToken`). Usage counters that end in `tokens` stay visible
  (test `tests/test_review_fixes.py::test_redaction_covers_camel_case_and_common_tokens`).
- Reasoning keys (`thinking`, `redacted_thinking`, `reasoning`, `signature`) are removed.
- Size limits: strings 4,000 chars, 200 items, depth 8.

Other rules:

- The stream mapper never reads `thinking` or `redacted_thinking` blocks (`runner/event_mapper.py`).
- Tool inputs are stored only as a short summary (one key, max 300 chars). Tool outputs are stored only as a
  500-char preview.
- Some content is stored on purpose: the public assistant text of each agent (max 4,000 chars per block),
  and the first 1,500 chars of each `Agent` delegation prompt. Both are redacted first.
- Hooks send only ids and names, never tool inputs or outputs (`FORWARD_FIELDS`).
- The API request log has method, path, status and duration. It never logs query strings or bodies.
- Unexpected API errors return "internal server error" without details.

Limit: redaction is pattern-based. It cannot find every secret. Do not give secrets to agents.

### 3.9 Run-bound MCP sessions

The runner starts the MCP server with `AGENT_FLEET_RUN_ID`. In that mode:

- every tool call must name the bound run,
- `create_run` is refused,
- the runner's permission rules do not include `create_run`.

This stops a runner session from starting new runs (recursive runs) or writing into other runs.

### 3.10 Workspace scoping

All lookups use `repositories/scoped.py`. A record of another workspace is reported as "not found".
Tests: `test_workspace_isolation`, `test_workspace_header_isolation`, `test_workspace_scoping`.

This is data separation, **not** authorization. In local mode any caller can choose a workspace with the
`X-Agent-Fleet-Workspace` header or `AGENT_FLEET_WORKSPACE_ID`.

### 3.11 Availability controls

- Run timeout `AGENT_FLEET_RUN_TIMEOUT_SECONDS` (minimum 30, default 1,800).
- Leases and recovery for crashed runners (`services/queue.py`). Recovery needs an expired lease and a
  runner heartbeat older than one lease period, so a live runner never loses its runs.
- Limit of active subagents per run (`AgentService._check_capacity`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`).
- Limit of parallel runs per runner (`AGENT_FLEET_RUNNER_MAX_CONCURRENT_RUNS`, max 8).
- Input size limits: descriptions 20,000 chars, titles 200 chars, event messages 2,000 chars.
- The hook relay has a 2-second timeout and always exits 0, so it never blocks Claude Code.

### 3.12 Commercial-mode guard

The local Claude Code connector is for local development and self-hosting. Commercial use stays disabled
until the provider terms are reviewed.

- `AGENT_FLEET_COMMERCIAL_MODE` defaults to `false`.
- When it is `true`, the runner refuses to start: "The local Claude Code connector is disabled when
  AGENT_FLEET_COMMERCIAL_MODE=true." (`runner/worker.Runner.run_forever`).
- The provider health details show `commercial_mode` and the note "local development / self-hosted connector
  (not for commercial distribution)".
- The API and the MCP server do not check this flag. Only the runner, which starts Claude Code, checks it.

## 4. What local mode does not provide

- User authentication of any kind.
- Workspace authorization.
- Protected remote MCP.
- Rate limiting.
- Audit logging.
- Encryption at rest. The SQLite file and the run folders are plain files.
- Retention and deletion controls.

## 5. Production requirements

A multi-user or hosted deployment needs at least these items. None of them is implemented.

1. **Real authentication.** Replace `api/deps.get_workspace_id` with verified identities (for example
   OIDC). Remove the trust in the `X-Agent-Fleet-Workspace` header.
2. **Workspace authorization.** Check membership and roles on every request and every MCP call.
3. **Secure secret storage.** Keep provider keys only as ciphertext in `provider_connections`. Get the
   key-encryption key from a KMS or secret manager, never from the database or `.env`.
4. **Protected remote MCP.** Add an authenticated transport (for example OAuth) with TLS. Bind each session
   to a user and a workspace from the token, not from environment variables.
5. **Per-tenant isolation.** Run each tenant's executions in separate sandboxes (containers or VMs) with
   separate file systems and credentials. A shared local runner is not acceptable.
6. **Rate limiting** per user, per workspace and per endpoint, including the SSE stream.
7. **Audit logging** of every authentication, permission change, run start, approval and data export.
   The audit log must be tamper-evident and separate from `run_events`.
8. **Permission policies** that an administrator controls, with server-side approval flows. The
   `awaiting_approval` status and the approval events exist but are not used today.
9. **Encryption** in transit (TLS everywhere) and at rest (database, backups, run files).
10. **Retention and deletion.** Configurable retention for runs, events, messages and run folders, and a
    verified delete path for user requests.
11. **A production database.** PostgreSQL with tested migrations, backups and monitoring.
12. **Provider terms.** A commercial service must use a provider integration whose terms allow it (for
    example the Anthropic API with the customer's own key), not a user's local Claude Code login.

## 6. Safe use in local mode

1. Keep `AGENT_FLEET_API_HOST=127.0.0.1`.
2. Keep `read_only` unless a run must change files.
3. Add only trusted folders to `AGENT_FLEET_ALLOWED_WORKSPACE_ROOTS`.
4. Keep `AGENT_FLEET_ALLOW_WEB_TOOLS=false` unless a run needs the web.
5. Do not put secrets in task descriptions.
6. Keep `.env` out of version control (`.gitignore` already excludes it).
7. Report security problems privately to the repository owner. Do not include credentials.
