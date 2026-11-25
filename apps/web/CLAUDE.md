# apps/web — Agent Fleet dashboard

## Current state

- **What it is:** the dark monitoring console for Agent Fleet (package `@agent-fleet/web`).
  Home page `/` is the "Multi-Agent Fleet" dashboard: Agent Network (React Flow), Cross-Agent
  Collaboration timeline, Teamwork Tasks, Agent Inspector drawer and New Run modal.
- **Stack:** Next.js 16.4.6 (App Router, Turbopack), React 19.3.1, TypeScript 6.0.3 (strict),
  Tailwind CSS 4.3.5, `@xyflow/react` 13.0.3, TanStack React Query 5.108.4, lucide-react 1.78.0.
  Tests: Vitest 5.1.1 + Testing Library + jsdom 31. ESLint 10 with `eslint-config-next` 16.4.6.
- **Run:** `pnpm dev` (port 3000), `pnpm build`, `pnpm start`, `pnpm lint`, `pnpm typecheck`, `pnpm test`.
  API URL: `NEXT_PUBLIC_AGENT_FLEET_API_URL` (default `http://127.0.0.1:8420`).
- **Folders:**
  - `app/` routes: `/`, `/network`, `/runs`, `/tasks`, `/messages`, `/agents`, `/providers`, `/settings`.
    Views that read `?run=` render inside `<Suspense>`.
  - `components/` shared UI (`ui/`) and the shell (`shell/` sidebar, page header).
  - `features/` dashboard, network, timeline, tasks, inspector, runs, providers, messages, agents, settings.
  - `hooks/` React Query hooks, SSE hook (`useRunStream`), live run (`useLiveRun`), selection, dialog focus.
  - `lib/` types (mirror backend schemas), API client + `ApiError`, SSE client, event merge and
    categories, live-state overlay, tree layout, timeline geometry, graph builder, formatters.
  - `styles/globals.css` palette tokens (`--af-*`) and Tailwind theme. `tests/` Vitest suites.
- **Decisions:**
  - The snapshot is the source of truth. Events newer than `snapshot.run.event_count` update it in
    memory (`lib/liveState.ts`); a debounced refetch (400 ms, max wait 2.5 s) refreshes the snapshot.
  - SSE: own reconnect with exponential backoff, resume with `?after=<last sequence>`, dedup by
    sequence number, batch window 50 ms, stop on `event: end`.
  - Timeline x axis: strict time order with a minimum gap; idle gaps are shortened (labelled in the UI).
  - No demo data and no invented numbers: missing values show "Not available"; costs are labelled
    "Estimated cost (client-side)".
  - Our CSS loads before React Flow CSS so the `@layer` order puts `xyflow` above Tailwind base.

## Change log

- 2026-11-25 — Built the dashboard from scratch (all files in `apps/web`). Why: frontend for the
  Agent Fleet MVP. Checks: typecheck, lint, 49 Vitest tests and `next build` pass.

## Open items

- `next dev` writes `AGENTS.md` here (Next.js agent rules); set `agentRules: false` in `next.config.ts` to stop it.
- ESLint 10 gives peer warnings for `eslint-plugin-import`, `-react`, `-jsx-a11y` (documented by Next.js).
- Keyboard users open the inspector from the timeline lanes, the agent search (Enter) or the Agents page;
  React Flow node focus + Enter does not open it.
- No end-to-end browser tests (Playwright) yet.
