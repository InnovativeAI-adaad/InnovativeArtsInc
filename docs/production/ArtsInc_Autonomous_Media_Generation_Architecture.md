# ArtsInc Autonomous Media Generation Architecture

**Status:** Product roadmap architecture  
**Audience:** HUMAN-0, operators, reviewers, service owners, and implementation agents  
**Scope:** End-to-end autonomous media generation from brief intake through release, growth, rights accounting, and observability.

---

## 1. Architecture Goals

The ArtsInc autonomous media generation platform coordinates creative ideation, AI-assisted media generation, governance, release operations, growth campaigns, and rights accounting as one auditable lifecycle.

Primary goals:

1. Convert approved creative briefs into release-ready media packages with deterministic checkpoints.
2. Preserve creator ownership, provenance, IP safety, and HUMAN-0 authority boundaries.
3. Route generation work through provider adapters without coupling roadmap logic to a single vendor.
4. Produce metadata, quality evidence, rights records, campaign plans, and observability events as first-class artifacts.
5. Support progressive rollout from MVP to beta to production without weakening governance gates.

Non-goals for this roadmap document:

- It does not define final product UI designs.
- It does not override `AUTONOMY.md`, `GOVERNANCE.md`, `SECURITY.md`, or other normative governance sources.
- It does not authorize production release, paid outreach, rights registration, or high-risk automation without the approval gates defined below.

---

## 2. End-to-End Lifecycle

The lifecycle is implemented as a governed pipeline. Each phase emits durable artifacts, updates job state, and records evidence for review.

| # | Phase | Purpose | Primary services/modules | Required outputs | Gate outcome |
|---|---|---|---|---|---|
| 1 | Brief intake | Capture creative intent, audience, constraints, assets, and release goals. | `services/media_conductor/service.py`, `projects/jrt/metadata/schema/media_job.schema.json` | `brief.json`, input asset refs, initial job record | Accept, reject, or request clarification |
| 2 | Creative planning | Translate the brief into campaign context, artist profile, style DNA, and prompt plan candidates. | `services/creative_planner/planner.py`, `services/ar_orchestrator/orchestrator.py` | `creative_plan.json`, `style_dna.json`, prompt plan set | Plan approved or held for revision |
| 3 | Generation strategy | Select model/provider presets, seed policy, novelty threshold, and fallback strategy. | `services/release_pipeline/generation_scheduler.py`, `pipelines/media_state_machine.py` | `generation_strategy.json`, scheduler decision metadata | Strategy locked or rejected |
| 4 | IP gates | Evaluate novelty, similarity, constraints, and release intent before provider execution or release packaging. | `core/agents/ip_agent/agent.py`, `core/gatekeeper/creative_policy.py`, `core/gatekeeper/authorization.py` | `ip_audit.json`, similarity evidence, authorization evidence | Pass, remediate, or HUMAN-0 escalation |
| 5 | Provider generation | Execute provider-specific generation through adapters and capture replay contracts. | `services/media_generation/service.py`, `services/media_generation/adapters.py` | stems/renders, `provider_result.json`, replay contract | Generated, failed, or fallback provider selected |
| 6 | Quality analysis | Validate media quality, metadata completeness, structural checks, and remediation attempts. | `pipelines/validate_media_outputs.py`, `projects/jrt/metadata/quality_rules.json` | `quality_report.json`, remediation log | Pass, auto-remediate, or block |
| 7 | Metadata | Finalize track, asset, contributor, campaign, and release metadata. | `projects/jrt/metadata/track_manifest.json`, `projects/jrt/metadata/control_plane.runtime.json`, `projects/jrt/metadata/agent_runtime_config.json` | `metadata_final.json`, track manifest update | Metadata finalized or blocked |
| 8 | Release packaging | Build signed artifact references, split sheet, DSP/PRO payloads, and release bundle. | `services/release_pipeline/service.py`, `services/release_pipeline/adapters.py` | `release_bundle.json`, `split_sheet.json`, signed artifact refs | Ready for HUMAN-0 release approval |
| 9 | Growth campaign | Prepare clips, attribution, experiments, CRM sync, and outreach governance. | `services/growth_ops/clip_contract.py`, `services/growth_ops/experiment_runner.py`, `services/growth_ops/attribution.py`, `services/growth_ops/crm_connectors.py`, `services/growth_ops/governance.py` | `campaign_plan.json`, clip jobs, experiment config | Approved campaign or held for HUMAN-0 |
| 10 | Rights ledger | Record ownership, splits, events, reconciliation, and payout/export evidence. | `services/rights_ledger/ledger.py`, `services/rights_ledger/splits.py`, `services/rights_ledger/events.py`, `services/rights_ledger/reconciliation.py`, `services/rights_ledger/payout_export.py` | ledger entries, split versions, payout export refs | Ledger committed or exception opened |
| 11 | Observability | Emit metrics, dashboard snapshots, provenance entries, incident records, and audit trails. | `registry/metrics.jsonl`, `registry/dashboard_snapshot.json`, `registry/provenance_log.jsonl`, `registry/version_manifest.json`, `projects/jrt/metadata/incidents/` | metrics rows, dashboard snapshots, provenance rows, incident reports | Healthy, degraded, or incident escalation |

