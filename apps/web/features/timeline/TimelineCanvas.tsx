"use client";
import type { RefObject } from "react";
import { EventShape } from "@/components/ui/EventShape";
import { CATEGORY_BY_ID, isImplicit } from "@/lib/events";
import { formatTime, truncate } from "@/lib/format";
import type { TimelineGeometry } from "@/lib/timeline";
import type { AgentRead } from "@/lib/types";

const LANE_H = 30;
const HEADER_H = 20;
const LABEL_W = 136;
const MARKER = 12;

const LINK_COLOR = { message: "var(--af-primary)", delegation: "var(--af-orange)" } as const;

interface TimelineCanvasProps {
  geometry: TimelineGeometry;
  scrollRef: RefObject<HTMLDivElement | null>;
  selectedAgentId: string | null;
  selectedSeq: number | null;
  agentNames: Map<string, AgentRead>;
  onSelectEvent: (seq: number | null) => void;
  onSelectAgent: (agentId: string | null, open?: boolean) => void;
}

const laneY = (lane: number) => HEADER_H + lane * LANE_H + LANE_H / 2;

/** Lanes, markers and connector lines. Lane labels stay fixed while the time axis scrolls. */
export function TimelineCanvas({
  geometry,
  scrollRef,
  selectedAgentId,
  selectedSeq,
  onSelectEvent,
  onSelectAgent,
}: TimelineCanvasProps) {
  const { lanes, markers, links, ticks, width, compressed } = geometry;
  const height = HEADER_H + lanes.length * LANE_H;
  const selectedLane = lanes.findIndex((l) => l.agentId !== null && l.agentId === selectedAgentId);

  if (lanes.length === 0) {
    return <p className="px-3 py-6 text-center text-[12px] text-fg-2">No lanes match the search.</p>;
  }

  return (
    <div className="min-h-[140px] flex-1 overflow-y-auto" data-testid="timeline">
      <div className="flex" style={{ minHeight: height }}>
        <ul className="shrink-0 border-r border-line-soft" style={{ width: LABEL_W, paddingTop: HEADER_H }} aria-label="Timeline lanes">
          {lanes.map((lane, i) => (
            <li key={lane.id} style={{ height: LANE_H }}>
              <button
                type="button"
                disabled={!lane.agentId}
                aria-pressed={i === selectedLane}
                aria-label={lane.agentId ? `Select agent ${lane.label}` : `${lane.label} lane`}
                onClick={() => lane.agentId && onSelectAgent(lane.agentId === selectedAgentId ? null : lane.agentId)}
                className={`flex h-full w-full items-center gap-2 px-2 text-left disabled:cursor-default ${
                  i === selectedLane ? "bg-panel-2" : "hover:bg-panel-2/60"
                }`}
              >
                <span aria-hidden className="h-4 w-1 shrink-0 rounded-full" style={{ background: lane.color }} />
                <span className="min-w-0">
                  <span className="block truncate text-[11px] font-medium text-fg">{lane.label}</span>
                  <span className="block truncate text-[9px] text-fg-3">{lane.sublabel}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>

        <div ref={scrollRef} className="min-w-0 flex-1 overflow-x-auto overflow-y-hidden" tabIndex={0} aria-label="Timeline, scroll horizontally">
          <div className="relative" style={{ width: Math.max(width, 200), height }}>
            <svg aria-hidden width={Math.max(width, 200)} height={height} className="absolute inset-0">
              <defs>
                {(["message", "delegation"] as const).map((kind) => (
                  <marker key={kind} id={`af-arrow-${kind}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M0,0 L8,4 L0,8 z" style={{ fill: LINK_COLOR[kind] }} />
                  </marker>
                ))}
              </defs>
              {lanes.map((lane, i) => (
                <rect
                  key={lane.id}
                  x={0}
                  y={HEADER_H + i * LANE_H}
                  width={Math.max(width, 200)}
                  height={LANE_H}
                  style={{ fill: i === selectedLane ? "rgb(168 85 247 / 0.07)" : i % 2 ? "rgb(255 255 255 / 0.012)" : "transparent" }}
                />
              ))}
              {lanes.map((lane, i) => (
                <line key={`l-${lane.id}`} x1={0} x2={Math.max(width, 200)} y1={laneY(i)} y2={laneY(i)} style={{ stroke: "var(--af-border-soft)" }} strokeDasharray="1 5" />
              ))}
              {ticks.map((t) => (
                <g key={`t-${t.x}`}>
                  <line x1={t.x} x2={t.x} y1={HEADER_H - 4} y2={height} style={{ stroke: "var(--af-border-soft)" }} strokeWidth={0.5} />
                  <text x={t.x + 3} y={12} style={{ fill: "var(--af-text-3)", fontSize: 9, fontFamily: "var(--font-mono)" }}>
                    {formatTime(t.label)}
                  </text>
                </g>
              ))}
              {links.map((link) => {
                const y1 = laneY(link.fromLane);
                const y2 = laneY(link.toLane);
                const dir = y2 > y1 ? 1 : -1;
                const active =
                  link.sequence === selectedSeq || link.fromLane === selectedLane || link.toLane === selectedLane;
                return (
                  <line
                    key={`k-${link.id}`}
                    x1={link.x}
                    x2={link.x}
                    y1={y1 + dir * (MARKER / 2)}
                    y2={y2 - dir * (MARKER / 2 + 1)}
                    style={{ stroke: LINK_COLOR[link.kind], opacity: active ? 0.95 : 0.45 }}
                    strokeWidth={active ? 1.6 : 1}
                    strokeDasharray={link.kind === "message" ? "3 2" : undefined}
                    markerEnd={`url(#af-arrow-${link.kind})`}
                  />
                );
              })}
            </svg>

            {markers.map((m) => {
              const info = CATEGORY_BY_ID[m.category];
              const selected = m.event.sequence_number === selectedSeq;
              const implicit = isImplicit(m.event);
              return (
                <button
                  key={m.event.sequence_number}
                  type="button"
                  className="absolute flex items-center justify-center rounded-sm"
                  style={{
                    left: m.x - MARKER / 2,
                    top: laneY(m.lane) - MARKER / 2,
                    width: MARKER,
                    height: MARKER,
                    opacity: implicit ? 0.45 : 1,
                    outline: selected ? "1.5px solid var(--af-text)" : undefined,
                    outlineOffset: 2,
                  }}
                  title={`${m.event.event_type} · ${formatTime(m.event.timestamp)}\n${truncate(m.event.message, 160)}`}
                  aria-label={`${info.label}: ${m.event.event_type} at ${formatTime(m.event.timestamp)}`}
                  aria-pressed={selected}
                  data-category={m.category}
                  onClick={() => onSelectEvent(selected ? null : m.event.sequence_number)}
                >
                  <EventShape info={info} size={MARKER - 2} />
                </button>
              );
            })}
          </div>
        </div>
      </div>
      {compressed ? (
        <p className="px-3 py-1 text-[10px] text-fg-3">Idle gaps are shortened. Tick labels show real times.</p>
      ) : null}
    </div>
  );
}
