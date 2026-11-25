"use client";
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  type NodeMouseHandler,
  type NodeTypes,
} from "@xyflow/react";
import { Crosshair, Maximize2, Network } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { SearchInput } from "@/components/ui/SearchInput";
import { useNow } from "@/hooks/useNow";
import { eventLink } from "@/lib/events";
import { toMs } from "@/lib/format";
import { agentMatches, buildGraph, type AgentFlowNode } from "@/lib/graph";
import type { AgentRead, EventRead, TaskRead } from "@/lib/types";
import { AgentNode } from "./AgentNode";
import { NetworkLegend } from "./NetworkLegend";

const nodeTypes: NodeTypes = { agent: AgentNode } as unknown as NodeTypes;

/** A message edge pulses for this long after the message. */
const RECENT_MESSAGE_MS = 6000;

export interface AgentNetworkPanelProps {
  agents: AgentRead[];
  tasks: TaskRead[];
  events: EventRead[];
  runEnded: boolean;
  live: boolean;
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string | null, open?: boolean) => void;
  className?: string;
}

function NetworkCanvas(props: AgentNetworkPanelProps & { search: string }) {
  const { agents, tasks, events, runEnded, live, selectedAgentId, onSelectAgent, search } = props;
  const { fitView } = useReactFlow();
  const now = useNow(live && !runEnded, 1000);

  // Message pairs with a message in the last few seconds. Used for the "recent message" pulse.
  const recentKey = useMemo(() => {
    if (!live || runEnded) return "";
    const pairs = new Set<string>();
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const e = events[i];
      const ms = toMs(e.timestamp);
      if (ms === null || now - ms > RECENT_MESSAGE_MS) break;
      const link = eventLink(e);
      if (link?.kind === "message") pairs.add(`${link.from}|${link.to}`);
    }
    return [...pairs].sort().join(",");
  }, [events, now, live, runEnded]);

  const graph = useMemo(
    () =>
      buildGraph({
        agents,
        tasks,
        events,
        selectedAgentId,
        search,
        runEnded,
        recentMessagePairs: new Set(recentKey ? recentKey.split(",") : []),
      }),
    [agents, tasks, events, selectedAgentId, search, runEnded, recentKey],
  );

  // Fit the view when the nodes are measured, and again when agents are added or removed (re-layout).
  const agentCount = agents.length;
  const initialized = useNodesInitialized();
  useEffect(() => {
    if (agentCount === 0 || !initialized) return;
    const id = requestAnimationFrame(() => void fitView({ padding: "12%", duration: 250 }));
    return () => cancelAnimationFrame(id);
  }, [agentCount, initialized, fitView]);

  const onNodeClick: NodeMouseHandler<AgentFlowNode> = (_event, node) => onSelectAgent(node.id, true);

  return (
    <ReactFlow<AgentFlowNode>
      nodes={graph.nodes}
      edges={graph.edges}
      nodeTypes={nodeTypes}
      onNodeClick={onNodeClick}
      onPaneClick={() => onSelectAgent(null)}
      nodesDraggable={false}
      nodesConnectable={false}
      edgesFocusable={false}
      fitView
      fitViewOptions={{ padding: "12%" }}
      minZoom={0.2}
      maxZoom={1.75}
      forceColorMode="dark"
      proOptions={{ hideAttribution: true }}
      className="af-flow"
    >
      <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#34333a" />
      <Controls showInteractive={false} position="bottom-right" />
    </ReactFlow>
  );
}

function FocusButtons({ agents, selectedAgentId, search, onSelectAgent }: Pick<AgentNetworkPanelProps, "agents" | "selectedAgentId" | "onSelectAgent"> & { search: string }) {
  const { fitView } = useReactFlow();
  const focus = (id: string) => void fitView({ nodes: [{ id }], padding: "30%", maxZoom: 1.2, duration: 300 });
  const firstMatch = search ? agents.find((a) => agentMatches(a, search)) : undefined;
  return (
    <>
      <button
        type="button"
        className="af-icon-btn"
        aria-label="Focus selected agent"
        title="Focus selected agent"
        disabled={!selectedAgentId && !firstMatch}
        onClick={() => {
          const id = selectedAgentId ?? firstMatch?.id;
          if (!id) return;
          if (!selectedAgentId) onSelectAgent(id);
          focus(id);
        }}
      >
        <Crosshair aria-hidden size={13} />
      </button>
      <button
        type="button"
        className="af-icon-btn"
        aria-label="Fit view"
        title="Fit view"
        onClick={() => void fitView({ padding: "12%", duration: 250 })}
      >
        <Maximize2 aria-hidden size={13} />
      </button>
    </>
  );
}

/** Panel A: the agent network graph. */
export function AgentNetworkPanel(props: AgentNetworkPanelProps) {
  const { agents, className = "", onSelectAgent } = props;
  const [search, setSearch] = useState("");
  const matches = search ? agents.filter((a) => agentMatches(a, search)) : [];

  return (
    <ReactFlowProvider>
      <Panel
        id="agent-network"
        label="Panel A"
        title="Agent Network"
        className={className}
        bodyClassName="flex flex-col"
        actions={
          <>
            <form
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                if (matches[0]) onSelectAgent(matches[0].id, true);
              }}
            >
              <SearchInput value={search} onChange={setSearch} label="Search agents in network" placeholder="Search agents" className="w-36" />
            </form>
            {search ? (
              <span className="text-[10px] text-fg-3" aria-live="polite">
                {matches.length} match{matches.length === 1 ? "" : "es"}
              </span>
            ) : null}
            <FocusButtons agents={agents} selectedAgentId={props.selectedAgentId} search={search} onSelectAgent={onSelectAgent} />
          </>
        }
      >
        {agents.length === 0 ? (
          <EmptyState icon={<Network size={22} />} title="No agents in this run yet" className="flex-1">
            Agents appear here when the orchestrator registers them. The graph updates live.
          </EmptyState>
        ) : (
          <div className="relative min-h-[320px] flex-1" aria-label="Agent network graph" role="region">
            <NetworkCanvas {...props} search={search} />
          </div>
        )}
        <div className="border-t border-line-soft">
          <NetworkLegend />
        </div>
      </Panel>
    </ReactFlowProvider>
  );
}