### 2.1 Lifecycle State Alignment

The current media state machine defines the durable stage spine:

```text
draft_lyrics -> refined_lyrics -> prompt_packaged -> generation_strategized
-> generation_strategy_locked -> audio_generated -> audio_verified
-> metadata_finalized -> provenance_written -> rollout_packaged
```

Roadmap services should map product phases to this spine rather than inventing incompatible status values. If a future product stage is required, it must be introduced through a schema/state-machine migration with tests and governance review.

---

## 3. Service Map

### 3.1 Orchestration and Control

| Area | Existing module | Responsibility in roadmap architecture |
|---|---|---|
| Media conductor | `services/media_conductor/service.py` | Owns durable job execution, checkpointing, state transitions, handler ordering, and final media job emission. |
| State machine | `pipelines/media_state_machine.py` and `pipelines/media_state_machine.md` | Defines legal lifecycle stages, required runtime payload fields, and release/rollout transition metadata. |
| A&R orchestration | `services/ar_orchestrator/orchestrator.py` | Scores novelty/risk/confidence for demo intake and prepares release-prep decisions with provenance references. |
| Governance control plane | `core/governance/control_plane.py` | Centralizes actor/action evaluation, approvals, denials, and policy outcomes. |
| Gatekeeper | `core/gatekeeper/authorization.py`, `core/gatekeeper/creative_policy.py`, `core/gatekeeper/ratification.py`, `core/gatekeeper/abort.py` | Validates scoped authorization, safe creative constraints, ratification requirements, and abort paths. |

### 3.2 Creative and Generation

| Area | Existing module | Responsibility in roadmap architecture |
|---|---|---|
| Creative planner | `services/creative_planner/planner.py` | Builds campaign context, artist profile, style DNA fingerprints, prompt plans, trial outcomes, and lifecycle decisions. |
| Generation scheduler | `services/release_pipeline/generation_scheduler.py` | Scores candidate generation plans, resolves provider presets, selects fallback providers, and persists scheduler decision metadata. |
| Media generation service | `services/media_generation/service.py` | Executes workflow generation contracts, writes generation provenance, and normalizes generation results. |
| Provider adapters | `services/media_generation/adapters.py` | Provides adapter boundary for concrete model/provider calls and stubbed deterministic generation. |
| IP agent | `core/agents/ip_agent/agent.py` | Performs similarity/novelty audits, release-intent checks, provenance reading, telemetry emission, and scoring. |

### 3.3 Release, Growth, Rights, and Records

| Area | Existing module/path | Responsibility in roadmap architecture |
|---|---|---|
| Release pipeline | `services/release_pipeline/service.py` | Builds release bundles, generates split sheets, schedules generation jobs, and signs artifact references. |
| Release adapters | `services/release_pipeline/adapters.py` | Defines DSP and PRO adapter interfaces plus stub submission/registration implementations. |
| Growth clip contract | `services/growth_ops/clip_contract.py` | Defines clip asset, campaign metadata, variant strategy, and clip generation job contracts. |
| Growth experiments | `services/growth_ops/experiment_runner.py` | Registers variants, ingests metric events, and selects experiment winners. |
| Attribution | `services/growth_ops/attribution.py` | Connects campaign events to monetization ledger evidence. |
| CRM connectors | `services/growth_ops/crm_connectors.py` | Manages first-party audience records and consent state changes. |
| Growth governance | `services/growth_ops/governance.py` | Blocks non-compliant or high-risk outreach until checks and human approval are satisfied. |
| Rights ledger | `services/rights_ledger/ledger.py`, `services/rights_ledger/splits.py`, `services/rights_ledger/events.py` | Maintains immutable rights entries, split versions, and typed rights events. |
| Reconciliation/payouts | `services/rights_ledger/reconciliation.py`, `services/rights_ledger/payout_export.py` | Builds reconciliation reports and exports payout records to accounting/on-chain writers. |
| Metadata workspace | `projects/jrt/metadata/` | Stores runtime config, track manifest, quality rules, schema, job queue/checkpoints, and incident records. |
| Registry | `registry/` | Stores metrics, dashboard snapshots, provenance logs, version manifests, and asset index artifacts. |

