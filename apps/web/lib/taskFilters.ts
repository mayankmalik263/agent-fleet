// Task filter groups for the Teamwork Tasks panel.
import type { AgentRead, TaskRead, TaskStatus } from "./types";

export type TaskFilter = "all" | "in_progress" | "pending" | "review" | "done" | "failed";

export const TASK_FILTERS: readonly { id: TaskFilter; label: string; statuses: readonly TaskStatus[] | null }[] = [
  { id: "all", label: "All", statuses: null },
  { id: "in_progress", label: "In progress", statuses: ["in_progress", "blocked"] },
  { id: "pending", label: "Pending", statuses: ["pending"] },
  { id: "review", label: "In review", statuses: ["review"] },
  { id: "done", label: "Done", statuses: ["completed"] },
  { id: "failed", label: "Failed", statuses: ["failed", "cancelled"] },
];

export function matchesFilter(task: TaskRead, filter: TaskFilter): boolean {
  const def = TASK_FILTERS.find((f) => f.id === filter);
  return !def || def.statuses === null || def.statuses.includes(task.status);
}

export function matchesSearch(task: TaskRead, search: string, agents: Map<string, AgentRead>): boolean {
  const q = search.trim().toLowerCase();
  if (!q) return true;
  const agent = task.assigned_agent_id ? agents.get(task.assigned_agent_id) : undefined;
  return [task.title, task.description, agent?.name ?? "", agent?.role ?? ""].some((v) => v.toLowerCase().includes(q));
}

/** Filter and sort tasks: active first, then newest first. */
export function filterTasks(
  tasks: readonly TaskRead[],
  filter: TaskFilter,
  search: string,
  agents: Map<string, AgentRead>,
): TaskRead[] {
  const rank = (t: TaskRead) =>
    t.status === "in_progress" || t.status === "blocked" ? 0 : t.status === "review" ? 1 : t.status === "pending" ? 2 : 3;
  return tasks
    .filter((t) => matchesFilter(t, filter) && matchesSearch(t, search, agents))
    .sort((a, b) => rank(a) - rank(b) || b.created_at.localeCompare(a.created_at));
}

export function countByFilter(tasks: readonly TaskRead[]): Record<TaskFilter, number> {
  const out = { all: 0, in_progress: 0, pending: 0, review: 0, done: 0, failed: 0 } as Record<TaskFilter, number>;
  for (const t of tasks) {
    for (const f of TASK_FILTERS) if (matchesFilter(t, f.id)) out[f.id] += 1;
  }
  return out;
}
