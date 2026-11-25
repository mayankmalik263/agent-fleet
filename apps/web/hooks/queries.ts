// React Query hooks for the Agent Fleet API.
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { RunListParams } from "@/lib/types";

export const queryKeys = {
  overview: ["overview"] as const,
  runs: (params: RunListParams = {}) => ["runs", params] as const,
  runsAll: ["runs"] as const,
  snapshot: (runId: string) => ["snapshot", runId] as const,
  systemStatus: ["system-status"] as const,
  agent: (agentId: string) => ["agent", agentId] as const,
  agentsAll: ["agent"] as const,
  messages: (runId: string) => ["messages", runId] as const,
  approvals: (runId: string) => ["approvals", runId] as const,
};

export function useOverview() {
  return useQuery({ queryKey: queryKeys.overview, queryFn: api.overview, refetchInterval: 15_000 });
}

export function useRuns(params: RunListParams = {}) {
  return useQuery({ queryKey: queryKeys.runs(params), queryFn: () => api.listRuns(params), refetchInterval: 10_000 });
}

export function useSnapshot(runId: string | null) {
  return useQuery({
    queryKey: queryKeys.snapshot(runId ?? ""),
    queryFn: () => api.snapshot(runId as string),
    enabled: !!runId,
    placeholderData: undefined,
  });
}

export function useSystemStatus(options: { enabled?: boolean; refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: () => api.systemStatus(false),
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchInterval ?? 20_000,
  });
}

export function useAgentDetails(agentId: string | null) {
  return useQuery({
    queryKey: queryKeys.agent(agentId ?? ""),
    queryFn: () => api.agentDetails(agentId as string),
    enabled: !!agentId,
  });
}

export function useRunMessages(runId: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.messages(runId ?? ""),
    queryFn: () => api.runMessages(runId as string, { limit: 500 }),
    enabled: !!runId && enabled,
  });
}
