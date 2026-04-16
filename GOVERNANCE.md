# GOVERNANCE.md — Constitutional Subordination Contract

> **Standard:** SPEC-IAI-005 | ADAAD v9.77.1 · Phase 144 · 241 Hard-class invariants
>
> **Authority:** HUMAN-0 — Dustin L. Reid (sole architect, InnovativeAI LLC)
>
> **Ratified:** 2026-04-16 via session directive "approved, devadaad"
>
> ⚠️ This file may only be amended by HUMAN-0. No agent may self-approve changes
> to this document. Amendments are forward-only (CVR principle).

---

## 1. Constitutional Hierarchy

```
ADAAD Constitutional Core (constitution.yaml · policy_version 1.0.0)
              │
              │  HUMAN-0 gate — irreducible
              ▼
  InnovativeArtsInc GovernanceGate
              │
     ┌────────┼────────┐
     ▼        ▼        ▼
  AutoAgent  MCP      WorkflowEngine
  (Tier 🟢)  Bridge   (Tier 🟡/🔴)
             (Tier 🟡)
```

ADAAD's `constitution.yaml` supersedes all InnovativeArtsInc agent directives in any
conflict. There are no exceptions.

---

## 2. Subordination Rules (Hard-class — Non-Overridable)

| Rule   | Statement |
|--------|-----------|
| SUB-01 | InnovativeArtsInc agents may not modify any ADAAD canonical file (VERSION, pyproject.toml, CHANGELOG.md, .adaad_agent_state.json) without explicit HUMAN-0 sign-off. |
| SUB-02 | InnovativeArtsInc autonomy tiers (🟢/🟡/🔴 defined in AUTONOMY.md) are bounded by ADAAD constitution.yaml. Constitution supersedes in all conflicts. |
| SUB-03 | No InnovativeArtsInc agent may self-approve a constitutional amendment. The HUMAN-0 gate is irreducible and cannot be delegated. |
| SUB-04 | InnovativeArtsInc GovernanceGate must wrap all external provider calls uniformly. Bare MCP calls that bypass the gate are a Hard-class violation. |
| SUB-05 | Fail-closed behavior is constitutional. Missing credential, missing MCP registration, or missing HUMAN-0 ratification → hard failure. Silent degradation is prohibited. |
| SUB-06 | DORK architectural permanence applies. Any capability added to InnovativeArtsInc agents must be architecturally permanent and grow in value indefinitely. No finite-task scoped implementations. |
| SUB-07 | Rollback is always a forward amendment. Destructive rewrites of `AGENT_LOG.md`, governance artifacts, or any constitutional document are prohibited. |

---

## 3. Governance Gates

Three gates apply to every autonomous action. All must PASS before execution.

### Gate IAI-G1 — Tier Classification

Every action is classified into exactly one autonomy tier before execution.

| Tier | Definition | Unattended execution |
|------|------------|---------------------|
| 🟢 | Fully autonomous — no human notification required | ✅ |
| 🟡 | Notify owner — execute then notify | ✅ (with post-notification) |
| 🔴 | Human required — must not execute without HUMAN-0 sign-off | ❌ |

**Hard rules:**
- Actions touching ADAAD canonical files are unconditionally 🔴.
- Unclassified actions block with `TIER_UNCLASSIFIED`.
- Mid-execution tier escalation triggers `TIER_BOUNDARY_VIOLATION` → abort.

### Gate IAI-G2 — MCP Server Authorization

Every MCP call must reference a registered server with permitted scope.

- Server must appear in `MCP_REGISTRY.md` with `status: active`.
- Operation must be listed in `permitted_scopes` (no wildcards).
- Caller tier must meet `tier_minimum` for the server.
- Failure modes: `MCP_UNREGISTERED_SERVER`, `MCP_SCOPE_VIOLATION`, `MCP_TIER_INSUFFICIENT`.

### Gate IAI-G3 — Credential Isolation (Always-On)

Scans every output surface for credential token patterns before emission.

- Cannot be disabled by any agent tier.
- Failure mode: `CREDENTIAL_LEAK_DETECTED` → hard abort + HUMAN-0 alert.
- See `SECURITY.md §4` for full specification.

---

## 4. HUMAN-0 Actions (Exclusive — Never Delegated)

The following actions require physical execution by Dustin L. Reid on ADAADell or
equivalent authorized hardware:

| Action | Reason |
|--------|--------|
| GPG-signed annotated tag creation | Cryptographic identity — non-delegable |
| Ed25519 key ceremony | Threshold signing — physical presence required |
| Constitutional amendment ratification | HUMAN-0 gate is irreducible |
| MCP server registration ceremony | `registered_by: HUMAN-0` invariant |
| GA gate sequence execution (Gates 2–4) | Release authority |
| Patent provisional filing | Legal instrument |

---

## 5. Amendment Protocol

1. ArchitectAgent drafts proposed amendment as a finding (FINDING-IAI-XXX).
2. Amendment is presented to HUMAN-0 for review — no code is executed during this phase.
3. HUMAN-0 issues ratification phrase on record (session directive or written sign-off).
4. MutationAgent executes amendment as a forward commit, never a rewrite.
5. Governance artifact (ILA JSON + sign-off record) is written to `artifacts/governance/`.
6. Amendment is logged in `AGENT_LOG.md` as a `🔴` entry with `human_ratified: true`.

---

## 6. Open Findings — Pending HUMAN-0 Physical Execution

| Finding | Description | Blocking |
|---------|-------------|---------|
| FINDING-IAI-001 | Planned MCP servers (Spotify, Stripe, Vercel, Supabase, Slack) require HUMAN-0 registration ceremony | Any call to these servers |
| FINDING-66-003 | ADAAD patent provisional filing | GA readiness |
| FINDING-126-NEW-001 | Ghost tag v9.59.0 GPG re-sign on ADAADell | Ledger integrity |
| FINDING-66-004 | Ed25519 2-of-3 threshold key ceremony on ADAADell | v1.1-GA (P0) |

---

*GOVERNANCE.md is owner-maintained only. ADAAD-Agent may read but never modify autonomously.*

*Constitutional authority: ADAAD constitution.yaml · policy_version 1.0.0 · HUMAN-0: Dustin L. Reid*
