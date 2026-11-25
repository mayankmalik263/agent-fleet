"use client";
import { Bot } from "lucide-react";
import { useMemo } from "react";
import { AgentAvatar } from "@/components/ui/AgentAvatar";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useAgentSelection } from "@/hooks/useAgentSelection";
import { agentStatusTone } from "@/lib/colors";
import { durationMs, formatDateTime, formatDuration, formatTokens, NOT_AVAILABLE } from "@/lib/format";
import { taskStatsByAgent } from "@/lib/graph";
import { RunPage } from "../dashboard/RunPage";
import type { RunScopeContext } from "../dashboard/RunScope";
import { AgentInspector } from "../inspector/AgentInspector";

function AgentsBody({ ctx }: { ctx: RunScopeContext }) {
  const { live } = ctx;
  const { inspectorAgentId, selectAgent, closeInspector } = useAgentSelection();
  const agentById = useMemo(() => new Map(live.agents.map((a) => [a.id, a])), [live.agents]);
  const stats = useMemo(() => taskStatsByAgent(live.agents, live.tasks), [live.agents, live.tasks]);

  return (
    <div className="flex min-h-0 flex-1 flex-col p-3">
      <Panel title={`Agents (${live.agents.length})`} label="Selected run" className="flex-1">
        {live.agents.length === 0 ? (
          <EmptyState icon={<Bot size={22} />} title="No agents in this run yet" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-[12px]">
              <thead className="af-label">
                <tr className="border-b border-line-soft">
                  <th className="px-3 py-2 font-semibold">Agent</th>
                  <th className="px-3 py-2 font-semibold">Model</th>
                  <th className="px-3 py-2 font-semibold">Status</th>
                  <th className="px-3 py-2 font-semibold">Parent</th>
                  <th className="px-3 py-2 font-semibold">Completed tasks</th>
                  <th className="px-3 py-2 font-semibold">Tool calls</th>
                  <th className="px-3 py-2 font-semibold">Tokens</th>
                  <th className="px-3 py-2 font-semibold">Started</th>
                  <th className="px-3 py-2 font-semibold">Duration</th>
                </tr>
              </thead>
              <tbody>
                {live.agents.map((a) => {
                  const s = stats.get(a.id);
                  return (
                    <tr key={a.id} className="border-b border-line-soft/60">
                      <td className="px-3 py-1.5">
                        <button type="button" className="flex items-center gap-2 text-left hover:text-primary" onClick={() => selectAgent(a.id, true)}>
                          <AgentAvatar name={a.name} role={a.role} size={20} />
                          <span>
                            <span className="block font-medium">{a.name}</span>
                            <span className="block text-[10px] text-fg-3">{a.role}</span>
                          </span>
                        </button>
                      </td>
                      <td className="px-3 py-1.5">{a.model_alias}</td>
                      <td className="px-3 py-1.5">
                        <StatusBadge tone={agentStatusTone(a.status)} status={a.status} />
                      </td>
                      <td className="px-3 py-1.5 text-fg-2">{a.parent_agent_id ? agentById.get(a.parent_agent_id)?.name ?? NOT_AVAILABLE : "Root"}</td>
                      <td className="px-3 py-1.5 tabular-nums">{s ? `${s.completed} / ${s.total}` : NOT_AVAILABLE}</td>
                      <td className="px-3 py-1.5 tabular-nums">{a.tool_call_count}</td>
                      <td className="px-3 py-1.5 text-fg-2">{formatTokens(a.input_tokens, a.output_tokens) ?? NOT_AVAILABLE}</td>
                      <td className="af-mono px-3 py-1.5 text-fg-2">{formatDateTime(a.started_at)}</td>
                      <td className="px-3 py-1.5 tabular-nums">{a.completed_at || !a.started_at ? formatDuration(durationMs(a.started_at, a.completed_at)) : "In progress"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <AgentInspector
        agentId={inspectorAgentId}
        fallback={inspectorAgentId ? agentById.get(inspectorAgentId) : undefined}
        agents={agentById}
        runEnded={live.ended}
        onClose={closeInspector}
      />
    </div>
  );
}

export function AgentsView() {
  return (
    <RunPage label="Agents" title="Agents" description="Agents of the selected run. Durations of running agents show in the inspector.">
      {(ctx) => <AgentsBody ctx={ctx} />}
    </RunPage>
  );
}
