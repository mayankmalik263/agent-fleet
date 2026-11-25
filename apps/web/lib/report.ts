// Final report helpers: the Markdown export and the cost estimate from the run usage.
import type { AgentRead, RunRead, TaskRead } from "./types";

/** Client-side cost estimate reported by Claude Code, or null when the run has none. */
export function estimatedCost(run: RunRead): number | null {
  const value = run.usage_json?.["estimated_cost_usd"];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** The report as one Markdown document: the final summary (or the failure), then every task result. */
export function buildReportMarkdown(run: RunRead, tasks: TaskRead[], agents: AgentRead[]): string {
  const names = new Map(agents.map((a) => [a.id, a.name]));
  const parts: string[] = [];
  const summary = run.final_summary?.trim();
  if (summary) {
    parts.push(summary.startsWith("#") ? summary : `# ${run.title}\n\n${summary}`);
  } else {
    parts.push(`# ${run.title}`);
    parts.push(`Status: ${run.status}.`);
    if (run.error_message) parts.push(`Error: ${run.error_message}`);
  }
  parts.push(`---\n\n**Task:** ${run.task_description}`);
  if (tasks.length) {
    parts.push("## Task results");
    for (const t of tasks) {
      const who = t.assigned_agent_id ? names.get(t.assigned_agent_id) ?? "unknown agent" : "unassigned";
      parts.push(`### ${t.title} (${t.status}, ${who})`);
      parts.push(t.result_summary?.trim() || "No result was submitted.");
      if (t.error_message) parts.push(`Error: ${t.error_message}`);
    }
  }
  parts.push(`_Agent Fleet run ${run.id}_`);
  return parts.join("\n\n") + "\n";
}
