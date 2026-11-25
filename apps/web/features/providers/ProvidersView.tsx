"use client";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { DetailList } from "@/components/ui/DetailList";
import { ErrorState } from "@/components/ui/ErrorState";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { queryKeys, useSystemStatus } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { Tone } from "@/lib/colors";
import { COMMANDS } from "@/lib/config";
import { formatDateTime, humanize } from "@/lib/format";
import type { ProviderConnectionStatus } from "@/lib/types";

function providerTone(status: ProviderConnectionStatus): Tone {
  if (status === "connected") return "success";
  if (status === "unsupported_in_local_mode" || status === "not_configured") return "neutral";
  if (status === "authentication_required") return "warning";
  return "danger";
}

function integrationTone(status: string): Tone {
  if (status === "available") return "success";
  if (status === "installed") return "warning";
  return "neutral";
}

function detailValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Providers, runner and integrations from GET /api/v1/system/status. */
export function ProvidersView() {
  const status = useSystemStatus();
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  // ?refresh=true re-runs provider detection on the server.
  const refresh = async () => {
    setRefreshing(true);
    try {
      const fresh = await api.systemStatus(true);
      queryClient.setQueryData(queryKeys.systemStatus, fresh);
    } catch {
      await status.refetch();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <>
      <PageHeader label="Execution" title="Providers" description="Execution providers, the local runner and optional integrations.">
        {status.data ? <StatusBadge tone={status.data.status === "ok" ? "success" : "warning"} status={status.data.status} /> : null}
        <button type="button" className="af-btn" onClick={() => void refresh()} disabled={refreshing}>
          <RefreshCw aria-hidden size={12} className={refreshing ? "af-pulse" : undefined} /> {refreshing ? "Checking…" : "Re-check"}
        </button>
      </PageHeader>
      <div className="grid gap-3 p-3 lg:grid-cols-2">
        {status.isError && !status.data ? (
          <div className="af-panel lg:col-span-2">
            <ErrorState error={status.error} onRetry={() => void status.refetch()} />
          </div>
        ) : status.isPending ? (
          <p role="status" className="px-3 py-6 text-[12px] text-fg-2">
            Loading system status…
          </p>
        ) : (
          <>
            {status.data.providers.map((p) => (
              <Panel key={p.provider} title={p.label} label="Provider">
                <div className="space-y-2 px-3 py-2">
                  <StatusBadge tone={providerTone(p.status)} status={p.status} />
                  <p className="text-[12px] text-fg-2">{p.message}</p>
                  <DetailList
                    items={[
                      { label: "Provider id", value: <span className="af-mono">{p.provider}</span> },
                      { label: "Local mode", value: p.local_mode_supported ? "Supported" : "Not supported" },
                      ...Object.entries(p.details).map(([k, v]) => ({ label: humanize(k), value: detailValue(v) })),
                    ]}
                  />
                </div>
              </Panel>
            ))}
            <Panel title="Local runner" label="Runner">
              <div className="space-y-2 px-3 py-2">
                <StatusBadge tone={status.data.runner.any_online ? "success" : "danger"} status={status.data.runner.any_online ? "online" : "offline"} />
                {!status.data.runner.any_online ? (
                  <p className="text-[12px] text-fg-2">
                    No runner is online. Start it: <code className="af-mono rounded bg-bg px-1">{COMMANDS.runner}</code>
                  </p>
                ) : null}
                <DetailList
                  items={[
                    { label: "Queued runs", value: String(status.data.runner.queued_runs) },
                    { label: "Active runs", value: String(status.data.runner.active_runs) },
                  ]}
                />
                {status.data.runner.runners.length ? (
                  <ul className="flex flex-col gap-1">
                    {status.data.runner.runners.map((r) => (
                      <li key={r.id} className="flex items-center justify-between rounded bg-bg/60 px-2 py-1 text-[11px]">
                        <span>
                          {r.name} <span className="text-fg-3">· {r.runtime_type}</span>
                        </span>
                        <span className="text-fg-2">
                          {r.online ? "online" : "offline"} · last seen {formatDateTime(r.last_seen_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[11px] text-fg-3">No runner has registered yet.</p>
                )}
              </div>
            </Panel>
            {status.data.integrations.map((i) => (
              <Panel key={i.name} title={i.name === "graphify" ? "Graphify" : humanize(i.name)} label="Integration (optional)">
                <div className="space-y-2 px-3 py-2">
                  <StatusBadge tone={integrationTone(i.status)} status={i.status} />
                  <p className="text-[12px] text-fg-2">{i.message}</p>
                  <DetailList items={Object.entries(i.details).map(([k, v]) => ({ label: humanize(k), value: detailValue(v) }))} />
                </div>
              </Panel>
            ))}
            <Panel title="System" label="API">
              <div className="px-3 py-2">
                <DetailList
                  items={[
                    { label: "Version", value: status.data.version },
                    { label: "Mode", value: status.data.mode },
                    { label: "Database", value: status.data.database },
                  ]}
                />
              </div>
            </Panel>
          </>
        )}
      </div>
    </>
  );
}
