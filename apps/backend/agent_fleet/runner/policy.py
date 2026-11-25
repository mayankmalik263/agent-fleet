"""Turn a run's permission policy into Claude Code CLI options.

Read-only (default): built-in tools limited to Read/Grep/Glob/Agent, mode dontAsk (anything not
pre-approved is denied, never prompted). Workspace edit (needs dashboard confirmation): adds Edit/Write
and an explicit Bash allowlist in acceptEdits mode; destructive commands are denied.
`--permission-prompts none` makes sure an unattended run never waits for an approval.
Never used: --dangerously-skip-permissions, bypassPermissions.
"""

from ..core.config import Settings
from ..core.enums import PermissionPolicy

MCP_SERVER_NAME = "agent-fleet"
MCP_TOOLS = (
    "register_agent",
    "update_agent_status",
    "create_task",
    "update_task_status",
    "submit_task_result",
    "send_agent_message",
    "append_run_event",
    "get_run_snapshot",
    "get_agent_details",
    "complete_run",
    "fail_run",
    "query_code_graph",
)
READ_TOOLS = ("Read", "Grep", "Glob", "Agent")
WEB_TOOLS = ("WebSearch", "WebFetch")
EDIT_TOOLS = ("Edit", "Write", "Bash")
DENY_ALWAYS_READ_ONLY = ("Bash", "Edit", "Write", "NotebookEdit")
DENY_DESTRUCTIVE = (
    "Bash(rm *)",
    "Bash(rmdir *)",
    "Bash(del *)",
    "Bash(git push *)",
    "Bash(git reset *)",
    "Bash(git clean *)",
    "Bash(git checkout *)",
    "Bash(curl *)",
    "Bash(wget *)",
    "Bash(sudo *)",
    "Bash(chmod *)",
    "Bash(chown *)",
    "Bash(Remove-Item *)",
    "Bash(format *)",
    "Bash(shutdown *)",
    "Bash(git diff --output*)",
    "Bash(git log --output*)",
)


def mcp_tool_rules() -> list[str]:
    return [f"mcp__{MCP_SERVER_NAME}__{name}" for name in MCP_TOOLS]


def policy_args(policy: PermissionPolicy, settings: Settings, *, web_access: bool | None = None) -> list[str]:
    allow_web = settings.allow_web_tools if web_access is None else web_access
    web = list(WEB_TOOLS) if allow_web else []
    if policy == PermissionPolicy.READ_ONLY:
        tools = [*READ_TOOLS, *web]
        allowed = [*tools, *mcp_tool_rules()]
        return [
            "--tools",
            ",".join(tools),
            "--permission-mode",
            "dontAsk",
            "--allowedTools",
            ",".join(allowed),
            "--disallowedTools",
            ",".join(DENY_ALWAYS_READ_ONLY),
        ]
    tools = [*READ_TOOLS, *EDIT_TOOLS, *web]
    bash_rules = [f"Bash({pattern})" for pattern in settings.edit_bash_patterns]
    allowed = [*READ_TOOLS, "Edit", "Write", *web, *bash_rules, *mcp_tool_rules()]
    return [
        "--tools",
        ",".join(tools),
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        ",".join(allowed),
        "--disallowedTools",
        ",".join(DENY_DESTRUCTIVE),
    ]
