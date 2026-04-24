"""Telemetry helpers for stage metrics and dashboard snapshots."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_METRICS_PATH = _REPO_ROOT / "registry" / "metrics.jsonl"
_DASHBOARD_PATH = _REPO_ROOT / "registry" / "dashboard_snapshot.json"


def _read_metrics() -> list[dict]:
    if not _METRICS_PATH.exists():
        return []

    records: list[dict] = []
    for raw_line in _METRICS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def append_stage_metric(
    *,
    job_id: str,
    stage: str,
    duration_ms: int,
    result: str,
    fitness_score: float,
    uniqueness_validation_time_ms: int | None = None,
    novelty_index: float | None = None,
    similarity_guardrail_pass: bool | None = None,
) -> dict:
    """Append a stage-completion record and refresh dashboard snapshot."""
    _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "job_id": job_id,
        "stage": stage,
        "duration_ms": duration_ms,
        "result": result,
        "fitness_score": fitness_score,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    if uniqueness_validation_time_ms is not None:
        record["uniqueness_validation_time_ms"] = uniqueness_validation_time_ms
    if novelty_index is not None:
        record["novelty_index"] = novelty_index
    if similarity_guardrail_pass is not None:
        record["similarity_guardrail_pass"] = similarity_guardrail_pass
    with _METRICS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")

    write_dashboard_snapshot()
    return record


def write_dashboard_snapshot() -> dict:
    """Generate a compact dashboard snapshot from stage metric history."""
    metrics = _read_metrics()
    total = len(metrics)

    success_count = sum(1 for item in metrics if item.get("result") == "success")
    retry_count = sum(1 for item in metrics if item.get("result") == "retry")

    failure_codes: Counter[str] = Counter()
    for item in metrics:
        result = str(item.get("result", ""))
        if result.startswith("failure:"):
            failure_codes[result.split(":", 1)[1]] += 1
        elif result == "failure":
            failure_codes["unspecified"] += 1

    active_queue = {
        item.get("job_id")
        for item in metrics
        if item.get("result") in {"queued", "in_progress"}
    }
    finalized_jobs = {
        item.get("job_id")
        for item in metrics
        if str(item.get("result", "")).startswith("failure") or item.get("result") == "success"
    }

    queue_depth = len({job for job in active_queue if job and job not in finalized_jobs})

    snapshot = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "queue_depth": queue_depth,
        "success_rate": round((success_count / total), 4) if total else 0.0,
        "retry_rate": round((retry_count / total), 4) if total else 0.0,
        "top_failure_codes": [
            {"code": code, "count": count}
            for code, count in failure_codes.most_common(5)
        ],
        "sample_size": total,
    }

    _DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DASHBOARD_PATH.write_text(
        json.dumps(snapshot, indent=2) + "\n",
        encoding="utf-8",
    )
    return snapshot
