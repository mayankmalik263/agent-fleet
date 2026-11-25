"use client";
import { useMemo } from "react";
import { useAgentSelection } from "@/hooks/useAgentSelection";
import { RunPage } from "../dashboard/RunPage";
import type { RunScopeContext } from "../dashboard/RunScope";
import { AgentInspector } from "../inspector/AgentInspector";
import { AgentNetworkPanel } from "./AgentNetworkPanel";

function NetworkBody({ ctx }: { ctx: RunScopeContext }) {
  const { live, events, stream } = ctx;
  const { selectedAgentId, inspectorAgentId, selectAgent, closeInspector } = useAgentSelection();
  const agentById = useMemo(() => new Map(live.agents.map((a) => [a.id, a])), [live.agents]);
  const selected = selectedAgentId && agentById.has(selectedAgentId) ? selectedAgentId : null;
  return (
    <div className="flex min-h-0 flex-1 flex-col p-3">
      <AgentNetworkPanel
        agents={live.agents}
        tasks={live.tasks}
        events={events}
        runEnded={live.ended}
        live={stream.status === "open"}
        selectedAgentId={selected}
        onSelectAgent={selectAgent}
        className="min-h-[560px] flex-1"
      />
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

export function NetworkView() {
  return (
    <RunPage label="Agent Network" title="Agent Network" description="Delegation hierarchy of the selected run. Click an agent to inspect it.">
      {(ctx) => <NetworkBody ctx={ctx} />}
    </RunPage>
  );
}
