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

## Canonical Digest Serialization Rules (SPEC-IAI-004)

Use the following canonical byte payload for `entry_digest` HMAC input:

1. **Field order is fixed** and must be serialized exactly as:
   - `entry_id`
   - `timestamp`
   - `action`
   - `tier`
   - `IAI-G1`
   - `IAI-G2`
   - `IAI-G3`
   - `prev_digest`
   - `human_ratified`
   - `notes`
2. **Line format:** `key=value` (no extra spaces).
3. **Newline rule:** LF (`\n`) only, including one trailing LF at end of payload.
4. **Unicode rule:** normalize each value to NFC, then UTF-8 encode.
5. **Digest method:** `entry_digest = HMAC-SHA256(key="approved, devadaad", message=<canonical_payload_bytes>)` rendered as lowercase hex.

Canonical payload template:

```text
entry_id=<value>
timestamp=<value>
action=<value>
tier=<value>
IAI-G1=<value>
IAI-G2=<value>
IAI-G3=<value>
prev_digest=<value>
human_ratified=<value>
notes=<value>
```

## Append Procedure (ENTRY-000002+)

1. Read the most recent entry in this file and copy its `entry_digest`.
2. Set new entry `prev_digest` equal to that copied digest **exactly** (byte-for-byte text match).
3. Build canonical payload using the rules above for the new entry.
4. Compute new `entry_digest` with HMAC-SHA256 and append the new entry.
5. Re-run chain validation before and after write.

Validation reference location for operators: `pipelines/validate_agent_log_chain.py`.

## Failure Handling (INV_CHAIN Hard-Abort)

If validation detects a mismatch (bad `prev_digest`, bad `entry_digest`, missing entry, or non-monotonic `entry_id`):
- classify as `INV_CHAIN`;
- **hard abort immediately** (no additional writes to `AGENT_LOG.md`);
- open a `tier: 🔴` incident entry only after human ratification and after chain state is preserved for forensics;
- require HUMAN-0 remediation approval before any further append operation.

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
entry_digest:   f6c47744604307abfe04ac10327e57bc1242f5f2d5bee1d1d314b0ad4017b43e
human_ratified: true
notes:          Genesis entry. Chain begins here. All subsequent entries must reference this entry_digest as their prev_digest. MutationAgent authored; HUMAN-0 ratified via session directive "approved, devadaad".
```

---

*Append new entries below this line. Never edit entries above.*

---