---

## 4. Required Schemas

The roadmap requires schemas to be explicit, versioned, and validated before production use.

| Schema | Location | Required by | Minimum fields |
|---|---|---|---|
| Media job schema | `projects/jrt/metadata/schema/media_job.schema.json` | Lifecycle state emission | `job_id`, `track_id`, `stage`, `input_assets`, `output_assets`, `agent_owner`, `status`, `attempt`, `created_at`, `provenance_refs` |
| Brief schema | `projects/jrt/metadata/schema/brief.schema.json` | Brief intake | `brief_id`, `owner`, `objective`, `audience`, `constraints`, `source_assets`, `approval_status` |
| Creative plan schema | `projects/jrt/metadata/schema/creative_plan.schema.json` | Creative planning | `plan_id`, `job_id`, `artist_profile`, `campaign_context`, `style_dna`, `prompt_plans`, `risk_notes` |
| Generation strategy schema | `projects/jrt/metadata/schema/generation_strategy.schema.json` | Strategy lock | `strategy_id`, `job_id`, `provider`, `model_preset`, `seed_policy`, `novelty_threshold`, `fallbacks`, `locked_by` |
| IP audit schema | `projects/jrt/metadata/schema/ip_audit.schema.json` | IP gate | `audit_id`, `job_id`, `similarity_methods`, `novelty_index`, `policy_version`, `decision`, `evidence_refs` |
| Provider result schema | `projects/jrt/metadata/schema/provider_result.schema.json` | Provider generation | `provider`, `model_version`, `prompt_hash`, `seed`, `output_assets`, `usage`, `status`, `replay_contract` |
| Quality report schema | `projects/jrt/metadata/schema/quality_report.schema.json` | Quality analysis | `report_id`, `job_id`, `rules_version`, `checks`, `failures`, `remediation_attempts`, `decision` |
| Release bundle schema | `projects/jrt/metadata/schema/release_bundle.schema.json` | Release packaging | `bundle_id`, `track_id`, `assets`, `metadata_ref`, `split_sheet_ref`, `signed_artifacts`, `approval_state` |
| Campaign plan schema | `projects/jrt/metadata/schema/campaign_plan.schema.json` | Growth campaign | `campaign_id`, `release_id`, `channels`, `clip_jobs`, `experiments`, `audiences`, `governance_status` |
| Rights ledger event schema | `projects/jrt/metadata/schema/rights_event.schema.json` | Rights ledger | `event_id`, `event_type`, `track_id`, `split_version`, `amount`, `source_ref`, `created_at` |
| Observability event schema | `projects/jrt/metadata/schema/observability_event.schema.json` | Observability | `event_id`, `job_id`, `stage`, `severity`, `duration_ms`, `result`, `timestamp`, `correlation_id` |

MVP may begin with documented schema stubs for not-yet-implemented objects, but beta requires machine validation for every artifact that can influence release, paid growth, or rights accounting.

---

## 5. Required Artifact Directories

All generated artifacts must be stored under predictable directories so jobs are reproducible and reviewable.

