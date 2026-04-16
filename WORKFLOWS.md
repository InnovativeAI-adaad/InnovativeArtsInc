# WORKFLOWS.md — Autonomous Workflow Definitions

> Part of the **InnovativeArtsInc** Agent Documentation Suite  
> Defines all automated and semi-automated workflows ADAAD-Agent can execute.

---

## 1. Workflow Structure

Each workflow defines:
- **Trigger** — what starts it (event, schedule, or manual)
- **Steps** — ordered list of tool calls
- **Level** — autonomy level of the highest-step
- **Rollback** — what happens on failure

---

## 2. Active Workflows

---

### 🔁 WF-001 · PR Review & Merge

**Trigger:** Pull request opened against `dev` or `staging`  
**Level:** 🟡 2  

```yaml
steps:
  1. read_repo         # Fetch the diff
  2. review_code       # Analyze changes, check for issues
  3. run_tests         # Trigger CI test suite
  4. lint_code         # Check style compliance
  5. comment_on_pr     # Post review summary
  6. [if all pass]
     merge_pr          # Merge to target branch
  7. write_agent_log   # Record outcome

rollback:
  - If tests fail: request_changes on PR, notify owner via email
  - If merge conflict: comment on PR with conflict details, escalate to owner
```

---

### 📋 WF-002 · Issue Triage

**Trigger:** New issue opened  
**Level:** 🟢 1  

```yaml
steps:
  1. read_issue        # Read title, body, labels
  2. classify_issue    # Bug / Feature / Docs / Question
  3. assign_labels     # Apply classification label
  4. comment_on_issue  # Post triage summary comment
  5. [if duplicate]
     close_issue       # Close with link to original
  6. write_agent_log   # Record triage result

rollback:
  - If classification uncertain: label as "needs-triage", notify owner
```

---

### 📝 WF-003 · Auto Documentation

**Trigger:** Push to `main` or `dev` branch  
**Level:** 🟡 2  

```yaml
steps:
  1. read_repo         # Scan changed files
  2. explain_code      # Generate docstrings / comments where missing
  3. generate_readme   # Update README if structure changed
  4. commit_files      # Commit docs to docs/ branch
  5. open_pr           # Open PR: "docs: auto-update [date]"
  6. write_agent_log   # Record what was documented

rollback:
  - If no changes needed: skip silently, log "no-op"
```

---

### 📦 WF-004 · Release Preparation

**Trigger:** Tag pushed matching `v*.*.*`  
**Level:** 🟡 2  

```yaml
steps:
  1. read_repo         # Get commits since last release
  2. generate_changelog# Summarize commits into changelog
  3. draft_release     # Create GitHub draft release with notes
  4. send_email        # Notify owner: "Release vX.X.X ready for review"
  5. write_agent_log   # Record release prep

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
  1. read_repo         # Detect new audio/metadata files
  2. catalog_music     # Extract and store track metadata
  3. generate_metadata # Write AI-generated descriptions
  4. tag_audio         # Apply ID3 tags if missing
  5. create_issue      # "New tracks added: [list]"
  6. write_agent_log   # Record catalog update

rollback:
  - If file format unsupported: create issue with details
```

---

### 📊 WF-006 · Daily Activity Summary

**Trigger:** Scheduled — daily at 9:00 AM UTC  
**Level:** 🟢 1  

```yaml
steps:
  1. read_agent_log    # Pull last 24h of agent actions
  2. list_branches     # Check active branches
  3. search_github     # Get open PRs and issues count
  4. list_calendar     # Check upcoming milestones
  5. send_email        # Send summary digest to owner
  6. write_agent_log   # Log: "daily summary sent"
```

---

### 🧹 WF-007 · Stale Issue Cleanup

**Trigger:** Scheduled — every Monday at 12:00 UTC  
**Level:** 🟢 1  

```yaml
steps:
  1. list_issues       # Get all open issues
  2. [for each issue older than 30 days with no activity]
     comment_on_issue  # "This issue has been inactive for 30 days."
     assign_labels     # Add "stale" label
  3. write_agent_log   # Record stale count and actions
```

---

### 🚀 WF-008 · Marketing Asset Generation

**Trigger:** Manual — owner triggers with `@ADAAD-Agent create marketing [brief]`  
**Level:** 🟡 2  

```yaml
steps:
  1. read_brief        # Parse owner's marketing brief
  2. web_search        # Research target audience & trends
  3. draft_press_release # Generate press copy
  4. generate_social   # Draft social media posts (3 platforms)
  5. commit_files      # Save to marketing/ directory
  6. open_pr           # PR: "marketing: [campaign name]"
  7. send_email        # Notify owner for review
  8. write_agent_log   # Record generation

rollback:
  - All output is draft only — never publish without owner approval
```

---

## 3. Creating a New Workflow

To define a new workflow:

1. Assign it the next `WF-NNN` identifier
2. Define trigger, level, steps, and rollback
3. Add all tool calls to `TOOLS.md` if not present
4. Ensure no step exceeds the workflow's stated level
5. Open a PR labeled `workflow-definition` for owner review

---

## 4. Workflow Logging

Every workflow execution appends to `AGENT_LOG.md`:

```
[ISO-8601] WF-001 | PR Review | PR #12 | outcome: merged | 4 steps | approved: autonomous
```

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
