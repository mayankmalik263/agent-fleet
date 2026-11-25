# Dashboard design

This document describes the design of the Agent Fleet dashboard in `apps/web`.
The design follows the user's written specification. No reference screenshot was supplied, so the layout
follows the text description of the "Multi-Agent Fleet" console.

## 1. Design philosophy

- The dashboard is an **infrastructure monitoring console**. It is not an administration panel and not a chat.
- Density is a feature. Panels show much data in a small area, with small labels and compact type.
- **Every number comes from the API.** When a value is not reported, the UI shows "Not available".
  The UI never invents counts, progress, durations, connections or costs.
- Cost from Claude Code is always labelled "Estimated cost (client-side)". It is never shown as a charge.
- Colour carries meaning (agent role, status, event category). The UI uses bright colour only for accents.

## 2. Layout

| Area | Content | Code |
|---|---|---|
| Sidebar | Compact icon navigation: Overview, Agent Network, Runs, Tasks, Messages, Agents, Providers, Settings | `components/shell/Sidebar.tsx` |
| Header | Label `AGENT NETWORK / TIME`, title "Multi-Agent Fleet", description, run selector, run status, stream status, **New Run** button, four stat tiles | `features/dashboard/DashboardHeader.tsx` |
| Left column (≈50%) | Panel A: Agent Network | `features/network/AgentNetworkPanel.tsx` |
| Right column, top | Panel B: Cross-Agent Collaboration timeline | `features/timeline/TimelinePanel.tsx` |
| Right column, bottom | Panel C: Teamwork Tasks | `features/tasks/TasksPanel.tsx` |

The stat tiles are Total agents, Running agents (status `running` or `reviewing`), Work items (tasks)
and Messages. They describe the selected run. The run comes from `?run=<id>` or is the latest run.

## 3. Colour system

The palette is a set of CSS variables in `styles/globals.css`. Change a variable to change the theme.

| Variable | Value | Use |
|---|---|---|
| `--af-bg` | `#171719` | Page background |
| `--af-panel` | `#242428` | Panel surface |
| `--af-panel-2` | `#2B2B30` | Secondary surface, cards |
| `--af-border` / `--af-border-soft` | `#44434B` / `#34333A` | Thin borders |
| `--af-primary` | `#A855F7` | Primary accent, orchestrator, active state |
| `--af-blue` | `#3B82F6` | Researcher, info |
| `--af-green` | `#22C55E` | Reviewer, success |
| `--af-orange` | `#F97316` | Executor |
| `--af-yellow` | `#EAB308` | Analyst, warning |
| `--af-red` | `#EF4444` | Errors, failures |
| `--af-text` / `--af-text-2` / `--af-text-3` | `#F4F4F5` / `#A1A1AA` / `#8B8B95` | Main, secondary and tertiary text |
| `--af-focus` | `#C084FC` | Focus ring |

Role accents are in `lib/colors.ts`. Unknown roles get a stable colour from a fixed cycle.

## 4. Agent node

An agent node (`features/network/AgentNode.tsx`) shows:

- An avatar with initials, in the role accent colour.
- Name, role and model alias, and a status dot.
- Tokens in and out, only when the API reports them. Otherwise "Not available".
- Duration from `started_at` to `completed_at`. The value counts up live while the agent runs.
- "Completed tasks x / y" and "Tool calls". These are separate labels with separate sources.
- A progress bar, only when the current task has a real `progress_percentage`.

The graph layout (`lib/layout.ts`) is a deterministic tree. Parents are above their children.
The layout runs again, with fit view, when an agent is added. Edges:

- Solid arrows: parent → child delegation.
- Dashed edges: task delegation (creator → assignee).
- Dotted edges: messages. A message edge pulses for 6 seconds after a new message.

Selecting a node highlights its parent, its children and the related edges. Other nodes dim.
The legend (`NetworkLegend.tsx`) lists system events, agent messages, tool calls, tool results,
delegation, reviewer activity and errors.

## 5. Timeline

The timeline (`features/timeline/`) has one lane per agent, in hierarchy order, and one "System" lane
for events without an agent.

- Markers keep strict time order. Long idle gaps are shortened. A note says so, and tick labels show real times.
- Arrows connect a message sender to its receiver, and a delegating agent to the assigned agent.
- Colour and shape show the event category (`components/ui/EventShape.tsx`).
- Controls: lane search, earliest and latest buttons, zoom from 0.25× to 4×, category filters, horizontal scroll.
- A selected event shows its timestamp, type, sender, receiver, task, tool and source. The summary is the
  stored event message only. Hidden reasoning is never stored, so it cannot be shown.
- Events that the system closed (`payload.implicit = true`) are dimmed.

## 6. Task cards

Task cards (`features/tasks/TaskCard.tsx`) are compact and expandable.

- The left border colour shows the status.
- The collapsed card shows the assigned agent, model, title, status, objective, progress (only when real)
  and the latest update.
- The expanded card shows the full description, the delegating and assigned agents, start and completion
  times, the result, errors and related messages.
- Filters: All, In progress (includes blocked), Pending, In review, Done, Failed (includes cancelled).
  Each filter shows a count. A search field filters by text.

## 7. Interaction states

| State | Behaviour |
|---|---|
| Live run | The SSE client replays history, then streams new events. The header shows Connecting, Live, Reconnecting or Run ended. |
| New agent or task | The node, lane or card appears without a page reload. The snapshot is fetched again with a debounce. |
| Selected agent | The network, timeline and inspector highlight the same agent. |
| Agent Inspector | A drawer (`features/inspector/AgentInspector.tsx`) with name, role, model, parent, current task, status, start time, duration, recent messages, tool activity, task results and usage. |
| New Run | A modal with title, description, provider (Local Claude Code; the Anthropic API is shown disabled), workspace path, model, permission policy and maximum concurrent agents. "Workspace edit" shows a warning and needs a confirmation checkbox. When Claude Code or the runner is not ready, the modal says what is missing and the button becomes "Queue run". |
| No runs | An empty state explains how to connect Claude Code, start a first run, start the runner and check status. |
| API unreachable | An error state says "Start the backend: pnpm dev:api" and offers Retry. |

Modals and drawers trap keyboard focus, close with Esc and return focus. All controls have visible focus rings.

## 8. Responsive behaviour

- Desktop (1024 px and wider) uses the two-column layout.
- Below 1024 px, a Network / Timeline / Tasks switcher replaces the columns. Only one panel shows at a time.
- At 375 px wide the page has no horizontal scroll. Wide content (the timeline) scrolls inside its own panel.

## 9. Known limits

- Keyboard users open the inspector with agent search + Enter, or from the Agents page. Pressing Enter
  on a focused graph node does not open it.
- Graph arrowheads use fixed hex colours (SVG attributes), not the CSS variables.
- The message-edge pulse compares event times with the browser clock. A large clock difference hides it.
- There are no browser end-to-end tests. Component tests run in jsdom (Vitest).
