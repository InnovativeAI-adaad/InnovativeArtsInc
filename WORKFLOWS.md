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

**Trigger:** New files pushed to `projects/jrt/audio/` or `projects/jrt/metadata/`  
**Level:** 🟡 2 (highest canonical step tier: L2 via `generate_metadata`, `catalog_music`, `tag_audio`)  

```yaml
steps:
  1. read_repo            # Detect new files under projects/jrt/audio and projects/jrt/metadata
     owner: MediaAgent
     notes:
       - Sync/update metadata index from projects/jrt/metadata before ingest
       - Ensure each audio asset has a matching metadata file before ingest
  2. generate_metadata    # Normalize and validate ingest metadata package
     owner: MediaAgent
     notes:
       - Require planned schemas:
         - projects/jrt/metadata/schema/track.schema.json
         - projects/jrt/metadata/schema/provenance.schema.json
         - projects/jrt/metadata/schema/ingest-summary.schema.json
       - If any schema is missing, block ingest to prevent orphan assets
  3. catalog_music        # Extract and store track metadata
     owner: MediaAgent
  4. tag_audio            # Apply ID3 tags if missing
     owner: MediaAgent
  5. generate_metadata    # Finalize and persist ingest artifacts
     owner: IPAgent
     notes:
       - Build rollout package for downstream distribution
       - Write source lineage and audio fingerprint/provenance references
       - Required per run:
         - update track manifest
         - update provenance/log
         - append ingest summary entry
  6. create_issue         # "New tracks added: [list]"
     owner: MediaAgent
  7. write_agent_log      # Record catalog update and artifact paths
     owner: MediaAgent

rollback:
  - If unsupported file type is detected in projects/jrt/audio/: skip ingest for that file, create issue, and log rollback action with path + MIME type
  - If expected metadata file is missing under projects/jrt/metadata/: stop ingest batch, create issue, and mark run as blocked (no partial ingest)
  - If planned schema files are missing: fail fast before catalog step and record "orphan-asset prevention gate tripped"
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

## 4. Gate IAI-G2 Validation Checklist (MCP)

For any workflow step that interacts with MCP authorization:

- [ ] Read `MCP_REGISTRY.md` directly during Gate IAI-G2 validation.
- [ ] Do **not** read `MCP_SERVERS.md` for authorization, scope, endpoint, tier, or approval enforcement decisions.
- [ ] If `MCP_SERVERS.md` and `MCP_REGISTRY.md` differ, treat `MCP_REGISTRY.md` as authoritative override.
- [ ] Block execution when server status is not `active` in `MCP_REGISTRY.md`.

---

## 5. Workflow Logging

Every workflow execution appends to `AGENT_LOG.md`:

```
[ISO-8601] WF-001 | PR Review | PR #12 | outcome: merged | 4 steps | approved: autonomous
```

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
