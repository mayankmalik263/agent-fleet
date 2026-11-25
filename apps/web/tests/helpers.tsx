// Shared test helpers: fetch routing, a controllable EventSource and a render wrapper.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

type Handler = (url: URL, init?: RequestInit) => { status?: number; body: unknown } | Promise<{ status?: number; body: unknown }>;

/** Route fetch calls by "METHOD /path". Unknown routes return 404 with the API error shape. */
export function mockFetch(routes: Record<string, Handler | unknown>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
    const key = `${(init?.method ?? "GET").toUpperCase()} ${url.pathname}`;
    const route = routes[key];
    if (route === undefined) {
      return new Response(JSON.stringify({ error: { code: "not_found", message: `no mock for ${key}`, details: {} } }), { status: 404 });
    }
    const result = typeof route === "function" ? await (route as Handler)(url, init) : { body: route };
    return new Response(JSON.stringify(result.body), { status: result.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** EventSource stand-in that tests drive by hand. */
export class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  closed = false;
  onopen: ((ev: Event) => unknown) | null = null;
  onmessage: ((ev: MessageEvent) => unknown) | null = null;
  onerror: ((ev: Event) => unknown) | null = null;
  private listeners = new Map<string, ((ev: MessageEvent) => void)[]>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  static reset() {
    MockEventSource.instances = [];
  }

  static latest(): MockEventSource {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }

  addEventListener(type: string, listener: (ev: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close() {
    this.closed = true;
  }

  open() {
    this.onopen?.(new Event("open"));
  }

  emit(data: unknown, id?: number) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data), lastEventId: id !== undefined ? String(id) : "" }));
  }

  emitNamed(type: string, data: unknown) {
    for (const l of this.listeners.get(type) ?? []) l(new MessageEvent(type, { data: JSON.stringify(data) }));
  }

  fail() {
    this.onerror?.(new Event("error"));
  }
}

export function makeTestClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 0 }, mutations: { retry: false } } });
}

export function renderWithClient(ui: ReactElement, client = makeTestClient()) {
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) };
}
