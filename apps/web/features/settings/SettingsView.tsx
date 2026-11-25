import { PageHeader } from "@/components/shell/PageHeader";
import { DetailList } from "@/components/ui/DetailList";
import { Panel } from "@/components/ui/Panel";
import { apiBaseUrl, COMMANDS, DEFAULT_API_URL } from "@/lib/config";

const PALETTE = [
  ["--af-bg", "Background"],
  ["--af-panel", "Panel"],
  ["--af-panel-2", "Panel 2"],
  ["--af-border", "Border"],
  ["--af-primary", "Primary"],
  ["--af-blue", "Blue"],
  ["--af-green", "Green"],
  ["--af-orange", "Orange"],
  ["--af-yellow", "Yellow"],
  ["--af-red", "Red"],
  ["--af-text", "Text"],
  ["--af-text-2", "Text 2"],
] as const;

const ROLES = [
  ["orchestrator", "--af-primary"],
  ["researcher", "--af-blue"],
  ["analyst", "--af-yellow"],
  ["executor", "--af-orange"],
  ["reviewer", "--af-green"],
] as const;

const Code = ({ children }: { children: string }) => <code className="af-mono rounded bg-bg px-1 py-0.5">{children}</code>;

/** Read-only configuration and palette preview. */
export function SettingsView() {
  return (
    <>
      <PageHeader label="Configuration" title="Settings" description="Read-only view. Change values in environment variables and styles/globals.css." />
      <div className="grid gap-3 p-3 lg:grid-cols-2">
        <Panel title="API connection" label="Dashboard">
          <div className="px-3 py-2">
            <DetailList
              items={[
                { label: "API URL", value: <Code>{apiBaseUrl()}</Code> },
                { label: "Default", value: <Code>{DEFAULT_API_URL}</Code> },
                { label: "Override", value: <span>Set <Code>NEXT_PUBLIC_AGENT_FLEET_API_URL</Code> before you build or start the dashboard.</span> },
                { label: "CORS", value: "The API allows http://localhost:3000 and http://127.0.0.1:3000 by default." },
              ]}
            />
          </div>
        </Panel>
        <Panel title="Commands" label="Local development">
          <div className="px-3 py-2">
            <DetailList
              items={[
                { label: "Backend API", value: <Code>{COMMANDS.api}</Code> },
                { label: "Runner", value: <Code>{COMMANDS.runner}</Code> },
                { label: "Dashboard", value: <Code>{COMMANDS.web}</Code> },
                { label: "MCP check", value: <Code>{COMMANDS.mcpList}</Code> },
              ]}
            />
          </div>
        </Panel>
        <Panel title="Palette" label="Theme tokens">
          <ul className="grid grid-cols-2 gap-2 px-3 py-2 sm:grid-cols-3">
            {PALETTE.map(([token, label]) => (
              <li key={token} className="flex items-center gap-2 text-[11px]">
                <span aria-hidden className="h-5 w-5 rounded border border-line" style={{ background: `var(${token})` }} />
                <span>
                  <span className="block text-fg">{label}</span>
                  <span className="af-mono block text-fg-3">{token}</span>
                </span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Agent role accents" label="Theme tokens">
          <ul className="flex flex-col gap-1.5 px-3 py-2">
            {ROLES.map(([role, token]) => (
              <li key={role} className="flex items-center gap-2 text-[12px]">
                <span aria-hidden className="h-3 w-3 rounded-full" style={{ background: `var(${token})` }} />
                {role}
              </li>
            ))}
            <li className="text-[11px] text-fg-3">Other roles get a stable colour from the same palette.</li>
          </ul>
        </Panel>
      </div>
    </>
  );
}
