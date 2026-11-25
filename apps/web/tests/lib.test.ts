import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { categorizeEvent, eventLink, mergeEvents, parseEventFrame } from "@/lib/events";
import { durationMs, formatDuration, formatTokens, initials, toMs } from "@/lib/format";
import { buildGraph, taskStatsByAgent } from "@/lib/graph";
import { hierarchicalLayout, hierarchyOrder } from "@/lib/layout";
import { applyEvents } from "@/lib/liveState";
import { countByFilter, filterTasks } from "@/lib/taskFilters";
import { buildLanes, computeTimeline, DEFAULT_TIMELINE, SYSTEM_LANE_ID } from "@/lib/timeline";
import { usageLines } from "@/lib/usage";
import { agents, events, makeEvent, makeSnapshot, tasks } from "./fixtures";

const opts = { nodeWidth: 100, nodeHeight: 50, hGap: 10, vGap: 20 };

describe("hierarchicalLayout", () => {
  it("puts children one level below the parent and centres the parent", () => {
    const pos = hierarchicalLayout(
      [
        { id: "root", parentId: null },
        { id: "a", parentId: "root" },
        { id: "b", parentId: "root" },
      ],
      opts,
    );
    expect(pos.a.y).toBe(70);
    expect(pos.b.y).toBe(70);
    expect(pos.root.y).toBe(0);
    expect(pos.b.x - pos.a.x).toBe(110);
    // The parent sits over the middle of its children.
    expect(pos.root.x + 50).toBe((pos.a.x + 50 + pos.b.x + 50) / 2);
  });

  it("never overlaps nodes on the same level", () => {
    const items = [
      { id: "r", parentId: null },
      { id: "a", parentId: "r" },
      { id: "b", parentId: "r" },
      { id: "a1", parentId: "a" },
      { id: "a2", parentId: "a" },
      { id: "b1", parentId: "b" },
      { id: "b2", parentId: "b" },
      { id: "b3", parentId: "b" },
    ];
    const pos = hierarchicalLayout(items, opts);
    const level2 = ["a1", "a2", "b1", "b2", "b3"].map((id) => pos[id].x).sort((x, y) => x - y);
    for (let i = 1; i < level2.length; i += 1) expect(level2[i] - level2[i - 1]).toBeGreaterThanOrEqual(110);
  });

  it("is deterministic and handles orphans and cycles", () => {
    const items = [
      { id: "x", parentId: "y" },
      { id: "y", parentId: "x" },
      { id: "o", parentId: "missing" },
    ];
    const first = hierarchicalLayout(items, opts);
    expect(Object.keys(first).sort()).toEqual(["o", "x", "y"]);
    expect(hierarchicalLayout(items, opts)).toEqual(first);
    expect(hierarchyOrder(items)).toHaveLength(3);
  });

  it("re-layouts when an agent is added", () => {
    const before = hierarchicalLayout([{ id: "r", parentId: null }, { id: "a", parentId: "r" }], opts);
    const after = hierarchicalLayout([{ id: "r", parentId: null }, { id: "a", parentId: "r" }, { id: "b", parentId: "r" }], opts);
    expect(after.b).toBeDefined();
    // The parent moves to stay centred over both children.
    expect(after.r.x).not.toBe(before.r.x);
    expect(after.b.y).toBe(after.a.y);
  });
});

describe("mergeEvents", () => {
  it("removes duplicates and orders by sequence number", () => {
    const merged = mergeEvents([events[0], events[2]], [events[1], events[2], events[3]]);
    expect(merged.map((e) => e.sequence_number)).toEqual([1, 2, 3, 4]);
  });

  it("returns the same array when nothing is new", () => {
    const log = [events[0], events[1]];
    expect(mergeEvents(log, [events[1]])).toBe(log);
    expect(mergeEvents(log, [])).toBe(log);
  });

  it("parses SSE frames and rejects bad data", () => {
    expect(parseEventFrame(JSON.stringify(events[0]))?.sequence_number).toBe(1);
    expect(parseEventFrame("not json")).toBeNull();
    expect(parseEventFrame("{}")).toBeNull();
  });
});

