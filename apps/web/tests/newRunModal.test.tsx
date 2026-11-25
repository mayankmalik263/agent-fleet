import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NewRunModal } from "@/features/runs/NewRunModal";
import { makeRun, makeSystemStatus } from "./fixtures";
import { mockFetch, renderWithClient } from "./helpers";

function renderModal(routes: Record<string, unknown>) {
  const fetchMock = mockFetch(routes);
  const onCreated = vi.fn();
  const onClose = vi.fn();
  renderWithClient(<NewRunModal open onClose={onClose} onCreated={onCreated} />);
  return { fetchMock, onCreated, onClose };
}

const postBody = (fetchMock: ReturnType<typeof mockFetch>) => {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
  return call ? JSON.parse(String(call[1]?.body)) : null;
};

describe("New Run modal", () => {
  it("submits the default read-only run with Local Claude Code", async () => {
    const user = userEvent.setup();
    const { fetchMock, onCreated } = renderModal({
      "GET /api/v1/system/status": makeSystemStatus(),
      "POST /api/v1/runs": () => ({ status: 201, body: makeRun({ id: "new-run", status: "queued" }) }),
    });
    expect(await screen.findByText(/Local Claude Code is connected and a runner is online/)).toBeInTheDocument();
    expect(screen.getByLabelText("Execution provider")).toHaveValue("claude_code_local");
    expect(screen.getByRole("option", { name: "Anthropic API (unavailable)" })).toBeDisabled();
    expect(screen.getByText("Anthropic API: Planned extension point.")).toBeInTheDocument();

    const submit = screen.getByRole("button", { name: "Start run" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("Task description"), "Audit the error handling");
    await user.type(screen.getByLabelText("Run title"), "Audit");
    await user.click(submit);

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: "new-run" })));
    expect(postBody(fetchMock)).toEqual({
      title: "Audit",
      task_description: "Audit the error handling",
      execution_provider: "claude_code_local",
      workspace_path: null,
      orchestrator_model: "sonnet",
      permission_policy: "read_only",
      max_concurrent_agents: 4,
      confirm_workspace_edit: false,
      web_access: true,
    });
  });

  it("requires a confirmation and a path for workspace edit", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderModal({
      "GET /api/v1/system/status": makeSystemStatus(),
      "POST /api/v1/runs": () => ({ status: 201, body: makeRun({ id: "edit-run" }) }),
    });
    await user.type(screen.getByLabelText("Task description"), "Fix the bug");
    await user.selectOptions(screen.getByLabelText("Permission policy"), "workspace_edit");

    expect(screen.getByText("Workspace edit lets agents change files in the workspace path.")).toBeInTheDocument();
    const submit = await screen.findByRole("button", { name: "Start run" });
    expect(submit).toBeDisabled();
    expect(screen.getByText("Confirm that agents may edit files in the workspace.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Workspace path (required)"), "D:\\repo");
    expect(submit).toBeDisabled();
    await user.click(screen.getByLabelText("I allow agents to edit files in this workspace."));
    expect(submit).toBeEnabled();
    await user.click(submit);

    await waitFor(() => expect(postBody(fetchMock)).not.toBeNull());
    expect(postBody(fetchMock)).toMatchObject({ permission_policy: "workspace_edit", confirm_workspace_edit: true, workspace_path: "D:\\repo" });
  });

  it("warns when the runtime is not ready but still allows queueing", async () => {
    renderModal({
      "GET /api/v1/system/status": makeSystemStatus({
        status: "degraded",
        providers: [
          { provider: "claude_code_local", label: "Local Claude Code", status: "authentication_required", message: "Run claude auth login.", local_mode_supported: true, details: {} },
        ],
        runner: { runners: [], any_online: false, queued_runs: 0, active_runs: 0 },
      }),
    });
    const warning = await screen.findByTestId("runtime-warning");
    expect(warning).toHaveTextContent("Local Claude Code is authentication required: Run claude auth login.");
    expect(warning).toHaveTextContent("Start the runner: pnpm dev:runner");
    fireEvent.change(screen.getByLabelText("Task description"), { target: { value: "Plan" } });
    expect(screen.getByRole("button", { name: "Queue run" })).toBeEnabled();
  });

  it("shows API validation errors", async () => {
    const user = userEvent.setup();
    renderModal({
      "GET /api/v1/system/status": makeSystemStatus(),
      "POST /api/v1/runs": () => ({
        status: 422,
        body: {
          error: {
            code: "validation_failed",
            message: "workspace path is outside the allowed roots",
            details: { errors: [{ loc: ["body", "workspace_path"], msg: "not allowed", type: "value_error" }] },
          },
        },
      }),
    });
    await user.type(screen.getByLabelText("Task description"), "Do it");
    await user.click(await screen.findByRole("button", { name: "Start run" }));
    const error = await screen.findByTestId("run-error");
    expect(error).toHaveTextContent("workspace path is outside the allowed roots");
    expect(error).toHaveTextContent("workspace_path: not allowed");
  });

  it("closes with Escape", async () => {
    const { onClose } = renderModal({ "GET /api/v1/system/status": makeSystemStatus() });
    await screen.findByRole("dialog", { name: "New Run" });
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
