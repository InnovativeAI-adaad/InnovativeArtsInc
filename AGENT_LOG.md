# AGENT_LOG.md — HMAC-Chained Audit Ledger

> **Constitutional Standard:** SPEC-IAI-004 | ADAAD v9.77.1
>
> This ledger is **append-only**. Every entry must chain to the prior entry's
> `entry_digest` via `prev_digest`. Any gap or digest mismatch is an `INV_CHAIN`
> violation — hard abort, do not continue.
>
> ⚠️ This file may **never** be modified retrospectively. Corrections are forward
> amendments only (CVR principle). Owner: HUMAN-0 (Dustin L. Reid).

---

## Entry Schema

```
entry_id:       [monotonic integer, zero-padded to 6 digits]
timestamp:      [ISO-8601 UTC]
action:         [string — exact description of action taken]
tier:           [🟢 autonomous | 🟡 notify-owner | 🔴 human-required]
gate_results:
  IAI-G1:       [PASS | FAIL:<FAILURE_MODE>]
  IAI-G2:       [PASS | FAIL:<FAILURE_MODE> | N/A]
  IAI-G3:       [PASS | FAIL:CREDENTIAL_LEAK_DETECTED]
prev_digest:    [HMAC-SHA256 of entry_id N-1 | GENESIS for entry 000001]
entry_digest:   [HMAC-SHA256 of this entry's canonical fields]
human_ratified: [true | false]
notes:          [optional — error detail, ratification phrase, or audit note]
```

**Invariants:**
- `prev_digest` must match `entry_digest` of the immediately prior entry exactly.
- Entries where `tier: 🔴` must carry `human_ratified: true` before `action` is populated.
- `IAI-G3` is always evaluated — it cannot be `N/A`.
- `entry_id` is monotonic and never reused.

---

## Log Entries

---

### ENTRY-000001
```
entry_id:       000001
timestamp:      2026-04-16T00:00:00Z
action:         GENESIS — AGENT_LOG.md initialized with HMAC chain standard per SPEC-IAI-004. Constitutional subordination to ADAAD v9.77.1 established. HUMAN-0 ratification on record: "approved, devadaad" — Dustin L. Reid.
tier:           🔴
gate_results:
  IAI-G1:       PASS
  IAI-G2:       N/A
  IAI-G3:       PASS
prev_digest:    GENESIS
entry_digest:   [to be computed by runtime HMAC engine on first live execution]
human_ratified: true
notes:          Genesis entry. Chain begins here. All subsequent entries must reference this entry_digest as their prev_digest. MutationAgent authored; HUMAN-0 ratified via session directive "approved, devadaad".
```

---

*Append new entries below this line. Never edit entries above.*

---
