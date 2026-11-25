"use client";
import { X } from "lucide-react";
import { useId, useRef, type ReactNode } from "react";
import { useDialogFocus } from "@/hooks/useDialogFocus";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
}

/** Side drawer on the right edge. Esc closes it. */
export function Drawer({ open, onClose, title, subtitle, children }: DrawerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useDialogFocus(open, onClose, ref);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div aria-hidden className="absolute inset-0 bg-black/40" onClick={onClose} />
      <aside
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative z-10 flex h-full w-full max-w-[440px] flex-col border-l border-line bg-panel shadow-2xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line-soft px-4 py-3">
          <div className="min-w-0">
            <div className="af-label">Agent Inspector</div>
            <h2 id={titleId} className="truncate text-[14px] font-semibold">
              {title}
            </h2>
            {subtitle ? <div className="mt-0.5 text-[12px] text-fg-2">{subtitle}</div> : null}
          </div>
          <button type="button" className="af-icon-btn" onClick={onClose} aria-label="Close inspector">
            <X aria-hidden size={14} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
      </aside>
    </div>
  );
}
