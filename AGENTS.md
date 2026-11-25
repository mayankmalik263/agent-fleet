# Agents in Agent Fleet

Agent Fleet uses one orchestrator and four specialized subagents. The definitions are official Claude Code
subagent files in `.claude/agents/`. Interactive Claude Code sessions in this repository read them directly.
The local runner passes the same definitions to each run with `claude --agents <file>`.

| Agent | File | Model alias | Purpose | Can edit files |
|---|---|---|---|---|
| Orchestrator | (main session) | `sonnet` (selectable: `haiku`) | Plans, delegates, monitors, consolidates, publishes the final summary | Only in "Workspace edit" runs |
| Researcher | `.claude/agents/researcher.md` | `haiku` | Gathers evidence and returns sourced findings with uncertainty | No |
| Analyst | `.claude/agents/analyst.md` | `haiku` | Extracts key data, patterns and contradictions | No |
| Executor | `.claude/agents/executor.md` | `sonnet` | Produces deliverables, reports changed files and test results | Only in "Workspace edit" runs |
| Quality Reviewer | `.claude/agents/reviewer.md` | `sonnet` | Reviews results, returns a verdict and issues | No |

## Rules for every agent

- Receive one clearly scoped task. Know the run id, your agent id and your task id (prompt header lines).
- Report start, meaningful status changes and completion with the `agent-fleet` MCP tools.
- Submit a structured result with `submit_task_result`. Report failures; do not hide them.
- Do not duplicate another agent's work. Subagents do not start further subagents.
- Never put secrets or hidden reasoning into tool arguments.

## Limits

- Default: at most 4 active subagents per run (`AGENT_FLEET_MAX_CONCURRENT_AGENTS`, per run in the New Run form).
- These agents run inside your own Claude Code session and share its subscription usage and limits.
  They are not independent, separately billed model instances.
