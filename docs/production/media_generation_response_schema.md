# Media Generation Response Schema (WF-005)

`generate_music_for_wf005` now returns a normalized schema while preserving legacy fields for transition compatibility.

## Canonical fields

- `job_id`: deterministic job id (same value as replay key)
- `replay_key`: deterministic replay contract key
- `provider_generation_id`: provider-side generation id
- `artifacts`: array of artifact records:
  - `type`
  - `path`
  - `digest`
  - `duration` or `resolution`
- `cost`:
  - `estimated`
  - `actual`
  - `currency`
  - `provider_rate_ref`
- `provenance_ref`: provenance ledger reference
- `policy_ref`: uniqueness/policy report reference

## Transition aliases (backward compatibility)

The service keeps pre-existing fields so downstream callers are not broken:

- `audio_path`
- `render_metadata`
- `uniqueness_report_ref`
- `analysis_artifact`
- `replayed`
- `artifact_refs` (alias of `artifacts`)
- `cost_summary` (alias of `cost`)

## Provider response normalization

HTTP provider adapters normalize malformed/variant provider payloads before persistence:

- normalizes generation id aliases (`id`, `generation_id`, `prediction.id`)
- normalizes audio location aliases (`audio_base64`, `audio`, `audio_url`, `url`, `output`)
- drops malformed values and preserves observable raw key list for auditing