| Directory | Purpose | Retention expectation |
|---|---|---|
| `projects/jrt/metadata/briefs/` | Intake briefs and brief approval records. | Keep every submitted brief version. |
| `projects/jrt/metadata/plans/` | Creative plans, style DNA fingerprints, prompt plan candidates, and planner decisions. | Keep all locked plans and rejected plan evidence. |
| `projects/jrt/metadata/strategies/` | Generation strategy locks, scheduler decisions, provider/fallback decisions. | Keep every locked strategy. |
| `projects/jrt/metadata/jobs/` | Job records, queues, emitted media job files, and job README. | Keep terminal job records. |
| `projects/jrt/metadata/jobs/checkpoints/` | Resume checkpoints written by the conductor. | Keep until job closeout plus audit window. |
| `projects/jrt/metadata/ip_audits/` | Similarity, novelty, and IP decision evidence. | Keep release-related audits indefinitely unless governance defines retention. |
| `projects/jrt/metadata/provider_results/` | Provider responses, replay contracts, and generation usage summaries. | Keep release-producing results and failed attempts needed for audit. |
| `projects/jrt/metadata/quality_reports/` | Validation reports and remediation attempt logs. | Keep all reports tied to released or candidate assets. |
| `projects/jrt/metadata/releases/` | Release bundles, signed artifact refs, split sheets, DSP/PRO payloads. | Keep indefinitely for released works. |
| `projects/jrt/metadata/campaigns/` | Campaign plans, clip jobs, experiment configs, attribution snapshots. | Keep through campaign closeout and finance reconciliation. |
| `projects/jrt/metadata/rights/` | Rights events, split versions, reconciliation reports, payout export manifests. | Keep indefinitely for accounting/legal traceability. |
| `projects/jrt/metadata/incidents/` | Incident reports, blocked actions, degraded-service notes, postmortems. | Keep per governance/security policy. |
| `registry/` | Cross-cutting metrics, dashboards, provenance, version manifest, and asset index. | Append-only where applicable; preserve production release evidence. |

---

## 6. Governance Gates and HUMAN-0 Approval Points

### 6.1 Gate Principles

1. **Fail closed:** Missing schemas, missing approvals, incomplete metadata, or unavailable policy inputs must block release-impacting progress.
2. **Separate generation from release:** A generation may be executed for evaluation, but release packaging, publication, paid promotion, and rights registration require stronger gates.
3. **Preserve auditability:** Every gate writes an artifact with actor, timestamp, policy version, decision, and evidence references.
4. **Escalate high-risk actions:** Any action involving public release, paid/bulk outreach, rights changes, cross-border data export, or production deployment requires HUMAN-0 review unless a narrower normative policy explicitly delegates it.

### 6.2 Required Gates

| Gate | Trigger | Automated checks | HUMAN-0 approval required? | Blocking condition |
|---|---|---|---|---|
| Brief acceptance | New brief enters roadmap pipeline | Required fields, source asset availability, owner identity, constraints present | Yes for externally committed projects or brand-sensitive topics | Missing owner, missing constraints, unsafe request |
| Creative plan lock | Prompt plans/style DNA selected | Plan completeness, policy-safe constraints, novelty/risk notes | Required when style imitation, sensitive subject matter, or brand-risk tier is elevated | Unbounded style reference, missing risk notes |
| Generation strategy lock | Provider/model/seed policy selected | Runtime payload fields, seed policy, novelty threshold, fallback plan | Required for budget-impacting provider spend or provider terms exceptions | Missing fallback, weak novelty threshold, unapproved spend |
| IP uniqueness gate | Before release candidate status | Similarity audit, provenance comparison, release-intent input completeness | Required for any borderline or failed audit override | Similarity threshold breach, missing evidence |
| Provider generation gate | Before external provider execution | Provider authorization, prompt hash, replay contract, usage budget | Required when provider is new, cost exceeds threshold, or data leaves approved boundary | Unauthorized provider, missing replay contract |
| Quality gate | Before metadata finalization | Quality rules, metadata completeness, structural checks, remediation result | Required to override a failed required check | Required check failed with no approved waiver |
| Release package gate | Before `rollout_packaged`/publication | Bundle validation, signed artifact refs, split sheet, provenance refs | **Always required** | Unsigned artifact, missing split, invalid bundle |
| Growth campaign gate | Before paid/bulk outreach or CRM activation | Consent, channel policy, audience size, risk score, required checks | **Always required for high-risk outreach** | Missing consent, policy non-compliance, no approval |
| Rights ledger gate | Before split update, registration, payout export | Split version validation, event type, reconciliation evidence | Required for split changes, payout export, PRO registration | Unresolved ownership dispute or invalid split |
| Production observability gate | Before production enablement | Metrics path, dashboard snapshot, incident path, alert owner | Required for production launch | No rollback/incident owner, missing dashboard |

### 6.3 HUMAN-0 Approval Points

HUMAN-0 must explicitly approve:

