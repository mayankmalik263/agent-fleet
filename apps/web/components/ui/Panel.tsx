import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  label?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}

/** A dashboard panel with a compact header. */
export function Panel({ title, label, actions, children, className = "", bodyClassName = "", id }: PanelProps) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section id={id} aria-labelledby={headingId} className={`af-panel flex min-h-0 min-w-0 flex-col ${className}`}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft px-3 py-2">
        <div className="min-w-0">
          {label ? <div className="af-label">{label}</div> : null}
          <h2 id={headingId} className="truncate text-[13px] font-semibold text-fg">
            {title}
          </h2>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-1.5">{actions}</div> : null}
      </header>
      <div className={`relative min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
