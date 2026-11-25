// Timeline geometry: lanes per agent, marker positions and connector links.
// Markers keep strict time order on the x axis. Short gaps get a minimum width so markers do not overlap.
// Long idle gaps are shortened to a maximum width, so the timeline stays readable. Tick labels show real times.
import { roleAccent } from "./colors";
import { categorizeEvent, eventLink, type EventCategory } from "./events";
import { toMs } from "./format";
import { hierarchyOrder } from "./layout";
import type { AgentRead, EventRead } from "./types";

export const SYSTEM_LANE_ID = "__system__";

export interface TimelineLane {
  id: string;
  agentId: string | null;
  label: string;
  sublabel: string;
  color: string;
}

export interface TimelineMarker {
  event: EventRead;
  lane: number;
  x: number;
  category: EventCategory;
}

export interface TimelineLink {
  id: string;
  fromLane: number;
  toLane: number;
  x: number;
  kind: "message" | "delegation";
  sequence: number;
}

export interface TimelineTick {
  x: number;
  label: string;
}

export interface TimelineGeometry {
  lanes: TimelineLane[];
  markers: TimelineMarker[];
  links: TimelineLink[];
  ticks: TimelineTick[];
  width: number;
  /** True when at least one long gap was shortened. */
  compressed: boolean;
}

export interface TimelineOptions {
  /** Pixels per second of real time. Zoom changes this value. */
  pxPerSecond: number;
  minGap: number;
  maxGap: number;
  padding: number;
  tickSpacing: number;
  /** Visible categories. All categories show when this is undefined. */
  categories?: ReadonlySet<EventCategory>;
  /** Visible lane ids. All lanes show when this is undefined. */
  laneIds?: ReadonlySet<string>;
}

export const DEFAULT_TIMELINE: TimelineOptions = {
  pxPerSecond: 40,
  minGap: 14,
  maxGap: 120,
  padding: 24,
  tickSpacing: 110,
};

/** One lane per agent in hierarchy order, plus a System lane for events without an agent. */
export function buildLanes(agents: readonly AgentRead[], events: readonly EventRead[]): TimelineLane[] {
  const byId = new Map(agents.map((a) => [a.id, a]));
  const order = hierarchyOrder(agents.map((a) => ({ id: a.id, parentId: a.parent_agent_id })));
  const lanes: TimelineLane[] = order.map((id) => {
    const a = byId.get(id) as AgentRead;
    return { id, agentId: id, label: a.name, sublabel: `${a.role} · ${a.model_alias}`, color: roleAccent(a.role) };
  });
  const known = new Set(order);
  let hasSystem = false;
  for (const e of events) {
    if (!e.agent_id) {
      hasSystem = true;
    } else if (!known.has(e.agent_id)) {
      known.add(e.agent_id);
      lanes.push({
        id: e.agent_id,
        agentId: e.agent_id,
        label: `Agent ${e.agent_id.slice(0, 6)}`,
        sublabel: "not in snapshot",
        color: "var(--af-text-2)",
      });
    }
  }
  if (hasSystem) {
    lanes.push({ id: SYSTEM_LANE_ID, agentId: null, label: "System", sublabel: "run and runtime events", color: "var(--af-text-2)" });
  }
  return lanes;
}

export function laneIdForEvent(event: EventRead): string {
  return event.agent_id ?? SYSTEM_LANE_ID;
}

/** Compute marker positions, connector links and time ticks. Pure function. */
export function computeTimeline(
  events: readonly EventRead[],
  lanes: readonly TimelineLane[],
  options: TimelineOptions = DEFAULT_TIMELINE,
  roleOf?: (agentId: string) => string | undefined,
): TimelineGeometry {
  const { pxPerSecond, minGap, maxGap, padding, tickSpacing, categories, laneIds } = options;
  const visibleLanes = laneIds ? lanes.filter((l) => laneIds.has(l.id)) : [...lanes];
  const laneIndex = new Map(visibleLanes.map((l, i) => [l.id, i]));

  const sorted = [...events].sort((a, b) => a.sequence_number - b.sequence_number);
  const markers: TimelineMarker[] = [];
  const links: TimelineLink[] = [];
  const ticks: TimelineTick[] = [];
  let x = padding;
  let prevMs: number | null = null;
  let lastTick = -Infinity;
  let compressed = false;

  for (const event of sorted) {
    const lane = laneIndex.get(laneIdForEvent(event));
    if (lane === undefined) continue;
    const category = categorizeEvent(event, roleOf);
    if (categories && !categories.has(category)) continue;

    const ms = toMs(event.timestamp);
    if (prevMs !== null && ms !== null) {
      const raw = (Math.max(0, ms - prevMs) / 1000) * pxPerSecond;
      if (raw > maxGap) compressed = true;
      x += Math.min(maxGap, Math.max(minGap, raw));
    } else if (markers.length > 0) {
      x += minGap;
    }
    if (ms !== null) prevMs = ms;

    markers.push({ event, lane, x, category });
    if (x - lastTick >= tickSpacing) {
      ticks.push({ x, label: event.timestamp });
      lastTick = x;
    }

    const link = eventLink(event);
    if (link) {
      const fromLane = laneIndex.get(link.from);
      const toLane = laneIndex.get(link.to);
      if (fromLane !== undefined && toLane !== undefined && fromLane !== toLane) {
        links.push({ id: `${event.sequence_number}`, fromLane, toLane, x, kind: link.kind, sequence: event.sequence_number });
      }
    }
  }

  return { lanes: visibleLanes, markers, links, ticks, width: x + padding * 2, compressed };
}
