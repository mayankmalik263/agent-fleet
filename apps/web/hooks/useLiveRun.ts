// Combine the run snapshot with the live event stream into one view of the run.
import { useMemo } from "react";
import { applyEvents, type LiveRunState } from "@/lib/liveState";
import type { EventSourceLike } from "@/lib/sse";
import { useSnapshot } from "./queries";
import { useRunStream } from "./useRunStream";

export interface UseLiveRunOptions {
  createEventSource?: (url: string) => EventSourceLike;
}

export function useLiveRun(runId: string | null, options: UseLiveRunOptions = {}) {
  const snapshot = useSnapshot(runId);
  const stream = useRunStream(runId, { createEventSource: options.createEventSource });
  const live: LiveRunState | null = useMemo(
    () => (snapshot.data ? applyEvents(snapshot.data, stream.events) : null),
    [snapshot.data, stream.events],
  );
  return { snapshot, stream, live, events: stream.events };
}
