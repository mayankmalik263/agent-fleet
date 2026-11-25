import { roleAccent } from "@/lib/colors";
import { initials } from "@/lib/format";

interface AgentAvatarProps {
  name: string;
  role: string;
  size?: number;
}

/** Round avatar with agent initials in the role accent colour. */
export function AgentAvatar({ name, role, size = 28 }: AgentAvatarProps) {
  const color = roleAccent(role);
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold"
      style={{
        width: size,
        height: size,
        fontSize: Math.max(9, Math.round(size * 0.38)),
        color,
        background: `color-mix(in srgb, ${color} 16%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 55%, transparent)`,
      }}
    >
      {initials(name)}
    </span>
  );
}
