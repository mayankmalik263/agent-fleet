import { TONE_COLOR, type Tone } from "@/lib/colors";

interface StatusDotProps {
  tone: Tone;
  pulse?: boolean;
  /** Accessible text. When missing, the dot is decorative. */
  label?: string;
  size?: number;
}

export function StatusDot({ tone, pulse = false, label, size = 8 }: StatusDotProps) {
  return (
    <span
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={`inline-block shrink-0 rounded-full ${pulse ? "af-pulse" : ""}`}
      style={{
        width: size,
        height: size,
        background: TONE_COLOR[tone],
        boxShadow: pulse ? `0 0 0 3px color-mix(in srgb, ${TONE_COLOR[tone]} 25%, transparent)` : undefined,
      }}
    />
  );
}
