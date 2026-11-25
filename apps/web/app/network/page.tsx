import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/shell/PageFallback";
import { NetworkView } from "@/features/network/NetworkView";

export const metadata: Metadata = { title: "Agent Network · Agent Fleet" };

// The view reads ?run= from the URL, so it renders inside a Suspense boundary.
export default function Page() {
  return (
    <Suspense fallback={<PageFallback />}>
      <NetworkView />
    </Suspense>
  );
}
