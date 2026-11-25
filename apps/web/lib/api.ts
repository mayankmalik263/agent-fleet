// Typed fetch client for the Agent Fleet REST API.
import { apiBaseUrl } from "./config";
import type {
  AgentDetails,
  AgentRead,
  ApprovalRead,
  ErrorBody,
  EventRead,
  MessageRead,
  Overview,
  Page,
  ProviderStatus,
  RunCreate,
  RunListItem,
  RunListParams,
  RunRead,
  RunnerStatusResponse,
  RunSnapshot,
  SystemStatus,
  TaskRead,
} from "./types";

/** An error from the API, or a network failure (status 0). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** True when the API did not answer at all. */
  get isNetworkError(): boolean {
    return this.status === 0;
  }

  /** Field level messages from a 422 validation error. */
  get fieldErrors(): string[] {
    const errors = this.details.errors;
    if (!Array.isArray(errors)) return [];
    return errors
      .map((e) => {
        if (!e || typeof e !== "object") return "";
        const item = e as { loc?: unknown; msg?: unknown };
        const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
        const msg = typeof item.msg === "string" ? item.msg : "";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter(Boolean);
  }
}

type Query = Record<string, string | number | boolean | string[] | undefined | null>;

/** Build a full API URL with query parameters. Arrays become repeated keys. */
export function buildUrl(path: string, query?: Query): string {
  const url = new URL(apiBaseUrl() + path);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      if (Array.isArray(value)) value.forEach((v) => url.searchParams.append(key, v));
      else url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function isErrorBody(value: unknown): value is { error: ErrorBody } {
  if (!value || typeof value !== "object") return false;
  const err = (value as { error?: unknown }).error;
  return !!err && typeof err === "object" && typeof (err as { message?: unknown }).message === "string";
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit & { query?: Query } = {},
): Promise<T> {
  const { query, headers, ...rest } = init;
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      ...rest,
      headers: { Accept: "application/json", ...(rest.body ? { "Content-Type": "application/json" } : {}), ...headers },
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the Agent Fleet API at ${apiBaseUrl()}.`);
  }
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    if (isErrorBody(data)) {
      const { code, message, details } = data.error;
      throw new ApiError(response.status, code, message, details ?? {});
    }
    throw new ApiError(response.status, "http_error", `Request failed with status ${response.status}.`);
  }
  return data as T;
}

const v1 = "/api/v1";

export const api = {
  health: () => apiFetch<{ status: string }>("/health"),
  systemStatus: (refresh = false) =>
    apiFetch<SystemStatus>(`${v1}/system/status`, { query: { refresh: refresh || undefined } }),
  providers: (refresh = false) =>
    apiFetch<ProviderStatus[]>(`${v1}/system/providers`, { query: { refresh: refresh || undefined } }),
  overview: () => apiFetch<Overview>(`${v1}/overview`),
  runnerStatus: () => apiFetch<RunnerStatusResponse>(`${v1}/runner/status`),

  listRuns: (params: RunListParams = {}) =>
    apiFetch<Page<RunListItem>>(`${v1}/runs`, { query: { ...params } }),
  getRun: (id: string) => apiFetch<RunRead>(`${v1}/runs/${encodeURIComponent(id)}`),
  createRun: (body: RunCreate) =>
    apiFetch<RunRead>(`${v1}/runs`, { method: "POST", body: JSON.stringify(body) }),
  cancelRun: (id: string) =>
    apiFetch<RunRead>(`${v1}/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  snapshot: (id: string) => apiFetch<RunSnapshot>(`${v1}/runs/${encodeURIComponent(id)}/snapshot`),
  events: (id: string, query: { after?: number; limit?: number; offset?: number; event_type?: string[]; agent_id?: string } = {}) =>
    apiFetch<Page<EventRead>>(`${v1}/runs/${encodeURIComponent(id)}/events`, { query }),
  runAgents: (id: string) => apiFetch<AgentRead[]>(`${v1}/runs/${encodeURIComponent(id)}/agents`),
  runTasks: (id: string) => apiFetch<TaskRead[]>(`${v1}/runs/${encodeURIComponent(id)}/tasks`),
  runMessages: (id: string, query: { limit?: number; offset?: number; agent_id?: string } = {}) =>
    apiFetch<Page<MessageRead>>(`${v1}/runs/${encodeURIComponent(id)}/messages`, { query }),
  runApprovals: (id: string) => apiFetch<ApprovalRead[]>(`${v1}/runs/${encodeURIComponent(id)}/approvals`),

  agentDetails: (id: string) => apiFetch<AgentDetails>(`${v1}/agents/${encodeURIComponent(id)}`),
  getTask: (id: string) => apiFetch<TaskRead>(`${v1}/tasks/${encodeURIComponent(id)}`),
};

/** URL of the SSE stream for one run, starting after the given sequence number. */
export function eventStreamUrl(runId: string, after: number): string {
  return buildUrl(`${v1}/runs/${encodeURIComponent(runId)}/events/stream`, { after: after > 0 ? after : undefined });
}

/** A short message for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unknown error";
}
