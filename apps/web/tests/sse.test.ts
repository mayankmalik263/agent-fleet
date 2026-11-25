import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backoffDelay, RunEventStream, type StreamStatusInfo } from "@/lib/sse";
import type { EventRead } from "@/lib/types";
import { makeEvent, RUN_ID } from "./fixtures";
import { MockEventSource } from "./helpers";

function setup() {
  const batches: EventRead[][] = [];
  const statuses: StreamStatusInfo[] = [];
  const stream = new RunEventStream({
    runId: RUN_ID,
    onEvents: (e) => batches.push(e),
    onStatus: (s) => statuses.push(s),
    createEventSource: (url) => new MockEventSource(url),
    flushMs: 0,
    jitter: false,
    minBackoffMs: 100,
    maxBackoffMs: 400,
  });
  stream.start();
  return { stream, batches, statuses };
}

describe("RunEventStream", () => {
  beforeEach(() => {
    MockEventSource.reset();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("replays from after=0 and drops duplicate sequence numbers", () => {
    const { batches, statuses } = setup();
    const es = MockEventSource.latest();
    expect(es.url).toContain(`/api/v1/runs/${RUN_ID}/events/stream`);
    expect(es.url).not.toContain("after=");
    es.open();
    es.emit(makeEvent(1, "run.created"), 1);
    es.emit(makeEvent(2, "run.started"), 2);
    es.emit(makeEvent(2, "run.started"), 2);
    expect(batches.flat().map((e) => e.sequence_number)).toEqual([1, 2]);
    expect(statuses.map((s) => s.status)).toEqual(["connecting", "open"]);
  });

  it("ignores events of other runs and bad frames", () => {
    const { batches } = setup();
    const es = MockEventSource.latest();
    es.emit({ ...makeEvent(1, "run.created"), run_id: "other" });
    es.onmessage?.(new MessageEvent("message", { data: "garbage" }));
    expect(batches).toHaveLength(0);
  });

  it("reconnects with backoff and resumes after the last sequence number", () => {
    const { statuses, stream } = setup();
    const first = MockEventSource.latest();
    first.emit(makeEvent(5, "agent.started"), 5);
    first.fail();
    expect(first.closed).toBe(true);
    expect(statuses.at(-1)).toMatchObject({ status: "reconnecting", retryInMs: 100 });
    vi.advanceTimersByTime(100);
    const second = MockEventSource.latest();
    expect(second).not.toBe(first);
    expect(second.url).toContain("after=5");
    // No message arrived on the second connection, so the delay doubles.
    second.fail();
    expect(statuses.at(-1)).toMatchObject({ status: "reconnecting", retryInMs: 200 });
    stream.stop();
  });

  it("grows the backoff while the connection keeps failing", () => {
    setup();
    MockEventSource.latest().fail();
    vi.advanceTimersByTime(100);
    MockEventSource.latest().fail();
    vi.advanceTimersByTime(200);
    MockEventSource.latest().fail();
    expect(MockEventSource.instances).toHaveLength(3);
    expect(backoffDelay(0, 100, 400)).toBe(100);
    expect(backoffDelay(2, 100, 400)).toBe(400);
    expect(backoffDelay(9, 100, 400)).toBe(400);
  });

  it("stops for good on the end event", () => {
    const { statuses } = setup();
    const es = MockEventSource.latest();
    es.emitNamed("end", { run_id: RUN_ID, last_sequence: 3 });
    expect(es.closed).toBe(true);
    expect(statuses.at(-1)?.status).toBe("ended");
    vi.advanceTimersByTime(10_000);
    expect(MockEventSource.instances).toHaveLength(1);
  });

  it("batches events that arrive inside the flush window", () => {
    const batches: EventRead[][] = [];
    const stream = new RunEventStream({
      runId: RUN_ID,
      onEvents: (e) => batches.push(e),
      createEventSource: (url) => new MockEventSource(url),
      flushMs: 50,
    });
    stream.start();
    const es = MockEventSource.latest();
    es.emit(makeEvent(2, "agent.started"));
    es.emit(makeEvent(1, "run.created"));
    expect(batches).toHaveLength(0);
    vi.advanceTimersByTime(50);
    expect(batches).toHaveLength(1);
    expect(batches[0].map((e) => e.sequence_number)).toEqual([1, 2]);
    stream.stop();
  });
});
