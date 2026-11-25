// Turn the raw event log into a readable activity story for Panel B.
// Rules: one row per meaningful step, in sequence order. A tool start and its result become one row.
// Successful Agent Fleet reporting calls (mcp__agent-fleet__*) are hidden, because their effect has its
// own event (task created, task completed and so on). Failed reporting calls stay visible as problems.
import { isImplicit, payloadString } from "./events";
import { toMs, truncate } from "./format";
import type { AgentRead, EventRead, TaskRead } from "./types";

export type ActivityKind = "milestone" | "delegation" | "message" | "tool" | "status" | "problem" | "system";
export type ActivityGroup = "conversation" | "work" | "progress" | "problems";
export type ActivityTone = "neutral" | "info" | "success" | "warning" | "danger" | "active";

export interface ActivityItem {
  key: string;
  seq: number;
  timestamp: string;
  kind: ActivityKind;
  group: ActivityGroup;
  tone: ActivityTone;
  /** The agent that did the step. */
  agentId: string | null;
  /** The other agent (receiver of a message, assignee of a task). */
  targetId: string | null;
  /** One short sentence. Agent names are given separately in agentId and targetId. */
  text: string;
  /** Optional longer text (message body, tool output, error). */
  detail: string | null;
  /** The system closed this item, not the agent. */
  implicit: boolean;
}

export interface ActivitySummary {
  agents: number;
  tasksDone: number;
  tasksFailed: number;
  tasksTotal: number;
  messages: number;
  toolCalls: number;
  toolFailures: number;
  problems: number;
}

export const ACTIVITY_GROUPS: readonly { id: ActivityGroup | "all"; label: string }[] = [
  { id: "all", label: "Everything" },
  { id: "conversation", label: "Conversation" },
  { id: "work", label: "Tool work" },
  { id: "progress", label: "Progress" },
  { id: "problems", label: "Problems" },
];

const REPORTING_TOOL = "mcp__agent-fleet__";
const DELEGATION_TOOLS = new Set(["Agent", "Task"]);
const MARKER_LINE = /^\s*AGENT_FLEET_(RUN|AGENT|TASK)_ID:.*$/gm;

const HANDBACK_TAGS = /<(tools-used-before-summary|usage)>[\s\S]*?<\/\1>/g;
const HANDBACK_START = "[Subagent hand-back]";
const HANDBACK_BODY = "The report follows:";

/** Remove Claude Code hand-back metadata from a subagent result (older runs stored it). */
export function stripHandback(text: string): string {
  let out = text.replace(HANDBACK_TAGS, "");
  const start = out.indexOf(HANDBACK_START);
  if (start !== -1) {
    const body = out.indexOf(HANDBACK_BODY, start);
    // Without the body marker (a cut preview), the rest is only the notice.
    out =
      body === -1
        ? out.slice(0, start)
        : out
            .slice(body + HANDBACK_BODY.length)
            .split("\n")
            .map((line) => (line.startsWith("  ") ? line.slice(2) : line))
            .join("\n");
  }
  return out.replace(/\n\s*agentId:\s*\S+\s*$/, "").trim();
}

function cleanMessage(text: string, sender: string | undefined): string {
  let body = text;
  // Event messages start with "sender to receiver: " or "sender: ".
  if (sender && body.startsWith(sender)) {
    const colon = body.indexOf(": ");
    if (colon > 0 && colon < sender.length + 60) body = body.slice(colon + 2);
  }
  return stripHandback(body).replace(MARKER_LINE, "").replace(/\n{3,}/g, "\n\n").trim();
}

function toolLabel(name: string): string {
  return name.startsWith(REPORTING_TOOL) ? name.slice(REPORTING_TOOL.length) : name.replace(/^mcp__/, "").replace(/__/g, " · ");
}

function quoted(text: string): string {
  return `“${truncate(text, 90)}”`;
}

