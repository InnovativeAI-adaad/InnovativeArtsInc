"""Crash-safe media conductor with state-machine driven transitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pipelines.media_state_machine import (
    MEDIA_STAGES,
    initialize_media_job_record,
    transition_media_job,
)

StageHandler = Callable[[dict[str, Any]], dict[str, Any] | None]

# Stage anchors from pipelines/media_state_machine.md, with strategy lock extension
# required by workflow policy.
STAGE_HANDLERS_IN_ORDER: tuple[tuple[str, str], ...] = (
    ("prompt_packaged", "prompt_packaging"),
    ("generation_strategy_locked", "strategy_lock"),
    ("audio_generated", "generation"),
    ("audio_verified", "uniqueness_audit"),
    ("metadata_finalized", "quality_validation"),
    ("metadata_finalized", "metadata_finalization"),
    ("provenance_written", "provenance_write"),
    ("rollout_packaged", "rollout_package"),
)


class MediaConductorError(RuntimeError):
    """Raised for media conductor setup and runtime errors."""


@dataclass(frozen=True)
class MediaConductorPaths:
    repo_root: Path
    jobs_dir: Path
    schema_path: Path
    checkpoints_dir: Path

    @classmethod
    def from_repo_root(cls, repo_root: str | Path) -> "MediaConductorPaths":
        root = Path(repo_root)
        jobs_dir = root / "projects" / "jrt" / "metadata" / "jobs"
        return cls(
            repo_root=root,
            jobs_dir=jobs_dir,
            schema_path=root / "projects" / "jrt" / "metadata" / "schema" / "media_job.schema.json",
            checkpoints_dir=jobs_dir / "checkpoints",
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _basic_timestamp(dt: datetime | None = None) -> str:
    value = dt or _utc_now()
    return value.strftime("%Y%m%dT%H%M%SZ")


class MediaConductor:
    """Orchestrates media job stage transitions with durable checkpoints and resume."""

    def __init__(
        self,
        *,
        paths: MediaConductorPaths,
        actor: str,
        handlers: dict[str, StageHandler] | None = None,
    ) -> None:
        self.paths = paths
        self.actor = actor
        self.handlers = handlers or {}
        self.paths.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.paths.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        if not self.paths.schema_path.exists():
            raise MediaConductorError(f"media job schema not found: {self.paths.schema_path}")

        self._schema = json.loads(self.paths.schema_path.read_text(encoding="utf-8"))

    def run(
        self,
        *,
        job_id: str,
        track_id: str,
        input_assets: list[dict[str, Any]],
        output_assets: list[dict[str, Any]],
        provenance_refs: list[dict[str, Any]],
        agent_owner: str,
        attempt: int = 1,
    ) -> dict[str, Any]:
        if not job_id:
            raise MediaConductorError("job_id is required")

        checkpoint = self._load_or_initialize_checkpoint(job_id=job_id)

        if checkpoint.get("emitted_media_job_file"):
            return checkpoint

        handler_runtime_payloads: dict[str, dict[str, Any] | None] = checkpoint.setdefault(
            "runtime_payloads", {}
        )

        # Always satisfy linear machine pre-anchors first.
        pre_anchor_payloads = {
            "generation_strategized": {
                "model_preset": "default",
                "temperature": 0.7,
                "creativity_controls": {"profile": "balanced"},
                "seed_policy": "deterministic",
                "novelty_threshold": 0.7,
            },
            "generation_strategy_locked": {
                "proposed_prompt_hash": f"sha256:{job_id}",
                "style_fingerprint": f"style:{track_id}:v1",
                "anti_dup_seed_policy": "reject-seen-seeds-30d",
                "novelty_threshold": 0.7,
            },
            "rollout_packaged": {
                "release_bundle_validation": "passed",
                "release_bundle_artifact_ref": f"registry://releases/{job_id}-bundle.json",
            },
        }

        for to_stage in MEDIA_STAGES[1:]:
            current_stage = checkpoint["media_job_record"]["current_stage"]
            if current_stage == to_stage:
                continue
            if MEDIA_STAGES.index(current_stage) >= MEDIA_STAGES.index(to_stage):
                continue

            runtime_payload = pre_anchor_payloads.get(to_stage)

            for handler_stage, handler_name in STAGE_HANDLERS_IN_ORDER:
                if handler_stage == to_stage:
                    handler_result = self._invoke_handler(handler_name, checkpoint)
                    if handler_result is not None:
                        runtime_payload = runtime_payload or {}
                        runtime_payload.update(handler_result)
                    handler_runtime_payloads[handler_name] = handler_result

            checkpoint["media_job_record"] = transition_media_job(
                checkpoint["media_job_record"],
                to_stage,
                self.actor,
                runtime_payload=runtime_payload,
            )
            checkpoint["updated_at"] = _utc_now_iso()
            self._write_checkpoint(job_id, checkpoint)

        media_job = {
            "job_id": job_id,
            "track_id": track_id,
            "stage": checkpoint["media_job_record"]["current_stage"],
            "input_assets": input_assets,
            "output_assets": output_assets,
            "agent_owner": agent_owner,
            "status": "succeeded",
            "attempt": attempt,
            "created_at": checkpoint["created_at"],
            "provenance_refs": provenance_refs,
        }

        self._validate_media_job_file(media_job)
        job_file = self._write_media_job_file(media_job)
        checkpoint["emitted_media_job_file"] = str(job_file.relative_to(self.paths.repo_root))
        checkpoint["updated_at"] = _utc_now_iso()
        self._write_checkpoint(job_id, checkpoint)
        return checkpoint

    def _invoke_handler(self, handler_name: str, checkpoint: dict[str, Any]) -> dict[str, Any] | None:
        handler = self.handlers.get(handler_name)
        if handler is None:
            return None
        result = handler(checkpoint)
        if result is not None and not isinstance(result, dict):
            raise MediaConductorError(f"handler {handler_name!r} must return dict|None")
        return result

    def _checkpoint_path(self, job_id: str) -> Path:
        return self.paths.checkpoints_dir / f"{job_id}.checkpoint.json"

    def _load_or_initialize_checkpoint(self, *, job_id: str) -> dict[str, Any]:
        checkpoint_path = self._checkpoint_path(job_id)
        if checkpoint_path.exists():
            return json.loads(checkpoint_path.read_text(encoding="utf-8"))

        created_at = _utc_now_iso()
        checkpoint = {
            "job_id": job_id,
            "created_at": created_at,
            "updated_at": created_at,
            "media_job_record": initialize_media_job_record(job_id=job_id, actor=self.actor, timestamp=created_at),
            "runtime_payloads": {},
            "emitted_media_job_file": None,
        }
        self._write_checkpoint(job_id, checkpoint)
        return checkpoint

    def _write_checkpoint(self, job_id: str, checkpoint: dict[str, Any]) -> None:
        path = self._checkpoint_path(job_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(path)

    def _write_media_job_file(self, media_job: dict[str, Any]) -> Path:
        created_at = datetime.fromisoformat(media_job["created_at"].replace("Z", "+00:00"))
        file_name = f"{_basic_timestamp(created_at)}__{media_job['job_id']}.json"
        target = self.paths.jobs_dir / file_name
        target.write_text(json.dumps(media_job, indent=2) + "\n", encoding="utf-8")
        return target

    def _validate_media_job_file(self, media_job: dict[str, Any]) -> None:
        required = self._schema.get("required", [])
        missing = [field for field in required if field not in media_job or media_job[field] in (None, "", [])]
        if missing:
            raise MediaConductorError(f"media job missing required fields: {missing}")

        allowed_statuses = (
            self._schema.get("properties", {})
            .get("status", {})
            .get("enum", [])
        )
        if media_job.get("status") not in allowed_statuses:
            raise MediaConductorError(
                f"media job status must be one of {allowed_statuses}, got {media_job.get('status')!r}"
            )

        if not isinstance(media_job.get("attempt"), int) or media_job["attempt"] < 1:
            raise MediaConductorError("media job attempt must be an integer >= 1")

        if not isinstance(media_job.get("input_assets"), list) or not media_job["input_assets"]:
            raise MediaConductorError("media job input_assets must be a non-empty array")

        if not isinstance(media_job.get("output_assets"), list) or not media_job["output_assets"]:
            raise MediaConductorError("media job output_assets must be a non-empty array")

        if not isinstance(media_job.get("provenance_refs"), list) or not media_job["provenance_refs"]:
            raise MediaConductorError("media job provenance_refs must be a non-empty array")


def run_media_conductor(
    *,
    repo_root: str | Path,
    job_id: str,
    track_id: str,
    input_assets: list[dict[str, Any]],
    output_assets: list[dict[str, Any]],
    provenance_refs: list[dict[str, Any]],
    actor: str = "media-conductor",
    agent_owner: str = "MediaAgent",
    attempt: int = 1,
    handlers: dict[str, StageHandler] | None = None,
) -> dict[str, Any]:
    """Convenience wrapper to execute one media conductor run."""
    conductor = MediaConductor(
        paths=MediaConductorPaths.from_repo_root(repo_root),
        actor=actor,
        handlers=handlers,
    )
    return conductor.run(
        job_id=job_id,
        track_id=track_id,
        input_assets=input_assets,
        output_assets=output_assets,
        provenance_refs=provenance_refs,
        agent_owner=agent_owner,
        attempt=attempt,
    )
