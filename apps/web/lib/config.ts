// Runtime configuration for the dashboard.

export const DEFAULT_API_URL = "http://127.0.0.1:8420";

/** Base URL of the Agent Fleet API, without a trailing slash. */
export function apiBaseUrl(): string {
  const value = process.env.NEXT_PUBLIC_AGENT_FLEET_API_URL;
  const url = value && value.trim() ? value.trim() : DEFAULT_API_URL;
  return url.replace(/\/+$/, "");
}

/** Command hints that the UI shows to the user. */
export const COMMANDS = {
  api: "pnpm dev:api",
  runner: "pnpm dev:runner",
  web: "pnpm dev:web",
  mcpList: "claude mcp list",
} as const;
