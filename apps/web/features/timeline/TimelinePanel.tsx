"use client";
import { Activity, ChevronFirst, ChevronLast, Filter, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { SearchInput } from "@/components/ui/SearchInput";
import { ACTIVITY_GROUPS, buildActivity, summarizeActivity, type ActivityGroup } from "@/lib/activity";
import { EVENT_CATEGORIES, type EventCategory } from "@/lib/events";
import { buildLanes, computeTimeline, DEFAULT_TIMELINE } from "@/lib/timeline";
import type { AgentRead, EventRead, TaskRead } from "@/lib/types";
import { ActivityFeed } from "./ActivityFeed";
import { EventDetails } from "./EventDetails";
import { TimelineCanvas } from "./TimelineCanvas";

const ZOOM_LEVELS = [0.25, 0.5, 1, 1.5, 2.5, 4] as const;
type View = "story" | "lanes";

export interface TimelinePanelProps {
  agents: AgentRead[];
  events: EventRead[];
  tasks?: TaskRead[];
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string | null, open?: boolean) => void;
  className?: string;
}

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="font-semibold tabular-nums" style={{ color: tone ?? "var(--af-text)" }}>
        {value}
      </span>
      <span className="text-fg-3">{label}</span>
    </span>
  );
}

/** Panel B: cross-agent collaboration. "Story" tells what each agent did; "Lanes" is the time chart. */
export function TimelinePanel({ agents, events, tasks = [], selectedAgentId, onSelectAgent, className = "" }: TimelinePanelProps) {
  const [view, setView] = useState<View>("story");
  const [group, setGroup] = useState<ActivityGroup | "all">("all");
  const [search, setSearch] = useState("");
  const [zoomIndex, setZoomIndex] = useState(2);
  const [hidden, setHidden] = useState<ReadonlySet<EventCategory>>(new Set());
  const [filterOpen, setFilterOpen] = useState(false);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const agentById = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents]);
  const roleOf = useCallback((id: string) => agentById.get(id)?.role, [agentById]);

  // ---- story view
  const activity = useMemo(() => buildActivity(events, agents, tasks), [events, agents, tasks]);
  const summary = useMemo(() => summarizeActivity(activity, agents, tasks), [activity, agents, tasks]);
  const storyItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return activity.filter((item) => {
      if (group !== "all" && item.group !== group) return false;
      if (!q) return true;
      const who = `${item.agentId ? agentById.get(item.agentId)?.name ?? "" : ""} ${item.targetId ? agentById.get(item.targetId)?.name ?? "" : ""}`;
      return `${who} ${item.text} ${item.detail ?? ""}`.toLowerCase().includes(q);
    });
  }, [activity, group, search, agentById]);
  const groupCounts = useMemo(() => {
    const counts: Record<string, number> = { all: activity.length };
    for (const item of activity) counts[item.group] = (counts[item.group] ?? 0) + 1;
    return counts;
  }, [activity]);

  // ---- lanes view
  const lanes = useMemo(() => buildLanes(agents, events), [agents, events]);
  const zoom = ZOOM_LEVELS[zoomIndex];
  const geometry = useMemo(() => {
    if (view !== "lanes") return null;
    const q = search.trim().toLowerCase();
    const laneIds = q ? new Set(lanes.filter((l) => `${l.label} ${l.sublabel}`.toLowerCase().includes(q)).map((l) => l.id)) : undefined;
    const categories = hidden.size ? new Set(EVENT_CATEGORIES.map((c) => c.id).filter((c) => !hidden.has(c))) : undefined;
    return computeTimeline(
      events,
      lanes,
      {
        ...DEFAULT_TIMELINE,
        pxPerSecond: DEFAULT_TIMELINE.pxPerSecond * zoom,
        minGap: Math.max(6, DEFAULT_TIMELINE.minGap * Math.sqrt(zoom)),
        maxGap: DEFAULT_TIMELINE.maxGap * zoom,
        laneIds,
        categories,
      },
      roleOf,
    );
  }, [view, events, lanes, search, hidden, zoom, roleOf]);

  const selectedEvent = selectedSeq !== null ? events.find((e) => e.sequence_number === selectedSeq) ?? null : null;

  const scrollTo = (where: "start" | "end") => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ left: where === "start" ? 0 : el.scrollWidth, behavior: "smooth" });
  };

  const toggleCategory = (id: EventCategory) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const viewSwitch = (
    <div role="tablist" aria-label="Collaboration view" className="flex rounded-md border border-line-soft p-0.5">
      {(["story", "lanes"] as const).map((v) => (
        <button
          key={v}
          type="button"
          role="tab"
          aria-selected={view === v}
          className={`rounded px-2 py-0.5 text-[11px] ${view === v ? "bg-primary/20 text-fg" : "text-fg-2 hover:text-fg"}`}
          onClick={() => setView(v)}
        >
          {v === "story" ? "Story" : "Lanes"}
        </button>
      ))}
    </div>
  );

  const laneActions = (
    <>
      <button type="button" className="af-icon-btn" aria-label="Go to earliest event" title="Earliest" onClick={() => scrollTo("start")}>
        <ChevronFirst aria-hidden size={13} />
      </button>
      <button type="button" className="af-icon-btn" aria-label="Go to latest event" title="Latest" onClick={() => scrollTo("end")}>
        <ChevronLast aria-hidden size={13} />
      </button>
      <button
        type="button"
        className="af-icon-btn"
        aria-label="Zoom out timeline"
        title="Zoom out"
        disabled={zoomIndex === 0}
        onClick={() => setZoomIndex((z) => Math.max(0, z - 1))}
      >
        <ZoomOut aria-hidden size={13} />
      </button>
      <span className="af-mono w-9 text-center text-fg-2" aria-live="polite" aria-label={`Timeline zoom ${zoom} times`}>
        {zoom}×
      </span>
      <button
        type="button"
        className="af-icon-btn"
        aria-label="Zoom in timeline"
        title="Zoom in"
        disabled={zoomIndex === ZOOM_LEVELS.length - 1}
        onClick={() => setZoomIndex((z) => Math.min(ZOOM_LEVELS.length - 1, z + 1))}
      >
        <ZoomIn aria-hidden size={13} />
      </button>
      <button
        type="button"
        className="af-icon-btn"
        aria-label="Filter event types"
        aria-expanded={filterOpen}
        aria-controls="timeline-filters"
        title="Filter event types"
        onClick={() => setFilterOpen((v) => !v)}
        style={hidden.size ? { color: "var(--af-primary)", borderColor: "var(--af-primary)" } : undefined}
      >
        <Filter aria-hidden size={13} />
      </button>
    </>
  );

  return (
    <Panel
      id="collaboration-timeline"
      label="Panel B"
      title="Cross-Agent Collaboration"
      className={className}
      bodyClassName="flex flex-col"
      actions={
        <>
          {viewSwitch}
          <SearchInput
            value={search}
            onChange={setSearch}
            label={view === "story" ? "Search activity" : "Search agents in timeline"}
            placeholder={view === "story" ? "Search" : "Search agents"}
            className="w-28"
          />
          {view === "lanes" ? laneActions : null}
        </>
      }
    >
      {events.length === 0 ? (
        <EmptyState icon={<Activity size={22} />} title="No events yet" className="flex-1">
          Events stream in as agents start, delegate tasks, send messages and call tools.
        </EmptyState>
      ) : view === "story" ? (
        <>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 border-b border-line-soft px-3 py-1.5 text-[11px]" aria-label="Run summary">
            <Stat label="agents" value={summary.agents} />
            <Stat label="tasks done" value={`${summary.tasksDone}/${summary.tasksTotal}`} tone={summary.tasksTotal && summary.tasksDone === summary.tasksTotal ? "var(--af-green)" : undefined} />
            {summary.tasksFailed ? <Stat label="tasks failed" value={summary.tasksFailed} tone="var(--af-red)" /> : null}
            <Stat label="messages" value={summary.messages} />
            <Stat label="tool calls" value={summary.toolCalls} />
            {summary.problems ? <Stat label="problems" value={summary.problems} tone="var(--af-red)" /> : null}
          </div>
          <div role="group" aria-label="Activity filter" className="flex flex-wrap gap-1 border-b border-line-soft px-3 py-1.5">
            {ACTIVITY_GROUPS.map((g) => (
              <button key={g.id} type="button" className="af-chip" aria-pressed={group === g.id} onClick={() => setGroup(g.id)}>
                {g.label}
                <span className="tabular-nums text-fg-3">{groupCounts[g.id] ?? 0}</span>
              </button>
            ))}
          </div>
          {storyItems.length === 0 ? (
            <p className="py-6 text-center text-[12px] text-fg-2">No activity matches this filter.</p>
          ) : (
            <ActivityFeed items={storyItems} agents={agentById} selectedAgentId={selectedAgentId} onSelectAgent={onSelectAgent} />
          )}
        </>
      ) : (
        <>
          {filterOpen ? (
            <div id="timeline-filters" role="group" aria-label="Event type filter" className="flex flex-wrap gap-1 border-b border-line-soft px-3 py-1.5">
              {EVENT_CATEGORIES.map((c) => (
                <button key={c.id} type="button" className="af-chip" aria-pressed={!hidden.has(c.id)} onClick={() => toggleCategory(c.id)}>
                  <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: c.color }} />
                  {c.label}
                </button>
              ))}
            </div>
          ) : null}
          {geometry ? (
            <TimelineCanvas
              geometry={geometry}
              scrollRef={scrollRef}
              selectedAgentId={selectedAgentId}
              selectedSeq={selectedSeq}
              agentNames={agentById}
              onSelectEvent={setSelectedSeq}
              onSelectAgent={onSelectAgent}
            />
          ) : null}
          {selectedEvent ? <EventDetails event={selectedEvent} agents={agentById} onClose={() => setSelectedSeq(null)} /> : null}
        </>
      )}
    </Panel>
  );
}
