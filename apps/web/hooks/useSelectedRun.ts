// The run that the user looks at: `?run=<id>` in the URL, else the latest run.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import { useRuns } from "./queries";

export const RUN_LIST_PARAMS = { limit: 50, sort: "-created_at" } as const;

export function useSelectedRun() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const runs = useRuns(RUN_LIST_PARAMS);
  const fromUrl = searchParams.get("run");
  const latest = runs.data?.items[0]?.id ?? null;
  const runId = fromUrl || latest;

  const selectRun = useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("run", id);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  return { runId, fromUrl: !!fromUrl, runs, selectRun };
}
