"use client";
import { AlertTriangle, ArrowRight, CheckCircle2, CircleDot, Flag, MessageSquare, Send, Wrench, type LucideIcon } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AgentAvatar } from "@/components/ui/AgentAvatar";
import { relativeTime, type ActivityItem, type ActivityKind, type ActivityTone } from "@/lib/activity";
import { formatTime } from "@/lib/format";
import type { AgentRead } from "@/lib/types";

const KIND_ICON: Record<ActivityKind, LucideIcon> = {
  milestone: Flag,
  delegation: Send,
  message: MessageSquare,
  tool: Wrench,
  status: CircleDot,
  problem: AlertTriangle,
  system: CircleDot,
};

const TONE_VAR: Record<ActivityTone, string> = {
  neutral: "var(--af-text-3)",
  info: "var(--af-blue)",
  success: "var(--af-green)",
  warning: "var(--af-yellow)",
  danger: "var(--af-red)",
  active: "var(--af-primary)",
};

function AgentChip({ agent, onSelect }: { agent: AgentRead | undefined; onSelect: (id: string) => void }) {
  if (!agent) return <span className="font-medium text-fg-2">Agent Fleet</span>;
  return (
    <button
      type="button"
      onClick={() => onSelect(agent.id)}
      className="inline-flex max-w-[180px] items-center gap-1 rounded px-0.5 align-middle font-medium text-fg hover:bg-panel-2"
      title={`${agent.name} (${agent.role}, ${agent.model_alias})`}
    >
      <AgentAvatar name={agent.name} role={agent.role} size={16} />
      <span className="truncate">{agent.name}</span>
    </button>
  );
}

function Detail({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 220 || text.split("\n").length > 3;
  return (
    <div className="mt-1 rounded border border-line-soft bg-bg/50 px-2 py-1 text-[11px] text-fg-2">
      <p className={`whitespace-pre-wrap break-words ${open || !long ? "" : "line-clamp-3"}`}>{text}</p>
      {long ? (
        <button type="button" className="mt-0.5 text-[11px] text-primary hover:underline" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? "Show less" : "Show more"}
        </button>
      ) : null}
    </div>
  );
}

interface ActivityFeedProps {
  items: ActivityItem[];
  agents: Map<string, AgentRead>;
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string | null, open?: boolean) => void;
}

/** Panel B "Story" view: what each agent did, in plain sentences, in time order. */
export function ActivityFeed({ items, agents, selectedAgentId, onSelectAgent }: ActivityFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const start = items[0]?.timestamp;
  const select = (id: string) => onSelectAgent(id, false);

  // Follow new rows while the user is at the bottom; stop following when the user scrolls up.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [items.length]);

  const involves = useMemo(
    () => (item: ActivityItem) => !selectedAgentId || item.agentId === selectedAgentId || item.targetId === selectedAgentId,
    [selectedAgentId],
  );

  return (
    <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-3 py-2" aria-label="Activity story">
      <ol className="relative flex flex-col">
        {items.map((item) => {
          const Icon = KIND_ICON[item.kind];
          const color = TONE_VAR[item.tone];
          const dim = !involves(item) || item.implicit;
          if (item.kind === "milestone") {
            return (
              <li key={item.key} className="my-1.5 first:mt-0" style={{ opacity: dim && selectedAgentId ? 0.45 : 1 }}>
                <div className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-[12px]" style={{ borderColor: `color-mix(in srgb, ${color} 45%, transparent)`, background: `color-mix(in srgb, ${color} 9%, transparent)` }}>
                  {item.tone === "success" ? <CheckCircle2 aria-hidden size={14} style={{ color }} /> : <Icon aria-hidden size={14} style={{ color }} />}
                  <span className="font-semibold text-fg">{item.text}</span>
                  <span className="af-mono ml-auto text-[10px] text-fg-3" title={formatTime(item.timestamp)}>
                    {relativeTime(item.timestamp, start)}
                  </span>
                </div>
                {item.detail ? <Detail text={item.detail} /> : null}
              </li>
            );
          }
          return (
            <li key={item.key} className="group grid grid-cols-[40px_18px_1fr] gap-x-1.5 py-1" style={{ opacity: dim ? 0.45 : 1 }}>
              <span className="af-mono pt-0.5 text-right text-[10px] text-fg-3" title={formatTime(item.timestamp)}>
                {relativeTime(item.timestamp, start)}
              </span>
              <span className="relative flex justify-center pt-0.5">
                <span aria-hidden className="absolute top-5 bottom-[-8px] w-px bg-line-soft group-last:hidden" />
                <Icon aria-hidden size={13} style={{ color }} />
              </span>
              <div className="min-w-0 text-[12px] leading-5 text-fg-2">
                <AgentChip agent={item.agentId ? agents.get(item.agentId) : undefined} onSelect={select} />{" "}
                <span className={item.kind === "problem" ? "text-red" : ""}>{item.text}</span>
                {item.targetId ? (
                  <>
                    {" "}
                    {item.kind === "message" && item.text !== "said" ? null : <ArrowRight aria-hidden size={11} className="inline text-fg-3" />}{" "}
                    <AgentChip agent={agents.get(item.targetId)} onSelect={select} />
                  </>
                ) : null}
                {item.detail ? <Detail text={item.detail} /> : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
