"use client";
import type { ReactNode } from "react";
import { AgentAvatar } from "@/components/ui/AgentAvatar";
import { DetailList } from "@/components/ui/DetailList";
import { Drawer } from "@/components/ui/Drawer";
import { ErrorState } from "@/components/ui/ErrorState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useAgentDetails } from "@/hooks/queries";
import { useNow } from "@/hooks/useNow";
import { agentStatusTone, taskStatusTone } from "@/lib/colors";
import { isImplicit, payloadString } from "@/lib/events";
import { durationMs, formatCount, formatDateTime, formatDuration, formatTime, humanize, NOT_AVAILABLE, truncate } from "@/lib/format";
import { AGENT_ACTIVE, type AgentDetails, type AgentRead } from "@/lib/types";

interface AgentInspectorProps {
  agentId: string | null;
  /** Agent data from the live run view. Shown while the details load. */
  fallback?: AgentRead;
  /** Other agents of the run, to resolve names. */
  agents: Map<string, AgentRead>;
  runEnded: boolean;
  onClose: () => void;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="af-label mb-1.5">{title}</h3>
      {children}
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-[11px] text-fg-3">{children}</p>;
}

function InspectorBody({ details, agents, runEnded }: { details: AgentDetails; agents: Map<string, AgentRead>; runEnded: boolean }) {
  const { agent, parent, current_task: currentTask, children, recent_messages: messages, tool_events: tools, tasks } = details;
  const live = !runEnded && AGENT_ACTIVE.includes(agent.status) && !agent.completed_at;
  const now = useNow(live);
  const name = (id: string | null) => (id ? agents.get(id)?.name ?? "Unknown agent" : "Broadcast");
  const hasUsage = agent.input_tokens !== null || agent.output_tokens !== null;
  const results = tasks.filter((t) => t.result_summary || t.error_message);

  return (
    <>
      <DetailList
        items={[
          { label: "Role", value: agent.role },
          { label: "Model", value: agent.model_alias },
          { label: "Status", value: <StatusBadge tone={agentStatusTone(agent.status)} status={agent.status} pulse={live} /> },
          { label: "Parent", value: parent ? `${parent.name} (${parent.role})` : "None (root agent)" },
          { label: "Current task", value: currentTask ? currentTask.title : "None" },
          { label: "Started", value: formatDateTime(agent.started_at) },
          { label: "Completed", value: agent.completed_at ? formatDateTime(agent.completed_at) : live ? "Running" : NOT_AVAILABLE },
          {
            label: live ? "Duration (live)" : "Duration",
            value: formatDuration(durationMs(agent.started_at, agent.completed_at, live ? now : undefined)),
          },
          { label: "Children", value: children.length ? children.map((c) => c.name).join(", ") : "None" },
          { label: "Tool calls", value: String(agent.tool_call_count) },
        ]}
      />

      <Section title="Usage">
        {hasUsage ? (
          <DetailList
            items={[
              { label: "Input tokens", value: agent.input_tokens !== null ? formatCount(agent.input_tokens) : NOT_AVAILABLE },
              { label: "Output tokens", value: agent.output_tokens !== null ? formatCount(agent.output_tokens) : NOT_AVAILABLE },
            ]}
          />
        ) : (
          <Empty>Not available. The runtime did not report token usage for this agent.</Empty>
        )}
      </Section>

      <Section title={`Tasks (${tasks.length})`}>
        {tasks.length === 0 ? (
          <Empty>No tasks assigned.</Empty>
        ) : (
          <ul className="flex flex-col gap-1">
            {tasks.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-2 text-[12px]">
                <span className="min-w-0 truncate">{t.title}</span>
                <StatusBadge tone={taskStatusTone(t.status)} status={t.status} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Task results">
        {results.length === 0 ? (
          <Empty>No results submitted yet.</Empty>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {results.map((t) => (
              <li key={t.id} className="rounded bg-bg/60 px-2 py-1.5 text-[11px]">
                <div className="font-medium text-fg">{t.title}</div>
                {t.result_summary ? <p className="text-fg-2">{truncate(t.result_summary, 400)}</p> : null}
                {t.error_message ? <p className="text-red">{truncate(t.error_message, 300)}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Recent messages (${messages.length})`}>
        {messages.length === 0 ? (
          <Empty>No messages.</Empty>
        ) : (
          <ul className="flex flex-col gap-1">
            {messages.slice(-12).map((m) => (
              <li key={m.id} className="rounded bg-bg/60 px-2 py-1 text-[11px]">
                <div className="text-fg-2">
                  {name(m.sender_agent_id)} → {name(m.receiver_agent_id)}{" "}
                  <span className="text-fg-3">· {humanize(m.message_type)} · {formatTime(m.timestamp)}</span>
                </div>
                <p className="text-fg">{truncate(m.content, 240)}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Tool activity (${tools.length})`}>
        {tools.length === 0 ? (
          <Empty>No tool events recorded.</Empty>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {tools.slice(-15).map((e) => (
              <li key={e.id} className={`flex gap-2 text-[11px] ${isImplicit(e) ? "opacity-60" : ""}`}>
                <span className="af-mono shrink-0 text-fg-3">{formatTime(e.timestamp)}</span>
                <span className={`shrink-0 ${e.event_type === "tool.failed" ? "text-red" : "text-blue"}`}>
                  {payloadString(e, "tool_name") ?? e.event_type}
                </span>
                <span className="min-w-0 truncate text-fg-2">{e.message}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

/** Drawer with details for one agent, from GET /api/v1/agents/{id}. */
export function AgentInspector({ agentId, fallback, agents, runEnded, onClose }: AgentInspectorProps) {
  const details = useAgentDetails(agentId);
  const agent = details.data?.agent ?? fallback;
  return (
    <Drawer
      open={!!agentId}
      onClose={onClose}
      title={agent?.name ?? "Agent"}
      subtitle={
        agent ? (
          <span className="inline-flex items-center gap-1.5">
            <AgentAvatar name={agent.name} role={agent.role} size={16} /> {agent.role} · {agent.model_alias}
          </span>
        ) : undefined
      }
    >
      {details.isError ? (
        <ErrorState error={details.error} onRetry={() => void details.refetch()} compact />
      ) : details.data ? (
        <InspectorBody details={details.data} agents={agents} runEnded={runEnded} />
      ) : (
        <p className="text-[12px] text-fg-2" role="status">
          Loading agent details…
        </p>
      )}
    </Drawer>
  );
}
