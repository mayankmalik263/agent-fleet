import { X } from "lucide-react";
import { DetailList } from "@/components/ui/DetailList";
import { EventShape } from "@/components/ui/EventShape";
import { CATEGORY_BY_ID, categorizeEvent, eventLink, isImplicit, payloadString } from "@/lib/events";
import { formatDateTime, NOT_AVAILABLE, shortId } from "@/lib/format";
import type { AgentRead, EventRead } from "@/lib/types";
import { usageLines } from "@/lib/usage";

interface EventDetailsProps {
  event: EventRead;
  agents: Map<string, AgentRead>;
  onClose: () => void;
}

/** Details of one timeline event. The summary is event.message only (no other content). */
export function EventDetails({ event, agents, onClose }: EventDetailsProps) {
  const name = (id: string | null | undefined) => (id ? agents.get(id)?.name ?? shortId(id) : NOT_AVAILABLE);
  const category = CATEGORY_BY_ID[categorizeEvent(event, (id) => agents.get(id)?.role)];
  const link = eventLink(event);
  const receiver = link ? link.to : null;
  const sender = link ? link.from : event.agent_id;
  const tool = payloadString(event, "tool_name");
  // Usage events carry token counts and an estimated cost. Costs are client-side estimates, not charges.
  const usage = event.event_type === "execution.usage_reported" ? usageLines(event.payload) : [];

  return (
    <div className="max-h-[45%] shrink-0 overflow-y-auto border-t border-line-soft bg-panel-2/60 px-3 py-2" role="region" aria-label="Selected event">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <EventShape info={category} size={10} />
          <span className="af-mono truncate text-fg">{event.event_type}</span>
          <span className="text-[10px] text-fg-3">#{event.sequence_number}</span>
          {isImplicit(event) ? <span className="text-[10px] text-fg-3">(closed by the system)</span> : null}
        </div>
        <button type="button" className="af-icon-btn" aria-label="Close event details" onClick={onClose}>
          <X aria-hidden size={12} />
        </button>
      </div>
      <DetailList
        className="sm:grid-cols-[auto_1fr_auto_1fr]"
        items={[
          { label: "Timestamp", value: formatDateTime(event.timestamp) },
          { label: "Sender", value: name(sender) },
          { label: "Receiver", value: receiver ? name(receiver) : NOT_AVAILABLE },
          { label: "Task", value: event.task_id ? <span className="af-mono">{shortId(event.task_id)}</span> : NOT_AVAILABLE },
          { label: "Tool", value: tool ?? NOT_AVAILABLE },
          { label: "Source", value: event.source },
          { label: "Summary", value: event.message || NOT_AVAILABLE },
          ...usage.map((u) => ({ label: u.label, value: u.value })),
        ]}
      />
    </div>
  );
}