describe("event classification", () => {
  it("maps event types to legend categories", () => {
    expect(categorizeEvent(makeEvent(1, "run.created"))).toBe("system");
    expect(categorizeEvent(makeEvent(1, "message.sent"))).toBe("message");
    expect(categorizeEvent(makeEvent(1, "tool.started"))).toBe("tool_call");
    expect(categorizeEvent(makeEvent(1, "tool.completed"))).toBe("tool_result");
    expect(categorizeEvent(makeEvent(1, "tool.failed"))).toBe("error");
    expect(categorizeEvent(makeEvent(1, "task.created"))).toBe("delegation");
    expect(categorizeEvent(makeEvent(1, "task.review_requested"))).toBe("review");
    expect(categorizeEvent(makeEvent(1, "task.started", { agent_id: "a-rev" }), () => "reviewer")).toBe("review");
    expect(categorizeEvent(makeEvent(1, "agent.started"))).toBe("agent");
  });

  it("links message sender to receiver and delegation creator to assignee", () => {
    expect(eventLink(events[3])).toEqual({ from: "a-orch", to: "a-res", kind: "message" });
    expect(eventLink(events[2])).toEqual({ from: "a-orch", to: "a-res", kind: "delegation" });
    expect(eventLink(events[0])).toBeNull();
  });
});

describe("applyEvents (live state)", () => {
  it("ignores events already in the snapshot", () => {
    const live = applyEvents(makeSnapshot(), events);
    expect(live.agents).toHaveLength(3);
    expect(live.messageCount).toBe(1);
  });

  it("adds agents, tasks and messages from newer events", () => {
    const newer = [
      makeEvent(7, "agent.created", { agent_id: "a-new", parent_agent_id: "a-orch", payload: { name: "patcher", role: "executor", model_alias: "sonnet", status: "queued" } }),
      makeEvent(8, "agent.started", { agent_id: "a-new" }),
      makeEvent(9, "task.created", { agent_id: "a-orch", task_id: "t-new", payload: { assigned_agent_id: "a-new", created_by_agent_id: "a-orch" } }),
      makeEvent(10, "task.progress", { task_id: "t-2", payload: { from: "in_progress", to: "in_progress", progress_percentage: 70 } }),
      makeEvent(11, "message.sent", { agent_id: "a-new", payload: { receiver_agent_id: "a-orch" } }),
    ];
    const live = applyEvents(makeSnapshot(), [...events, ...newer]);
    const agent = live.agents.find((a) => a.id === "a-new");
    expect(agent).toMatchObject({ name: "patcher", role: "executor", status: "running", parent_agent_id: "a-orch" });
    expect(live.tasks.find((t) => t.id === "t-new")?.assigned_agent_id).toBe("a-new");
    expect(live.tasks.find((t) => t.id === "t-2")?.progress_percentage).toBe(70);
    expect(live.messageCount).toBe(2);
    expect(live.eventCount).toBe(11);
  });

  it("marks the run as ended on run.completed", () => {
    const live = applyEvents(makeSnapshot(), [makeEvent(7, "run.completed", { payload: { from: "running", to: "completed" } })]);
    expect(live.run.status).toBe("completed");
    expect(live.ended).toBe(true);
  });
});

describe("timeline geometry", () => {
  it("creates one lane per agent in hierarchy order plus a System lane", () => {
    const lanes = buildLanes(agents, events);
    expect(lanes.map((l) => l.id)).toEqual(["a-orch", "a-res", "a-rev", SYSTEM_LANE_ID]);
  });

  it("orders markers by time, keeps a minimum gap and links sender to receiver", () => {
    const lanes = buildLanes(agents, events);
    const geo = computeTimeline(events, lanes, DEFAULT_TIMELINE);
    const xs = geo.markers.map((m) => m.x);
    for (let i = 1; i < xs.length; i += 1) expect(xs[i] - xs[i - 1]).toBeGreaterThanOrEqual(DEFAULT_TIMELINE.minGap);
    expect(geo.markers[0].lane).toBe(3); // run.created goes to the System lane
    const message = geo.links.find((l) => l.kind === "message");
    expect(message).toMatchObject({ fromLane: 0, toLane: 1 });
    expect(geo.links.some((l) => l.kind === "delegation")).toBe(true);
  });

  it("shortens long idle gaps and filters by category and lane", () => {
    const lanes = buildLanes(agents, events);
    const gap = [makeEvent(1, "run.created"), makeEvent(2, "run.started", { timestamp: "2026-11-24T23:00:00Z" })];
    const geo = computeTimeline(gap, lanes, DEFAULT_TIMELINE);
    expect(geo.markers[1].x - geo.markers[0].x).toBe(DEFAULT_TIMELINE.maxGap);
    expect(geo.compressed).toBe(true);
    const onlyMessages = computeTimeline(events, lanes, { ...DEFAULT_TIMELINE, categories: new Set(["message"]) });
    expect(onlyMessages.markers).toHaveLength(1);
    const oneLane = computeTimeline(events, lanes, { ...DEFAULT_TIMELINE, laneIds: new Set(["a-res"]) });
    expect(oneLane.lanes).toHaveLength(1);
    expect(oneLane.markers.every((m) => m.event.agent_id === "a-res")).toBe(true);
  });
});

