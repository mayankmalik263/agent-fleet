import type { ReactNode } from "react";

export interface DetailItem {
  label: string;
  value: ReactNode;
}

/** Compact two-column list of labels and values. */
export function DetailList({ items, className = "" }: { items: DetailItem[]; className?: string }) {
  return (
    <dl className={`grid grid-cols-[minmax(84px,auto)_1fr] gap-x-3 gap-y-1 text-[12px] ${className}`}>
      {items.map((item, i) => (
        <div key={`${item.label}-${i}`} className="contents">
          <dt className="text-fg-3">{item.label}</dt>
          <dd className="min-w-0 break-words text-fg">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
