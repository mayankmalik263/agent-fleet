"use client";
import { useId } from "react";
import { formatDateTime, humanize } from "@/lib/format";
import type { RunListItem } from "@/lib/types";

interface RunSelectorProps {
  runs: RunListItem[];
  runId: string | null;
  onSelect: (runId: string) => void;
}

/** Drop-down list of recent runs. The newest run is the default. */
export function RunSelector({ runs, runId, onSelect }: RunSelectorProps) {
  const id = useId();
  const known = runs.some((r) => r.id === runId);
  return (
    <div className="flex min-w-0 items-center gap-2">
      <label htmlFor={id} className="af-label shrink-0">
        Run
      </label>
      <select id={id} className="af-input min-w-0 max-w-[320px] truncate" value={runId ?? ""} onChange={(e) => onSelect(e.target.value)}>
        {!known && runId ? <option value={runId}>Run {runId.slice(0, 8)}</option> : null}
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {r.title} · {humanize(r.status)} · {formatDateTime(r.created_at)}
          </option>
        ))}
      </select>
    </div>
  );
}
