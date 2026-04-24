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
- **Job Record Gate** — every autonomous run emits one job JSON file validated against `projects/jrt/metadata/schema/media_job.schema.json`

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
         - projects/jrt/metadata/schema/media_job.schema.json
       - If any schema is missing, block ingest to prevent orphan assets
  3. generate_metadata    # Compose generation prompt package
     owner: MediaAgent
     notes:
       - Build prompt package with required `generate_music` params: `prompt`, `style_profile`, `seed`, `length` (+ optional `tempo`, `key`)
       - Persist package reference in job record fields `input_assets` and `provenance_refs` for replay/audit
       - Set `stage` to generation-prep and emit `status: running` with current `attempt`
  4. verify_uniqueness_strategy  # Pre-generation novelty/guardrail strategy gate
     owner: IPAgent
     notes:
       - Required inputs: `prompt_package_ref`, `style_dna_fingerprint`, `seed_policy`
       - Required outputs: `decision_artifact_ref`, `novelty_metrics`, `guardrail_pass_fail`
       - Persist decision artifact + metrics under `provenance_refs` before generation is allowed
       - Set media job `status` to `blocked` when guardrail fails; only pass allows generation execution
  5. generate_music       # Execute auditable music generation
     owner: MediaAgent
     notes:
       - Execute only when `verify_uniqueness_strategy` returns `guardrail_pass_fail: pass`
       - Must use contracted provider interface and capture provider generation ID
       - Required outputs: `audio_path`, `render_metadata`, `uniqueness_report_ref`
       - Record rendered artifact under `output_assets`, and attach provider/model references under `provenance_refs`
  6. generate_metadata    # Run post-generation uniqueness/similarity gate (separate control)
     owner: IPAgent
     notes:
       - This gate remains independent from `verify_uniqueness_strategy` and runs after audio is generated
       - Evaluate generated audio against similarity thresholds before catalog/tag
       - Write gate metrics and decision artifact, then reference artifact via `provenance_refs` using `uniqueness_report_ref`
       - Set media job `status` to `blocked` when gate fails, otherwise continue with `status: running`
  7. generate_metadata    # Emit per-run job metadata (hard gate)
     owner: MediaAgent
     notes:
       - Emit exactly one JSON file under projects/jrt/metadata/jobs/ per autonomous run
       - Filename contract: `<created_at>__<job_id>.json` where `created_at` is UTC ISO-8601 basic timestamp (`YYYYMMDDTHHMMSSZ`)
       - Validate emitted file against projects/jrt/metadata/schema/media_job.schema.json
       - Required schema fields in emitted record: `job_id`, `track_id`, `stage`, `input_assets`, `output_assets`, `agent_owner`, `status`, `attempt`, `created_at`, `provenance_refs`
       - Current emitter: `python pipelines/validate_media_outputs.py --jobs-dir projects/jrt/metadata/jobs`
       - Block workflow progression if validation fails or file is missing
  8. catalog_music        # Extract and store track metadata
     owner: MediaAgent
     notes:
       - Execute only when `verify_uniqueness_strategy` is pass, post-generation uniqueness/similarity gate has passed, and job `status` is not `blocked`
  9. tag_audio            # Apply ID3 tags if missing
     owner: MediaAgent
     notes:
       - Execute only when `verify_uniqueness_strategy` is pass, post-generation uniqueness/similarity gate has passed, and generated `audio_path` is approved
  10. generate_metadata    # Finalize and persist ingest artifacts
     owner: IPAgent
     notes:
       - Build rollout package for downstream distribution
       - Write source lineage and audio fingerprint/provenance references
       - Required per run:
         - update track manifest
         - update provenance/log
         - append ingest summary entry
         - include the emitted media job file path from projects/jrt/metadata/jobs/
  11. create_issue         # "New tracks added: [list]"
     owner: MediaAgent
  12. write_agent_log      # Record catalog update and artifact paths + job record path
     owner: MediaAgent

rollback:
  - If unsupported file type is detected in projects/jrt/audio/: skip ingest for that file, create issue, and log rollback action with path + MIME type
  - If expected metadata file is missing under projects/jrt/metadata/: stop ingest batch, create issue, and mark run as blocked (no partial ingest)
  - If planned schema files are missing: fail fast before catalog step and record "orphan-asset prevention gate tripped"
  - If `verify_uniqueness_strategy` fails (`guardrail_pass_fail: fail`): block generation execution, emit issue containing decision artifact + novelty metrics, and require prompt/style/seed-policy revision before retry attempt
  - If the per-run media job JSON is missing or fails schema validation: fail fast before catalog step and record "media-job gate tripped"
  - If post-generation uniqueness/similarity gate fails: block release packaging, emit issue containing similarity metrics + report reference, and require prompt/model revision before retry attempt
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


