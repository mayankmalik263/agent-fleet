import { StatusDot } from "@/components/ui/StatusDot";
import type { Tone } from "@/lib/colors";
import type { StreamStatusInfo } from "@/lib/sse";

const VIEW: Record<StreamStatusInfo["status"], { tone: Tone; text: string }> = {
  idle: { tone: "neutral", text: "Not connected" },
  connecting: { tone: "warning", text: "Connecting" },
  open: { tone: "success", text: "Live" },
  reconnecting: { tone: "danger", text: "Reconnecting" },
  ended: { tone: "neutral", text: "Run ended · history loaded" },
};

/** Visible state of the SSE connection. */
export function ConnectionBadge({ status }: { status: StreamStatusInfo }) {
  const view = VIEW[status.status];
  const retry = status.status === "reconnecting" && status.retryInMs ? ` in ${Math.ceil(status.retryInMs / 1000)}s` : "";
  return (
    <span
      role="status"
      aria-live="polite"
      data-testid="connection-status"
      className="inline-flex items-center gap-1.5 rounded-full border border-line-soft bg-panel px-2 py-[2px] text-[11px] text-fg-2"
    >
      <StatusDot tone={view.tone} pulse={status.status === "open"} size={7} />
      <span>
        Stream: {view.text}
        {retry}
      </span>
    </span>
  );
}
