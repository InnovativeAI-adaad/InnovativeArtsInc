"""IPAgent baseline implementation with ADAAD-required agent signatures."""

from __future__ import annotations

import datetime as dt
import json
import math
import time
from pathlib import Path
from typing import Any

from core.agents.ip_agent.hasher import append_provenance_entries
from core.agents.ip_agent.telemetry import append_stage_metric


_DEF_NAME = "ip_agent"
_STAGE_RUN = "ip_agent.run"
_SIMILARITY_AUDIT_DIR = Path("registry/similarity_audits")


def info() -> dict:
    return {
        "name": _DEF_NAME,
        "version": "0.3.0",
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


def _flatten_tokens(value: Any, *, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        tokens: set[str] = set()
        for key, nested in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            tokens.update(_flatten_tokens(nested, prefix=child_prefix))
        return tokens
    if isinstance(value, list):
        tokens: set[str] = set()
        for index, nested in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            tokens.update(_flatten_tokens(nested, prefix=child_prefix))
        return tokens
    return {f"{prefix}={value}" if prefix else str(value)}


def _jaccard_similarity(left: Any, right: Any) -> float:
    left_tokens = _flatten_tokens(left)
    right_tokens = _flatten_tokens(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union if union else 0.0


def _to_float_vector(value: Any) -> list[float] | None:
    if isinstance(value, list) and value:
        vector: list[float] = []
        for item in value:
            if not isinstance(item, (int, float)):
                return None
            vector.append(float(item))
        return vector
    return None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    max_len = max(len(left), len(right))
    padded_left = left + ([0.0] * (max_len - len(left)))
    padded_right = right + ([0.0] * (max_len - len(right)))

    numerator = sum(a * b for a, b in zip(padded_left, padded_right))
    left_norm = math.sqrt(sum(a * a for a in padded_left))
    right_norm = math.sqrt(sum(b * b for b in padded_right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _load_json_file(path_value: Any) -> Any:
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_candidate_render_metadata(payload: dict) -> Any:
    if "render_metadata" in payload:
        return payload["render_metadata"]
    return _load_json_file(payload.get("render_metadata_path"))


def _load_candidate_audio_fingerprint(payload: dict) -> Any:
    if "audio_fingerprint" in payload:
        return payload["audio_fingerprint"]
    loaded = _load_json_file(payload.get("audio_fingerprint_path"))
    if loaded is not None:
        return loaded
    raw_path = payload.get("audio_fingerprint_path")
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _extract_prior_signature(entry: dict) -> tuple[Any, Any]:
    render_metadata = entry.get("render_metadata")
    audio_fingerprint = entry.get("audio_fingerprint")

    if render_metadata is None and audio_fingerprint is None:
        file_value = entry.get("file")
        if file_value:
            loaded = _load_json_file(file_value)
            if isinstance(loaded, dict):
                render_metadata = loaded.get("render_metadata")
                audio_fingerprint = loaded.get("audio_fingerprint")

    return render_metadata, audio_fingerprint


def _similarity_score(
    candidate_render_metadata: Any,
    candidate_audio_fingerprint: Any,
    prior_render_metadata: Any,
    prior_audio_fingerprint: Any,
) -> float:
    scores: list[float] = []

    if candidate_render_metadata is not None and prior_render_metadata is not None:
        scores.append(_jaccard_similarity(candidate_render_metadata, prior_render_metadata))

    if candidate_audio_fingerprint is not None and prior_audio_fingerprint is not None:
        left_vec = _to_float_vector(candidate_audio_fingerprint)
        right_vec = _to_float_vector(prior_audio_fingerprint)
        if left_vec is not None and right_vec is not None:
            scores.append(_cosine_similarity(left_vec, right_vec))
        else:
            scores.append(_jaccard_similarity(candidate_audio_fingerprint, prior_audio_fingerprint))

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _read_provenance_entries(log_path: str) -> list[dict]:
    path = Path(log_path)
    if not path.exists():
        return []

    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
    return entries


def run_similarity_audit(payload: dict) -> dict:
    log_path = str(payload.get("provenance_log_path", "registry/provenance_log.jsonl"))
    job_id = str(payload.get("job_id") or "unknown")

    candidate_render_metadata = _load_candidate_render_metadata(payload)
    candidate_audio_fingerprint = _load_candidate_audio_fingerprint(payload)
    if candidate_render_metadata is None and candidate_audio_fingerprint is None:
        raise ValueError(
            "Similarity audit requires render metadata and/or audio fingerprint input"
        )

    prior_entries = _read_provenance_entries(log_path)
    max_similarity = 0.0
    most_similar_ref: dict | None = None

    for entry in prior_entries:
        prior_render_metadata, prior_audio_fingerprint = _extract_prior_signature(entry)
        similarity = _similarity_score(
            candidate_render_metadata,
            candidate_audio_fingerprint,
            prior_render_metadata,
            prior_audio_fingerprint,
        )
        if similarity > max_similarity:
            max_similarity = similarity
            most_similar_ref = {
                "job_id": entry.get("job_id"),
                "track_id": entry.get("track_id"),
                "file": entry.get("file"),
                "sha256": entry.get("sha256"),
            }

    revise_threshold = float(payload.get("similarity_revise_threshold", 0.75))
    block_threshold = float(payload.get("similarity_block_threshold", 0.9))

    if max_similarity >= block_threshold:
        decision = "block"
    elif max_similarity >= revise_threshold:
        decision = "revise"
    else:
        decision = "pass"

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = _SIMILARITY_AUDIT_DIR / f"{job_id}_{timestamp}.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    audit_payload = {
        "job_id": job_id,
        "decision": decision,
        "max_similarity": round(max_similarity, 6),
        "thresholds": {
            "revise": revise_threshold,
            "block": block_threshold,
        },
        "most_similar_ref": most_similar_ref,
        "candidate": {
            "render_metadata": candidate_render_metadata,
            "audio_fingerprint": candidate_audio_fingerprint,
        },
        "provenance_log_path": log_path,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    artifact_path.write_text(json.dumps(audit_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    return {
        "decision": decision,
        "max_similarity": max_similarity,
        "audit_artifact_path": str(artifact_path),
        "audit_artifact": audit_payload,
    }


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
        return {
            "ok": False,
            "error": "At least one output artifact is required",
            "stage_result_code": "failure:missing_output_files",
        }

    track_id = payload.get("track_id")

    if not payload.get("job_id") or not track_id:
        _record_stage(
            job_id=job_id,
            stage=_STAGE_RUN,
            started_at=started_at,
            result="failure:missing_required_ids",
            fitness_score=0.0,
        )
        return {
            "ok": False,
            "error": "job_id and track_id are required",
            "stage_result_code": "failure:missing_required_ids",
        }

    try:
        audit_result = run_similarity_audit(payload)
        provenance_refs = list(payload.get("provenance_refs") or [])
        provenance_refs.append(audit_result["audit_artifact_path"])

        provenance_targets = [*output_files, audit_result["audit_artifact_path"]]
        entries = append_provenance_entries(
            provenance_targets,
            job_id=payload["job_id"],
            track_id=track_id,
            agent=payload.get("agent", _DEF_NAME),
            parent_artifact_hash=payload.get("parent_artifact_hash"),
            retry_attempt=int(payload.get("retry_attempt", payload.get("attempt", 0)) or 0),
            log_path=payload.get("provenance_log_path", "registry/provenance_log.jsonl"),
        )

        stage_result_code = "success"
        ok = True
        error = None
        if audit_result["decision"] == "revise":
            stage_result_code = "failure:similarity_revise_required"
            ok = False
            error = (
                "Similarity audit requires revision before continuation; "
                f"max_similarity={audit_result['max_similarity']:.4f}"
            )
        elif audit_result["decision"] == "block":
            stage_result_code = "failure:similarity_blocked"
            ok = False
            error = (
                "Similarity audit blocked pipeline completion; "
                f"max_similarity={audit_result['max_similarity']:.4f}"
            )

        result = {
            "ok": ok,
            "entries": entries,
            "similarity_audit": {
                "decision": audit_result["decision"],
                "max_similarity": audit_result["max_similarity"],
            },
            "provenance_refs": provenance_refs,
            "stage_result_code": stage_result_code,
        }
        if error:
            result["error"] = error

        _record_stage(
            job_id=payload["job_id"],
            stage=_STAGE_RUN,
            started_at=started_at,
            result=stage_result_code,
            fitness_score=score(result),
        )
        return result
    except Exception as exc:
        stage_result_code = "failure:similarity_audit_exception"
        _record_stage(
            job_id=payload["job_id"],
            stage=_STAGE_RUN,
            started_at=started_at,
            result=stage_result_code,
            fitness_score=0.0,
        )
        return {
            "ok": False,
            "error": f"Similarity audit/provenance append failed; blocking pipeline completion: {exc}",
            "output_files": output_files,
            "job_id": payload["job_id"],
            "track_id": track_id,
            "stage_result_code": stage_result_code,
        }


def mutate(src: str) -> str:
    return src


def score(output: dict) -> float:
    if output.get("ok") and output.get("entries"):
        return 1.0
    return 0.0
