import { AlertTriangle, RefreshCw } from "lucide-react";
import { ApiError, errorMessage } from "@/lib/api";
import { apiBaseUrl, COMMANDS } from "@/lib/config";

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  compact?: boolean;
}

/** Shows an API error. A network error gets a hint to start the backend. */
export function ErrorState({ error, onRetry, title, compact = false }: ErrorStateProps) {
  const unreachable = error instanceof ApiError && error.isNetworkError;
  return (
    <div
      role="alert"
      className={`flex flex-col items-center justify-center gap-2 text-center ${compact ? "px-3 py-4" : "px-6 py-10"}`}
    >
      <AlertTriangle aria-hidden className="text-red" size={compact ? 18 : 24} />
      <p className="text-[13px] font-medium text-fg">
        {title ?? (unreachable ? "The Agent Fleet API is not reachable" : "Request failed")}
      </p>
      <p className="max-w-md text-[12px] text-fg-2">{errorMessage(error)}</p>
      {unreachable ? (
        <p className="text-[12px] text-fg-2">
          Start the backend: <code className="af-mono rounded bg-bg px-1.5 py-0.5 text-fg">{COMMANDS.api}</code>
          <span className="block pt-1 text-fg-3">Expected at {apiBaseUrl()}</span>
        </p>
      ) : null}
      {onRetry ? (
        <button type="button" className="af-btn mt-1" onClick={onRetry}>
          <RefreshCw aria-hidden size={12} /> Retry
        </button>
      ) : null}
    </div>
  );
}
