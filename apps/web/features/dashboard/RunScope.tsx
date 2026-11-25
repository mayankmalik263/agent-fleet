"use client";
import { useState, type ReactNode } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { useLiveRun } from "@/hooks/useLiveRun";
import { useSelectedRun } from "@/hooks/useSelectedRun";
import type { LiveRunState } from "@/lib/liveState";
import type { StreamStatusInfo } from "@/lib/sse";
import type { EventRead, RunListItem, RunSnapshot } from "@/lib/types";
import { NewRunModal } from "../runs/NewRunModal";
import { RunSelector } from "../runs/RunSelector";
import { ConnectionBadge } from "./ConnectionBadge";
import { NoRunsState } from "./NoRunsState";

export interface RunScopeContext {
  runId: string;
  runs: RunListItem[];
  snapshot: RunSnapshot;
  live: LiveRunState;
  events: EventRead[];
  stream: StreamStatusInfo;
  openNewRun: () => void;
  /** Run selector and connection badge, ready to place in a header. */
  runControls: ReactNode;
  connection: ReactNode;
}

interface RunScopeProps {
  /** Header shown in every state. Receives the context when a run is loaded. */
  header: (ctx: { openNewRun: () => void; runControls: ReactNode; connection: ReactNode; live: LiveRunState | null }) => ReactNode;
  children: (ctx: RunScopeContext) => ReactNode;
}

function Loading({ text }: { text: string }) {
  return (
    <div role="status" className="flex flex-1 items-center justify-center px-6 py-16 text-[12px] text-fg-2">
      <span className="af-pulse mr-2 inline-block h-2 w-2 rounded-full bg-primary" aria-hidden />
      {text}
    </div>
  );
}

/**
 * Resolves the selected run (?run= or the latest), loads its snapshot and live events,
 * and handles the loading, empty and error states for every page that shows one run.
 */
export function RunScope({ header, children }: RunScopeProps) {
  const { runId, runs, selectRun } = useSelectedRun();
  const { snapshot, stream, live, events } = useLiveRun(runId);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const openNewRun = () => setNewRunOpen(true);

  const runList = runs.data?.items ?? [];
  const runControls = runId ? <RunSelector runs={runList} runId={runId} onSelect={selectRun} /> : null;
  const connection = runId ? <ConnectionBadge status={stream.status} /> : null;

  let body: ReactNode;
  if (runs.isError && !runs.data) {
    body = <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />;
  } else if (runs.isPending) {
    body = <Loading text="Loading runs…" />;
  } else if (!runId) {
    body = <NoRunsState onNewRun={openNewRun} />;
  } else if (snapshot.isError && !snapshot.data) {
    body = <ErrorState error={snapshot.error} title="This run could not be loaded" onRetry={() => void snapshot.refetch()} />;
  } else if (!snapshot.data || !live) {
    body = <Loading text="Loading run snapshot…" />;
  } else {
    body = children({
      runId,
      runs: runList,
      snapshot: snapshot.data,
      live,
      events,
      stream: stream.status,
      openNewRun,
      runControls,
      connection,
    });
  }

  return (
    <>
      {header({ openNewRun, runControls, connection, live })}
      {body}
      <NewRunModal
        open={newRunOpen}
        onClose={() => setNewRunOpen(false)}
        onCreated={(run) => {
          setNewRunOpen(false);
          selectRun(run.id);
        }}
      />
    </>
  );
}
