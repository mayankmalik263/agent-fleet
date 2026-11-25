import { EventShape } from "@/components/ui/EventShape";
import { EVENT_CATEGORIES } from "@/lib/events";

/** Legend for event colours and edge styles. */
export function NetworkLegend() {
  return (
    <div aria-label="Legend" role="group" className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-1.5 text-[10px] text-fg-2">
      {EVENT_CATEGORIES.slice(0, 7).map((c) => (
        <span key={c.id} className="inline-flex items-center gap-1">
          <EventShape info={c} size={9} />
          {c.label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1" title="Solid arrow: parent agent delegates to child agent">
        <svg aria-hidden width="18" height="8">
          <line x1="0" y1="4" x2="18" y2="4" style={{ stroke: "var(--af-text-2)" }} strokeWidth="1.5" />
        </svg>
        Parent → child
      </span>
      <span className="inline-flex items-center gap-1" title="Dotted line: messages between agents">
        <svg aria-hidden width="18" height="8">
          <line x1="0" y1="4" x2="18" y2="4" style={{ stroke: "var(--af-primary)" }} strokeWidth="1.5" strokeDasharray="2 3" />
        </svg>
        Messages
      </span>
    </div>
  );
}
