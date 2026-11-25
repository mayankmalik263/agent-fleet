"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Globe } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Modal } from "@/components/ui/Modal";
import { queryKeys, useSystemStatus } from "@/hooks/queries";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { PermissionPolicy, RunCreate, RunRead } from "@/lib/types";
import { API_PROVIDER, RuntimeAvailability, runtimeProblems } from "./RuntimeAvailability";

interface NewRunModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (run: RunRead) => void;
}

function Field({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-[12px] font-medium text-fg">
        {label}
      </label>
      {children}
      {hint ? <div className="text-[11px] text-fg-3">{hint}</div> : null}
    </div>
  );
}

function NewRunForm({ onClose, onCreated }: Omit<NewRunModalProps, "open">) {
  const ids = { title: useId(), desc: useId(), provider: useId(), path: useId(), model: useId(), policy: useId(), max: useId(), confirm: useId(), web: useId() };
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [workspacePath, setWorkspacePath] = useState("");
  const [model, setModel] = useState<"sonnet" | "haiku">("sonnet");
  const [policy, setPolicy] = useState<PermissionPolicy>("read_only");
  const [maxAgents, setMaxAgents] = useState(4);
  const [confirmEdit, setConfirmEdit] = useState(false);
  const [webAccess, setWebAccess] = useState(true);
  const queryClient = useQueryClient();
  // Fetch a fresh runtime status each time the modal opens.
  const system = useSystemStatus({ refetchInterval: false });
  const apiProvider = system.data?.providers.find((p) => p.provider === API_PROVIDER);
  const runtime = runtimeProblems(system.data);

  const mutation = useMutation({
    mutationFn: (body: RunCreate) => api.createRun(body),
    onSuccess: (run) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runsAll });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      onCreated(run);
    },
  });

  const workspaceEdit = policy === "workspace_edit";
  const missing: string[] = [];
  if (!description.trim()) missing.push("Enter a task description.");
  if (workspaceEdit && !workspacePath.trim()) missing.push("Workspace edit needs a workspace path.");
  if (workspaceEdit && !confirmEdit) missing.push("Confirm that agents may edit files in the workspace.");
  if (!Number.isInteger(maxAgents) || maxAgents < 1 || maxAgents > 20) missing.push("Max concurrent agents must be 1 to 20.");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (missing.length) return;
    mutation.mutate({
      title: title.trim() || null,
      task_description: description.trim(),
      execution_provider: "claude_code_local",
      workspace_path: workspacePath.trim() || null,
      orchestrator_model: model,
      permission_policy: policy,
      max_concurrent_agents: maxAgents,
      confirm_workspace_edit: workspaceEdit && confirmEdit,
      web_access: webAccess,
    });
  };

  const apiError = mutation.error;
  const fieldErrors = apiError instanceof ApiError ? apiError.fieldErrors : [];
  const queueOnly = !system.isPending && !runtime.ready;

  return (
    <form onSubmit={submit} className="flex flex-col gap-3" aria-label="New run" noValidate>
      <Field label="Run title" htmlFor={ids.title} hint="Optional. The first line of the task is used when empty.">
        <input id={ids.title} data-autofocus className="af-input" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="Task description" htmlFor={ids.desc}>
        <textarea
          id={ids.desc}
          required
          rows={5}
          maxLength={20000}
          className="af-input resize-y"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe the goal for the orchestrator."
        />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Execution provider"
          htmlFor={ids.provider}
          hint={apiProvider ? `Anthropic API: ${apiProvider.message}` : "Anthropic API is not available in local mode."}
        >
          <select id={ids.provider} className="af-input" value="claude_code_local" onChange={() => undefined}>
            <option value="claude_code_local">Local Claude Code</option>
            <option value="anthropic_api" disabled>
              Anthropic API (unavailable)
            </option>
          </select>
        </Field>
        <Field label="Model (orchestrator)" htmlFor={ids.model}>
          <select id={ids.model} className="af-input" value={model} onChange={(e) => setModel(e.target.value as "sonnet" | "haiku")}>
            <option value="sonnet">Sonnet</option>
            <option value="haiku">Haiku</option>
          </select>
        </Field>
        <Field label="Permission policy" htmlFor={ids.policy}>
          <select
            id={ids.policy}
            className="af-input"
            value={policy}
            onChange={(e) => {
              setPolicy(e.target.value as PermissionPolicy);
              setConfirmEdit(false);
            }}
          >
            <option value="read_only">Read-only</option>
            <option value="workspace_edit">Workspace edit</option>
          </select>
        </Field>
        <Field label="Max concurrent agents" htmlFor={ids.max}>
          <input
            id={ids.max}
            type="number"
            min={1}
            max={20}
            className="af-input"
            value={Number.isFinite(maxAgents) ? maxAgents : ""}
            onChange={(e) => setMaxAgents(e.target.valueAsNumber)}
          />
        </Field>
      </div>
      <Field
        label={workspaceEdit ? "Workspace path (required)" : "Workspace path (optional)"}
        htmlFor={ids.path}
        hint="A folder that the API allows. Agents work inside this folder."
      >
        <input id={ids.path} className="af-input af-mono" value={workspacePath} onChange={(e) => setWorkspacePath(e.target.value)} placeholder={"D:\\projects\\my-repo"} />
      </Field>

      <label htmlFor={ids.web} className="flex items-start gap-2 rounded-md border border-line-soft bg-panel-2/50 px-3 py-2 text-[12px]">
        <input id={ids.web} type="checkbox" className="mt-0.5" checked={webAccess} onChange={(e) => setWebAccess(e.target.checked)} />
        <span>
          <span className="flex items-center gap-1.5 font-medium text-fg">
            <Globe aria-hidden size={13} className="text-blue" /> Web access (WebSearch and WebFetch)
          </span>
          <span className="block text-fg-2">
            Needed for research on the internet (papers, documentation, news). Agents send search queries and open web pages.
            {workspacePath.trim() ? " Turn it off for private code: a web request could carry workspace content." : ""}
          </span>
        </span>
      </label>

      {workspaceEdit ? (
        <div role="alert" className="rounded-md border border-orange/50 bg-orange/10 px-3 py-2 text-[12px]">
          <p className="flex items-center gap-2 font-medium text-fg">
            <AlertTriangle aria-hidden size={14} className="text-orange" />
            Workspace edit lets agents change files in the workspace path.
          </p>
          <p className="mt-1 text-fg-2">Claude Code runs with accept-edits mode and a command allowlist. Destructive commands are denied. Review changes with version control.</p>
          <label htmlFor={ids.confirm} className="mt-2 flex items-center gap-2 text-fg">
            <input id={ids.confirm} type="checkbox" checked={confirmEdit} onChange={(e) => setConfirmEdit(e.target.checked)} />
            I allow agents to edit files in this workspace.
          </label>
        </div>
      ) : null}

      <RuntimeAvailability status={system.data} loading={system.isPending} error={system.error} />

      {apiError ? (
        <div role="alert" className="rounded-md border border-red/50 bg-red/10 px-3 py-2 text-[12px] text-fg" data-testid="run-error">
          <p className="font-medium">{errorMessage(apiError)}</p>
          {fieldErrors.length ? (
            <ul className="mt-1 list-disc pl-5 text-fg-2">
              {fieldErrors.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {missing.length && (description || workspaceEdit) ? (
        <ul className="text-[11px] text-fg-3" aria-live="polite">
          {missing.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      ) : null}

      <div className="flex items-center justify-end gap-2 pt-1">
        <button type="button" className="af-btn" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="af-btn af-btn-primary" disabled={missing.length > 0 || mutation.isPending}>
          {mutation.isPending ? "Creating…" : queueOnly ? "Queue run" : "Start run"}
        </button>
      </div>
    </form>
  );
}

/** Modal form for POST /api/v1/runs. */
export function NewRunModal({ open, onClose, onCreated }: NewRunModalProps) {
  return (
    <Modal open={open} onClose={onClose} title="New Run" description="Queue a run for the local runner. The orchestrator plans and delegates the work." width={640}>
      {open ? <NewRunForm onClose={onClose} onCreated={onCreated} /> : null}
    </Modal>
  );
}