- Public release or release package promotion to a production distribution lane.
- Any override of IP, novelty, similarity, metadata, or quality failures.
- Any new provider that receives non-public assets or incurs production spend.
- Any paid campaign, bulk email/SMS, influencer outreach, cross-border audience data export, or other high-risk growth action.
- Any split-sheet change, rights registration, payout export, or ledger correction that affects ownership/economics.
- Any production deployment, main-branch merge tied to release automation, or change to normative governance/authority rules.

Approval artifacts must include `approved_by`, `approved_at`, `scope`, `policy_version`, `evidence_refs`, and `expiration` when approval is time-bound.

---

## 7. Milestones

### 7.1 MVP Milestone

Target outcome: one auditable internal release candidate can move from brief to packaged rollout without public distribution.

Required capabilities:

- Brief intake artifact and media job schema validation.
- Conductor-driven state transitions through `rollout_packaged` in a non-production lane.
- Creative planner prompt/style outputs saved as artifacts.
- Generation scheduler decision metadata and fallback selection.
- Stub or approved provider generation through adapter boundary.
- IP similarity audit evidence and quality report generation.
- Release bundle and split sheet generation without live DSP/PRO submission.
- Registry metrics/provenance rows for each stage.
- HUMAN-0 approval records for strategy lock and release-package review.

Exit criteria:

- A reviewer can reconstruct the run from `projects/jrt/metadata/` and `registry/` artifacts.
- Invalid state transitions and missing required schema fields fail closed.
- No paid outreach, public release, or live rights registration is automated.

### 7.2 Beta Milestone

Target outcome: limited, HUMAN-0 supervised releases and campaigns can run with controlled provider integrations.

Required capabilities:

- Machine-validated schemas for brief, creative plan, strategy, IP audit, provider result, quality report, release bundle, campaign plan, rights events, and observability events.
- Provider adapters with budget controls, replay contracts, and fallback routing.
- Automated remediation attempts for defined quality failures.
- DSP/PRO adapter dry-run and supervised submission modes.
- Growth campaign governance with consent checks, experiment tracking, attribution, and campaign closeout reports.
- Rights ledger split versioning, reconciliation reports, and payout export dry runs.
- Dashboard snapshots that expose queue health, success/retry/failure counts, and stage-level metrics.
- Incident records for blocked actions and failed gates.

Exit criteria:

- All high-risk gates produce explicit HUMAN-0 approval artifacts.
- Limited live releases can be performed only after release-package approval.
- Campaign actions are blocked unless consent, compliance checks, and required approvals are present.

### 7.3 Production Milestone

Target outcome: production-grade autonomous media operations with auditable releases, growth loops, rights accounting, and operational monitoring.

Required capabilities:

- Full schema registry with versioning and migration policy.
- Production provider allowlist, usage budgets, rollback/fallback runbooks, and data-boundary controls.
- End-to-end provenance for source assets, prompts, generated outputs, metadata, release bundles, campaigns, and rights events.
- Production DSP/PRO submission paths gated by HUMAN-0 release approval.
- Growth automation with real-time guardrails, rate limits, consent enforcement, attribution, and kill switches.
- Rights ledger reconciliation and payout export controls suitable for accounting review.
- Observability dashboard, alerting, incident ownership, postmortem workflow, and service-level objectives.
- Disaster recovery plan for registry, metadata, asset index, and ledger records.

Exit criteria:

- Production releases are reproducible from immutable artifacts and registry evidence.
- Every release-impacting action has a traceable actor, approval scope, policy version, and provenance reference.
- HUMAN-0 can pause generation, release, growth, or rights workflows without code changes.

---

## 8. Roadmap Implementation Notes

1. Add missing schema files incrementally under `projects/jrt/metadata/schema/`, starting with brief, creative plan, generation strategy, IP audit, quality report, release bundle, campaign plan, rights event, and observability event schemas.
2. Keep provider implementations behind `services/media_generation/adapters.py` and release destinations behind `services/release_pipeline/adapters.py`.
3. Treat `registry/provenance_log.jsonl` and `registry/metrics.jsonl` as append-oriented evidence logs; never rewrite production evidence during normal operation.
4. Use `projects/jrt/metadata/incidents/` for every blocked high-risk action, failed production gate, or HUMAN-0 override request.
5. Update this architecture document whenever a new lifecycle phase, gate, artifact directory, or production-impacting service is introduced.
