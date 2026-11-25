# Security policy

Agent Fleet in this repository is a **local development MVP**. Local mode is **not** a production
multi-tenant SaaS security implementation. Read [docs/SECURITY.md](docs/SECURITY.md) for the full model.

## Summary of local-mode protections

- The API binds to `127.0.0.1`. CORS allows only the local dashboard origin.
- No Claude credentials are read, stored, copied or logged. Agent Fleet calls only the documented
  `claude --version`, `claude auth status --json` and `claude --help` commands and keeps only
  `loggedIn`, `authMethod`, `apiProvider` and `subscriptionType`.
- Claude Code runs with argument arrays (never `shell=True`), a timeout, a run-specific MCP configuration,
  and an explicit permission policy. `--dangerously-skip-permissions` and `bypassPermissions` are never used.
- Runs may only use workspace folders inside the configured roots. Paths are resolved, so `..` and
  symbolic links cannot escape.
- Secrets and hidden reasoning are removed from stored events, messages and logs.
- Each runner-started Claude session can access only its own run through MCP and cannot create runs.

## Not provided in local mode

Real user authentication, workspace authorization, protected remote MCP, rate limiting, audit logging,
encryption at rest and retention controls. Do not expose the API or MCP server to a network.

## Reporting a problem

Open a private issue with the repository owner. Do not include credentials in reports.