describe("formatters", () => {
  it("formats durations and live spans", () => {
    expect(formatDuration(65_000)).toBe("1m 05s");
    expect(formatDuration(3_720_000)).toBe("1h 02m");
    expect(formatDuration(null)).toBe("Not available");
    expect(durationMs("2026-01-01T00:00:00Z", null, Date.parse("2026-01-01T00:00:10Z"))).toBe(10_000);
    expect(durationMs("2026-01-01T00:00:00Z", null)).toBeNull();
  });

  it("treats a datetime without zone as UTC", () => {
    expect(toMs("2026-01-01T00:00:00")).toBe(Date.parse("2026-01-01T00:00:00Z"));
  });

  it("returns null token text when usage is missing", () => {
    expect(formatTokens(null, null)).toBeNull();
    expect(formatTokens(1500, 20)).toBe("1.5k in / 20 out");
    expect(initials("research-lead")).toBe("RL");
  });

  it("labels costs as client-side estimates", () => {
    expect(usageLines({ estimated_cost_usd: 0.0123, usage: { input_tokens: 2000 } })).toEqual([
      { label: "Estimated cost (client-side)", value: "$0.0123" },
      { label: "Input tokens", value: "2k" },
    ]);
    expect(usageLines(null)).toEqual([]);
  });

  it("reads field errors from API validation errors", () => {
    const err = new ApiError(422, "validation_failed", "request validation failed", {
      errors: [{ loc: ["body", "task_description"], msg: "Field required" }],
    });
    expect(err.fieldErrors).toEqual(["task_description: Field required"]);
  });
});

describe("graph and task helpers", () => {
  it("counts completed tasks per agent and finds real progress", () => {
    const stats = taskStatsByAgent(agents, tasks);
    expect(stats.get("a-res")).toMatchObject({ total: 2, completed: 1, currentProgress: 40 });
    expect(stats.get("a-orch")).toMatchObject({ total: 0, completed: 0, currentProgress: null });
  });

  it("builds delegation edges parent to child and dims unrelated nodes", () => {
    const graph = buildGraph({ agents, tasks, events, selectedAgentId: "a-res", search: "", runEnded: false });
    expect(graph.nodes).toHaveLength(3);
    expect(graph.edges.filter((e) => e.id.startsWith("d:")).map((e) => [e.source, e.target])).toEqual([
      ["a-orch", "a-res"],
      ["a-orch", "a-rev"],
    ]);
    expect(graph.edges.some((e) => e.id === "m:a-orch:a-res")).toBe(true);
    expect(graph.nodes.find((n) => n.id === "a-rev")?.data.dimmed).toBe(true);
    expect(graph.nodes.find((n) => n.id === "a-orch")?.data.dimmed).toBe(false);
  });

  it("filters tasks by status group and search", () => {
    const byId = new Map(agents.map((a) => [a.id, a]));
    expect(filterTasks(tasks, "done", "", byId).map((t) => t.id)).toEqual(["t-1"]);
    expect(filterTasks(tasks, "failed", "", byId).map((t) => t.id)).toEqual(["t-4"]);
    expect(filterTasks(tasks, "all", "reviewer", byId).map((t) => t.id).sort()).toEqual(["t-3", "t-4"]);
    expect(countByFilter(tasks)).toMatchObject({ all: 4, in_progress: 1, pending: 1, review: 0, done: 1, failed: 1 });
  });
});
