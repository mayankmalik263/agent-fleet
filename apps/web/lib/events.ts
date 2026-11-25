// Event log helpers: merge, de-duplication, classification and payload access.
import type { EventRead } from "./types";

export type EventCategory =
  | "system"
  | "message"
  | "tool_call"
  | "tool_result"
  | "delegation"
  | "review"
  | "error"
  | "task"
  | "agent";

export interface CategoryInfo {
  id: EventCategory;
  label: string;
  color: string;
  /** Marker shape in the timeline and the legend. */
  shape: "circle" | "square" | "square-outline" | "diamond" | "triangle" | "ring" | "bar";
}

/** Legend order. The first seven entries are the categories that the product brief names. */
export const EVENT_CATEGORIES: readonly CategoryInfo[] = [
  { id: "system", label: "System events", color: "var(--af-text-2)", shape: "bar" },
  { id: "message", label: "Agent messages", color: "var(--af-primary)", shape: "circle" },
  { id: "tool_call", label: "Tool calls", color: "var(--af-blue)", shape: "square" },
  { id: "tool_result", label: "Tool results", color: "var(--af-blue)", shape: "square-outline" },
  { id: "delegation", label: "Delegation", color: "var(--af-orange)", shape: "diamond" },
  { id: "review", label: "Reviewer activity", color: "var(--af-green)", shape: "ring" },
  { id: "error", label: "Errors", color: "var(--af-red)", shape: "triangle" },
  { id: "task", label: "Task updates", color: "var(--af-yellow)", shape: "circle" },
  { id: "agent", label: "Agent lifecycle", color: "var(--af-text-2)", shape: "ring" },
];

export const CATEGORY_BY_ID: Record<EventCategory, CategoryInfo> = Object.fromEntries(
  EVENT_CATEGORIES.map((c) => [c.id, c]),
) as Record<EventCategory, CategoryInfo>;

export function payloadValue(event: EventRead, key: string): unknown {
  return event.payload ? event.payload[key] : undefined;
}

export function payloadString(event: EventRead, key: string): string | null {
  const value = payloadValue(event, key);
  return typeof value === "string" && value ? value : null;
}

export function payloadNumber(event: EventRead, key: string): number | null {
  const value = payloadValue(event, key);
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** True when the system closed the item, not the agent (payload.implicit = true). */
export function isImplicit(event: EventRead): boolean {
  return payloadValue(event, "implicit") === true;
}

/**
 * Put an event in one display category.
 * `roleOf` gives the role of an agent id. Task and agent events from a reviewer count as reviewer activity.
 */
export function categorizeEvent(event: EventRead, roleOf?: (agentId: string) => string | undefined): EventCategory {
  const type = event.event_type;
  if (type.endsWith(".failed") || type === "approval.rejected") return "error";
  if (type === "tool.started") return "tool_call";
  if (type === "tool.completed") return "tool_result";
  if (type === "task.created") return "delegation";
  if (type === "task.review_requested") return "review";
  if (type.startsWith("message.")) {
    return payloadString(event, "message_type") === "review" ? "review" : "message";
  }
  if (type.startsWith("task.") || type.startsWith("agent.")) {
    const role = event.agent_id && roleOf ? roleOf(event.agent_id) : undefined;
    if (role && role.toLowerCase().includes("review")) return "review";
    return type.startsWith("task.") ? "task" : "agent";
  }
  return "system";
}

/** The two agents that an event connects, for message and delegation events. */
export function eventLink(event: EventRead): { from: string; to: string; kind: "message" | "delegation" } | null {
  if (event.event_type === "message.sent") {
    const to = payloadString(event, "receiver_agent_id");
    if (event.agent_id && to) return { from: event.agent_id, to, kind: "message" };
    return null;
  }
  if (event.event_type === "task.created") {
    const from = payloadString(event, "created_by_agent_id") ?? event.agent_id;
    const to = payloadString(event, "assigned_agent_id");
    if (from && to) return { from, to, kind: "delegation" };
  }
  return null;
}

/**
 * Merge new events into a sorted event log.
 * Removes duplicates by sequence_number and keeps the log ordered by sequence_number.
 * Returns the same array when nothing new arrives, so React can skip a render.
 */
export function mergeEvents(existing: readonly EventRead[], incoming: readonly EventRead[]): EventRead[] {
  if (incoming.length === 0) return existing as EventRead[];
  const seen = new Set<number>();
  for (const e of existing) seen.add(e.sequence_number);
  const fresh: EventRead[] = [];
  for (const e of incoming) {
    if (seen.has(e.sequence_number)) continue;
    seen.add(e.sequence_number);
    fresh.push(e);
  }
  if (fresh.length === 0) return existing as EventRead[];
  fresh.sort((a, b) => a.sequence_number - b.sequence_number);
  const last = existing.length ? existing[existing.length - 1].sequence_number : -Infinity;
  // Fast path: all new events come after the current tail.
  if (fresh[0].sequence_number > last) return [...existing, ...fresh];
  return [...existing, ...fresh].sort((a, b) => a.sequence_number - b.sequence_number);
}

/** Parse one SSE data frame. Returns null when the frame is not a valid event. */
export function parseEventFrame(data: string): EventRead | null {
  try {
    const value = JSON.parse(data) as Partial<EventRead>;
    if (typeof value.sequence_number !== "number" || typeof value.event_type !== "string") return null;
    return value as EventRead;
  } catch {
    return null;
  }
}

export function isRunTerminalEvent(event: EventRead): boolean {
  return event.event_type === "run.completed" || event.event_type === "run.failed" || event.event_type === "run.cancelled";
}
