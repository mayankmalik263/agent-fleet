"use client";
import { AlertTriangle, Check, Copy, Download, FileText, Globe, Loader2, Maximize2, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { AgentAvatar } from "@/components/ui/AgentAvatar";
import { Markdown } from "@/components/ui/Markdown";
import { Modal } from "@/components/ui/Modal";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useRetryRun } from "@/hooks/useRetryRun";
import { errorMessage } from "@/lib/api";
import { runStatusTone, taskStatusTone } from "@/lib/colors";
import { durationMs, formatDateTime, formatDuration, shortId } from "@/lib/format";
import { buildReportMarkdown, estimatedCost } from "@/lib/report";
import type { AgentRead, RunRead, TaskRead } from "@/lib/types";

export interface ReportPanelProps {
  run: RunRead;
  tasks: TaskRead[];
  agents: AgentRead[];
  runEnded: boolean;
  className?: string;
}

function TaskResults({ tasks, agents }: { tasks: TaskRead[]; agents: Map<string, AgentRead> }) {
  if (tasks.length === 0) return null;
  return (
    <section aria-label="Task results" className="mt-4">
      <h3 className="af-label mb-1.5">Task results ({tasks.length})</h3>
      <ul className="flex flex-col gap-1.5">
        {tasks.map((task) => {
          const agent = task.assigned_agent_id ? agents.get(task.assigned_agent_id) : undefined;
          return (
            <li key={task.id}>
              <details className="group rounded-md border border-line-soft bg-panel-2/60">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-2.5 py-1.5 text-[12px]">
                  {agent ? <AgentAvatar name={agent.name} role={agent.role} size={16} /> : null}
                  <span className="min-w-0 flex-1 truncate font-medium text-fg">{task.title}</span>
                  <span className="hidden text-[11px] text-fg-3 sm:inline">{agent?.name ?? "Unassigned"}</span>
                  <StatusBadge tone={taskStatusTone(task.status)} status={task.status} />
                </summary>
                <div className="border-t border-line-soft px-3 py-2">
                  {task.result_summary ? (
                    <Markdown text={task.result_summary} className="text-[12px]" />
                  ) : (
                    <p className="text-[12px] text-fg-3">No result was submitted for this task.</p>
                  )}
                  {task.error_message ? <p className="mt-2 text-[12px] text-red">Error: {task.error_message}</p> : null}
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ReportBody({ run, tasks, agents, runEnded, onRetry, retrying }: ReportPanelProps & { onRetry: (web?: boolean) => void; retrying: boolean }) {
  const agentById = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents]);
  const done = tasks.filter((t) => t.status === "completed").length;
  const webProblem = !run.web_access && /web|internet|search tool|online/i.test(`${run.error_message ?? ""} ${run.final_summary ?? ""}`);

  let main;
  if (!runEnded) {
    main = (
      <div role="status" className="flex items-start gap-3 rounded-md border border-line-soft bg-panel-2/50 px-3 py-3 text-[12px]">
        <Loader2 aria-hidden size={16} className="mt-0.5 animate-spin text-primary" />
        <div>
          <p className="font-medium text-fg">The orchestrator is still working.</p>
          <p className="text-fg-2">
            The final report appears here when the run finishes. {tasks.length ? `${done} of ${tasks.length} tasks are done.` : "No tasks yet."}
          </p>
        </div>
      </div>
    );
  } else if (run.status === "completed" && run.final_summary?.trim()) {
    main = <Markdown text={run.final_summary} />;
  } else {
    const failed = run.status === "failed";
    main = (
      <div role="alert" className={`rounded-md border px-3 py-2.5 text-[12px] ${failed ? "border-red/50 bg-red/10" : "border-line bg-panel-2/60"}`}>
        <p className="flex items-center gap-2 font-semibold text-fg">
          <AlertTriangle aria-hidden size={14} className={failed ? "text-red" : "text-fg-2"} />
          {failed ? "The run failed. No final report was written." : run.status === "cancelled" ? "The run was cancelled." : "The run ended without a report."}
        </p>
        {run.error_message ? <Markdown text={run.error_message} className="mt-1.5 text-[12px]" /> : null}
        <div className="mt-2.5 flex flex-wrap gap-2">
          {webProblem ? (
            <button type="button" className="af-btn af-btn-primary" disabled={retrying} onClick={() => onRetry(true)}>
              <Globe aria-hidden size={13} /> Retry with web access
            </button>
          ) : null}
          <button type="button" className={`af-btn ${webProblem ? "" : "af-btn-primary"}`} disabled={retrying} onClick={() => onRetry()}>
            <RotateCcw aria-hidden size={13} /> Retry run
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-3">
      {main}
      <TaskResults tasks={tasks} agents={agentById} />
    </div>
  );
}

/** Panel D: the final report of the run, with the task results and retry actions. */
export function ReportPanel({ run, tasks, agents, runEnded, className = "" }: ReportPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const retry = useRetryRun(run.id);
  const markdown = useMemo(() => buildReportMarkdown(run, tasks, agents), [run, tasks, agents]);
  const cost = estimatedCost(run);
  const duration = durationMs(run.started_at, run.completed_at);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `agent-fleet-report-${shortId(run.id)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };
  const onRetry = (web?: boolean) => retry.mutate(web === undefined ? {} : { web_access: web });

  const body = <ReportBody run={run} tasks={tasks} agents={agents} runEnded={runEnded} onRetry={onRetry} retrying={retry.isPending} />;

  return (
    <Panel
      id="final-report"
      label="Panel D"
      title="Final Report"
      className={className}
      bodyClassName="flex flex-col"
      actions={
        <>
          <StatusBadge tone={runStatusTone(run.status)} status={run.status} pulse={!runEnded} />
          <button type="button" className="af-icon-btn" aria-label="Copy report as Markdown" title={copied ? "Copied" : "Copy as Markdown"} onClick={() => void copy()}>
            {copied ? <Check aria-hidden size={13} /> : <Copy aria-hidden size={13} />}
          </button>
          <button type="button" className="af-icon-btn" aria-label="Download report as Markdown" title="Download .md" onClick={download}>
            <Download aria-hidden size={13} />
          </button>
          <button type="button" className="af-icon-btn" aria-label="Open report in a large window" title="Open large" onClick={() => setExpanded(true)}>
            <Maximize2 aria-hidden size={13} />
          </button>
          {runEnded && run.source !== "claude_code" ? (
            <button type="button" className="af-btn" disabled={retry.isPending} onClick={() => onRetry()} title="Queue a new run with the same task and settings">
              <RotateCcw aria-hidden size={13} /> {retry.isPending ? "Queuing…" : "Retry run"}
            </button>
          ) : null}
        </>
      }
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line-soft px-4 py-1.5 text-[11px] text-fg-3">
        <span className="flex items-center gap-1">
          <FileText aria-hidden size={12} /> {run.title}
        </span>
        <span>Model: {run.orchestrator_model}</span>
        <span className="flex items-center gap-1">
          <Globe aria-hidden size={12} /> Web access: {run.web_access ? "on" : "off"}
        </span>
        {run.completed_at ? <span>Finished: {formatDateTime(run.completed_at)}</span> : null}
        {duration !== null && runEnded ? <span>Duration: {formatDuration(duration)}</span> : null}
        {cost !== null ? <span title="Client-side estimate from Claude Code. Not an invoice.">Estimated cost (client-side): ${cost.toFixed(2)}</span> : null}
        {run.retry_of_run_id ? (
          <Link href={`?run=${encodeURIComponent(run.retry_of_run_id)}`} className="text-primary underline underline-offset-2">
            Retry of run {shortId(run.retry_of_run_id)}
          </Link>
        ) : null}
      </div>
      {retry.isError ? (
        <p role="alert" className="border-b border-line-soft px-4 py-1.5 text-[12px] text-red">
          Retry failed: {errorMessage(retry.error)}
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto">{body}</div>
      <Modal open={expanded} onClose={() => setExpanded(false)} title={`Final Report — ${run.title}`} width={960}>
        <div className="-mx-4 max-h-[75vh] overflow-y-auto">{body}</div>
      </Modal>
    </Panel>
  );
}
