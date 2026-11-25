import { Plus } from "lucide-react";
import type { ReactNode } from "react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { runStatusTone } from "@/lib/colors";
import type { RunRead } from "@/lib/types";

export interface HeaderStats {
  totalAgents: number;
  runningAgents: number;
  totalTasks: number;
  totalMessages: number;
}

interface DashboardHeaderProps {
  stats: HeaderStats | null;
  run: RunRead | null;
  runSelector?: ReactNode;
  connection?: ReactNode;
  onNewRun: () => void;
}

function Stat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="min-w-[92px] rounded-md border border-line-soft bg-panel px-3 py-1.5">
      <div className="af-label">{label}</div>
      <div className="text-[18px] leading-6 font-semibold tabular-nums text-fg" aria-label={`${label}: ${value ?? "not available"}`}>
        {value ?? "—"}
      </div>
    </div>
  );
}

/** Global header: title, run selector, live stats and the New Run button. */
export function DashboardHeader({ stats, run, runSelector, connection, onNewRun }: DashboardHeaderProps) {
  return (
    <header className="flex flex-col gap-3 border-b border-line-soft px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="af-label">Agent Fleet · Agent Network / Time</div>
          <h1 className="text-[20px] leading-7 font-semibold tracking-tight">Multi-Agent Fleet</h1>
          <p className="text-[12px] text-fg-2">
            Live view of agents, delegation, messages and tasks for one run. All numbers come from the local Agent Fleet API.
          </p>
        </div>
        <button type="button" className="af-btn af-btn-primary px-3 py-1.5 text-[13px]" onClick={onNewRun}>
          <Plus aria-hidden size={14} /> New Run
        </button>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {runSelector}
          {run ? <StatusBadge tone={runStatusTone(run.status)} status={run.status} pulse={run.status === "running"} /> : null}
          {connection}
        </div>
        <div className="flex flex-wrap gap-2" aria-label="Run statistics" role="group">
          <Stat label="Total agents" value={stats?.totalAgents ?? null} />
          <Stat label="Running agents" value={stats?.runningAgents ?? null} />
          <Stat label="Work items" value={stats?.totalTasks ?? null} />
          <Stat label="Messages" value={stats?.totalMessages ?? null} />
        </div>
      </div>
    </header>
  );
}
