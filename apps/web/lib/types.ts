// Types that mirror the backend schemas.
// Source of truth: apps/backend/agent_fleet/schemas/models.py and core/enums.py.
// Datetimes arrive as ISO 8601 strings.

export type RunSource = "dashboard" | "claude_code" | "api";
export type ExecutionMode = "local_claude_code" | "api_provider";
export type ProviderName = "claude_code_local" | "anthropic_api";

export type RunStatus =
  | "queued"
  | "planning"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentStatus =
  | "idle"
  | "queued"
  | "running"
  | "waiting"
  | "reviewing"
  | "completed"
  | "failed"
  | "cancelled";

export type TaskStatus =
  | "pending"
  | "in_progress"
  | "blocked"
  | "review"
  | "completed"
  | "failed"
  | "cancelled";

export type TaskPriority = "low" | "normal" | "high" | "critical";
export type PermissionPolicy = "read_only" | "workspace_edit";
export type MessageType = "instruction" | "question" | "answer" | "status" | "result" | "review" | "note";
export type EventSource = "api" | "mcp" | "runner" | "hook" | "system";
export type ApprovalStatus = "pending" | "approved" | "rejected";
export type RunnerStatus = "online" | "busy" | "offline";
export type ProviderConnectionStatus =
  | "connected"
  | "disconnected"
  | "not_configured"
  | "authentication_required"
  | "unsupported_in_local_mode";

export const RUN_TERMINAL: readonly RunStatus[] = ["completed", "failed", "cancelled"];
export const AGENT_TERMINAL: readonly AgentStatus[] = ["completed", "failed", "cancelled"];
export const AGENT_ACTIVE: readonly AgentStatus[] = ["running", "waiting", "reviewing"];
export const TASK_TERMINAL: readonly TaskStatus[] = ["completed", "failed", "cancelled"];

export type JsonObject = Record<string, unknown>;

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ErrorBody {
  code: string;
  message: string;
  details: JsonObject;
}

export interface RunCreate {
  title?: string | null;
  task_description: string;
  execution_provider: ProviderName;
  workspace_path?: string | null;
  orchestrator_model: "sonnet" | "haiku";
  permission_policy: PermissionPolicy;
  max_concurrent_agents: number;
  confirm_workspace_edit: boolean;
  /** WebSearch and WebFetch for the run's agents. */
  web_access?: boolean;
}

export interface RunRetry {
  /** Retry only this task. Omit to retry the whole run. */
  task_id?: string | null;
  /** Default: the value of the original run. */
  web_access?: boolean | null;
}

export interface RunRead {
  id: string;
  workspace_id: string;
  title: string;
  task_description: string;
  source: RunSource;
  execution_mode: ExecutionMode;
  provider: ProviderName;
  root_agent_id: string | null;
  status: RunStatus;
  workspace_path: string | null;
  permission_policy: PermissionPolicy;
  orchestrator_model: string;
  max_concurrent_agents: number;
  web_access: boolean;
  retry_of_run_id: string | null;
  session_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  final_summary: string | null;
  error_message: string | null;
  attempt_count: number;
  cancel_requested: boolean;
  usage_json: JsonObject | null;
  event_count: number;
}

export interface RunListItem extends RunRead {
  agent_count: number;
  task_count: number;
  message_count: number;
}

export interface AgentRead {
  id: string;
  run_id: string;
  name: string;
  role: string;
  model_alias: string;
  provider: string;
  parent_agent_id: string | null;
  status: AgentStatus;
  current_task_id: string | null;
  external_ref: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  tool_call_count: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface TaskRead {
  id: string;
  run_id: string;
  title: string;
  description: string;
  assigned_agent_id: string | null;
  created_by_agent_id: string | null;
  parent_task_id: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  progress_percentage: number | null;
  result_summary: string | null;
  result_payload: JsonObject | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface MessageRead {
  id: string;
  run_id: string;
  sender_agent_id: string | null;
  receiver_agent_id: string | null;
  task_id: string | null;
  message_type: MessageType;
  content: string;
  metadata_json: JsonObject | null;
  timestamp: string;
}

export interface EventRead {
  id: string;
  run_id: string;
  sequence_number: number;
  event_type: string;
  agent_id: string | null;
  parent_agent_id: string | null;
  task_id: string | null;
  timestamp: string;
  message: string;
  payload: JsonObject | null;
  source: EventSource;
}

export interface ApprovalRead {
  id: string;
  run_id: string;
  requested_by_agent_id: string | null;
  action_type: string;
  description: string;
  status: ApprovalStatus;
  created_at: string;
  resolved_at: string | null;
}

export interface HierarchyNode {
  agent_id: string;
  name: string;
  children: HierarchyNode[];
}

export interface RunSnapshot {
  run: RunRead;
  agents: AgentRead[];
  hierarchy: HierarchyNode[];
  tasks: TaskRead[];
  recent_messages: MessageRead[];
  event_counts: Record<string, number>;
  total_events: number;
  agent_status_counts: Record<string, number>;
  task_status_counts: Record<string, number>;
}

export interface AgentDetails {
  agent: AgentRead;
  parent: AgentRead | null;
  current_task: TaskRead | null;
  children: AgentRead[];
  recent_messages: MessageRead[];
  tool_events: EventRead[];
  tasks: TaskRead[];
}

export interface ProviderStatus {
  provider: string;
  label: string;
  status: ProviderConnectionStatus;
  message: string;
  local_mode_supported: boolean;
  details: JsonObject;
}

export interface RunnerRead {
  id: string;
  name: string;
  runtime_type: string;
  status: RunnerStatus;
  last_seen_at: string | null;
  details_json: JsonObject | null;
  online: boolean;
}

export interface RunnerStatusResponse {
  runners: RunnerRead[];
  any_online: boolean;
  queued_runs: number;
  active_runs: number;
}

export interface IntegrationStatus {
  name: string;
  status: string;
  message: string;
  details: JsonObject;
}

export interface SystemStatus {
  status: "ok" | "degraded";
  version: string;
  mode: "local";
  database: string;
  providers: ProviderStatus[];
  runner: RunnerStatusResponse;
  integrations: IntegrationStatus[];
}

export interface Overview {
  total_runs: number;
  active_runs: number;
  total_agents: number;
  running_agents: number;
  total_tasks: number;
  total_messages: number;
  total_events: number;
  runs_by_status: Record<string, number>;
  latest_run_id: string | null;
}

export interface RunListParams {
  limit?: number;
  offset?: number;
  status?: RunStatus[];
  source?: RunSource;
  search?: string;
  sort?: string;
}
