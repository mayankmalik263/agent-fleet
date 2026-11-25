import type { ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, children, actions, className = "" }: EmptyStateProps) {
  return (
    <div role="status" className={`flex flex-col items-center justify-center gap-2 px-6 py-8 text-center ${className}`}>
      {icon ? <div className="text-fg-3">{icon}</div> : null}
      <p className="text-[13px] font-medium text-fg">{title}</p>
      {children ? <div className="max-w-md text-[12px] text-fg-2">{children}</div> : null}
      {actions ? <div className="mt-1 flex flex-wrap justify-center gap-2">{actions}</div> : null}
    </div>
  );
}
