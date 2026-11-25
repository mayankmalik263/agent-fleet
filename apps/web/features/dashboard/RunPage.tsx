"use client";
import { Plus } from "lucide-react";
import type { ReactNode } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { RunScope, type RunScopeContext } from "./RunScope";

interface RunPageProps {
  label: string;
  title: string;
  description: string;
  children: (ctx: RunScopeContext) => ReactNode;
}

/** Frame for secondary pages that show data of the selected run. */
export function RunPage({ label, title, description, children }: RunPageProps) {
  return (
    <RunScope
      header={({ openNewRun, runControls, connection }) => (
        <PageHeader label={label} title={title} description={description}>
          {runControls}
          {connection}
          <button type="button" className="af-btn af-btn-primary" onClick={openNewRun}>
            <Plus aria-hidden size={13} /> New Run
          </button>
        </PageHeader>
      )}
    >
      {children}
    </RunScope>
  );
}
