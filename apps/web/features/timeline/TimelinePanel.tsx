"use client";
import { ChevronFirst, ChevronLast, Filter, Activity, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { SearchInput } from "@/components/ui/SearchInput";
import { EVENT_CATEGORIES, type EventCategory } from "@/lib/events";
import { buildLanes, computeTimeline, DEFAULT_TIMELINE } from "@/lib/timeline";
import type { AgentRead, EventRead } from "@/lib/types";
import { EventDetails } from "./EventDetails";
import { TimelineCanvas } from "./TimelineCanvas";

const ZOOM_LEVELS = [0.25, 0.5, 1, 1.5, 2.5, 4] as const;

export interface TimelinePanelProps {
  agents: AgentRead[];
  events: EventRead[];
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string | null, open?: boolean) => void;
  className?: string;
}

/** Panel B: cross-agent collaboration timeline. */
export function TimelinePanel({ agents, events, selectedAgentId, onSelectAgent, className = "" }: TimelinePanelProps) {
  const [search, setSearch] = useState("");
  const [zoomIndex, setZoomIndex] = useState(2);
  const [hidden, setHidden] = useState<ReadonlySet<EventCategory>>(new Set());
  const [filterOpen, setFilterOpen] = useState(false);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const agentById = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents]);
  const roleOf = useCallback((id: string) => agentById.get(id)?.role, [agentById]);
  const lanes = useMemo(() => buildLanes(agents, events), [agents, events]);

  const zoom = ZOOM_LEVELS[zoomIndex];
  const geometry = useMemo(() => {
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
  }, [events, lanes, search, hidden, zoom, roleOf]);

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

  return (
    <Panel
      id="collaboration-timeline"
      label="Panel B"
      title="Cross-Agent Collaboration"
      className={className}
      bodyClassName="flex flex-col"
      actions={
        <>
          <SearchInput value={search} onChange={setSearch} label="Search agents in timeline" placeholder="Search agents" className="w-32" />
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
      }
    >
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

      {events.length === 0 ? (
        <EmptyState icon={<Activity size={22} />} title="No events yet" className="flex-1">
          Events stream in as agents start, delegate tasks, send messages and call tools.
        </EmptyState>
      ) : (
        <TimelineCanvas
          geometry={geometry}
          scrollRef={scrollRef}
          selectedAgentId={selectedAgentId}
          selectedSeq={selectedSeq}
          agentNames={agentById}
          onSelectEvent={setSelectedSeq}
          onSelectAgent={onSelectAgent}
        />
      )}

      {selectedEvent ? (
        <EventDetails event={selectedEvent} agents={agentById} onClose={() => setSelectedSeq(null)} />
      ) : null}
    </Panel>
  );
}
