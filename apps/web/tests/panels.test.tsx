import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgentInspector } from "@/features/inspector/AgentInspector";
import { TasksPanel } from "@/features/tasks/TasksPanel";
import { TimelinePanel } from "@/features/timeline/TimelinePanel";
import { agents, events, makeAgentDetails, messages, RUN_ID, tasks } from "./fixtures";
import { mockFetch, renderWithClient } from "./helpers";

const agentMap = new Map(agents.map((a) => [a.id, a]));

describe("Teamwork Tasks panel", () => {
  const renderPanel = () => {
    mockFetch({ [`GET /api/v1/runs/${RUN_ID}/messages`]: { items: messages, total: 1, limit: 500, offset: 0 } });
    renderWithClient(<TasksPanel runId={RUN_ID} tasks={tasks} agents={agents} events={events} />);
  };
  const titles = () => within(screen.getByRole("list", { name: "Tasks" })).getAllByRole("article").map((a) => a.getAttribute("aria-label"));

  it("filters by status group", async () => {
    const user = userEvent.setup();
    renderPanel();
    expect(titles()).toHaveLength(4);
    await user.click(screen.getByRole("button", { name: /^Done/ }));
    expect(titles()).toEqual(["Task Map error paths"]);
    await user.click(screen.getByRole("button", { name: /^Failed/ }));
    expect(titles()).toEqual(["Task Broken step"]);
    await user.click(screen.getByRole("button", { name: /^In review/ }));
    expect(screen.getByText("No tasks match this filter.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^In progress/ }));
    expect(titles()).toEqual(["Task Classify failures"]);
  });

  it("searches by title and agent", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.type(screen.getByLabelText("Search tasks"), "code-reviewer");
    expect(titles().sort()).toEqual(["Task Broken step", "Task Review patch"]);
  });

  it("shows progress only when the API reports it and expands details", async () => {
    const user = userEvent.setup();
    renderPanel();
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    const card = screen.getByRole("article", { name: "Task Map error paths" });
    await user.click(within(card).getByRole("button", { expanded: false }));
    expect(within(card).getByText("Found 14 paths.")).toBeInTheDocument();
    expect(within(card).getByText("orchestrator")).toBeInTheDocument();
    expect(await within(card).findByText("Start with api/errors.py.")).toBeInTheDocument();
    const failed = screen.getByRole("article", { name: "Task Broken step" });
    await user.click(within(failed).getByRole("button", { expanded: false }));
    expect(within(failed).getByText("Tool crashed")).toBeInTheDocument();
  });
});

describe("Cross-Agent Collaboration timeline", () => {
  it("renders lanes and markers and shows event details on click", async () => {
    const user = userEvent.setup();
    const onSelectAgent = vi.fn();
    renderWithClient(<TimelinePanel agents={agents} events={events} selectedAgentId={null} onSelectAgent={onSelectAgent} />);
    const lanes = screen.getByRole("list", { name: "Timeline lanes" });
    expect(within(lanes).getAllByRole("listitem")).toHaveLength(4);
    expect(within(lanes).getByText("System")).toBeInTheDocument();
    const timeline = screen.getByTestId("timeline");
    expect(timeline.querySelectorAll("[data-category]")).toHaveLength(6);
    // Two connectors: one delegation (task.created) and one message.
    expect(timeline.querySelectorAll("line[marker-end]")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: /Agent messages: message.sent/ }));
    const details = screen.getByRole("region", { name: "Selected event" });
    expect(within(details).getByText("research-lead")).toBeInTheDocument();
    expect(within(details).getByText("orchestrator")).toBeInTheDocument();
    expect(within(details).getByText("orchestrator to research-lead: Start with api/errors.py.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Select agent research-lead" }));
    expect(onSelectAgent).toHaveBeenCalledWith("a-res");
  });

  it("filters event types and searches lanes", async () => {
    const user = userEvent.setup();
    renderWithClient(<TimelinePanel agents={agents} events={events} selectedAgentId={null} onSelectAgent={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Filter event types" }));
    await user.click(screen.getByRole("button", { name: "Tool calls" }));
    const timeline = screen.getByTestId("timeline");
    expect(timeline.querySelectorAll('[data-category="tool_call"]')).toHaveLength(0);
    expect(timeline.querySelectorAll("[data-category]")).toHaveLength(5);
    await user.type(screen.getByLabelText("Search agents in timeline"), "research");
    expect(within(screen.getByRole("list", { name: "Timeline lanes" })).getAllByRole("listitem")).toHaveLength(1);
  });

  it("shows an empty state without events", () => {
    renderWithClient(<TimelinePanel agents={agents} events={[]} selectedAgentId={null} onSelectAgent={() => {}} />);
    expect(screen.getByText("No events yet")).toBeInTheDocument();
  });
});

describe("Agent inspector", () => {
  it("shows details from GET /api/v1/agents/{id}", async () => {
    mockFetch({ "GET /api/v1/agents/a-res": makeAgentDetails() });
    renderWithClient(<AgentInspector agentId="a-res" fallback={agents[1]} agents={agentMap} runEnded={false} onClose={() => {}} />);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Loading agent details…")).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByText("orchestrator (orchestrator)")).toBeInTheDocument());
    expect(within(dialog).getByText("researcher")).toBeInTheDocument();
    expect(within(dialog).getAllByText("Classify failures").length).toBeGreaterThan(0);
    expect(within(dialog).getByText(/Not available. The runtime did not report token usage/)).toBeInTheDocument();
    expect(within(dialog).getByText("Found 14 paths.")).toBeInTheDocument();
    expect(within(dialog).getByText("Start with api/errors.py.")).toBeInTheDocument();
    expect(within(dialog).getByText("Read")).toBeInTheDocument();
    expect(within(dialog).getByText("Duration (live)")).toBeInTheDocument();
  });

  it("shows the API error message", async () => {
    mockFetch({
      "GET /api/v1/agents/a-res": () => ({ status: 404, body: { error: { code: "not_found", message: "agent not found", details: {} } } }),
    });
    const onClose = vi.fn();
    renderWithClient(<AgentInspector agentId="a-res" agents={agentMap} runEnded={false} onClose={onClose} />);
    expect(await screen.findByText("agent not found")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close inspector" }));
    expect(onClose).toHaveBeenCalled();
  });
});
