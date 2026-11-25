import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FleetDashboard } from "@/features/dashboard/FleetDashboard";
import { events, makeAgentDetails, makeEvent, makeRunListItem, makeSnapshot, messages, RUN_ID } from "./fixtures";
import { mockFetch, MockEventSource, renderWithClient } from "./helpers";

function routes(overrides: Record<string, unknown> = {}) {
  return {
    "GET /api/v1/runs": { items: [makeRunListItem()], total: 1, limit: 50, offset: 0 },
    [`GET /api/v1/runs/${RUN_ID}/snapshot`]: makeSnapshot(),
    [`GET /api/v1/runs/${RUN_ID}/messages`]: { items: messages, total: 1, limit: 500, offset: 0 },
    "GET /api/v1/agents/a-res": makeAgentDetails(),
    ...overrides,
  };
}

const stat = (label: string, value: number | string) => screen.getByLabelText(`${label}: ${value}`);

describe("Fleet dashboard", () => {
  beforeEach(() => {
    MockEventSource.reset();
    vi.stubGlobal("EventSource", MockEventSource);
  });

  it("loads the latest run and shows real counters, graph and timeline", async () => {
    mockFetch(routes());
    renderWithClient(<FleetDashboard />);
    expect(screen.getByRole("heading", { name: "Multi-Agent Fleet" })).toBeInTheDocument();
    expect(screen.getByText("Loading runs…")).toBeInTheDocument();

    await waitFor(() => expect(stat("Total agents", 3)).toBeInTheDocument());
    expect(stat("Running agents", 2)).toBeInTheDocument();
    expect(stat("Work items", 4)).toBeInTheDocument();
    expect(stat("Messages", 1)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Agent Network" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cross-Agent Collaboration" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Teamwork Tasks" })).toBeInTheDocument();

    // React Flow renders one custom node per agent.
    await waitFor(() => expect(screen.getByTestId("agent-node-a-orch")).toBeInTheDocument());
    expect(screen.getByTestId("agent-node-a-res")).toBeInTheDocument();
    // Token usage shows only where the API reports it.
    expect(within(screen.getByTestId("agent-node-a-orch")).getByText("1.2k in / 300 out")).toBeInTheDocument();
    expect(within(screen.getByTestId("agent-node-a-res")).getAllByText("Not available").length).toBeGreaterThan(0);
    // A progress bar only for the agent with a real progress value.
    expect(within(screen.getByTestId("agent-node-a-res")).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
    expect(within(screen.getByTestId("agent-node-a-orch")).queryByRole("progressbar")).toBeNull();
  });

  it("applies SSE events incrementally, without duplicates", async () => {
    mockFetch(routes());
    renderWithClient(<FleetDashboard />);
    await waitFor(() => expect(stat("Total agents", 3)).toBeInTheDocument());
    const es = MockEventSource.latest();
    expect(es.url).toContain(`/runs/${RUN_ID}/events/stream`);

    act(() => {
      es.open();
      events.forEach((e) => es.emit(e, e.sequence_number));
    });
    await waitFor(() => expect(screen.getByTestId("connection-status")).toHaveTextContent("Live"));
    act(() => screen.getByRole("tab", { name: "Lanes" }).click());
    await waitFor(() => expect(screen.getByTestId("timeline").querySelectorAll("[data-category]")).toHaveLength(6));

    act(() => {
      es.emit(
        makeEvent(7, "agent.created", {
          agent_id: "a-new",
          parent_agent_id: "a-orch",
          payload: { name: "patch-executor", role: "executor", model_alias: "sonnet", status: "running" },
        }),
      );
      es.emit(makeEvent(8, "message.sent", { agent_id: "a-orch", payload: { receiver_agent_id: "a-new", message_type: "instruction" } }));
      // Replayed duplicates after a reconnect must not count twice.
      es.emit(makeEvent(8, "message.sent", { agent_id: "a-orch", payload: { receiver_agent_id: "a-new", message_type: "instruction" } }));
      es.emit(events[3]);
    });

    await waitFor(() => expect(stat("Total agents", 4)).toBeInTheDocument());
    expect(stat("Messages", 2)).toBeInTheDocument();
    expect(stat("Running agents", 3)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("agent-node-a-new")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Select agent patch-executor" })).toBeInTheDocument();
    expect(screen.getByTestId("timeline").querySelectorAll("[data-category]")).toHaveLength(8);

    act(() => es.emit(makeEvent(9, "run.completed", { payload: { from: "running", to: "completed" } })));
    await waitFor(() => expect(screen.getAllByText("Completed").length).toBeGreaterThan(0));
  });

  it("opens the agent inspector when a node is clicked", async () => {
    mockFetch(routes());
    renderWithClient(<FleetDashboard />);
    const node = await screen.findByTestId("agent-node-a-res");
    fireEvent.click(node);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "research-lead" })).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByText("orchestrator (orchestrator)")).toBeInTheDocument());
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("selects the run from ?run= in the URL", async () => {
    const { navigation } = await import("./navigation");
    navigation.search = "run=run-2";
    const fetchMock = mockFetch(routes({ "GET /api/v1/runs/run-2/snapshot": makeSnapshot({ run: { ...makeSnapshot().run, id: "run-2", title: "Other" }, agents: [] }) }));
    renderWithClient(<FleetDashboard />);
    await waitFor(() => expect(stat("Total agents", 0)).toBeInTheDocument());
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/runs/run-2/snapshot"))).toBe(true);
    expect(screen.getByText("No agents in this run yet")).toBeInTheDocument();
  });
});

describe("Dashboard empty and error states", () => {
  beforeEach(() => {
    MockEventSource.reset();
    vi.stubGlobal("EventSource", MockEventSource);
  });

  it("guides the user when there are no runs", async () => {
    mockFetch({ "GET /api/v1/runs": { items: [], total: 0, limit: 50, offset: 0 } });
    renderWithClient(<FleetDashboard />);
    expect(await screen.findByRole("heading", { name: "No runs yet" })).toBeInTheDocument();
    expect(screen.getByText(/Connect Claude Code/)).toBeInTheDocument();
    expect(screen.getByText("claude mcp list")).toBeInTheDocument();
    expect(screen.getByText("pnpm dev:runner")).toBeInTheDocument();
    expect(screen.getByLabelText("Total agents: not available")).toBeInTheDocument();
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it("tells the user to start the backend when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    renderWithClient(<FleetDashboard />);
    expect(await screen.findByText("The Agent Fleet API is not reachable")).toBeInTheDocument();
    expect(screen.getByText("pnpm dev:api")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
  });

  it("shows the API error message when the run cannot be loaded", async () => {
    mockFetch(
      routes({
        [`GET /api/v1/runs/${RUN_ID}/snapshot`]: () => ({ status: 404, body: { error: { code: "not_found", message: "run not found", details: {} } } }),
      }),
    );
    renderWithClient(<FleetDashboard />);
    expect(await screen.findByText("run not found")).toBeInTheDocument();
    expect(screen.getByText("This run could not be loaded")).toBeInTheDocument();
  });
});
