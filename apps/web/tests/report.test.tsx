// Tests for the fixes after the failed "MCP research papers" run: readable Panel B story,
// Panel D final report, retry of runs and tasks, and the safe Markdown renderer.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Markdown, parseMarkdown } from "@/components/ui/Markdown";
import { ReportPanel } from "@/features/report/ReportPanel";
import { TasksPanel } from "@/features/tasks/TasksPanel";
import { TimelinePanel } from "@/features/timeline/TimelinePanel";
import { buildActivity, stripHandback, summarizeActivity } from "@/lib/activity";
import { buildReportMarkdown } from "@/lib/report";
import { agents, events, makeEvent, makeRun, makeTask, RUN_ID, tasks } from "./fixtures";
import { mockFetch, renderWithClient } from "./helpers";
import { navigation } from "./navigation";

describe("activity story (Panel B)", () => {
  const log = [
    ...events.slice(0, 4),
    makeEvent(5, "tool.started", { agent_id: "a-res", payload: { tool_name: "Grep", tool_use_id: "u1", input_summary: "pattern=MCP" } }),
    makeEvent(6, "tool.completed", { agent_id: "a-res", payload: { tool_name: "Grep", tool_use_id: "u1", output_preview: "3 files" } }),
    makeEvent(7, "tool.started", { agent_id: "a-res", payload: { tool_name: "mcp__agent-fleet__update_task_status", tool_use_id: "u2" } }),
    makeEvent(8, "tool.completed", { agent_id: "a-res", payload: { tool_name: "mcp__agent-fleet__update_task_status", tool_use_id: "u2" } }),
    makeEvent(9, "tool.started", { agent_id: "a-res", payload: { tool_name: "mcp__agent-fleet__update_agent_status", tool_use_id: "u3" } }),
    makeEvent(10, "tool.failed", { agent_id: "a-res", payload: { tool_name: "mcp__agent-fleet__update_agent_status", tool_use_id: "u3", output_preview: "invalid_transition" } }),
    makeEvent(11, "message.sent", {
      agent_id: "a-orch",
      payload: { receiver_agent_id: "a-res", message_type: "instruction" },
      message: "orchestrator to research-lead: Delegated: papers\n\nAGENT_FLEET_RUN_ID: x\nAGENT_FLEET_AGENT_ID: y\nFind papers.",
    }),
    makeEvent(12, "execution.usage_reported", { payload: { estimated_cost_usd: 0.1 } }),
    makeEvent(13, "execution.usage_reported", { payload: { estimated_cost_usd: 0.17 } }),
    makeEvent(14, "run.failed", { message: "Run failed: No papers found." }),
  ];

  it("pairs tool calls, hides successful reporting calls and keeps failures", () => {
    const items = buildActivity(log, agents);
    const grep = items.find((i) => i.text.startsWith("used Grep"));
    expect(grep).toMatchObject({ tone: "success", detail: "3 files", agentId: "a-res" });
    expect(items.some((i) => i.text.includes("update_task_status"))).toBe(false);
    const failed = items.find((i) => i.text.includes("update_agent_status"));
    expect(failed).toMatchObject({ group: "problems", tone: "danger", detail: "invalid_transition" });
    const delegated = items.find((i) => i.kind === "message" && i.seq === 11);
    expect(delegated?.text).toBe("gave instructions to");
    expect(delegated?.detail).toBe("Delegated: papers\n\nFind papers.");
    expect(items.filter((i) => i.text.startsWith("Claude Code reported usage"))).toHaveLength(1);
    expect(items.at(-1)).toMatchObject({ kind: "milestone", text: "Run failed", detail: "No papers found." });
    const summary = summarizeActivity(items, agents, tasks);
    expect(summary).toMatchObject({ agents: 3, tasksDone: 1, tasksFailed: 1, tasksTotal: 4, toolCalls: 1 });
  });

  it("shows sentences by default and filters problems", async () => {
    const user = userEvent.setup();
    renderWithClient(<TimelinePanel agents={agents} events={log} tasks={tasks} selectedAgentId={null} onSelectAgent={() => {}} />);
    const story = screen.getByLabelText("Activity story");
    expect(within(story).getByText(/assigned the task/)).toBeInTheDocument();
    expect(within(story).getByText("used Grep (pattern=MCP)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Problems/ }));
    expect(within(screen.getByLabelText("Activity story")).queryByText(/used Grep/)).toBeNull();
    expect(within(screen.getByLabelText("Activity story")).getByText("Run failed")).toBeInTheDocument();
  });
});

describe("subagent hand-back clean-up", () => {
  it("keeps only the report text", () => {
    const raw = [
      "<tools-used-before-summary>WebFetch</tools-used-before-summary>",
      "  ",
      "[Subagent hand-back] Notice. The report follows:",
      "  Nine papers.",
      "  - one",
      "agentId: abc123",
      "<usage>tool_uses: 18</usage>",
    ].join("\n");
    expect(stripHandback(raw)).toBe("Nine papers.\n- one");
    expect(stripHandback("[Subagent hand-back] The text below is the final rep")).toBe("");
  });
});

describe("Markdown renderer", () => {
  it("parses headings, nested lists and tables", () => {
    const blocks = parseMarkdown("# Title\n\n- a\n  - b\n- c\n\n| x | y |\n|---|---|\n| 1 | 2 |\n");
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "list", "table"]);
    const list = blocks[1];
    expect(list.kind === "list" && list.items[0].children[0].text).toBe("b");
  });

  it("links only safe URLs and never renders HTML", () => {
    render(<Markdown text={'[ok](https://arxiv.org/abs/1) [bad](javascript:alert(1)) <img src=x onerror=alert(1)> **bold**'} />);
    expect(screen.getByRole("link", { name: "ok" })).toHaveAttribute("href", "https://arxiv.org/abs/1");
    expect(screen.queryByRole("link", { name: "bad" })).toBeNull();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
  });
});

