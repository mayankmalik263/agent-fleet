// Formatters for times, durations, counts and labels.

export const NOT_AVAILABLE = "Not available";

/** Parse an ISO string to epoch milliseconds. Returns null for missing or bad values. */
export function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  // The backend may send naive UTC datetimes. Treat a value with no zone as UTC.
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso);
  const ms = Date.parse(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(ms) ? null : ms;
}

/** Format a millisecond span as "1h 02m", "3m 05s" or "12s". */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return NOT_AVAILABLE;
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2, "0")}s`;
  if (total === 0 && ms > 0) return "<1s";
  return `${s}s`;
}

/**
 * Duration between a start and an end time.
 * When the end is missing and `now` is given, the span runs to `now` (live value).
 */
export function durationMs(
  startIso: string | null | undefined,
  endIso: string | null | undefined,
  now?: number,
): number | null {
  const start = toMs(startIso);
  if (start === null) return null;
  const end = toMs(endIso) ?? (now !== undefined ? now : null);
  if (end === null) return null;
  return Math.max(0, end - start);
}

export function formatTime(iso: string | null | undefined): string {
  const ms = toMs(iso);
  if (ms === null) return NOT_AVAILABLE;
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function formatDateTime(iso: string | null | undefined): string {
  const ms = toMs(iso);
  if (ms === null) return NOT_AVAILABLE;
  const d = new Date(ms);
  return `${d.toLocaleDateString([], { year: "numeric", month: "short", day: "2-digit" })} ${d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })}`;
}

/** Compact integer: 950, 1.2k, 3.4M. */
export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NOT_AVAILABLE;
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (abs >= 10_000) return `${Math.round(value / 1000)}k`;
  if (abs >= 1_000) return `${(value / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(value);
}

/** Token usage text. Returns null when the API has no usage data. */
export function formatTokens(input: number | null | undefined, output: number | null | undefined): string | null {
  if ((input === null || input === undefined) && (output === null || output === undefined)) return null;
  const parts: string[] = [];
  if (input !== null && input !== undefined) parts.push(`${formatCount(input)} in`);
  if (output !== null && output !== undefined) parts.push(`${formatCount(output)} out`);
  return parts.join(" / ");
}

/** One or two initials from an agent name, for example "research-lead" gives "RL". */
export function initials(name: string): string {
  const words = name
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .split(/[\s._\-:]+/)
    .filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export function truncate(text: string | null | undefined, max: number): string {
  if (!text) return "";
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, Math.max(0, max - 1))}…` : clean;
}

/** "in_progress" becomes "In progress". */
export function humanize(value: string | null | undefined): string {
  if (!value) return NOT_AVAILABLE;
  const text = value.replace(/[_.]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function shortId(id: string | null | undefined): string {
  if (!id) return NOT_AVAILABLE;
  return id.length > 8 ? id.slice(0, 8) : id;
}

const SOURCE_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  claude_code: "Claude Code",
  api: "API",
};

const PROVIDER_LABELS: Record<string, string> = {
  claude_code_local: "Local Claude Code",
  anthropic_api: "Anthropic API",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? humanize(source);
}

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? humanize(provider);
}
