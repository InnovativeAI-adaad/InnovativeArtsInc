"""IPAgent baseline implementation with ADAAD-required agent signatures."""

from __future__ import annotations

from core.agents.ip_agent.hasher import append_provenance_entries


_DEF_NAME = "ip_agent"


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


def run(input=None) -> dict:
    payload = input or {}
    output_files = payload.get("output_files")
    file_path = payload.get("file_path")

    if output_files is None:
        output_files = [file_path] if file_path else []

    if not output_files:
        return {"ok": False, "error": "At least one output artifact is required"}

    job_id = payload.get("job_id")
    track_id = payload.get("track_id")

    if not job_id or not track_id:
        return {"ok": False, "error": "job_id and track_id are required"}

    try:
        entries = append_provenance_entries(
            output_files,
            job_id=job_id,
            track_id=track_id,
            agent=payload.get("agent", _DEF_NAME),
            parent_artifact_hash=payload.get("parent_artifact_hash"),
            log_path=payload.get("provenance_log_path", "registry/provenance_log.jsonl"),
        )
        return {"ok": True, "entries": entries}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Provenance append failed; blocking pipeline completion: {exc}",
            "output_files": output_files,
            "job_id": job_id,
            "track_id": track_id,
        }


def mutate(src: str) -> str:
    return src


def score(output: dict) -> float:
    if output.get("ok") and output.get("entries"):
        return 1.0
    return 0.0
