// Live run state: the last snapshot plus the events that arrived after it.
// The snapshot is the source of truth. Newer events update it in memory until the next snapshot fetch.
import { isRunTerminalEvent, payloadNumber, payloadString } from "./events";
import {
  AGENT_TERMINAL,
  RUN_TERMINAL,
  TASK_TERMINAL,
  type AgentRead,
  type AgentStatus,
  type EventRead,
  type RunRead,
  type RunSnapshot,
  type RunStatus,
  type TaskRead,
  type TaskStatus,
} from "./types";

export interface LiveRunState {
  run: RunRead;
  agents: AgentRead[];
  tasks: TaskRead[];
  /** Number of message.sent events: snapshot count plus newer events. */
  messageCount: number;
  /** Highest known sequence number. */
  eventCount: number;
  /** True when the run is terminal. Active indicators stop. */
  ended: boolean;
}

const AGENT_STATUSES: readonly AgentStatus[] = [
  "idle", "queued", "running", "waiting", "reviewing", "completed", "failed", "cancelled",
];
const TASK_STATUSES: readonly TaskStatus[] = [
  "pending", "in_progress", "blocked", "review", "completed", "failed", "cancelled",
];
const RUN_STATUSES: readonly RunStatus[] = [
  "queued", "planning", "running", "awaiting_approval", "completed", "failed", "cancelled",
];

function pick<T extends string>(value: string | null, allowed: readonly T[]): T | null {
  return value && (allowed as readonly string[]).includes(value) ? (value as T) : null;
}

const AGENT_TYPE_STATUS: Record<string, AgentStatus> = {
  "agent.started": "running",
  "agent.completed": "completed",
  "agent.failed": "failed",
  "agent.waiting": "waiting",
};

const TASK_TYPE_STATUS: Record<string, TaskStatus> = {
  "task.started": "in_progress",
  "task.blocked": "blocked",
  "task.review_requested": "review",
  "task.completed": "completed",
  "task.failed": "failed",
};

const RUN_TYPE_STATUS: Record<string, RunStatus> = {
  "run.started": "running",
  "run.queued": "queued",
  "run.completed": "completed",
  "run.failed": "failed",
  "run.cancelled": "cancelled",
};

function placeholderAgent(event: EventRead): AgentRead | null {
  if (!event.agent_id) return null;
  return {
    id: event.agent_id,
    run_id: event.run_id,
    name: payloadString(event, "name") ?? `agent-${event.agent_id.slice(0, 6)}`,
    role: payloadString(event, "role") ?? "agent",
    model_alias: payloadString(event, "model_alias") ?? "unknown",
    provider: "",
    parent_agent_id: event.parent_agent_id,
    status: pick(payloadString(event, "status"), AGENT_STATUSES) ?? "queued",
    current_task_id: null,
    external_ref: null,
    input_tokens: null,
    output_tokens: null,
    tool_call_count: 0,
    started_at: null,
    completed_at: null,
    created_at: event.timestamp,
  };
}

function placeholderTask(event: EventRead): TaskRead | null {
  if (!event.task_id) return null;
  return {
    id: event.task_id,
    run_id: event.run_id,
    // The real title arrives with the next snapshot. The event summary is a safe stand-in.
    title: event.message,
    description: "",
    assigned_agent_id: payloadString(event, "assigned_agent_id"),
    created_by_agent_id: payloadString(event, "created_by_agent_id") ?? event.agent_id,
    parent_task_id: payloadString(event, "parent_task_id"),
    priority: "normal",
    status: "pending",
    progress_percentage: null,
    result_summary: null,
    result_payload: null,
    error_message: null,
    created_at: event.timestamp,
    updated_at: event.timestamp,
    started_at: null,
    completed_at: null,
  };
}

/** Apply events that are newer than the snapshot. Pure function: inputs are not changed. */
export function applyEvents(snapshot: RunSnapshot, events: readonly EventRead[]): LiveRunState {
  const base = snapshot.run.event_count;
  let run: RunRead = snapshot.run;
  const agents = new Map(snapshot.agents.map((a) => [a.id, a]));
  const tasks = new Map(snapshot.tasks.map((t) => [t.id, t]));
  let messageCount = snapshot.event_counts["message.sent"] ?? 0;
  let eventCount = Math.max(snapshot.total_events, base);

  for (const event of events) {
    if (event.sequence_number <= base || event.run_id !== run.id) continue;
    eventCount = Math.max(eventCount, event.sequence_number);
    const type = event.event_type;
    const to = payloadString(event, "to");

    if (type === "message.sent") {
      messageCount += 1;
    } else if (type.startsWith("agent.")) {
      if (type === "agent.created") {
        if (!agents.has(event.agent_id ?? "")) {
          const agent = placeholderAgent(event);
          if (agent) agents.set(agent.id, agent);
        }
        continue;
      }
      const current = event.agent_id ? agents.get(event.agent_id) : undefined;
      if (!current) continue;
      const status = pick(to, AGENT_STATUSES) ?? AGENT_TYPE_STATUS[type];
      if (!status) continue;
      agents.set(current.id, {
        ...current,
        status,
        started_at: current.started_at ?? (status === "running" ? event.timestamp : null),
        completed_at: AGENT_TERMINAL.includes(status) ? current.completed_at ?? event.timestamp : current.completed_at,
      });
    } else if (type.startsWith("task.")) {
      if (type === "task.created") {
        if (event.task_id && !tasks.has(event.task_id)) {
          const task = placeholderTask(event);
          if (task) tasks.set(task.id, task);
        }
        continue;
      }
      const current = event.task_id ? tasks.get(event.task_id) : undefined;
      if (!current) continue;
      const status = pick(to, TASK_STATUSES) ?? TASK_TYPE_STATUS[type] ?? current.status;
      const progress = payloadNumber(event, "progress_percentage");
      tasks.set(current.id, {
        ...current,
        status,
        progress_percentage: progress ?? current.progress_percentage,
        updated_at: event.timestamp,
        started_at: current.started_at ?? (status === "in_progress" ? event.timestamp : null),
        completed_at: TASK_TERMINAL.includes(status) ? current.completed_at ?? event.timestamp : current.completed_at,
      });
    } else if (type.startsWith("run.")) {
      const status = pick(to, RUN_STATUSES) ?? RUN_TYPE_STATUS[type];
      if (!status) continue;
      run = {
        ...run,
        status,
        started_at: run.started_at ?? (status === "running" ? event.timestamp : null),
        completed_at: isRunTerminalEvent(event) ? run.completed_at ?? event.timestamp : run.completed_at,
      };
    }
  }

  return {
    run,
    agents: [...agents.values()],
    tasks: [...tasks.values()],
    messageCount,
    eventCount,
    ended: RUN_TERMINAL.includes(run.status),
  };
}

/** Agents that count as "running" in the header. Matches the backend overview rule. */
export function isRunningAgent(agent: AgentRead): boolean {
  return agent.status === "running" || agent.status === "reviewing";
}
