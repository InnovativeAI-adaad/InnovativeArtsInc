"""Media job state machine with strict transition validation.

Stages are linear and must progress in order:
  draft_lyrics -> refined_lyrics -> prompt_packaged -> generation_strategized
  -> generation_strategy_locked -> audio_generated -> audio_verified -> metadata_finalized
  -> provenance_written -> rollout_packaged
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

MEDIA_STAGES: tuple[str, ...] = (
    "draft_lyrics",
    "refined_lyrics",
    "prompt_packaged",
    "generation_strategized",
    "generation_strategy_locked",
    "audio_generated",
    "audio_verified",
    "metadata_finalized",
    "provenance_written",
    "rollout_packaged",
)

ALLOWED_RUNTIME_PAYLOAD_FIELDS_BY_STAGE: dict[str, tuple[str, ...]] = {
    "generation_strategized": (
        "model_preset",
        "temperature",
        "creativity_controls",
        "seed_policy",
        "novelty_threshold",
    ),
    "generation_strategy_locked": (
        "proposed_prompt_hash",
        "style_fingerprint",
        "anti_dup_seed_policy",
        "novelty_threshold",
    ),
}

_ALLOWED_NEXT_STAGE: dict[str, str] = {
    MEDIA_STAGES[idx]: MEDIA_STAGES[idx + 1]
    for idx in range(len(MEDIA_STAGES) - 1)
}


_COMPAT_ALLOWED_NEXT_STAGES: dict[str, tuple[str, ...]] = {
    "generation_strategized": ("generation_strategy_locked", "audio_generated"),
}


TRANSITION_METADATA_BY_TO_STAGE: dict[str, dict[str, Any]] = {
    "provenance_written": {
        "can_invoke_level_3": True,
        "ratification_scope": "publish_release",
        "level_3_actions": ("publish_release",),
    },
    "rollout_packaged": {
        "can_invoke_level_3": True,
        "ratification_scope": "deploy_production",
        "level_3_actions": ("deploy_production", "merge_pr_main"),
        "preconditions": {
            "release_bundle_validation": "passed",
        },
    },
}

class TransitionValidationError(ValueError):
    """Raised when a transition request violates state machine rules."""




def _validate_rollout_runtime_payload(runtime_payload: dict[str, Any] | None) -> None:
    if not isinstance(runtime_payload, dict):
        raise TransitionValidationError(
            "runtime_payload must be a dict for stage 'rollout_packaged'"
        )

    if runtime_payload.get("release_bundle_validation") != "passed":
        raise TransitionValidationError(
            "rollout_packaged requires release_bundle_validation='passed'"
        )

    artifact_ref = runtime_payload.get("release_bundle_artifact_ref")
    if not isinstance(artifact_ref, str) or not artifact_ref:
        raise TransitionValidationError(
            "rollout_packaged requires runtime_payload.release_bundle_artifact_ref"
        )

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_runtime_payload_for_stage(to_stage: str, runtime_payload: dict[str, Any] | None) -> None:
    required_fields = ALLOWED_RUNTIME_PAYLOAD_FIELDS_BY_STAGE.get(to_stage, ())
    if not required_fields:
        return

    if not isinstance(runtime_payload, dict):
        raise TransitionValidationError(
            f"runtime_payload must be a dict for stage {to_stage!r}"
        )

    missing_fields = [field for field in required_fields if runtime_payload.get(field) in (None, "")]
    if missing_fields:
        raise TransitionValidationError(
            f"runtime_payload missing required fields for stage {to_stage!r}: {missing_fields}"
        )


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
    runtime_payload: dict[str, Any] | None = None,
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
    compat_next_stages = _COMPAT_ALLOWED_NEXT_STAGES.get(current_stage, ())
    allowed_next_stages = (
        (expected_next,) if expected_next is not None else ()
    ) + tuple(stage for stage in compat_next_stages if stage != expected_next)

    if not allowed_next_stages:
        raise TransitionValidationError(
            f"{current_stage!r} is terminal and cannot transition further"
        )

    if to_stage not in allowed_next_stages:
        raise TransitionValidationError(
            "illegal transition requested: "
            f"{current_stage!r} -> {to_stage!r}; expected one of {allowed_next_stages!r}"
        )

    _validate_runtime_payload_for_stage(to_stage, runtime_payload)
    if to_stage == "rollout_packaged":
        _validate_rollout_runtime_payload(runtime_payload)

    new_record = deepcopy(media_job_record)
    new_record["current_stage"] = to_stage
    event = {
        "from_stage": current_stage,
        "to_stage": to_stage,
        "status": to_stage,
        "timestamp": timestamp or _utc_now_iso(),
        "actor": actor,
    }
    if runtime_payload is not None:
        event["runtime_payload"] = runtime_payload

    transition_metadata = TRANSITION_METADATA_BY_TO_STAGE.get(to_stage)
    if transition_metadata is not None:
        event["transition_metadata"] = deepcopy(transition_metadata)

    new_record.setdefault("transition_log", []).append(event)
    return new_record
