// Test data shaped like the backend responses.
import type {
  AgentDetails,
  AgentRead,
  EventRead,
  MessageRead,
  RunListItem,
  RunRead,
  RunSnapshot,
  SystemStatus,
  TaskRead,
} from "@/lib/types";

export const RUN_ID = "run-1";
const T0 = "2026-11-24T20:00:00Z";
const at = (seconds: number) => new Date(Date.parse(T0) + seconds * 1000).toISOString();

export function makeRun(overrides: Partial<RunRead> = {}): RunRead {
  return {
    id: RUN_ID,
    workspace_id: "ws",
    title: "API audit",
    task_description: "Audit the API",
    source: "claude_code",
    execution_mode: "local_claude_code",
    provider: "claude_code_local",
    root_agent_id: "a-orch",
    status: "running",
    workspace_path: null,
    permission_policy: "read_only",
    orchestrator_model: "sonnet",
    max_concurrent_agents: 4,
    web_access: false,
    retry_of_run_id: null,
    session_id: null,
    started_at: at(0),
    completed_at: null,
    created_at: at(0),
    updated_at: at(0),
    final_summary: null,
    error_message: null,
    attempt_count: 0,
    cancel_requested: false,
    usage_json: null,
    event_count: 6,
    ...overrides,
  };
}

export function makeAgent(id: string, name: string, role: string, parent: string | null, overrides: Partial<AgentRead> = {}): AgentRead {
  return {
    id,
    run_id: RUN_ID,
    name,
    role,
    model_alias: role === "orchestrator" ? "sonnet" : "haiku",
    provider: "claude_code_local",
    parent_agent_id: parent,
    status: "running",
    current_task_id: null,
    external_ref: null,
    input_tokens: null,
    output_tokens: null,
    tool_call_count: 0,
    started_at: at(1),
    completed_at: null,
    created_at: at(1),
    ...overrides,
  };
}

export function makeTask(id: string, title: string, assignee: string, status: TaskRead["status"], overrides: Partial<TaskRead> = {}): TaskRead {
  return {
    id,
    run_id: RUN_ID,
    title,
    description: `${title} description`,
    assigned_agent_id: assignee,
    created_by_agent_id: "a-orch",
    parent_task_id: null,
    priority: "normal",
    status,
    progress_percentage: null,
    result_summary: null,
    result_payload: null,
    error_message: null,
    created_at: at(2),
    updated_at: at(3),
    started_at: null,
    completed_at: null,
    ...overrides,
  };
}

export function makeEvent(seq: number, type: string, overrides: Partial<EventRead> = {}): EventRead {
  return {
    id: `e-${seq}`,
    run_id: RUN_ID,
    sequence_number: seq,
    event_type: type,
    agent_id: null,
    parent_agent_id: null,
    task_id: null,
    timestamp: at(seq),
    message: `${type} #${seq}`,
    payload: null,
    source: "mcp",
    ...overrides,
  };
}

export const agents: AgentRead[] = [
  makeAgent("a-orch", "orchestrator", "orchestrator", null, { input_tokens: 1200, output_tokens: 300, tool_call_count: 2 }),
  makeAgent("a-res", "research-lead", "researcher", "a-orch"),
  makeAgent("a-rev", "code-reviewer", "reviewer", "a-orch", { status: "queued", started_at: null }),
];

export const tasks: TaskRead[] = [
  makeTask("t-1", "Map error paths", "a-res", "completed", { result_summary: "Found 14 paths.", completed_at: at(4), started_at: at(2) }),
  makeTask("t-2", "Classify failures", "a-res", "in_progress", { progress_percentage: 40 }),
  makeTask("t-3", "Review patch", "a-rev", "pending"),
  makeTask("t-4", "Broken step", "a-rev", "failed", { error_message: "Tool crashed" }),
];

export const messages: MessageRead[] = [
  {
    id: "m-1",
    run_id: RUN_ID,
    sender_agent_id: "a-orch",
    receiver_agent_id: "a-res",
    task_id: "t-1",
    message_type: "instruction",
    content: "Start with api/errors.py.",
    metadata_json: null,
    timestamp: at(3),
  },
];

/** Events 1..6, matching run.event_count = 6 in the snapshot. */
export const events: EventRead[] = [
  makeEvent(1, "run.created"),
  makeEvent(2, "agent.created", { agent_id: "a-orch", payload: { name: "orchestrator", role: "orchestrator", model_alias: "sonnet", status: "running" } }),
  makeEvent(3, "task.created", { agent_id: "a-orch", task_id: "t-1", payload: { assigned_agent_id: "a-res", created_by_agent_id: "a-orch" } }),
  makeEvent(4, "message.sent", { agent_id: "a-orch", task_id: "t-1", payload: { receiver_agent_id: "a-res", message_type: "instruction", message_id: "m-1" }, message: "orchestrator to research-lead: Start with api/errors.py." }),
  makeEvent(5, "tool.started", { agent_id: "a-res", payload: { tool_name: "Read" } }),
  makeEvent(6, "task.completed", { agent_id: "a-res", task_id: "t-1" }),
];

export function makeSnapshot(overrides: Partial<RunSnapshot> = {}): RunSnapshot {
  return {
    run: makeRun(),
    agents,
    hierarchy: [],
    tasks,
    recent_messages: messages,
    event_counts: { "message.sent": 1 },
    total_events: 6,
    agent_status_counts: {},
    task_status_counts: {},
    ...overrides,
  };
}

export function makeRunListItem(overrides: Partial<RunListItem> = {}): RunListItem {
  return { ...makeRun(), agent_count: 3, task_count: 4, message_count: 1, ...overrides };
}

export function makeAgentDetails(): AgentDetails {
  return {
    agent: agents[1],
    parent: agents[0],
    current_task: tasks[1],
    children: [],
    recent_messages: messages,
    tool_events: [events[4]],
    tasks: [tasks[0], tasks[1]],
  };
}

export function makeSystemStatus(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    status: "ok",
    version: "0.2.0",
    mode: "local",
    database: "sqlite",
    providers: [
      { provider: "claude_code_local", label: "Local Claude Code", status: "connected", message: "Ready.", local_mode_supported: true, details: {} },
      {
        provider: "anthropic_api",
        label: "Anthropic API (bring your own key)",
        status: "unsupported_in_local_mode",
        message: "Planned extension point.",
        local_mode_supported: false,
        details: {},
      },
    ],
    runner: { runners: [], any_online: true, queued_runs: 0, active_runs: 0 },
    integrations: [],
    ...overrides,
  };
}
