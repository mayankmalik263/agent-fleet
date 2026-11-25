"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { RunRetry } from "@/lib/types";
import { queryKeys } from "./queries";

/**
 * POST /api/v1/runs/{id}/retry, then show the new run.
 * A retry is always a new run: a Claude Code session cannot continue after it ends.
 */
export function useRetryRun(runId: string) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  return useMutation({
    mutationFn: (body: RunRetry) => api.retryRun(runId, body),
    onSuccess: (run) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runsAll });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      const params = new URLSearchParams(searchParams.toString());
      params.set("run", run.id);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
  });
}
