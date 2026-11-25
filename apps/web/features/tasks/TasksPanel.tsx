"use client";
import { ListTodo } from "lucide-react";
import { useMemo, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { SearchInput } from "@/components/ui/SearchInput";
import { countByFilter, filterTasks, TASK_FILTERS, type TaskFilter } from "@/lib/taskFilters";
import type { AgentRead, EventRead, TaskRead } from "@/lib/types";
import { TaskCard } from "./TaskCard";

export interface TasksPanelProps {
  runId: string;
  tasks: TaskRead[];
  agents: AgentRead[];
  events: EventRead[];
  className?: string;
}

/** Panel C: teamwork tasks with status filters and search. */
export function TasksPanel({ runId, tasks, agents, events, className = "" }: TasksPanelProps) {
  const [filter, setFilter] = useState<TaskFilter>("all");
  const [search, setSearch] = useState("");
  const agentById = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents]);
  const counts = useMemo(() => countByFilter(tasks), [tasks]);
  const visible = useMemo(() => filterTasks(tasks, filter, search, agentById), [tasks, filter, search, agentById]);

  // Latest event per task gives the "latest update" line.
  const latestByTask = useMemo(() => {
    const map = new Map<string, EventRead>();
    for (const e of events) if (e.task_id) map.set(e.task_id, e);
    return map;
  }, [events]);

  return (
    <Panel
      id="teamwork-tasks"
      label="Panel C"
      title="Teamwork Tasks"
      className={className}
      bodyClassName="flex flex-col"
      actions={<SearchInput value={search} onChange={setSearch} label="Search tasks" className="w-36" />}
    >
      <div role="group" aria-label="Task status filter" className="flex flex-wrap gap-1 border-b border-line-soft px-3 py-1.5">
        {TASK_FILTERS.map((f) => (
          <button key={f.id} type="button" className="af-chip" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
            {f.label}
            <span className="tabular-nums text-fg-3">{counts[f.id]}</span>
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        {tasks.length === 0 ? (
          <EmptyState icon={<ListTodo size={22} />} title="No tasks in this run yet">
            Tasks appear when an agent delegates work to another agent.
          </EmptyState>
        ) : visible.length === 0 ? (
          <p className="py-6 text-center text-[12px] text-fg-2">No tasks match this filter.</p>
        ) : (
          <ul className="flex flex-col gap-1.5" aria-label="Tasks">
            {visible.map((task) => (
              <li key={task.id}>
                <TaskCard task={task} runId={runId} agents={agentById} latestEvent={latestByTask.get(task.id)} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}
