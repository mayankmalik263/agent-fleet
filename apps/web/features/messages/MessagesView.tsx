"use client";
import { MessagesSquare } from "lucide-react";
import { useMemo, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Panel } from "@/components/ui/Panel";
import { SearchInput } from "@/components/ui/SearchInput";
import { useRunMessages } from "@/hooks/queries";
import { formatDateTime, humanize, shortId } from "@/lib/format";
import { RunPage } from "../dashboard/RunPage";
import type { RunScopeContext } from "../dashboard/RunScope";

function MessagesBody({ ctx }: { ctx: RunScopeContext }) {
  const messages = useRunMessages(ctx.runId);
  const [search, setSearch] = useState("");
  const agents = useMemo(() => new Map(ctx.live.agents.map((a) => [a.id, a])), [ctx.live.agents]);
  const name = (id: string | null) => (id ? agents.get(id)?.name ?? shortId(id) : "All agents");
  const q = search.trim().toLowerCase();
  const items = (messages.data?.items ?? []).filter(
    (m) => !q || [m.content, name(m.sender_agent_id), name(m.receiver_agent_id), m.message_type].some((v) => v.toLowerCase().includes(q)),
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col p-3">
      <Panel
        title={`Messages${messages.data ? ` (${messages.data.total})` : ""}`}
        label="Agent messages"
        className="flex-1"
        actions={<SearchInput value={search} onChange={setSearch} label="Search messages" className="w-48" />}
      >
        {messages.isError ? (
          <ErrorState error={messages.error} onRetry={() => void messages.refetch()} compact />
        ) : messages.isPending ? (
          <p role="status" className="px-3 py-6 text-[12px] text-fg-2">
            Loading messages…
          </p>
        ) : items.length === 0 ? (
          <EmptyState icon={<MessagesSquare size={22} />} title={q ? "No messages match the search" : "No messages in this run"} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-[12px]">
              <thead className="af-label">
                <tr className="border-b border-line-soft">
                  <th className="px-3 py-2 font-semibold">Time</th>
                  <th className="px-3 py-2 font-semibold">From</th>
                  <th className="px-3 py-2 font-semibold">To</th>
                  <th className="px-3 py-2 font-semibold">Type</th>
                  <th className="px-3 py-2 font-semibold">Content</th>
                </tr>
              </thead>
              <tbody>
                {items.map((m) => (
                  <tr key={m.id} className="border-b border-line-soft/60 align-top">
                    <td className="af-mono px-3 py-1.5 whitespace-nowrap text-fg-2">{formatDateTime(m.timestamp)}</td>
                    <td className="px-3 py-1.5 whitespace-nowrap">{name(m.sender_agent_id)}</td>
                    <td className="px-3 py-1.5 whitespace-nowrap">{name(m.receiver_agent_id)}</td>
                    <td className="px-3 py-1.5 whitespace-nowrap text-fg-2">{humanize(m.message_type)}</td>
                    <td className="px-3 py-1.5 whitespace-pre-wrap">{m.content}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {messages.data && messages.data.total > messages.data.items.length ? (
              <p className="px-3 py-2 text-[11px] text-fg-3">
                Showing the first {messages.data.items.length} of {messages.data.total} messages.
              </p>
            ) : null}
          </div>
        )}
      </Panel>
    </div>
  );
}

export function MessagesView() {
  return (
    <RunPage label="Messages" title="Messages" description="Messages between agents in the selected run.">
      {(ctx) => <MessagesBody ctx={ctx} />}
    </RunPage>
  );
}
