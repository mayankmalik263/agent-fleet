"use client";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import { AgentAvatar } from "@/components/ui/AgentAvatar";
import { DetailList } from "@/components/ui/DetailList";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useRunMessages } from "@/hooks/queries";
import { taskStatusTone, TONE_COLOR } from "@/lib/colors";
import { formatDateTime, formatTime, humanize, NOT_AVAILABLE, truncate } from "@/lib/format";
import type { AgentRead, EventRead, TaskRead } from "@/lib/types";

interface TaskCardProps {
  task: TaskRead;
  runId: string;
  agents: Map<string, AgentRead>;
  latestEvent?: EventRead;
}

function RelatedMessages({ runId, taskId, agents }: { runId: string; taskId: string; agents: Map<string, AgentRead> }) {
  const messages = useRunMessages(runId);
  if (messages.isPending) return <p className="text-[11px] text-fg-3">Loading messages…</p>;
  if (messages.isError) return <p className="text-[11px] text-red">Messages could not be loaded.</p>;
  const related = messages.data.items.filter((m) => m.task_id === taskId);
  if (related.length === 0) return <p className="text-[11px] text-fg-3">No messages for this task.</p>;
  return (
    <ul className="flex flex-col gap-1">
      {related.slice(-8).map((m) => (
        <li key={m.id} className="rounded bg-bg/60 px-2 py-1 text-[11px]">
          <span className="text-fg-2">
            {agents.get(m.sender_agent_id ?? "")?.name ?? "Unknown"} → {m.receiver_agent_id ? agents.get(m.receiver_agent_id)?.name ?? "Unknown" : "all"}
          </span>{" "}
          <span className="text-fg-3">· {humanize(m.message_type)} · {formatTime(m.timestamp)}</span>
          <p className="text-fg">{truncate(m.content, 240)}</p>
        </li>
      ))}
    </ul>
  );
}

/** Compact, expandable task card. */
export function TaskCard({ task, runId, agents, latestEvent }: TaskCardProps) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  const assignee = task.assigned_agent_id ? agents.get(task.assigned_agent_id) : undefined;
  const creator = task.created_by_agent_id ? agents.get(task.created_by_agent_id) : undefined;
  const tone = taskStatusTone(task.status);

  return (
    <article
      className="rounded-md border border-line-soft bg-panel-2/70"
      style={{ borderLeft: `2px solid ${TONE_COLOR[tone]}` }}
      aria-label={`Task ${task.title}`}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 px-2.5 py-2 text-left"
      >
        {open ? <ChevronDown aria-hidden size={13} className="mt-0.5 text-fg-3" /> : <ChevronRight aria-hidden size={13} className="mt-0.5 text-fg-3" />}
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-fg">{task.title}</span>
            <StatusBadge tone={tone} status={task.status} />
          </span>
          <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-fg-2">
            {assignee ? <AgentAvatar name={assignee.name} role={assignee.role} size={14} /> : null}
            <span className="truncate">{assignee ? `${assignee.name} · ${assignee.model_alias}` : "Unassigned"}</span>
          </span>
          {task.description ? <span className="mt-1 block text-[11px] text-fg-2">{truncate(task.description, 140)}</span> : null}
          {task.progress_percentage !== null ? (
            <span className="mt-1.5 flex items-center gap-2">
              <ProgressBar value={task.progress_percentage} label={`Progress of ${task.title}`} />
              <span className="af-mono text-fg-2">{task.progress_percentage}%</span>
            </span>
          ) : null}
          <span className="mt-1 block truncate text-[10px] text-fg-3">
            Latest update:{" "}
            {latestEvent ? `${truncate(latestEvent.message, 90)} · ${formatTime(latestEvent.timestamp)}` : formatTime(task.updated_at)}
          </span>
        </span>
      </button>
      {open ? (
        <div id={bodyId} className="space-y-2 border-t border-line-soft px-3 py-2">
          <p className="whitespace-pre-wrap text-[12px] text-fg">{task.description || "No description."}</p>
          <DetailList
            items={[
              { label: "Delegated by", value: creator?.name ?? NOT_AVAILABLE },
              { label: "Assigned to", value: assignee ? `${assignee.name} (${assignee.role})` : NOT_AVAILABLE },
              { label: "Priority", value: humanize(task.priority) },
              { label: "Started", value: formatDateTime(task.started_at) },
              { label: "Completed", value: formatDateTime(task.completed_at) },
              { label: "Result", value: task.result_summary ?? NOT_AVAILABLE },
              {
                label: "Error",
                value: task.error_message ? <span className="text-red">{task.error_message}</span> : "None",
              },
            ]}
          />
          <div>
            <div className="af-label mb-1">Related messages</div>
            <RelatedMessages runId={runId} taskId={task.id} agents={agents} />
          </div>
        </div>
      ) : null}
    </article>
  );
}
