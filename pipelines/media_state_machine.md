# Media State Machine

Canonical stage order (linear only):

`draft_lyrics -> refined_lyrics -> prompt_packaged -> audio_generated -> audio_verified -> metadata_finalized -> provenance_written -> rollout_packaged`

## Allowed transitions

| From | To |
|---|---|
| `draft_lyrics` | `refined_lyrics` |
| `refined_lyrics` | `prompt_packaged` |
| `prompt_packaged` | `audio_generated` |
| `audio_generated` | `audio_verified` |
| `audio_verified` | `metadata_finalized` |
| `metadata_finalized` | `provenance_written` |
| `provenance_written` | `rollout_packaged` |
| `rollout_packaged` | terminal (no outgoing transition) |

## Validation policy

- Illegal jumps are rejected (fail-closed): no state update should occur.
- Backward moves are rejected.
- Skipping intermediate stages is rejected.
- Unknown stages are rejected.

## Media job record requirement

Every successful transition appends an event with:

- `status` (set to the target stage)
- `timestamp` (ISO-8601 UTC)
- `actor` (identity performing the transition)

Recommended event shape:

```json
{
  "from_stage": "audio_generated",
  "to_stage": "audio_verified",
  "status": "audio_verified",
  "timestamp": "2026-04-24T00:00:00+00:00",
  "actor": "media-pipeline"
}
```
