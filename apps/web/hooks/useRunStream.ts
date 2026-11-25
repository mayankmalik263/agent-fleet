// Subscribe to the SSE stream of one run and keep a merged, ordered event log.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useReducer, useRef } from "react";
import { mergeEvents } from "@/lib/events";
import { RunEventStream, type EventSourceLike, type StreamStatusInfo } from "@/lib/sse";
import type { EventRead, RunSnapshot } from "@/lib/types";
import { queryKeys } from "./queries";

interface State {
  runId: string | null;
  events: EventRead[];
  status: StreamStatusInfo;
}

type Action =
  | { type: "events"; runId: string; events: EventRead[] }
  | { type: "status"; runId: string; status: StreamStatusInfo };

const IDLE: StreamStatusInfo = { status: "idle", attempt: 0 };

function reducer(state: State, action: Action): State {
  // A message for another run starts a fresh log for that run.
  const base: State = state.runId === action.runId ? state : { runId: action.runId, events: [], status: IDLE };
  if (action.type === "events") {
    const events = mergeEvents(base.events, action.events);
    return events === base.events && base === state ? state : { ...base, events };
  }
  return { ...base, status: action.status };
}

export interface RunStreamResult {
  events: EventRead[];
  status: StreamStatusInfo;
}

export interface UseRunStreamOptions {
  createEventSource?: (url: string) => EventSourceLike;
  /** Delay for the debounced snapshot refresh. */
  refreshDelayMs?: number;
  /** Upper bound: refresh at least this often while events keep arriving. */
  refreshMaxWaitMs?: number;
}

export function useRunStream(runId: string | null, options: UseRunStreamOptions = {}): RunStreamResult {
  const [state, dispatch] = useReducer(reducer, { runId: null, events: [], status: IDLE });
  const queryClient = useQueryClient();
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  useEffect(() => {
    if (!runId) return;
    const { refreshDelayMs = 400, refreshMaxWaitMs = 2500, createEventSource } = optionsRef.current;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let firstPending: number | null = null;
    let runChanged = false;

    // Debounced refresh of the snapshot (and of lists that depend on run state).
    const refresh = () => {
      timer = null;
      firstPending = null;
      void queryClient.invalidateQueries({ queryKey: queryKeys.snapshot(runId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.agentsAll });
      void queryClient.invalidateQueries({ queryKey: queryKeys.messages(runId) });
      if (runChanged) {
        runChanged = false;
        void queryClient.invalidateQueries({ queryKey: queryKeys.runsAll });
        void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      }
    };
    const scheduleRefresh = () => {
      const now = Date.now();
      firstPending ??= now;
      if (timer) clearTimeout(timer);
      const wait = Math.max(0, Math.min(refreshDelayMs, firstPending + refreshMaxWaitMs - now));
      timer = setTimeout(refresh, wait);
    };

    const stream = new RunEventStream({
      runId,
      after: 0,
      createEventSource,
      onEvents: (events) => {
        dispatch({ type: "events", runId, events });
        // Refresh only when the events are newer than the cached snapshot.
        const known = queryClient.getQueryData<RunSnapshot>(queryKeys.snapshot(runId))?.run.event_count ?? 0;
        const fresh = events.filter((e) => e.sequence_number > known);
        if (fresh.length === 0) return;
        if (fresh.some((e) => e.event_type.startsWith("run."))) runChanged = true;
        scheduleRefresh();
      },
      onStatus: (status) => dispatch({ type: "status", runId, status }),
    });
    stream.start();
    return () => {
      stream.stop();
      if (timer) clearTimeout(timer);
    };
  }, [runId, queryClient]);

  if (!runId || state.runId !== runId) return { events: [], status: IDLE };
  return { events: state.events, status: state.status };
}
