import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/shell/PageFallback";
import { TasksView } from "@/features/tasks/TasksView";

export const metadata: Metadata = { title: "Tasks · Agent Fleet" };

// The view reads ?run= from the URL, so it renders inside a Suspense boundary.
export default function Page() {
  return (
    <Suspense fallback={<PageFallback />}>
      <TasksView />
    </Suspense>
  );
}
