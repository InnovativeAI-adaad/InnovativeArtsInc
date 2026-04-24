# AUTONOMY.md — Autonomous Capability Permissions

> Part of the **InnovativeArtsInc** Agent Documentation Suite.
> **Normative source for tier resolution:** this file is the canonical autonomy matrix. If any tier statement differs across docs, **`AUTONOMY.md` wins**.
>
> Documentation map: [`DOCS_INDEX.md`](./DOCS_INDEX.md)

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
| `verify_uniqueness_strategy` | 🟡 2 | Log + notify owner | Pre-generation novelty and guardrail decision gate. |
| `generate_music` | 🟡 2 | Log + notify owner | Execute provider-backed auditable music generation. |
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

## 2. Runtime Policy Block (Machine-Readable)

The following block is parsed by runtime policy loaders. Keep the markers and header stable:

- Start marker: `POLICY_START`
- End marker: `POLICY_END`
- Header fields (strict order): `action_id|risk_level|requires_human_ratification|abort_mode`

```text
POLICY_START
action_id|risk_level|requires_human_ratification|abort_mode
read_repo|low|false|continue
list_branches|low|false|continue
read_issue|low|false|continue
classify_issue|low|false|continue
assign_labels|low|false|continue
comment_on_issue|low|false|continue
comment_on_pr|low|false|continue
search_github|low|false|continue
run_tests|low|false|continue
lint_code|low|false|continue
create_issue|low|false|continue
read_agent_log|low|false|continue
write_agent_log|low|false|continue
create_branch|medium|false|quarantine
commit_files|medium|false|quarantine
open_pr_draft|medium|false|quarantine
review_code|medium|false|quarantine
close_issue|medium|false|quarantine
merge_pr_dev_staging|medium|false|quarantine
draft_release|medium|false|quarantine
send_email_owner|medium|false|quarantine
generate_readme|medium|false|quarantine
explain_code|medium|false|quarantine
catalog_music|medium|false|quarantine
generate_metadata|medium|false|quarantine
verify_uniqueness_strategy|medium|false|quarantine
generate_music|medium|false|quarantine
tag_audio|medium|false|quarantine
read_brief|medium|false|quarantine
web_search_trends|medium|false|quarantine
draft_press_release|medium|false|quarantine
generate_social_drafts|medium|false|quarantine
merge_pr_main|high|true|hard_stop
deploy_production|high|true|hard_stop
modify_secrets_or_env|high|true|hard_stop
delete_branch_or_file|high|true|hard_stop
modify_ci_cd|high|true|hard_stop
publish_release|high|true|hard_stop
modify_governance_docs|high|true|hard_stop
POLICY_END
```

---

## 3. Scheduling

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

## 4. Constraints & Guardrails

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

## 5. Conflict Resolution

If tier statements diverge between `AUTONOMY.md`, `AGENT.md`, and `WORKFLOWS.md`, resolve using this document. **`AUTONOMY.md` is normative and wins all tier conflicts.**

---

## 6. Review Gate

When a PR edits **any** of `AUTONOMY.md`, `AGENT.md`, or `WORKFLOWS.md`, reviewers must run a **tier-diff check** to confirm action names and tier assignments remain aligned with this canonical matrix.

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
