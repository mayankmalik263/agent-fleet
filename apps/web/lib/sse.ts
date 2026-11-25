// SSE client for the run event stream.
// - Replays from a cursor (after=0 on first connect, then the last seen sequence number).
// - Reconnects with exponential backoff and resumes with ?after=<last sequence>.
// - Drops duplicate sequence numbers and delivers events in batches.
// - Stops for good when the server sends the "end" event (run is terminal and fully sent).
import { eventStreamUrl } from "./api";
import { parseEventFrame } from "./events";
import type { EventRead } from "./types";

export type StreamStatus = "idle" | "connecting" | "open" | "reconnecting" | "ended";

export interface StreamStatusInfo {
  status: StreamStatus;
  attempt: number;
  /** Delay before the next reconnect attempt, when status is "reconnecting". */
  retryInMs?: number;
}

/** The subset of EventSource that the client uses. Tests pass a mock. */
export interface EventSourceLike {
  onopen: ((ev: Event) => unknown) | null;
  onmessage: ((ev: MessageEvent) => unknown) | null;
  onerror: ((ev: Event) => unknown) | null;
  addEventListener(type: string, listener: (ev: MessageEvent) => void): void;
  close(): void;
}

export interface RunEventStreamOptions {
  runId: string;
  /** Start after this sequence number. 0 replays the full log. */
  after?: number;
  onEvents: (events: EventRead[]) => void;
  onStatus?: (info: StreamStatusInfo) => void;
  onEnd?: (lastSequence: number) => void;
  createEventSource?: (url: string) => EventSourceLike;
  minBackoffMs?: number;
  maxBackoffMs?: number;
  /** Batch window in ms. Events that arrive inside the window are delivered together. */
  flushMs?: number;
  jitter?: boolean;
}

export function backoffDelay(attempt: number, minMs: number, maxMs: number, jitter = false): number {
  const base = Math.min(maxMs, minMs * 2 ** Math.max(0, attempt));
  if (!jitter) return base;
  // Up to 20 % random spread, so many tabs do not reconnect at the same moment.
  return Math.round(base * (0.8 + Math.random() * 0.2));
}

export class RunEventStream {
  private readonly options: Required<Omit<RunEventStreamOptions, "onStatus" | "onEnd" | "createEventSource">> &
    Pick<RunEventStreamOptions, "onStatus" | "onEnd" | "createEventSource">;
  private source: EventSourceLike | null = null;
  private lastSeq: number;
  private readonly seen = new Set<number>();
  private buffer: EventRead[] = [];
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private stopped = false;
  private ended = false;

  constructor(options: RunEventStreamOptions) {
    this.options = {
      after: 0,
      minBackoffMs: 1000,
      maxBackoffMs: 15000,
      flushMs: 50,
      jitter: true,
      ...options,
    };
    this.lastSeq = this.options.after;
  }

  get lastSequence(): number {
    return this.lastSeq;
  }

  start(): void {
    this.stopped = false;
    this.connect();
  }

  /** Close the connection and cancel all timers. No more callbacks run after this. */
  stop(): void {
    this.stopped = true;
    this.clearTimers();
    this.closeSource();
    this.buffer = [];
  }

  private connect(): void {
    if (this.stopped || this.ended) return;
    this.emitStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    const url = eventStreamUrl(this.options.runId, this.lastSeq);
    const factory = this.options.createEventSource ?? ((u: string) => new EventSource(u) as unknown as EventSourceLike);
    let source: EventSourceLike;
    try {
      source = factory(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.source = source;

    source.onopen = () => {
      if (this.source !== source) return;
      this.attempt = 0;
      this.emitStatus("open");
    };
    source.onmessage = (ev: MessageEvent) => {
      if (this.source !== source) return;
      this.receive(typeof ev.data === "string" ? ev.data : "");
    };
    source.addEventListener("end", () => {
      if (this.source !== source) return;
      this.ended = true;
      this.flush();
      this.closeSource();
      this.emitStatus("ended");
      this.options.onEnd?.(this.lastSeq);
    });
    source.onerror = () => {
      if (this.source !== source) return;
      // Own the retry: close the native source and reconnect with our cursor and backoff.
      this.closeSource();
      this.flush();
      this.scheduleReconnect();
    };
  }

  private receive(data: string): void {
    const event = parseEventFrame(data);
    if (!event || event.run_id !== this.options.runId) return;
    if (this.seen.has(event.sequence_number)) return;
    this.seen.add(event.sequence_number);
    if (event.sequence_number > this.lastSeq) this.lastSeq = event.sequence_number;
    // A message proves the connection works, so reset the backoff.
    this.attempt = 0;
    this.buffer.push(event);
    if (this.options.flushMs <= 0) {
      this.flush();
    } else if (!this.flushTimer) {
      this.flushTimer = setTimeout(() => this.flush(), this.options.flushMs);
    }
  }

  private flush(): void {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    if (this.stopped || this.buffer.length === 0) return;
    const batch = this.buffer.sort((a, b) => a.sequence_number - b.sequence_number);
    this.buffer = [];
    this.options.onEvents(batch);
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.ended) return;
    const delay = backoffDelay(this.attempt, this.options.minBackoffMs, this.options.maxBackoffMs, this.options.jitter);
    this.attempt += 1;
    this.emitStatus("reconnecting", delay);
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, delay);
  }

  private emitStatus(status: StreamStatus, retryInMs?: number): void {
    if (this.stopped) return;
    this.options.onStatus?.({ status, attempt: this.attempt, retryInMs });
  }

  private closeSource(): void {
    if (this.source) {
      this.source.onopen = null;
      this.source.onmessage = null;
      this.source.onerror = null;
      this.source.close();
      this.source = null;
    }
  }

  private clearTimers(): void {
    if (this.flushTimer) clearTimeout(this.flushTimer);
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.flushTimer = null;
    this.retryTimer = null;
  }
}