## 5. Periodic Documentation Consistency Pass

### 🧾 WF-009 · Documentation Consistency Pass

**Trigger:** Scheduled — first business day of each month at 15:00 UTC (or any PR touching constitutional/agent docs)  
**Level:** 🟡 2  

```yaml
steps:
  1. read_repo                # L1
  2. review_code              # L2
  3. write_agent_log          # L1

checks:
  - action_name_consistency:
      description: >
        Verify action names referenced in AGENT.md, TOOLS.md, and WORKFLOWS.md
        are aligned to canonical action names in AUTONOMY.md.
      required_result: no mismatches
  - mcp_reference_consistency:
      description: >
        Verify MCP server IDs/endpoints/status references in MCP_SERVERS.md do not
        conflict with MCP_REGISTRY.md (registry is authoritative).
      required_result: no conflicting entries
  - path_integrity:
      description: >
        Verify all referenced files/paths in these docs exist in-repo.
      required_result: all referenced paths resolvable
  - constitutional_ownership_constraints:
      description: >
        Verify ownership/edit constraints remain explicit for constitutional docs:
        AGENT.md, AUTONOMY.md, SECURITY.md, and GOVERNANCE.md.
      required_result: constraints explicitly documented and non-ambiguous

rollback:
  - If any check fails: open a docs remediation PR/issue, label `docs-governance`, and block merge until resolved.
```

### Reviewer Checklist (PR-Ready)

Use this checklist for PR review when docs in scope are changed:

- [ ] **Action matrix parity:** action names in `AGENT.md`, `TOOLS.md`, and `WORKFLOWS.md` match canonical names in `AUTONOMY.md`.
- [ ] **MCP parity:** no conflicting MCP server references between `MCP_SERVERS.md` and `MCP_REGISTRY.md`; registry remains authoritative.
- [ ] **Path validity:** every referenced file/path exists at review time.
- [ ] **Constitutional ownership clarity:** ownership/edit constraints for `AGENT.md`, `AUTONOMY.md`, `SECURITY.md`, and `GOVERNANCE.md` are explicit.
- [ ] **Drift handling:** if any item fails, PR includes remediation commit or linked follow-up issue before approval.

---

### 🎧 WF-010 · AR Demo Orchestration & Signing Gate

**Trigger:** New demo payload posted to `services/ar_orchestrator` ingestion endpoint or queued event from campaign intake.  
**Level:** 🔴 3 (contains Level 3-equivalent signing ratification gate).

```yaml
steps:
  1. read_repo                    # L1
  2. generate_metadata            # L2
     owner: AROrchestrator
     notes:
       - Ingest demo payload: audio_demo_url + artist_profile + campaign_context
       - Fail closed on missing required metadata fields
  3. generate_metadata            # L2
     owner: AROrchestrator
     notes:
       - Extract audio + metadata vectors and compute novelty/risk/confidence scoring
       - Emit structured score breakdown and decision reasons
  4. review_code                  # L2
     owner: AROrchestrator
     notes:
       - Apply deterministic policy states only:
         - reject
         - revise
         - escalate_to_human
         - approve_for_release_prep
       - Low confidence must escalate_to_human
  5. deploy_production            # L3-equivalent gate
     owner: Gatekeeper
     notes:
       - For approve_for_release_prep, require ratification scope `release_signoff`
       - Validate ratification with `core/gatekeeper/ratification.py`
       - Missing/invalid ratification blocks signing path
  6. write_agent_log              # L1
     owner: AROrchestrator
     notes:
       - Persist structured artifact with scores, decision, reasons
       - Write immutable provenance reference to registry/provenance_log.jsonl

rollback:
  - Missing artist/campaign metadata: reject payload and stop processing (fail-closed)
  - Low-confidence prediction: escalate_to_human and block release-prep approval
  - Missing/invalid ratification for signing path: block approval and emit gate failure artifact
```

---

## 6. Workflow Logging

Every workflow execution appends to `AGENT_LOG.md`:

```
[ISO-8601] WF-001 | PR Review | PR #12 | outcome: merged | 4 steps | approved: autonomous
```

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*

*Changelog: Terminology normalization — verified workflow step names match `AUTONOMY.md` §1 canonical action identifiers.*

