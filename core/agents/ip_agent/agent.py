"""IPAgent baseline implementation with ADAAD-required agent signatures."""

from __future__ import annotations

import time
import uuid

from core.agents.ip_agent.hasher import generate_provenance_entry
from core.agents.ip_agent.telemetry import append_stage_metric


_DEF_NAME = "ip_agent"


def info() -> dict:
    return {
        "name": _DEF_NAME,
        "version": "0.1.0",
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


def run(input=None) -> dict:
    payload = input or {}
    job_id = payload.get("job_id") or str(uuid.uuid4())

    queue_started = time.perf_counter()
    _record_stage(
        job_id=job_id,
        stage="queue",
        started_at=queue_started,
        result="queued",
        fitness_score=0.0,
    )

    validate_started = time.perf_counter()
    file_path = payload.get("file_path")
    asset_type = payload.get("asset_type", "unknown")
    if not file_path:
        _record_stage(
            job_id=job_id,
            stage="validate_input",
            started_at=validate_started,
            result="failure:missing_file_path",
            fitness_score=0.0,
        )
        return {"ok": False, "error": "file_path is required", "job_id": job_id}

    _record_stage(
        job_id=job_id,
        stage="validate_input",
        started_at=validate_started,
        result="success",
        fitness_score=0.0,
    )

    process_started = time.perf_counter()
    try:
        entry = generate_provenance_entry(file_path, asset_type)
    except FileNotFoundError as exc:
        _record_stage(
            job_id=job_id,
            stage="generate_provenance",
            started_at=process_started,
            result="failure:file_not_found",
            fitness_score=0.0,
        )
        return {"ok": False, "error": str(exc), "file_path": file_path, "job_id": job_id}
    except ValueError as exc:
        _record_stage(
            job_id=job_id,
            stage="generate_provenance",
            started_at=process_started,
            result="failure:invalid_path",
            fitness_score=0.0,
        )
        return {"ok": False, "error": str(exc), "file_path": file_path, "job_id": job_id}
    except Exception as exc:
        _record_stage(
            job_id=job_id,
            stage="generate_provenance",
            started_at=process_started,
            result="failure:runtime_error",
            fitness_score=0.0,
        )
        return {"ok": False, "error": str(exc), "file_path": file_path, "job_id": job_id}

    stage_fitness = 1.0
    _record_stage(
        job_id=job_id,
        stage="generate_provenance",
        started_at=process_started,
        result="success",
        fitness_score=stage_fitness,
    )

    score_started = time.perf_counter()
    output = {"ok": True, "entry": entry, "job_id": job_id}
    final_score = score(output)
    _record_stage(
        job_id=job_id,
        stage="score_output",
        started_at=score_started,
        result="success",
        fitness_score=final_score,
    )

    return output


def mutate(src: str) -> str:
    return src


def score(output: dict) -> float:
    if output.get("ok") and output.get("entry"):
        return 1.0
    return 0.0