function titleFromMessage(event: EventRead): string | null {
  const m = /Task '([^']+)'/.exec(event.message) ?? /for '([^']+)'/.exec(event.message);
  return m ? m[1] : null;
}

/** Build the activity rows. `agents` gives names for the message clean-up. */
export function buildActivity(
  events: readonly EventRead[],
  agents: readonly AgentRead[],
  tasks: readonly Pick<TaskRead, "id" | "title">[] = [],
): ActivityItem[] {
  const names = new Map(agents.map((a) => [a.id, a.name]));
  const titles = new Map(tasks.map((t) => [t.id, t.title]));
  const taskTitle = (event: EventRead) => (event.task_id ? titles.get(event.task_id) : undefined) ?? titleFromMessage(event);
  const items: ActivityItem[] = [];
  const toolRows = new Map<string, ActivityItem>();
  let lastUsage: ActivityItem | null = null;

  const push = (event: EventRead, row: Omit<ActivityItem, "key" | "seq" | "timestamp" | "implicit" | "agentId"> & { agentId?: string | null }) => {
    const item: ActivityItem = {
      key: `e${event.sequence_number}`,
      seq: event.sequence_number,
      timestamp: event.timestamp,
      implicit: isImplicit(event),
      agentId: row.agentId === undefined ? event.agent_id : row.agentId,
      ...row,
    };
    items.push(item);
    return item;
  };

  for (const event of events) {
    const type = event.event_type;
    const agentName = event.agent_id ? names.get(event.agent_id) : undefined;

    if (type.startsWith("tool.")) {
      const toolName = payloadString(event, "tool_name") ?? "tool";
      const toolUseId = payloadString(event, "tool_use_id");
      const reporting = toolName.startsWith(REPORTING_TOOL);
      if (type === "tool.started") {
        if (reporting || DELEGATION_TOOLS.has(toolName)) continue;
        const input = payloadString(event, "input_summary");
        const row = push(event, {
          kind: "tool",
          group: "work",
          tone: "active",
          targetId: null,
          text: `used ${toolLabel(toolName)}${input ? ` (${truncate(input, 80)})` : ""}`,
          detail: null,
        });
        if (toolUseId) toolRows.set(toolUseId, row);
        continue;
      }
      const failed = type === "tool.failed";
      const output = payloadString(event, "output_preview");
      const existing = toolUseId ? toolRows.get(toolUseId) : undefined;
      if (existing) {
        existing.tone = failed ? "danger" : "success";
        existing.detail = output;
        if (failed) {
          existing.group = "problems";
          existing.kind = "problem";
          existing.text = `${existing.text} — failed`;
        }
        continue;
      }
      if (!failed) continue; // result of a hidden call
      const denied = event.payload?.["denied"] === true;
      push(event, {
        kind: "problem",
        group: "problems",
        tone: "danger",
        targetId: null,
        text: denied
          ? `was denied permission for ${toolLabel(toolName)}`
          : reporting
            ? `could not report to Agent Fleet (${toolLabel(toolName)})`
            : `${toolLabel(toolName)} failed`,
        detail: output,
      });
      continue;
    }

    switch (type) {
      case "run.created":
      case "run.started":
      case "run.status_changed":
        push(event, { kind: "milestone", group: "progress", tone: "info", targetId: null, text: event.message, detail: null, agentId: null });
        break;
      case "run.completed":
        push(event, { kind: "milestone", group: "progress", tone: "success", targetId: null, text: "Run completed. The final report is in Panel D.", detail: null, agentId: null });
        break;
      case "run.failed":
        push(event, {
          kind: "milestone",
          group: "problems",
          tone: "danger",
          targetId: null,
          text: "Run failed",
          detail: event.message.replace(/^Run failed:\s*/, ""),
          agentId: null,
        });
        break;
      case "run.cancelled":
        push(event, { kind: "milestone", group: "progress", tone: "warning", targetId: null, text: event.message || "Run cancelled", detail: null, agentId: null });
        break;
      case "task.created": {
        const to = payloadString(event, "assigned_agent_id");
        const from = payloadString(event, "created_by_agent_id") ?? event.agent_id;
        const title = taskTitle(event);
        push(event, {
          kind: "delegation",
          group: "conversation",
          tone: "info",
          agentId: from,
          targetId: to,
          text: title ? `assigned the task ${quoted(title)} to` : "created a task",
          detail: null,
        });
        break;
      }
      case "task.started":
      case "task.completed":
      case "task.failed":
      case "task.status_changed": {
        const title = taskTitle(event);
        const failed = type === "task.failed";
        const done = type === "task.completed";
        const preview = payloadString(event, "result_preview") ?? payloadString(event, "error_message");
        push(event, {
          kind: failed ? "problem" : "status",
          group: failed ? "problems" : "progress",
          tone: failed ? "danger" : done ? "success" : "neutral",
          targetId: null,
          text: done
            ? `delivered ${title ? quoted(title) : "a task result"}`
            : failed
              ? `marked ${title ? quoted(title) : "a task"} as failed`
              : type === "task.started"
                ? `started ${title ? quoted(title) : "a task"}`
                : truncate(event.message, 140),
          detail: preview,
        });
        break;
      }
      case "message.sent": {
        const receiver = payloadString(event, "receiver_agent_id");
        const mtype = payloadString(event, "message_type") ?? "note";
        const body = cleanMessage(event.message, agentName);
        const verb =
          mtype === "instruction" ? "gave instructions to" : mtype === "result" ? "reported back to" : mtype === "review" ? "sent a review to" : receiver ? "wrote to" : "said";
        push(event, { kind: "message", group: "conversation", tone: "neutral", targetId: receiver, text: verb, detail: body || null });
        break;
      }
      case "agent.created": {
        push(event, { kind: "status", group: "progress", tone: "neutral", targetId: null, text: `joined the team (${event.message.replace(/^.*\(([^)]*)\).*$/, "$1")})`, detail: null });
        break;
      }
      case "agent.started":
        push(event, { kind: "status", group: "progress", tone: "active", targetId: null, text: "started working", detail: null });
        break;
      case "agent.completed":
        push(event, { kind: "status", group: "progress", tone: "success", targetId: null, text: isImplicit(event) ? "was closed when the run ended" : "finished", detail: null });
        break;
      case "agent.failed":
        push(event, { kind: "problem", group: "problems", tone: "danger", targetId: null, text: "failed", detail: payloadString(event, "error_message") });
        break;
      case "agent.status_changed":
        push(event, { kind: "status", group: "progress", tone: "neutral", targetId: null, text: truncate(event.message.replace(agentName ?? "\u0000", "").trim(), 140), detail: null });
        break;
      case "execution.notice":
        push(event, { kind: "problem", group: "problems", tone: "warning", targetId: null, text: event.message, detail: null, agentId: null });
        break;
      case "execution.usage_reported": {
        // Claude Code reports usage several times; show only the last report.
        const cost = event.payload?.["estimated_cost_usd"];
        const text = typeof cost === "number" ? `Claude Code reported usage (estimated cost, client-side: $${cost.toFixed(2)})` : "Claude Code reported usage";
        if (lastUsage) items.splice(items.indexOf(lastUsage), 1);
        lastUsage = push(event, { kind: "system", group: "progress", tone: "neutral", targetId: null, text, detail: null, agentId: null });
        break;
      }
      default:
        push(event, { kind: "system", group: "progress", tone: "neutral", targetId: null, text: event.message, detail: null, agentId: null });
    }
  }
  return items;
}

export function summarizeActivity(items: readonly ActivityItem[], agents: readonly AgentRead[], tasks: readonly { status: string }[]): ActivitySummary {
  return {
    agents: agents.length,
    tasksTotal: tasks.length,
    tasksDone: tasks.filter((t) => t.status === "completed").length,
    tasksFailed: tasks.filter((t) => t.status === "failed").length,
    messages: items.filter((i) => i.kind === "message").length,
    toolCalls: items.filter((i) => i.group === "work" || (i.kind === "problem" && i.text.startsWith("used "))).length,
    toolFailures: items.filter((i) => i.kind === "problem" && i.text.startsWith("used ")).length,
    problems: items.filter((i) => i.group === "problems").length,
  };
}

/** "+m:ss" from the first event. */
export function relativeTime(iso: string, startIso: string | undefined): string {
  const t = toMs(iso);
  const s = toMs(startIso);
  if (t === null || s === null) return "";
  const total = Math.max(0, Math.round((t - s) / 1000));
  const m = Math.floor(total / 60);
  const sec = String(total % 60).padStart(2, "0");
  return `+${m}:${sec}`;
}
