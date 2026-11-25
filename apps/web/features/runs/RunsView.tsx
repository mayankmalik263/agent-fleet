"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, History, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Panel } from "@/components/ui/Panel";
import { SearchInput } from "@/components/ui/SearchInput";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { queryKeys, useRuns } from "@/hooks/queries";
import { runStatusTone } from "@/lib/colors";
import { durationMs, formatDateTime, formatDuration, NOT_AVAILABLE, providerLabel, sourceLabel } from "@/lib/format";
import type { RunStatus } from "@/lib/types";
import { usageLines } from "@/lib/usage";
import { NewRunModal } from "./NewRunModal";

const PAGE_SIZE = 25;
const STATUSES: RunStatus[] = ["queued", "planning", "running", "awaiting_approval", "completed", "failed", "cancelled"];

/** Run history with search, status filter and paging. */
export function RunsView() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<RunStatus | "">("");
  const [page, setPage] = useState(0);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const statusId = useId();
  const router = useRouter();
  const queryClient = useQueryClient();
  const runs = useRuns({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    sort: "-created_at",
    search: search.trim() || undefined,
    status: status ? [status] : undefined,
  });
  const total = runs.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <PageHeader label="Run history" title="Runs" description="All runs in this workspace. Open a run to rebuild its network and timeline from the stored events.">
        <button type="button" className="af-btn af-btn-primary" onClick={() => setNewRunOpen(true)}>
          <Plus aria-hidden size={13} /> New Run
        </button>
      </PageHeader>
      <div className="flex min-h-0 flex-1 flex-col p-3">
        <Panel
          title={`Runs${runs.data ? ` (${total})` : ""}`}
          className="flex-1"
          actions={
            <>
              <SearchInput
                value={search}
                onChange={(v) => {
                  setSearch(v);
                  setPage(0);
                }}
                label="Search runs by title"
                className="w-48"
              />
              <label htmlFor={statusId} className="sr-only">
                Filter by status
              </label>
              <select
                id={statusId}
                className="af-input"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value as RunStatus | "");
                  setPage(0);
                }}
              >
                <option value="">All statuses</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </>
          }
        >
          {runs.isError ? (
            <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
          ) : runs.isPending ? (
            <p role="status" className="px-3 py-6 text-[12px] text-fg-2">
              Loading runs…
            </p>
          ) : runs.data.items.length === 0 ? (
            <EmptyState icon={<History size={22} />} title={search || status ? "No runs match the filters" : "No runs yet"}>
              {search || status ? null : "Start a run with New Run, or record one from Claude Code."}
            </EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] text-left text-[12px]">
                <thead className="af-label">
                  <tr className="border-b border-line-soft">
                    <th className="px-3 py-2 font-semibold">Title</th>
                    <th className="px-3 py-2 font-semibold">Source</th>
                    <th className="px-3 py-2 font-semibold">Provider</th>
                    <th className="px-3 py-2 font-semibold">Status</th>
                    <th className="px-3 py-2 font-semibold">Agents</th>
                    <th className="px-3 py-2 font-semibold">Tasks</th>
                    <th className="px-3 py-2 font-semibold">Started</th>
                    <th className="px-3 py-2 font-semibold">Duration</th>
                    <th className="px-3 py-2 font-semibold">Usage</th>
                    <th className="px-3 py-2 font-semibold">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data.items.map((r) => {
                    const usage = usageLines(r.usage_json);
                    const ended = !!r.completed_at;
                    return (
                      <tr key={r.id} className="border-b border-line-soft/60 align-top">
                        <td className="max-w-[280px] px-3 py-1.5">
                          <Link href={`/?run=${r.id}`} className="font-medium hover:text-primary">
                            {r.title}
                          </Link>
                          <div className="af-mono text-fg-3">{r.id.slice(0, 8)}</div>
                        </td>
                        <td className="px-3 py-1.5">{sourceLabel(r.source)}</td>
                        <td className="px-3 py-1.5">{providerLabel(r.provider)}</td>
                        <td className="px-3 py-1.5">
                          <StatusBadge tone={runStatusTone(r.status)} status={r.status} />
                        </td>
                        <td className="px-3 py-1.5 tabular-nums">{r.agent_count}</td>
                        <td className="px-3 py-1.5 tabular-nums">{r.task_count}</td>
                        <td className="af-mono px-3 py-1.5 whitespace-nowrap text-fg-2">{formatDateTime(r.started_at)}</td>
                        <td className="px-3 py-1.5 tabular-nums">
                          {ended || !r.started_at ? formatDuration(durationMs(r.started_at, r.completed_at)) : "In progress"}
                        </td>
                        <td className="px-3 py-1.5 text-fg-2">
                          {usage.length ? (
                            <ul>
                              {usage.slice(0, 4).map((u) => (
                                <li key={u.label}>
                                  {u.label}: <span className="text-fg">{u.value}</span>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            NOT_AVAILABLE
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          <Link href={`/?run=${r.id}`} className="af-btn" aria-label={`Open run ${r.title}`}>
                            Open
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {total > PAGE_SIZE ? (
            <div className="flex items-center justify-end gap-2 border-t border-line-soft px-3 py-2 text-[11px] text-fg-2">
              <button type="button" className="af-icon-btn" aria-label="Previous page" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft aria-hidden size={13} />
              </button>
              Page {page + 1} of {pages}
              <button type="button" className="af-icon-btn" aria-label="Next page" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
                <ChevronRight aria-hidden size={13} />
              </button>
            </div>
          ) : null}
        </Panel>
      </div>
      <NewRunModal
        open={newRunOpen}
        onClose={() => setNewRunOpen(false)}
        onCreated={(run) => {
          setNewRunOpen(false);
          void queryClient.invalidateQueries({ queryKey: queryKeys.runsAll });
          router.push(`/?run=${run.id}`);
        }}
      />
    </>
  );
}
