import { Activity, Plug, Play, Server } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { COMMANDS } from "@/lib/config";

function Step({ n, icon, title, children }: { n: number; icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <li className="af-panel flex gap-3 p-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-panel-2 text-primary" aria-hidden>
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-[12px] font-semibold">
          {n}. {title}
        </p>
        <div className="mt-0.5 text-[12px] text-fg-2">{children}</div>
      </div>
    </li>
  );
}

const Code = ({ children }: { children: ReactNode }) => <code className="af-mono rounded bg-bg px-1 py-0.5 text-fg">{children}</code>;

/** Shown when the API has no runs yet. */
export function NoRunsState({ onNewRun }: { onNewRun: () => void }) {
  return (
    <section aria-labelledby="no-runs-title" className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-10">
      <div>
        <div className="af-label">Getting started</div>
        <h2 id="no-runs-title" className="text-[16px] font-semibold">
          No runs yet
        </h2>
        <p className="text-[12px] text-fg-2">Agent Fleet records runs from Claude Code and from this dashboard. Follow these steps to see your first run.</p>
      </div>
      <ol className="grid gap-2 sm:grid-cols-2">
        <Step n={1} icon={<Plug size={14} />} title="Connect Claude Code">
          The project <Code>.mcp.json</Code> registers the <Code>agent-fleet</Code> MCP server. Check it with <Code>{COMMANDS.mcpList}</Code>.
        </Step>
        <Step n={2} icon={<Play size={14} />} title="Start a first run">
          Click <strong className="text-fg">New Run</strong>, or ask Claude Code to record an orchestration.
        </Step>
        <Step n={3} icon={<Server size={14} />} title="Start the runner">
          Queued dashboard runs need a runner: <Code>{COMMANDS.runner}</Code>.
        </Step>
        <Step n={4} icon={<Activity size={14} />} title="Review execution status">
          Open <Link className="text-primary underline-offset-2 hover:underline" href="/providers">Providers</Link> to check Claude Code and the runner.
        </Step>
      </ol>
      <div>
        <button type="button" className="af-btn af-btn-primary" onClick={onNewRun}>
          New Run
        </button>
      </div>
    </section>
  );
}
