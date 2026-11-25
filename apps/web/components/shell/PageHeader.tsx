import type { ReactNode } from "react";

interface PageHeaderProps {
  label: string;
  title: string;
  description?: string;
  children?: ReactNode;
}

/** Compact header for the secondary pages. */
export function PageHeader({ label, title, description, children }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3 border-b border-line-soft px-4 py-3">
      <div className="min-w-0">
        <div className="af-label">{label}</div>
        <h1 className="text-[18px] leading-7 font-semibold tracking-tight">{title}</h1>
        {description ? <p className="text-[12px] text-fg-2">{description}</p> : null}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </header>
  );
}
