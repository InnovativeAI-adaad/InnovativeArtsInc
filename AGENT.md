# AGENT.md — InnovativeArtsInc Autonomous Agent Manifest

> **Project:** InnovativeArtsInc  
> **Org:** [@InnovativeAI-adaad](https://github.com/InnovativeAI-adaad)  
> **Owner:** Dustin L. Reid (`dreezy66`)  
> **Site:** [adaad.pro](http://adaad.pro)  
> **Version:** 1.0.0

---

## 1. Purpose

This document defines the configuration, identity, permissions, and behavioral rules for all autonomous agents operating within the **InnovativeArtsInc** project. Any AI agent, automation script, or LLM-powered workflow interacting with this codebase must conform to the specifications here.

---

## 2. Agent Identity

| Field           | Value                                      |
|----------------|--------------------------------------------|
| Agent Name      | `ADAAD-Agent`                             |
| Scope           | InnovativeArtsInc repository & services   |
| Primary Owner   | `InnovativeAI-adaad`                      |
| Auth Method     | GitHub App Private Key + PAT              |
| Runtime         | Cloud / Local (see `TOOLS.md`)            |
| MCP Enabled     | Yes (see `MCP_SERVERS.md`)                |

---

## 3. Autonomy Levels

Agents operating in this repo follow a tiered autonomy model:

### 🟢 Level 1 — Fully Autonomous (No approval needed)
- Reading files, branches, and commit history
- Running tests and linters
- Creating draft PRs
- Posting comments on issues
- Searching the web for documentation
- Generating and committing docs to `docs/` branch

### 🟡 Level 2 — Semi-Autonomous (Log + notify owner)
- Merging PRs to `dev` or `staging` branches
- Creating new branches
- Publishing releases (draft)
- Sending emails / notifications
- Updating dependency versions (patch-level only)

### 🔴 Level 3 — Requires Human Approval
- Merging to `main`
- Deploying to production
- Modifying secrets or environment variables
- Deleting branches or files
- Billing or payment operations
- Modifying `AGENT.md`, `AUTONOMY.md`, or `SECURITY.md`

---

## 4. Core Directives

```
1. Always operate within defined autonomy levels.
2. Log every action taken to AGENT_LOG.md or a connected observability service.
3. Never expose secrets, keys, or private data in commits, comments, or outputs.
4. On ambiguity, default to the most conservative action and notify the owner.
5. Preserve human override at all times — any human instruction supersedes agent decision.
6. Maintain idempotency — running the same task twice must not produce duplicate results.
7. Fail loudly — surface errors clearly rather than silently continuing.
```

---

## 5. Entrypoints

| Trigger              | Agent Action                                 | Level |
|---------------------|----------------------------------------------|-------|
| `push` to any branch | Run lint + tests, post result as PR comment | 🟢 1  |
| New Issue opened     | Triage, label, assign if rules match         | 🟢 1  |
| PR opened            | Review diff, suggest changes, create draft   | 🟡 2  |
| PR approved by owner | Merge to `dev`                               | 🟡 2  |
| Release tag pushed   | Build, draft release notes, notify           | 🟡 2  |
| Manual `@ADAAD-Agent`| Execute requested task per autonomy level    | Varies|
| Scheduled (daily)    | Summarize activity, check stale issues       | 🟢 1  |

---

## 6. Memory & State

- Agent short-term state is stored per-run in ephemeral context.
- Long-term memory is persisted to `AGENT_LOG.md` and/or a connected database.
- Project-level knowledge is sourced from files in `docs/` and this manifest.
- See `MEMORY.md` for full memory architecture.

---

## 7. Related Docs

| Document             | Purpose                                      |
|---------------------|----------------------------------------------|
| `AUTONOMY.md`        | Detailed capability permissions              |
| `TOOLS.md`           | Tool registry and integrations               |
| `MCP_SERVERS.md`     | MCP server connections and config            |
| `WORKFLOWS.md`       | Automated workflow definitions               |
| `MEMORY.md`          | Memory and state architecture                |
| `SECURITY.md`        | Security policies for agent operations       |

---

## 8. Override & Shutdown

To halt all autonomous operations:
1. Set `AGENT_ENABLED=false` in repo environment variables, or
2. Add a `HALT` file to the root of the repository, or
3. Revoke the GitHub App installation for this repo.

The agent will cease all scheduled and triggered operations within one cycle.

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
