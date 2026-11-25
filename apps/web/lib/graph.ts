// Build React Flow nodes and edges from live run data. Pure functions, no React.
import { MarkerType, type Edge, type Node } from "@xyflow/react";
import { roleAccent } from "./colors";
import { eventLink } from "./events";
import { DEFAULT_LAYOUT, hierarchicalLayout, type LayoutOptions } from "./layout";
import type { AgentRead, EventRead, TaskRead } from "./types";

export interface AgentTaskStats {
  total: number;
  completed: number;
  /** Progress of the agent's current task, only when the API reports one. */
  currentProgress: number | null;
  currentTaskTitle: string | null;
}

export function taskStatsByAgent(agents: readonly AgentRead[], tasks: readonly TaskRead[]): Map<string, AgentTaskStats> {
  const stats = new Map<string, AgentTaskStats>();
  for (const agent of agents) stats.set(agent.id, { total: 0, completed: 0, currentProgress: null, currentTaskTitle: null });
  const byId = new Map(tasks.map((t) => [t.id, t]));
  for (const task of tasks) {
    if (!task.assigned_agent_id) continue;
    const s = stats.get(task.assigned_agent_id);
    if (!s) continue;
    s.total += 1;
    if (task.status === "completed") s.completed += 1;
  }
  for (const agent of agents) {
    const s = stats.get(agent.id) as AgentTaskStats;
    const current =
      (agent.current_task_id ? byId.get(agent.current_task_id) : undefined) ??
      tasks.find((t) => t.assigned_agent_id === agent.id && t.status === "in_progress");
    if (current) {
      s.currentTaskTitle = current.title;
      s.currentProgress = current.progress_percentage;
    }
  }
  return stats;
}

export type AgentNodeData = {
  agent: AgentRead;
  accent: string;
  stats: AgentTaskStats;
  selected: boolean;
  /** The node is not related to the selected agent. */
  dimmed: boolean;
  /** The node matches the agent search. */
  matched: boolean;
  /** The run is terminal: live indicators stop. */
  runEnded: boolean;
};

export type AgentFlowNode = Node<AgentNodeData, "agent">;

export interface GraphInput {
  agents: readonly AgentRead[];
  tasks: readonly TaskRead[];
  events: readonly EventRead[];
  selectedAgentId: string | null;
  search: string;
  runEnded: boolean;
  /** Message pairs "sender|receiver" that had a message very recently. */
  recentMessagePairs?: ReadonlySet<string>;
  layout?: LayoutOptions;
}

export function agentMatches(agent: AgentRead, search: string): boolean {
  const q = search.trim().toLowerCase();
  if (!q) return false;
  return [agent.name, agent.role, agent.model_alias].some((v) => v.toLowerCase().includes(q));
}

/** Agents directly related to the selected one: itself, its parent and its children. */
export function relatedAgentIds(agents: readonly AgentRead[], selectedId: string | null): Set<string> {
  const related = new Set<string>();
  if (!selectedId) return related;
  related.add(selectedId);
  const selected = agents.find((a) => a.id === selectedId);
  if (selected?.parent_agent_id) related.add(selected.parent_agent_id);
  for (const a of agents) if (a.parent_agent_id === selectedId) related.add(a.id);
  return related;
}

