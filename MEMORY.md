# MEMORY.md — Agent Memory & State Architecture

> Part of the **InnovativeArtsInc** Agent Documentation Suite

---

## 1. Memory Types

ADAAD-Agent uses three tiers of memory:

```
┌─────────────────────────────────────────────────────────┐
│  TIER 1 · Ephemeral (per-run context window)            │
│  Duration: Single task execution                        │
│  Storage: In-context only                              │
│  Access: Immediate, full fidelity                      │
├─────────────────────────────────────────────────────────┤
│  TIER 2 · Session (current workflow)                    │
│  Duration: Active workflow run                          │
│  Storage: Workflow state variable                      │
│  Access: Read/write during run                         │
├─────────────────────────────────────────────────────────┤
│  TIER 3 · Long-term (persistent project knowledge)      │
│  Duration: Permanent until explicitly updated           │
│  Storage: AGENT_LOG.md + MEMORY.md (this file)         │
│  Access: Retrieved at agent startup                    │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Long-Term Memory Store

The agent maintains the following persistent knowledge about this project:

### Project Identity
```yaml
project: InnovativeArtsInc
org: InnovativeAI-adaad
owner: Dustin L. Reid (dreezy66)
primary_site: adaad.pro
github: https://github.com/InnovativeAI-adaad/InnovativeArtsInc
domain: Music / Creative Arts / AI
```

### Repository Structure
```yaml
branches:
  main: production-ready code
  dev: active development
  staging: pre-production testing
  agent/*: agent-created branches
  docs: auto-generated documentation

protected_branches:
  - main
  - staging
```

### Owner Preferences
```yaml
commit_style: conventional commits preferred
pr_preference: draft first, owner reviews before merge to main
notification_channel: dustinreid82@gmail.com
agent_commit_prefix: "[AGENT]"
review_required_for: main branch merges, production deploys
```

### Known Integrations
```yaml
active:
  - GitHub App (InnovativeAI-adaad)
  - Gmail MCP
  - Google Calendar MCP
  - Llama API
  - ngrok (tunneling)
  - Gravatar API

planned:
  - Spotify API
  - Stripe
  - Vercel
  - Supabase
```

---

## 3. AGENT_LOG.md Format

The agent appends a structured log entry for every action:

```markdown
## [ISO-8601 Timestamp]
- **Workflow:** WF-NNN or ad-hoc
- **Action:** Description of what was done
- **Target:** File / Branch / Issue / PR / External
- **Level:** 1 | 2 | 3
- **Outcome:** success | failure | partial | skipped
- **Approved By:** autonomous | owner:[name]
- **Notes:** Any relevant detail or error
---
```

---

## 4. Context Injection

At the start of any agent task, the following context is injected:

```
1. Contents of AGENT.md         (identity + directives)
2. Contents of AUTONOMY.md      (permission boundaries)
3. Last 20 entries of AGENT_LOG.md (recent activity)
4. Relevant section of MEMORY.md  (project knowledge)
5. Current task description
```

This ensures the agent always operates with full project context without requiring human re-briefing.

---

## 5. Memory Update Protocol

The agent updates long-term memory when:
- A new integration is added or removed
- Owner preferences change
- Repo structure changes significantly
- A new team member or collaborator is added
- A major milestone is reached

Updates to this file are Level 2 — they are committed via PR with label `memory-update` and owner notification.

---

## 6. Forgetting & Privacy

- The agent does not retain personal data beyond what is listed here.
- Sensitive values (keys, tokens) are **never** written to memory files.
- Memory entries older than 90 days in `AGENT_LOG.md` may be archived to `AGENT_LOG_ARCHIVE.md`.
- Owner may request full memory wipe by opening an issue labeled `memory-reset`.

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
