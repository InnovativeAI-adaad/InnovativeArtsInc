# AUTONOMY.md — Autonomous Capability Permissions

> Part of the **InnovativeArtsInc** Agent Documentation Suite.
> **Normative source for tier resolution:** this file is the canonical autonomy matrix. If any tier statement differs across docs, **`AUTONOMY.md` wins**.

---

## 1. Canonical Autonomy Matrix (Normative)

| Action Name | Tier | Approval Model | Notes |
|---|---:|---|---|
| `read_repo` | 🟢 1 | Autonomous | Read branches/files/history. |
| `list_branches` | 🟢 1 | Autonomous | Read branch metadata only. |
| `read_issue` | 🟢 1 | Autonomous | Read issue content/metadata. |
| `classify_issue` | 🟢 1 | Autonomous | Bug/feature/docs/question triage. |
| `assign_labels` | 🟢 1 | Autonomous | Apply labels under repo policy. |
| `comment_on_issue` | 🟢 1 | Autonomous | Non-destructive issue comments. |
| `comment_on_pr` | 🟢 1 | Autonomous | PR feedback/status comments. |
| `search_github` | 🟢 1 | Autonomous | Read-only GitHub search/queries. |
| `run_tests` | 🟢 1 | Autonomous | Read-only validation runs. |
| `lint_code` | 🟢 1 | Autonomous | Static style/quality checks. |
| `create_issue` | 🟢 1 | Autonomous | Open issues labeled `agent-created`. |
| `read_agent_log` | 🟢 1 | Autonomous | Read log and telemetry records. |
| `write_agent_log` | 🟢 1 | Autonomous | Append action/audit records. |
| `create_branch` | 🟡 2 | Log + notify owner | Branch naming policy enforced. |
| `commit_files` | 🟡 2 | Log + notify owner | Commit must include `[AGENT]`. |
| `open_pr_draft` | 🟡 2 | Log + notify owner | Draft PR only. |
| `review_code` | 🟡 2 | Log + notify owner | Structured review and change requests. |
| `close_issue` | 🟡 2 | Log + notify owner | Must provide closure rationale. |
| `merge_pr_dev_staging` | 🟡 2 | Log + notify owner | CI must pass first. |
| `draft_release` | 🟡 2 | Log + notify owner | Draft only; no publish. |
| `send_email_owner` | 🟡 2 | Log + notify owner | Owner-targeted notifications only. |
| `generate_readme` | 🟡 2 | Log + notify owner | Documentation generation/update. |
| `explain_code` | 🟡 2 | Log + notify owner | Docstrings/comments generation. |
| `catalog_music` | 🟡 2 | Log + notify owner | Parse/index music metadata. |
| `generate_metadata` | 🟡 2 | Log + notify owner | AI metadata drafts. |
| `tag_audio` | 🟡 2 | Log + notify owner | Apply/repair ID3 tags. |
| `read_brief` | 🟡 2 | Log + notify owner | Parse owner campaign brief. |
| `web_search_trends` | 🟡 2 | Log + notify owner | Research-only web lookup. |
| `draft_press_release` | 🟡 2 | Log + notify owner | Draft communications only. |
| `generate_social_drafts` | 🟡 2 | Log + notify owner | Never direct publish. |
| `merge_pr_main` | 🔴 3 | Human approval required | Protected branch gate. |
| `deploy_production` | 🔴 3 | Human approval required | No autonomous production deploys. |
| `modify_secrets_or_env` | 🔴 3 | Human approval required | Includes credentials and env vars. |
| `delete_branch_or_file` | 🔴 3 | Human approval required | Destructive operation gate. |
| `modify_ci_cd` | 🔴 3 | Human approval required | Workflow/pipeline changes. |
| `publish_release` | 🔴 3 | Human approval required | Human publish decision required. |
| `modify_governance_docs` | 🔴 3 | Human approval required | `AGENT.md`, `AUTONOMY.md`, `SECURITY.md`. |

---

## 2. Scheduling

Agents may operate on these schedules without per-run approval:

```yaml
schedules:
  daily_summary:
    cron: "0 9 * * *"          # 9:00 AM UTC daily
    action: read_agent_log
    level: 1

  stale_issue_check:
    cron: "0 12 * * 1"         # Monday noon UTC
    action: search_github
    level: 1

  dependency_audit:
    cron: "0 8 * * 1"          # Monday morning
    action: run_tests
    level: 1

  release_check:
    cron: "0 10 * * 5"         # Friday morning
    action: draft_release
    level: 2
```

---

## 3. Constraints & Guardrails

```
- NEVER include credentials, tokens, or secrets in any output.
- NEVER impersonate the repo owner in communications.
- NEVER make financial transactions of any kind.
- ALWAYS prefix agent commits with [AGENT] in the commit message.
- ALWAYS create a PR rather than pushing directly to protected branches.
- ALWAYS include a rollback plan for Tier 2+ operations.
- Log every action to AGENT_LOG.md with timestamp, action, and outcome.
```

---

## 4. Conflict Resolution

If tier statements diverge between `AUTONOMY.md`, `AGENT.md`, and `WORKFLOWS.md`, resolve using this document. **`AUTONOMY.md` is normative and wins all tier conflicts.**

---

## 5. Review Gate

When a PR edits **any** of `AUTONOMY.md`, `AGENT.md`, or `WORKFLOWS.md`, reviewers must run a **tier-diff check** to confirm action names and tier assignments remain aligned with this canonical matrix.

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