export function buildGraph(input: GraphInput): { nodes: AgentFlowNode[]; edges: Edge[] } {
  const { agents, tasks, events, selectedAgentId, search, runEnded, recentMessagePairs } = input;
  const ids = new Set(agents.map((a) => a.id));
  const positions = hierarchicalLayout(
    agents.map((a) => ({ id: a.id, parentId: a.parent_agent_id })),
    input.layout ?? DEFAULT_LAYOUT,
  );
  const stats = taskStatsByAgent(agents, tasks);
  const related = relatedAgentIds(agents, selectedAgentId);

  // Message links between agents (from message.sent events), counted per direction.
  const messagePairs = new Map<string, number>();
  for (const e of events) {
    const link = eventLink(e);
    if (link?.kind === "message" && ids.has(link.from) && ids.has(link.to)) {
      const key = `${link.from}|${link.to}`;
      messagePairs.set(key, (messagePairs.get(key) ?? 0) + 1);
    }
  }

  const nodes: AgentFlowNode[] = agents.map((agent) => ({
    id: agent.id,
    type: "agent",
    position: positions[agent.id] ?? { x: 0, y: 0 },
    draggable: false,
    connectable: false,
    selected: agent.id === selectedAgentId,
    ariaLabel: `Agent ${agent.name}, ${agent.role}, status ${agent.status}`,
    data: {
      agent,
      accent: roleAccent(agent.role),
      stats: stats.get(agent.id) as AgentTaskStats,
      selected: agent.id === selectedAgentId,
      dimmed: !!selectedAgentId && !related.has(agent.id),
      matched: agentMatches(agent, search),
      runEnded,
    },
  }));

  const edges: Edge[] = [];
  const touchesSelection = (a: string, b: string) => !!selectedAgentId && (a === selectedAgentId || b === selectedAgentId);
  const dimmedEdge = (a: string, b: string) => !!selectedAgentId && !touchesSelection(a, b);

  // Delegation edges: parent to child.
  const delegationPairs = new Set<string>();
  for (const agent of agents) {
    const parent = agent.parent_agent_id;
    if (!parent || !ids.has(parent) || parent === agent.id) continue;
    delegationPairs.add(`${parent}|${agent.id}`);
    const active = !runEnded && (agent.status === "running" || agent.status === "reviewing");
    const highlighted = touchesSelection(parent, agent.id);
    edges.push({
      id: `d:${parent}:${agent.id}`,
      source: parent,
      target: agent.id,
      type: "smoothstep",
      animated: active,
      className: dimmedEdge(parent, agent.id) ? "af-edge-dim" : undefined,
      style: {
        stroke: highlighted ? "var(--af-primary)" : "var(--af-border)",
        strokeWidth: highlighted ? 2 : 1.25,
      },
      // Marker colours are SVG attributes, so they use fixed values that match the palette.
      markerEnd: { type: MarkerType.ArrowClosed, color: highlighted ? "#a855f7" : "#6b6a73", width: 16, height: 16 },
      ariaLabel: "Delegation",
      data: { kind: "delegation" },
    });
  }

  // Task delegations between agents that are not parent and child.
  for (const task of tasks) {
    const from = task.created_by_agent_id;
    const to = task.assigned_agent_id;
    if (!from || !to || from === to || !ids.has(from) || !ids.has(to)) continue;
    const key = `${from}|${to}`;
    if (delegationPairs.has(key)) continue;
    delegationPairs.add(key);
    edges.push({
      id: `t:${from}:${to}`,
      source: from,
      target: to,
      type: "smoothstep",
      className: dimmedEdge(from, to) ? "af-edge-dim" : undefined,
      style: { stroke: "var(--af-orange)", strokeWidth: 1.25, strokeDasharray: "5 4" },
      ariaLabel: "Task delegation",
      data: { kind: "delegation" },
    });
  }

  // Message edges. They are thin and only stand out when related to the selection or recent.
  for (const [key, count] of messagePairs) {
    const [from, to] = key.split("|");
    const highlighted = touchesSelection(from, to);
    const recent = recentMessagePairs?.has(key) ?? false;
    edges.push({
      id: `m:${from}:${to}`,
      source: from,
      target: to,
      type: "default",
      animated: recent && !runEnded,
      label: highlighted ? `${count} msg${count === 1 ? "" : "s"}` : undefined,
      className: dimmedEdge(from, to) ? "af-edge-dim" : undefined,
      style: {
        stroke: "var(--af-primary)",
        strokeOpacity: highlighted || recent ? 0.9 : 0.35,
        strokeWidth: highlighted || recent ? 1.5 : 1,
        strokeDasharray: "2 4",
      },
      labelStyle: { fill: "var(--af-text-2)", fontSize: 10 },
      labelBgStyle: { fill: "var(--af-panel)" },
      ariaLabel: `${count} messages`,
      data: { kind: "message", count },
    });
  }

  return { nodes, edges };
}
