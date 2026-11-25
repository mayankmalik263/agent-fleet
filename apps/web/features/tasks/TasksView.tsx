"use client";
import { RunPage } from "../dashboard/RunPage";
import { TasksPanel } from "./TasksPanel";

export function TasksView() {
  return (
    <RunPage label="Tasks" title="Tasks" description="All tasks of the selected run, with status filters and search.">
      {(ctx) => (
        <div className="flex min-h-0 flex-1 flex-col p-3">
          <TasksPanel runId={ctx.runId} tasks={ctx.live.tasks} agents={ctx.live.agents} events={ctx.events} className="min-h-[520px] flex-1" />
        </div>
      )}
    </RunPage>
  );
}
