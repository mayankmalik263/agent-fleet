"use client";
import {
  Bot,
  History,
  LayoutDashboard,
  ListTodo,
  MessagesSquare,
  Network,
  Plug,
  Settings,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Pages that show one run keep the ?run= parameter. */
  keepRun: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard, keepRun: true },
  { href: "/network", label: "Agent Network", icon: Network, keepRun: true },
  { href: "/runs", label: "Runs", icon: History, keepRun: false },
  { href: "/tasks", label: "Tasks", icon: ListTodo, keepRun: true },
  { href: "/messages", label: "Messages", icon: MessagesSquare, keepRun: true },
  { href: "/agents", label: "Agents", icon: Bot, keepRun: true },
  { href: "/providers", label: "Providers", icon: Plug, keepRun: false },
  { href: "/settings", label: "Settings", icon: Settings, keepRun: false },
];

function Logo() {
  return (
    <span
      aria-hidden
      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[11px] font-bold text-white"
      style={{ background: "linear-gradient(135deg, var(--af-primary), color-mix(in srgb, var(--af-primary) 55%, var(--af-blue)))" }}
    >
      AF
    </span>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const run = searchParams.get("run");

  const items = NAV_ITEMS.map((item) => {
    const href = item.keepRun && run ? `${item.href}?run=${encodeURIComponent(run)}` : item.href;
    const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
    return { ...item, href, active };
  });

  return (
    <nav
      aria-label="Main"
      className="flex shrink-0 border-line-soft bg-bg md:h-screen md:w-14 md:flex-col md:border-r xl:w-48 max-md:w-full max-md:items-center max-md:border-b"
    >
      <div className="flex items-center gap-2 px-3 py-3 md:justify-center xl:justify-start">
        <Logo />
        <span className="text-[13px] font-semibold md:hidden xl:inline">Agent Fleet</span>
      </div>
      <ul className="flex min-w-0 gap-0.5 overflow-x-auto px-2 max-md:flex-1 md:flex-col md:overflow-visible">
        {items.map(({ href, label, icon: Icon, active }) => (
          <li key={label} className="shrink-0">
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              title={label}
              className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[12px] transition-colors md:justify-center xl:justify-start ${
                active ? "bg-panel-2 text-fg" : "text-fg-2 hover:bg-panel hover:text-fg"
              }`}
            >
              <Icon aria-hidden size={15} className={active ? "text-primary" : undefined} />
              <span className="md:sr-only xl:not-sr-only">{label}</span>
            </Link>
          </li>
        ))}
      </ul>
      <div className="mt-auto hidden px-3 py-3 text-[10px] text-fg-3 xl:block">Local mode</div>
    </nav>
  );
}
