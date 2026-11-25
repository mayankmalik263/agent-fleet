import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/shell/PageFallback";
import { AgentsView } from "@/features/agents/AgentsView";

export const metadata: Metadata = { title: "Agents · Agent Fleet" };

// The view reads ?run= from the URL, so it renders inside a Suspense boundary.
export default function Page() {
  return (
    <Suspense fallback={<PageFallback />}>
      <AgentsView />
    </Suspense>
  );
}
