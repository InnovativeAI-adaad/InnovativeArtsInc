# WORKFLOWS.md — Autonomous Workflow Definitions

> Part of the **InnovativeArtsInc** Agent Documentation Suite.  
> Defines all automated and semi-automated workflows ADAAD-Agent can execute.

---

## 1. Workflow Structure

Each workflow defines:
- **Trigger** — what starts it (event, schedule, or manual)
- **Steps** — ordered list of action names from `AUTONOMY.md`
- **Level** — autonomy level of the highest-tiered step included
- **Rollback** — what happens on failure

---

## 2. Active Workflows

### 🔁 WF-001 · PR Review & Merge

**Trigger:** Pull request opened against `dev` or `staging`  
**Level:** 🟡 2  

```yaml
steps:
  1. read_repo               # L1
  2. review_code             # L2
  3. run_tests               # L1
  4. lint_code               # L1
  5. comment_on_pr           # L1
  6. [if all pass]
     merge_pr_dev_staging    # L2
  7. write_agent_log         # L1

rollback:
  - If tests fail: request changes on PR, notify owner via email
  - If merge conflict: comment on PR with conflict details, escalate to owner
```

---

### 📋 WF-002 · Issue Triage

**Trigger:** New issue opened  
**Level:** 🟡 2  

```yaml
steps:
  1. read_issue              # L1
  2. classify_issue          # L1
  3. assign_labels           # L1
  4. comment_on_issue        # L1
  5. [if duplicate]
     close_issue             # L2
  6. write_agent_log         # L1

rollback:
  - If classification uncertain: label as "needs-triage", notify owner
```

---

### 📝 WF-003 · Auto Documentation

**Trigger:** Push to `main` or `dev` branch  
**Level:** 🟡 2  

```yaml
steps:
  1. read_repo               # L1
  2. explain_code            # L2
  3. generate_readme         # L2
  4. commit_files            # L2
  5. open_pr_draft           # L2
  6. write_agent_log         # L1

rollback:
  - If no changes needed: skip silently, log "no-op"
```

---

### 📦 WF-004 · Release Preparation

**Trigger:** Tag pushed matching `v*.*.*`  
**Level:** 🟡 2  

```yaml
steps:
  1. read_repo               # L1
  2. draft_release           # L2
  3. send_email_owner        # L2
  4. write_agent_log         # L1

rollback:
  - If tag format invalid: comment on tag, notify owner
  - Never publish release without owner approval
```

---

### 🎵 WF-005 · Music Catalog Update (InnovativeArts)

**Trigger:** New files pushed to `music/` directory  
**Level:** 🟡 2  

```yaml
steps:
  1. read_repo               # L1
  2. catalog_music           # L2
  3. generate_metadata       # L2
  4. tag_audio               # L2
  5. create_issue            # L1
  6. write_agent_log         # L1

rollback:
  - If file format unsupported: create issue with details
```

---

### 📊 WF-006 · Daily Activity Summary

**Trigger:** Scheduled — daily at 9:00 AM UTC  
**Level:** 🟡 2  

```yaml
steps:
  1. read_agent_log          # L1
  2. list_branches           # L1
  3. search_github           # L1
  4. send_email_owner        # L2
  5. write_agent_log         # L1
```

---

### 🧹 WF-007 · Stale Issue Cleanup

**Trigger:** Scheduled — every Monday at 12:00 UTC  
**Level:** 🟢 1  

```yaml
steps:
  1. search_github           # L1
  2. [for each issue older than 30 days with no activity]
     comment_on_issue        # L1
     assign_labels           # L1
  3. write_agent_log         # L1
```

---

### 🚀 WF-008 · Marketing Asset Generation

**Trigger:** Manual — owner triggers with `@ADAAD-Agent create marketing [brief]`  
**Level:** 🟡 2  

```yaml
steps:
  1. read_brief              # L2
  2. web_search_trends       # L2
  3. draft_press_release     # L2
  4. generate_social_drafts  # L2
  5. commit_files            # L2
  6. open_pr_draft           # L2
  7. send_email_owner        # L2
  8. write_agent_log         # L1

rollback:
  - All output is draft only — never publish without owner approval
```

---

## 3. Creating a New Workflow

To define a new workflow:

1. Assign it the next `WF-NNN` identifier
2. Define trigger, level, steps, and rollback
3. Add all tool calls to `TOOLS.md` if not present
4. Set workflow level to the highest tier among its steps
5. Open a PR labeled `workflow-definition` for owner review

---

## 4. Conflict Resolution

If tier statements diverge between `WORKFLOWS.md`, `AGENT.md`, and `AUTONOMY.md`, `AUTONOMY.md` is authoritative and must be used for all tier decisions.

---

## 5. Review Gate

Any edit to `WORKFLOWS.md`, `AGENT.md`, or `AUTONOMY.md` requires a **tier-diff check** in review to verify no action/tier drift from the canonical matrix.

---

## 6. Workflow Logging

Every workflow execution appends to `AGENT_LOG.md`:

```
[ISO-8601] WF-001 | PR Review | PR #12 | outcome: merged | 4 steps | approved: autonomous
```

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
