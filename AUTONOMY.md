# AUTONOMY.md — Autonomous Capability Permissions

> Part of the **InnovativeArtsInc** Agent Documentation Suite  
> Cross-reference: `AGENT.md` for autonomy level definitions

---

## 1. GitHub Operations

| Capability                  | Permitted | Level | Notes                              |
|----------------------------|-----------|-------|------------------------------------|
| Read repos, branches, files | ✅        | 🟢 1  | All repos under InnovativeAI-adaad |
| Create branches             | ✅        | 🟡 2  | Naming: `agent/<task-slug>`        |
| Commit files                | ✅        | 🟡 2  | Must include `[AGENT]` in message  |
| Open PRs                    | ✅        | 🟡 2  | Always as draft first              |
| Merge PRs → `dev`           | ✅        | 🟡 2  | Requires passing CI                |
| Merge PRs → `main`          | ❌        | 🔴 3  | Human approval required            |
| Create issues               | ✅        | 🟢 1  | Labeled `agent-created`            |
| Close issues                | ✅        | 🟡 2  | Must comment reason before close   |
| Delete branches             | ✅        | 🔴 3  | Only merged/stale, owner approval  |
| Manage releases             | ✅        | 🟡 2  | Draft only; publish requires owner |
| Modify Actions workflows    | ❌        | 🔴 3  | Always requires human review       |

---

## 2. Code Operations

| Capability                  | Permitted | Level | Notes                              |
|----------------------------|-----------|-------|------------------------------------|
| Generate new code files     | ✅        | 🟡 2  | Must pass lint before commit       |
| Refactor existing code      | ✅        | 🟡 2  | Requires test coverage present     |
| Run tests                   | ✅        | 🟢 1  | Read-only, no side effects         |
| Install dependencies        | ✅        | 🟡 2  | Patch updates only autonomously    |
| Modify `package.json`       | ✅        | 🟡 2  | Minor/patch bumps only             |
| Modify CI/CD pipelines      | ❌        | 🔴 3  | Always human-reviewed              |
| Modify env/secrets files    | ❌        | 🔴 3  | Never autonomous                   |

---

## 3. Communication Operations

| Capability                  | Permitted | Level | Notes                              |
|----------------------------|-----------|-------|------------------------------------|
| Post GitHub comments        | ✅        | 🟢 1  | Issues, PRs, Discussions           |
| Send email notifications    | ✅        | 🟡 2  | Owner email only by default        |
| Post to Slack/Discord       | ✅        | 🟡 2  | Designated channels only           |
| Publish social media posts  | ❌        | 🔴 3  | Always requires human approval     |
| Send external API webhooks  | ✅        | 🟡 2  | Whitelisted endpoints only         |

---

## 4. Data & File Operations

| Capability                  | Permitted | Level | Notes                              |
|----------------------------|-----------|-------|------------------------------------|
| Read any project file       | ✅        | 🟢 1  | Unrestricted read access           |
| Write to `docs/`            | ✅        | 🟡 2  | Auto-generated docs OK             |
| Write to `src/`             | ✅        | 🟡 2  | Via PR only, never direct push     |
| Write to `config/`          | ✅        | 🔴 3  | Human approval always              |
| Delete files                | ❌        | 🔴 3  | Never autonomous                   |
| Access external APIs        | ✅        | 🟡 2  | Read-only external calls only      |
| Store data externally       | ✅        | 🟡 2  | Whitelisted services only          |

---

## 5. Scheduling

Agents may operate on these schedules without per-run approval:

```yaml
schedules:
  daily_summary:
    cron: "0 9 * * *"          # 9:00 AM UTC daily
    action: summarize_activity
    level: 1

  stale_issue_check:
    cron: "0 12 * * 1"         # Monday noon UTC
    action: label_stale_issues
    level: 1

  dependency_audit:
    cron: "0 8 * * 1"          # Monday morning
    action: audit_dependencies
    level: 2

  release_check:
    cron: "0 10 * * 5"         # Friday morning
    action: draft_release_notes
    level: 2
```

---

## 6. Constraints & Guardrails

```
- NEVER include credentials, tokens, or secrets in any output.
- NEVER impersonate the repo owner in communications.
- NEVER make financial transactions of any kind.
- NEVER modify AGENT.md, AUTONOMY.md, or SECURITY.md autonomously.
- ALWAYS prefix agent commits with [AGENT] in the commit message.
- ALWAYS create a PR rather than pushing directly to protected branches.
- ALWAYS include a rollback plan for Level 2+ operations.
- Log every action to AGENT_LOG.md with timestamp, action, and outcome.
```

---

## 7. Audit Trail

All agent actions are logged with:

```json
{
  "timestamp": "ISO-8601",
  "agent": "ADAAD-Agent",
  "level": 1 | 2 | 3,
  "action": "description",
  "target": "file/branch/issue/PR",
  "outcome": "success | failure | pending",
  "approved_by": "human | autonomous",
  "notes": "optional detail"
}
```

Logs are written to `AGENT_LOG.md` and optionally streamed to a connected observability service (see `TOOLS.md`).

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
