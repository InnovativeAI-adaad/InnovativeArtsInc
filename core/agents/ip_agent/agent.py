"""IPAgent baseline implementation with ADAAD-required agent signatures."""

from __future__ import annotations

import time

from core.agents.ip_agent.hasher import append_provenance_entries
from core.agents.ip_agent.telemetry import append_stage_metric


_DEF_NAME = "ip_agent"
_STAGE_RUN = "ip_agent.run"
_STAGE_UNIQUENESS_AUDIT = "ip_agent.uniqueness_audit"


def info() -> dict:
    return {
        "name": _DEF_NAME,
        "version": "0.2.0",
        "description": "Generates provenance metadata for creative assets.",
    }


def _record_stage(
    *,
    job_id: str,
    stage: str,
    started_at: float,
    result: str,
    fitness_score: float,
) -> None:
    append_stage_metric(
        job_id=job_id,
        stage=stage,
        duration_ms=int((time.perf_counter() - started_at) * 1000),
        result=result,
        fitness_score=fitness_score,
    )




def _emit_uniqueness_audit_stage(payload: dict, job_id: str) -> None:
    uniqueness_validation_time_ms = payload.get("uniqueness_validation_time_ms")
    novelty_index = payload.get("novelty_index")
    similarity_guardrail_pass = payload.get("similarity_guardrail_pass")

    if (
        uniqueness_validation_time_ms is None
        and novelty_index is None
        and similarity_guardrail_pass is None
    ):
        return

    append_stage_metric(
        job_id=job_id,
        stage=_STAGE_UNIQUENESS_AUDIT,
        duration_ms=int(uniqueness_validation_time_ms or 0),
        result="success" if similarity_guardrail_pass is not False else "failure:similarity_guardrail",
        fitness_score=(
            float(novelty_index)
            if novelty_index is not None
            else (1.0 if similarity_guardrail_pass else 0.0)
        ),
        uniqueness_validation_time_ms=(
            int(uniqueness_validation_time_ms)
            if uniqueness_validation_time_ms is not None
            else None
        ),
        novelty_index=float(novelty_index) if novelty_index is not None else None,
        similarity_guardrail_pass=(
            bool(similarity_guardrail_pass)
            if similarity_guardrail_pass is not None
            else None
        ),
    )


def run(input=None) -> dict:
    started_at = time.perf_counter()
    payload = input or {}
    output_files = payload.get("output_files")
    file_path = payload.get("file_path")

    if output_files is None:
        output_files = [file_path] if file_path else []

    job_id = str(payload.get("job_id") or "unknown")

    if not output_files:
        _record_stage(
            job_id=job_id,
            stage=_STAGE_RUN,
            started_at=started_at,
            result="failure:missing_output_files",
            fitness_score=0.0,
        )
        return {"ok": False, "error": "At least one output artifact is required"}

    track_id = payload.get("track_id")

    if not payload.get("job_id") or not track_id:
        _record_stage(
            job_id=job_id,
            stage=_STAGE_RUN,
            started_at=started_at,
            result="failure:missing_required_ids",
            fitness_score=0.0,
        )
        return {"ok": False, "error": "job_id and track_id are required"}

    _emit_uniqueness_audit_stage(payload, job_id=payload["job_id"])

    try:
        entries = append_provenance_entries(
            output_files,
            job_id=payload["job_id"],
            track_id=track_id,
            agent=payload.get("agent", _DEF_NAME),
            parent_artifact_hash=payload.get("parent_artifact_hash"),
            retry_attempt=int(payload.get("retry_attempt", payload.get("attempt", 0)) or 0),
            log_path=payload.get("provenance_log_path", "registry/provenance_log.jsonl"),
        )
        result = {"ok": True, "entries": entries}
        _record_stage(
            job_id=payload["job_id"],
            stage=_STAGE_RUN,
            started_at=started_at,
            result="success",
            fitness_score=score(result),
        )
        return result
    except Exception as exc:
        _record_stage(
            job_id=payload["job_id"],
            stage=_STAGE_RUN,
            started_at=started_at,
            result="failure:append_provenance_exception",
            fitness_score=0.0,
        )
        return {
            "ok": False,
            "error": f"Provenance append failed; blocking pipeline completion: {exc}",
            "output_files": output_files,
            "job_id": payload["job_id"],
            "track_id": track_id,
        }


def mutate(src: str) -> str:
    return src


def score(output: dict) -> float:
    if output.get("ok") and output.get("entries"):
        return 1.0
    return 0.0
