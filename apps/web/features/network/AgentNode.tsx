"use client";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import { AgentAvatar } from "@/components/ui/AgentAvatar";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusDot } from "@/components/ui/StatusDot";
import { useNow } from "@/hooks/useNow";
import { agentStatusTone } from "@/lib/colors";
import { durationMs, formatDuration, formatTokens, humanize, NOT_AVAILABLE } from "@/lib/format";
import type { AgentFlowNode } from "@/lib/graph";
import { AGENT_ACTIVE } from "@/lib/types";

function Metric({ label, value, muted = false }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[9px] font-medium tracking-wide text-fg-3 uppercase">{label}</div>
      <div className={`truncate text-[11px] tabular-nums ${muted ? "text-fg-3" : "text-fg"}`}>{value}</div>
    </div>
  );
}

/** Custom React Flow node for one agent. */
function AgentNodeView({ data }: NodeProps<AgentFlowNode>) {
  const { agent, accent, stats, selected, dimmed, matched, runEnded } = data;
  const live = !runEnded && AGENT_ACTIVE.includes(agent.status) && !agent.completed_at;
  const now = useNow(live);
  const duration = durationMs(agent.started_at, agent.completed_at, live ? now : undefined);
  const tokens = formatTokens(agent.input_tokens, agent.output_tokens);
  const tone = agentStatusTone(agent.status);

  return (
    <div
      className="relative w-[248px] overflow-hidden rounded-[10px] border bg-panel-2 px-3 py-2.5 text-left shadow-lg transition-opacity"
      style={{
        borderColor: selected ? accent : matched ? "var(--af-yellow)" : "var(--af-border-soft)",
        boxShadow: selected ? `0 0 0 1px ${accent}, 0 8px 24px rgb(0 0 0 / 0.35)` : undefined,
        opacity: dimmed ? 0.4 : 1,
      }}
      data-testid={`agent-node-${agent.id}`}
    >
      <span aria-hidden className="absolute inset-x-0 top-0 h-[2px]" style={{ background: accent }} />
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <div className="flex items-center gap-2">
        <AgentAvatar name={agent.name} role={agent.role} size={28} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-semibold text-fg" title={agent.name}>
            {agent.name}
          </div>
          <div className="truncate text-[10px] text-fg-2">
            <span style={{ color: accent }}>{agent.role}</span> · {agent.model_alias}
          </div>
        </div>
        <span className="flex items-center gap-1 text-[10px] text-fg-2" title={`Status: ${agent.status}`}>
          <StatusDot tone={tone} pulse={live} label={`Status ${agent.status}`} size={7} />
          {humanize(agent.status)}
        </span>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
        <Metric label="Tokens" value={tokens ?? NOT_AVAILABLE} muted={!tokens} />
        <Metric label={live ? "Duration (live)" : "Duration"} value={formatDuration(duration)} muted={duration === null} />
        <Metric label="Completed tasks" value={`${stats.completed} / ${stats.total}`} />
        <Metric label="Tool calls" value={String(agent.tool_call_count)} />
      </div>

      {stats.currentProgress !== null ? (
        <div className="mt-2">
          <div className="mb-0.5 flex justify-between text-[9px] text-fg-3">
            <span className="truncate pr-2">{stats.currentTaskTitle ?? "Current task"}</span>
            <span className="tabular-nums">{stats.currentProgress}%</span>
          </div>
          <ProgressBar value={stats.currentProgress} color={accent} label={`Task progress for ${agent.name}`} />
        </div>
      ) : null}
      <Handle type="source" position={Position.Bottom} isConnectable={false} />
    </div>
  );
}

export const AgentNode = memo(AgentNodeView);
