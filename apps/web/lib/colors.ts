// Colour tokens. Each value is a CSS variable, so the palette stays configurable in styles/globals.css.
import type { AgentStatus, RunStatus, TaskStatus } from "./types";

export const TOKENS = {
  primary: "var(--af-primary)",
  blue: "var(--af-blue)",
  green: "var(--af-green)",
  orange: "var(--af-orange)",
  yellow: "var(--af-yellow)",
  red: "var(--af-red)",
  text2: "var(--af-text-2)",
  border: "var(--af-border)",
} as const;

const ROLE_ACCENTS: Record<string, string> = {
  orchestrator: TOKENS.primary,
  researcher: TOKENS.blue,
  analyst: TOKENS.yellow,
  executor: TOKENS.orange,
  reviewer: TOKENS.green,
};

const CYCLE = [TOKENS.blue, TOKENS.green, TOKENS.orange, TOKENS.yellow, TOKENS.primary, TOKENS.red];

function hash(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** Accent colour for an agent role. Unknown roles get a stable colour from a cycle. */
export function roleAccent(role: string | null | undefined): string {
  const key = (role ?? "").toLowerCase();
  if (ROLE_ACCENTS[key]) return ROLE_ACCENTS[key];
  for (const [name, color] of Object.entries(ROLE_ACCENTS)) {
    if (key.includes(name)) return color;
  }
  return CYCLE[hash(key) % CYCLE.length];
}

export type Tone = "neutral" | "active" | "success" | "warning" | "danger" | "info";

export const TONE_COLOR: Record<Tone, string> = {
  neutral: TOKENS.text2,
  active: TOKENS.primary,
  success: TOKENS.green,
  warning: TOKENS.yellow,
  danger: TOKENS.red,
  info: TOKENS.blue,
};

export function agentStatusTone(status: AgentStatus): Tone {
  switch (status) {
    case "running":
    case "reviewing":
      return "active";
    case "waiting":
    case "queued":
      return "warning";
    case "completed":
      return "success";
    case "failed":
      return "danger";
    default:
      return "neutral";
  }
}

export function runStatusTone(status: RunStatus): Tone {
  switch (status) {
    case "running":
    case "planning":
      return "active";
    case "queued":
    case "awaiting_approval":
      return "warning";
    case "completed":
      return "success";
    case "failed":
      return "danger";
    default:
      return "neutral";
  }
}

export function taskStatusTone(status: TaskStatus): Tone {
  switch (status) {
    case "in_progress":
      return "active";
    case "review":
      return "info";
    case "blocked":
      return "warning";
    case "completed":
      return "success";
    case "failed":
      return "danger";
    default:
      return "neutral";
  }
}
