"use client";
import { X } from "lucide-react";
import { useId, useRef, type ReactNode } from "react";
import { useDialogFocus } from "@/hooks/useDialogFocus";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}

/** Centred modal dialog. Esc and the close button close it. Focus stays inside. */
export function Modal({ open, onClose, title, description, children, footer, width = 560 }: ModalProps) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descId = useId();
  useDialogFocus(open, onClose, ref);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:items-center">
      <div aria-hidden className="absolute inset-0" onClick={onClose} />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className="af-panel relative z-10 flex max-h-[calc(100vh-2rem)] w-full flex-col"
        style={{ maxWidth: width }}
      >
        <header className="flex items-start justify-between gap-3 border-b border-line-soft px-4 py-3">
          <div>
            <h2 id={titleId} className="text-[14px] font-semibold">
              {title}
            </h2>
            {description ? (
              <p id={descId} className="mt-0.5 text-[12px] text-fg-2">
                {description}
              </p>
            ) : null}
          </div>
          <button type="button" className="af-icon-btn" onClick={onClose} aria-label="Close dialog">
            <X aria-hidden size={14} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
        {footer ? <footer className="border-t border-line-soft px-4 py-3">{footer}</footer> : null}
      </div>
    </div>
  );
}
