"use client";
import { useMemo, useState } from "react";
import { useAgentSelection } from "@/hooks/useAgentSelection";
import { isRunningAgent } from "@/lib/liveState";
import { AgentInspector } from "../inspector/AgentInspector";
import { AgentNetworkPanel } from "../network/AgentNetworkPanel";
import { TasksPanel } from "../tasks/TasksPanel";
import { TimelinePanel } from "../timeline/TimelinePanel";
import { DashboardHeader, type HeaderStats } from "./DashboardHeader";
import { RunScope, type RunScopeContext } from "./RunScope";

type MobileView = "network" | "timeline" | "tasks";
const MOBILE_VIEWS: { id: MobileView; label: string }[] = [
  { id: "network", label: "Network" },
  { id: "timeline", label: "Timeline" },
  { id: "tasks", label: "Tasks" },
];

function DashboardBody({ ctx }: { ctx: RunScopeContext }) {
  const { live, events, runId, stream } = ctx;
  const { selectedAgentId, inspectorAgentId, selectAgent, closeInspector } = useAgentSelection();
  const [mobileView, setMobileView] = useState<MobileView>("network");
  const agentById = useMemo(() => new Map(live.agents.map((a) => [a.id, a])), [live.agents]);
  // Ignore a selection that does not belong to this run.
  const selected = selectedAgentId && agentById.has(selectedAgentId) ? selectedAgentId : null;

  const show = (view: MobileView) => (mobileView === view ? "flex" : "hidden lg:flex");

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      <div role="tablist" aria-label="Dashboard panels" className="flex gap-1 lg:hidden">
        {MOBILE_VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="tab"
            aria-selected={mobileView === v.id}
            className="af-chip flex-1 justify-center py-1"
            onClick={() => setMobileView(v.id)}
          >
            {v.label}
          </button>
        ))}
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-2">
        <AgentNetworkPanel
          agents={live.agents}
          tasks={live.tasks}
          events={events}
          runEnded={live.ended}
          live={stream.status === "open"}
          selectedAgentId={selected}
          onSelectAgent={selectAgent}
          className={`${show("network")} min-h-[480px] lg:min-h-[620px]`}
        />
        <div className={`${mobileView === "network" ? "hidden lg:grid" : "grid"} min-h-0 grid-rows-[minmax(300px,1fr)_minmax(300px,1fr)] gap-3`}>
          <TimelinePanel
            agents={live.agents}
            events={events}
            selectedAgentId={selected}
            onSelectAgent={selectAgent}
            className={show("timeline")}
          />
          <TasksPanel runId={runId} tasks={live.tasks} agents={live.agents} events={events} className={show("tasks")} />
        </div>
      </div>
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

/** Home page: the Multi-Agent Fleet dashboard. */
export function FleetDashboard() {
  return (
    <RunScope
      header={({ openNewRun, runControls, connection, live }) => {
        const stats: HeaderStats | null = live
          ? {
              totalAgents: live.agents.length,
              runningAgents: live.agents.filter(isRunningAgent).length,
              totalTasks: live.tasks.length,
              totalMessages: live.messageCount,
            }
          : null;
        return <DashboardHeader stats={stats} run={live?.run ?? null} runSelector={runControls} connection={connection} onNewRun={openNewRun} />;
      }}
    >
      {(ctx) => <DashboardBody ctx={ctx} />}
    </RunScope>
  );
}
