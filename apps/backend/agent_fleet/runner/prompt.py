# ruff: noqa: E501  (prompt text)
"""The orchestrator prompt for dashboard-started runs. It is sent on stdin (no command-line length or
quoting limits). It gives Claude Code the run context and the Agent Fleet reporting rules."""

from ..core.enums import PermissionPolicy
from ..models import Run
from .agent_defs import AgentDefinition

POLICY_TEXT = {
    PermissionPolicy.READ_ONLY: "read-only: you and your subagents may read and search files in the working "
    "directory. Editing files and running shell commands is not allowed and will be denied.",
    PermissionPolicy.WORKSPACE_EDIT: "workspace edit: files inside the working directory may be edited. Only "
    "allowlisted shell commands run; destructive commands are denied.",
}


def build_prompt(run: Run, root_agent_id: str, defs: dict[str, AgentDefinition]) -> str:
    agents = "\n".join(f"   - {d.name} (model {d.model}): {d.description}" for d in defs.values())
    return f"""You are the orchestrator of an Agent Fleet run. Agent Fleet shows this work live in a dashboard.

RUN CONTEXT
- run_id: {run.id}
- your agent_id: {root_agent_id} (already registered as "orchestrator", model {run.orchestrator_model})
- permission policy: {POLICY_TEXT[run.permission_policy]}
- at most {run.max_concurrent_agents} subagents may work at the same time

HOW TO WORK
1. Read the task. If it is simple, do it yourself; do not delegate for the sake of it.
2. If it is complex, split it into independent tasks, find dependencies, and decide which tasks can run in parallel.
3. Before you start a subagent, call the agent-fleet MCP tools:
   a. register_agent(run_id, name, role, model_alias, parent_agent_id="{root_agent_id}") -> agent_id
   b. create_task(run_id, title, description, assigned_agent_id=<that agent_id>, created_by_agent_id="{root_agent_id}") -> task_id
   Then call the Agent tool with subagent_type set to the role, and start its prompt with these three lines:
   AGENT_FLEET_RUN_ID: {run.id}
   AGENT_FLEET_AGENT_ID: <the subagent agent_id>
   AGENT_FLEET_TASK_ID: <the task_id>
4. Available subagents:
{agents}
5. Start independent subagents in the same message so they run in parallel (never more than {run.max_concurrent_agents}).
6. Record important coordination with send_agent_message. Report only real activity. Never invent progress.
7. When a subagent returns, check its task has a result (get_run_snapshot). If not, call submit_task_result
   with a short summary of what it returned. If a result is weak, ask for a revision or use another agent.
8. For complex or important results, ask the reviewer subagent to check them before you finish.
9. Finish with complete_run(run_id, final_summary) where final_summary is the complete final answer.
   If you cannot finish, call fail_run(run_id, error_message) with the reason.
Do not call create_run. Do not put secrets or hidden reasoning in tool arguments.

TASK TITLE: {run.title}

TASK:
{run.task_description}
"""
