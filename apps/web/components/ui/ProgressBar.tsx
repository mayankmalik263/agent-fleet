interface ProgressBarProps {
  value: number;
  color?: string;
  label: string;
}

/** Progress bar. Use it only when the API reports a real progress value. */
export function ProgressBar({ value, color = "var(--af-primary)", label }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className="h-1 w-full overflow-hidden rounded-full bg-bg"
    >
      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}