describe("Final Report (Panel D)", () => {
  it("renders the final summary as a report", () => {
    const run = makeRun({ status: "completed", final_summary: "# MCP papers\n\n## Summary\nThree papers found.", completed_at: "2026-11-24T20:01:00Z" });
    renderWithClient(<ReportPanel run={run} tasks={tasks} agents={agents} runEnded />);
    expect(screen.getByRole("heading", { name: "Final Report" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "MCP papers" })).toBeInTheDocument();
    expect(screen.getByText("Three papers found.")).toBeInTheDocument();
    expect(screen.getByLabelText("Task results")).toBeInTheDocument();
  });

  it("explains a failure and retries with web access", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetch({ [`POST /api/v1/runs/${RUN_ID}/retry`]: () => ({ status: 201, body: makeRun({ id: "run-retry", status: "queued" }) }) });
    const run = makeRun({ status: "failed", source: "dashboard", error_message: "No papers found. The researchers had no web search tool." });
    renderWithClient(<ReportPanel run={run} tasks={tasks} agents={agents} runEnded />);
    expect(screen.getByText("The run failed. No final report was written.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry with web access" }));
    const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/retry"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ web_access: true });
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/?run=run-retry", { scroll: false }));
  });

  it("waits while the run is active", () => {
    renderWithClient(<ReportPanel run={makeRun()} tasks={tasks} agents={agents} runEnded={false} />);
    expect(screen.getByText("The orchestrator is still working.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry run/ })).toBeNull();
  });

  it("exports one Markdown document", () => {
    const md = buildReportMarkdown(makeRun({ status: "failed", error_message: "boom" }), tasks, agents);
    expect(md).toContain("# API audit");
    expect(md).toContain("Error: boom");
    expect(md).toContain("### Map error paths (completed, research-lead)");
    expect(md).toContain("Found 14 paths.");
  });
});

describe("Retry task", () => {
  it("queues a new run for one failed task of a finished run", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetch({
      [`POST /api/v1/runs/${RUN_ID}/retry`]: () => ({ status: 201, body: makeRun({ id: "run-t" }) }),
      [`GET /api/v1/runs/${RUN_ID}/messages`]: { items: [], total: 0, limit: 50, offset: 0 },
    });
    const failed = makeTask("t-9", "Benchmarks", "a-res", "failed", { error_message: "no web" });
    renderWithClient(<TasksPanel runId={RUN_ID} tasks={[failed]} agents={agents} events={[]} runEnded runSource="dashboard" />);
    await user.click(screen.getByRole("button", { name: /Benchmarks/ }));
    await user.click(screen.getByRole("button", { name: "Retry task" }));
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/?run=run-t", { scroll: false }));
    const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/retry"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ task_id: "t-9" });
  });

  it("hides retry while the run is active", async () => {
    const user = userEvent.setup();
    mockFetch({ [`GET /api/v1/runs/${RUN_ID}/messages`]: { items: [], total: 0, limit: 50, offset: 0 } });
    const failed = makeTask("t-9", "Benchmarks", "a-res", "failed");
    renderWithClient(<TasksPanel runId={RUN_ID} tasks={[failed]} agents={agents} events={[]} runEnded={false} />);
    await user.click(screen.getByRole("button", { name: /Benchmarks/ }));
    expect(screen.queryByRole("button", { name: "Retry task" })).toBeNull();
  });
});
