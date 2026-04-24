# AGENT.md — InnovativeArtsInc Autonomous Agent Manifest

> **Project:** InnovativeArtsInc  
> **Org:** [@InnovativeAI-adaad](https://github.com/InnovativeAI-adaad)  
> **Owner:** Dustin L. Reid (`dreezy66`)  
> **Site:** [adaad.pro](http://adaad.pro)  
> **Version:** 1.0.1

---

## 1. Purpose

This document defines the configuration, identity, permissions, and behavioral rules for all autonomous agents operating within the **InnovativeArtsInc** project. Any AI agent, automation script, or LLM-powered workflow interacting with this codebase must conform to the specifications here.

---

## 2. Agent Identity

| Field | Value |
|---|---|
| Agent Name | `ADAAD-Agent` |
| Scope | InnovativeArtsInc repository & services |
| Primary Owner | `InnovativeAI-adaad` |
| Auth Method | GitHub App Private Key + PAT |
| Runtime | Cloud / Local (see `TOOLS.md`) |
| MCP Enabled | Yes (see `MCP_SERVERS.md`) |

---

## 3. Autonomy Levels

> This section mirrors the canonical matrix in `AUTONOMY.md` exactly (same action names and tiers).

### 🟢 Level 1 — Fully Autonomous (No approval needed)
- `read_repo`
- `list_branches`
- `read_issue`
- `classify_issue`
- `assign_labels`
- `comment_on_issue`
- `comment_on_pr`
- `search_github`
- `run_tests`
- `lint_code`
- `create_issue`
- `read_agent_log`
- `write_agent_log`

### 🟡 Level 2 — Semi-Autonomous (Log + notify owner)
- `create_branch`
- `commit_files`
- `open_pr_draft`
- `review_code`
- `close_issue`
- `merge_pr_dev_staging`
- `draft_release`
- `send_email_owner`
- `generate_readme`
- `explain_code`
- `catalog_music`
- `generate_metadata`
- `tag_audio`
- `read_brief`
- `web_search_trends`
- `draft_press_release`
- `generate_social_drafts`

### 🔴 Level 3 — Requires Human Approval
- `merge_pr_main`
- `deploy_production`
- `modify_secrets_or_env`
- `delete_branch_or_file`
- `modify_ci_cd`
- `publish_release`
- `modify_governance_docs`

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

> Entrypoint actions and tiers must match `AUTONOMY.md` action names.

| Trigger | Agent Action(s) | Tier |
|---|---|---:|
| `push` to any branch | `run_tests`, `lint_code`, `comment_on_pr`, `write_agent_log` | 🟢 1 |
| New Issue opened | `read_issue`, `classify_issue`, `assign_labels`, `comment_on_issue`, `write_agent_log` | 🟢 1 |
| PR opened | `read_repo`, `review_code`, `comment_on_pr`, `open_pr_draft`, `write_agent_log` | 🟡 2 |
| PR approved by owner for non-main targets | `merge_pr_dev_staging`, `write_agent_log` | 🟡 2 |
| Release tag pushed | `read_repo`, `draft_release`, `send_email_owner`, `write_agent_log` | 🟡 2 |
| Manual `@ADAAD-Agent` | Execute requested action at matrix tier (`AUTONOMY.md`) | Varies |
| Scheduled daily summary | `read_agent_log`, `search_github`, `send_email_owner`, `write_agent_log` | 🟡 2 |

---

## 6. Memory & State

- Agent short-term state is stored per-run in ephemeral context.
- Long-term memory is persisted to `AGENT_LOG.md` and/or a connected database.
- Project-level knowledge is sourced from files in `docs/` and this manifest.
- See `MEMORY.md` for full memory architecture.

---

## 7. Related Docs

| Document | Purpose |
|---|---|
| `AUTONOMY.md` | Canonical autonomy matrix and tier rules |
| `TOOLS.md` | Tool registry and integrations |
| `MCP_SERVERS.md` | MCP server connections and config |
| `WORKFLOWS.md` | Automated workflow definitions |
| `MEMORY.md` | Memory and state architecture |
| `SECURITY.md` | Security policies for agent operations |

---

## 8. Conflict Resolution

If tier statements diverge between `AGENT.md`, `WORKFLOWS.md`, and `AUTONOMY.md`, the canonical source is `AUTONOMY.md` and its mapping must be used.

---

## 9. Review Gate

If a change touches `AGENT.md`, `AUTONOMY.md`, or `WORKFLOWS.md`, PR review must include a **tier-diff check** confirming no drift from `AUTONOMY.md` action names/tier assignments.

---

## 10. Override & Shutdown

To halt all autonomous operations:
1. Set `AGENT_ENABLED=false` in repo environment variables, or
2. Add a `HALT` file to the root of the repository, or
3. Revoke the GitHub App installation for this repo.

The agent will cease all scheduled and triggered operations within one cycle.

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
