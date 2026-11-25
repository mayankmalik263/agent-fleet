import { TONE_COLOR, type Tone } from "@/lib/colors";
import { humanize } from "@/lib/format";
import { StatusDot } from "./StatusDot";

interface StatusBadgeProps {
  tone: Tone;
  status: string;
  pulse?: boolean;
  className?: string;
}

/** Small status pill: coloured dot plus the status text. */
export function StatusBadge({ tone, status, pulse, className = "" }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-[1px] text-[11px] font-medium whitespace-nowrap ${className}`}
      style={{
        color: TONE_COLOR[tone],
        borderColor: `color-mix(in srgb, ${TONE_COLOR[tone]} 35%, transparent)`,
        background: `color-mix(in srgb, ${TONE_COLOR[tone]} 10%, transparent)`,
      }}
    >
      <StatusDot tone={tone} pulse={pulse} size={6} />
      {humanize(status)}
    </span>
  );
}
