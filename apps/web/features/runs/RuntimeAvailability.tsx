import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { errorMessage } from "@/lib/api";
import { COMMANDS } from "@/lib/config";
import type { SystemStatus } from "@/lib/types";

export const CLAUDE_PROVIDER = "claude_code_local";
export const API_PROVIDER = "anthropic_api";

export interface RuntimeProblems {
  ready: boolean;
  problems: string[];
}

/** What blocks a queued run from executing right now. */
export function runtimeProblems(status: SystemStatus | undefined): RuntimeProblems {
  if (!status) return { ready: false, problems: [] };
  const problems: string[] = [];
  const claude = status.providers.find((p) => p.provider === CLAUDE_PROVIDER);
  if (!claude) problems.push("The Local Claude Code provider is not reported by the API.");
  else if (claude.status !== "connected") problems.push(`Local Claude Code is ${claude.status.replace(/_/g, " ")}: ${claude.message}`);
  if (!status.runner.any_online) problems.push(`No runner is online. Start the runner: ${COMMANDS.runner}`);
  return { ready: problems.length === 0, problems };
}

interface RuntimeAvailabilityProps {
  status: SystemStatus | undefined;
  loading: boolean;
  error: unknown;
}

/** Runtime check shown before a run is submitted. */
export function RuntimeAvailability({ status, loading, error }: RuntimeAvailabilityProps) {
  if (loading) {
    return (
      <p role="status" className="rounded-md border border-line-soft bg-bg/50 px-3 py-2 text-[12px] text-fg-2">
        Checking runtime availability…
      </p>
    );
  }
  if (error || !status) {
    return (
      <div role="alert" className="rounded-md border border-red/40 bg-red/10 px-3 py-2 text-[12px] text-fg">
        Runtime status is unknown: {error ? errorMessage(error) : "no data"}.
      </div>
    );
  }
  const { ready, problems } = runtimeProblems(status);
  if (ready) {
    return (
      <p role="status" className="flex items-center gap-2 rounded-md border border-green/40 bg-green/10 px-3 py-2 text-[12px] text-fg">
        <CheckCircle2 aria-hidden size={14} className="text-green" />
        Local Claude Code is connected and a runner is online. The run starts when a runner claims it.
      </p>
    );
  }
  return (
    <div role="alert" className="rounded-md border border-yellow/40 bg-yellow/10 px-3 py-2 text-[12px] text-fg" data-testid="runtime-warning">
      <p className="flex items-center gap-2 font-medium">
        <AlertTriangle aria-hidden size={14} className="text-yellow" />
        The run will be queued, but it cannot start yet.
      </p>
      <ul className="mt-1 list-disc pl-6 text-fg-2">
        {problems.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    </div>
  );
}
