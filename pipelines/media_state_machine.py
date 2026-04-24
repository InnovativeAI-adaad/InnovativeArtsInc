"""Media job state machine with strict transition validation.

Stages are linear and must progress in order:
  draft_lyrics -> refined_lyrics -> prompt_packaged -> audio_generated
  -> audio_verified -> metadata_finalized -> provenance_written
  -> rollout_packaged
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

MEDIA_STAGES: tuple[str, ...] = (
    "draft_lyrics",
    "refined_lyrics",
    "prompt_packaged",
    "audio_generated",
    "audio_verified",
    "metadata_finalized",
    "provenance_written",
    "rollout_packaged",
)

_ALLOWED_NEXT_STAGE: dict[str, str] = {
    MEDIA_STAGES[idx]: MEDIA_STAGES[idx + 1]
    for idx in range(len(MEDIA_STAGES) - 1)
}


class TransitionValidationError(ValueError):
    """Raised when a transition request violates state machine rules."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_media_job_record(job_id: str, actor: str, timestamp: str | None = None) -> dict:
    """Create a new media job record at the initial stage."""
    if not job_id:
        raise TransitionValidationError("job_id is required")
    if not actor:
        raise TransitionValidationError("actor is required")

    created_at = timestamp or _utc_now_iso()
    initial_stage = MEDIA_STAGES[0]

    return {
        "job_id": job_id,
        "current_stage": initial_stage,
        "transition_log": [
            {
                "from_stage": None,
                "to_stage": initial_stage,
                "status": initial_stage,
                "timestamp": created_at,
                "actor": actor,
            }
        ],
    }


def transition_media_job(
    media_job_record: dict,
    to_stage: str,
    actor: str,
    timestamp: str | None = None,
) -> dict:
    """Apply a legal transition and append status/timestamp/actor to job history.

    Fail-closed behavior:
      - Any invalid input or illegal jump raises TransitionValidationError.
      - The original record is not mutated on failure.
    """
    if not isinstance(media_job_record, dict):
        raise TransitionValidationError("media_job_record must be a dict")
    if not actor:
        raise TransitionValidationError("actor is required")

    current_stage = media_job_record.get("current_stage")
    if current_stage not in MEDIA_STAGES:
        raise TransitionValidationError(f"invalid current stage: {current_stage!r}")

    if to_stage not in MEDIA_STAGES:
        raise TransitionValidationError(f"invalid target stage: {to_stage!r}")

    expected_next = _ALLOWED_NEXT_STAGE.get(current_stage)
    if expected_next is None:
        raise TransitionValidationError(
            f"{current_stage!r} is terminal and cannot transition further"
        )

    if to_stage != expected_next:
        raise TransitionValidationError(
            "illegal transition requested: "
            f"{current_stage!r} -> {to_stage!r}; expected {expected_next!r}"
        )

    new_record = deepcopy(media_job_record)
    new_record["current_stage"] = to_stage
    new_record.setdefault("transition_log", []).append(
        {
            "from_stage": current_stage,
            "to_stage": to_stage,
            "status": to_stage,
            "timestamp": timestamp or _utc_now_iso(),
            "actor": actor,
        }
    )
    return new_record
