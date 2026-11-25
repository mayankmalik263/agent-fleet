import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/shell/PageFallback";
import { RunsView } from "@/features/runs/RunsView";

export const metadata: Metadata = { title: "Runs · Agent Fleet" };

// The view reads ?run= from the URL, so it renders inside a Suspense boundary.
export default function Page() {
  return (
    <Suspense fallback={<PageFallback />}>
      <RunsView />
    </Suspense>
  );
}
