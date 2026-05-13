#!/usr/bin/env python3
"""Write consolidated run summaries for autonomous media jobs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUMMARY_REF_TYPE = "run_summary"
SUMMARY_STAGE = "media_run.summary"
DEFAULT_SUMMARY_DIR = Path("projects/jrt/metadata/run_summaries")
DEFAULT_METRICS_PATH = Path("registry/metrics.jsonl")
DEFAULT_DASHBOARD_PATH = Path("registry/dashboard_snapshot.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _derive_stage_timings(job: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = job.get("stage_timings")
    if isinstance(explicit, list):
        return [item for item in explicit if isinstance(item, dict)]

    transition_log = job.get("transition_log")
    if not isinstance(transition_log, list):
        return []

    timings: list[dict[str, Any]] = []
    previous_time: datetime | None = None
    for row in transition_log:
        if not isinstance(row, dict):
            continue
        current_time = _parse_datetime(row.get("timestamp"))
        duration_ms = None
        if previous_time is not None and current_time is not None:
            duration_ms = max(int((current_time - previous_time).total_seconds() * 1000), 0)
        timings.append(
            {
                "stage": row.get("to_stage") or row.get("stage") or row.get("status") or "unknown",
                "started_at": row.get("timestamp"),
                "duration_ms": duration_ms,
                "actor": row.get("actor"),
            }
        )
        if current_time is not None:
            previous_time = current_time
    return timings


def _retry_counts(job: dict[str, Any]) -> dict[str, Any]:
    remediation_attempts = job.get("remediation_attempts")
    attempts = [item for item in remediation_attempts if isinstance(item, dict)] if isinstance(remediation_attempts, list) else []
    by_failure_type: Counter[str] = Counter(
        str(item.get("failure_type")) for item in attempts if item.get("failure_type")
    )
    configured_attempt = job.get("attempt") if isinstance(job.get("attempt"), int) else 1
    return {
        "job_attempt": configured_attempt,
        "total_retries": max(configured_attempt - 1, 0) + len(attempts),
        "remediation_attempts": len(attempts),
        "by_failure_type": dict(sorted(by_failure_type.items())),
    }


def _provider_model_ids(job: dict[str, Any]) -> list[dict[str, Any]]:
    providers: list[dict[str, Any]] = []

    generation_config = job.get("generation_config")
    if isinstance(generation_config, dict):
        model = generation_config.get("model_id") or generation_config.get("model_version")
        if model:
            providers.append(
                {
                    "provider_id": generation_config.get("provider_id") or generation_config.get("provider") or "unspecified",
                    "model_id": model,
                    "prompt_template_version": generation_config.get("prompt_template_version"),
                    "source": "generation_config",
                }
            )

    scheduler = job.get("scheduler")
    if isinstance(scheduler, dict) and (scheduler.get("selected_provider") or scheduler.get("selected_model")):
        providers.append(
            {
                "provider_id": scheduler.get("selected_provider") or "unspecified",
                "model_id": scheduler.get("selected_model") or "unspecified",
                "source": "scheduler",
            }
        )

    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in providers:
        key = (str(item.get("provider_id")), str(item.get("model_id")), str(item.get("source")))
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def _provenance_refs(job: dict[str, Any]) -> list[Any]:
    refs = job.get("provenance_refs")
    return refs if isinstance(refs, list) else []


def _find_ref(job: dict[str, Any], ref_type: str, ref_id: str | None = None) -> dict[str, Any] | None:
    for ref in _provenance_refs(job):
        if not isinstance(ref, dict):
            continue
        if ref.get("ref_type") != ref_type:
            continue
        if ref_id is None or ref.get("ref_id") == ref_id:
            return ref
    return None


def _gate_decision(job: dict[str, Any], phase: str) -> dict[str, Any]:
    explicit = job.get(f"{phase}_generation_gate_decision")
    if isinstance(explicit, dict):
        return explicit

    if phase == "pre":
        uniqueness = job.get("uniqueness_report")
        if isinstance(uniqueness, dict):
            decision = uniqueness.get("decision")
            return {
                "decision": "allowed" if decision == "pass" else "blocked" if decision == "block" else decision or "unknown",
                "source": "uniqueness_report",
                "details": uniqueness,
            }
        return {"decision": "unknown", "source": "not_recorded"}

    validation_ref = _find_ref(job, "validation_result", "all_required_checks_passed")
    if validation_ref is not None:
        passed = str(validation_ref.get("uri", "")).lower() == "true"
        return {
            "decision": "passed" if passed else "blocked",
            "source": "validation_result_ref",
            "all_required_checks_passed": passed,
        }
    status = job.get("status")
    return {
        "decision": "passed" if status in {"succeeded", "published"} else "blocked" if status == "blocked" else "failed" if status == "failed" else "unknown",
        "source": "job_status",
    }


def _quality_results(job: dict[str, Any]) -> dict[str, Any]:
    explicit = job.get("quality_results")
    if isinstance(explicit, dict):
        return explicit
    validation_ref = _find_ref(job, "validation_result", "all_required_checks_passed")
    tracks_ref = _find_ref(job, "tracks_evaluated")
    return {
        "all_required_checks_passed": str(validation_ref.get("uri", "")).lower() == "true" if validation_ref else None,
        "tracks_evaluated": int(tracks_ref["ref_id"]) if tracks_ref and str(tracks_ref.get("ref_id", "")).isdigit() else None,
        "source": "provenance_refs" if validation_ref or tracks_ref else "not_recorded",
    }


def _named_status(job: dict[str, Any], field_name: str, ref_type: str) -> dict[str, Any]:
    explicit = job.get(field_name)
    if isinstance(explicit, dict):
        return explicit
    if isinstance(explicit, str):
        return {"status": explicit, "source": field_name}
    ref = _find_ref(job, ref_type)
    if ref:
        return {"status": ref.get("ref_id"), "uri": ref.get("uri"), "source": "provenance_refs"}
    return {"status": "unknown", "source": "not_recorded"}


def _release_bundle_validation(job: dict[str, Any]) -> dict[str, Any]:
    explicit = job.get("release_bundle_validation")
    if isinstance(explicit, dict):
        return explicit
    if job.get("stage") == "rollout/platform_assets" and job.get("status") == "succeeded":
        return {"status": "passed", "source": "rollout_gate_status"}
    return _named_status(job, "release_bundle_validation", "release_bundle_validation")


def _job_flags(job: dict[str, Any], summary: dict[str, Any]) -> dict[str, bool]:
    status = str(job.get("status", "")).lower()
    stage = str(job.get("stage") or job.get("current_stage") or "").lower()
    post_decision = str(summary["post_generation_gate_decision"].get("decision", "")).lower()
    release_status = str(summary["release_bundle_validation"].get("status", "")).lower()
    return {
        "generated": any(token in stage for token in ("audio_generated", "audio_verified", "metadata_finalized", "provenance_written", "rollout", "release", "publish", "distribution"))
        or status in {"succeeded", "published"},
        "blocked": status == "blocked" or post_decision == "blocked",
        "failed": status == "failed" or post_decision == "failed",
        "release_ready": release_status == "passed" or "rollout" in stage or "release" in stage,
        "published": status == "published" or "publish" in stage or "distribution" in stage,
    }


def build_run_summary(job: dict[str, Any], *, summary_path: Path | None = None) -> dict[str, Any]:
    job_id = job.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("media job must include a non-empty job_id")

    summary: dict[str, Any] = {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "track_id": job.get("track_id"),
        "stage": job.get("stage") or job.get("current_stage"),
        "status": job.get("status", "unknown"),
        "attempt": job.get("attempt"),
        "created_at": job.get("created_at"),
        "generated_at": _utc_now(),
        "stage_timings": _derive_stage_timings(job),
        "retry_counts": _retry_counts(job),
        "provider_model_ids": _provider_model_ids(job),
        "pre_generation_gate_decision": _gate_decision(job, "pre"),
        "post_generation_gate_decision": _gate_decision(job, "post"),
        "quality_results": _quality_results(job),
        "release_bundle_validation": _release_bundle_validation(job),
        "campaign_plan_status": _named_status(job, "campaign_plan_status", "campaign_plan"),
        "rights_ledger_status": _named_status(job, "rights_ledger_status", "rights_ledger"),
    }
    summary["job_flags"] = _job_flags(job, summary)
    if summary_path is not None:
        summary["summary_path"] = str(summary_path)
    return summary


def append_run_summary_metric(summary: dict[str, Any], metrics_path: Path = DEFAULT_METRICS_PATH) -> dict[str, Any]:
    flags = summary.get("job_flags") if isinstance(summary.get("job_flags"), dict) else {}
    result = "success"
    if flags.get("blocked"):
        result = "blocked"
    elif flags.get("failed"):
        result = "failure"

    record = {
        "timestamp": _utc_now(),
        "job_id": summary["job_id"],
        "stage": SUMMARY_STAGE,
        "result": result,
        "status": summary.get("status", "unknown"),
        "summary_path": summary.get("summary_path"),
        "generated": bool(flags.get("generated")),
        "blocked": bool(flags.get("blocked")),
        "failed": bool(flags.get("failed")),
        "release_ready": bool(flags.get("release_ready")),
        "published": bool(flags.get("published")),
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _read_summaries(summary_dir: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    if not summary_dir.exists():
        return summaries
    for path in sorted(summary_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            summaries.append(payload)
    return summaries


def update_dashboard_snapshot(
    summary_dir: Path = DEFAULT_SUMMARY_DIR,
    dashboard_path: Path = DEFAULT_DASHBOARD_PATH,
) -> dict[str, Any]:
    summaries = _read_summaries(summary_dir)
    counts = {"generated": 0, "blocked": 0, "failed": 0, "release_ready": 0, "published": 0}
    for summary in summaries:
        flags = summary.get("job_flags")
        if not isinstance(flags, dict):
            flags = _job_flags(summary, summary)
        for name in counts:
            if flags.get(name):
                counts[name] += 1

    existing: dict[str, Any] = {}
    if dashboard_path.exists():
        try:
            loaded = json.loads(dashboard_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except json.JSONDecodeError:
            existing = {}

    existing.update(
        {
            "generated_at": _utc_now(),
            "media_job_counts": counts,
            "media_job_sample_size": len(summaries),
        }
    )
    _write_json(dashboard_path, existing)
    return existing


def attach_summary_provenance_ref(job: dict[str, Any], summary_path: Path) -> dict[str, Any]:
    refs = job.setdefault("provenance_refs", [])
    if not isinstance(refs, list):
        raise ValueError("media job provenance_refs must be an array")
    ref = {"ref_type": SUMMARY_REF_TYPE, "ref_id": str(job["job_id"]), "uri": str(summary_path)}
    if not any(isinstance(item, dict) and item.get("ref_type") == SUMMARY_REF_TYPE and item.get("uri") == str(summary_path) for item in refs):
        refs.append(ref)
    return ref


def write_media_run_summary(
    job: dict[str, Any],
    *,
    summary_dir: Path = DEFAULT_SUMMARY_DIR,
    metrics_path: Path = DEFAULT_METRICS_PATH,
    dashboard_path: Path = DEFAULT_DASHBOARD_PATH,
    append_metric: bool = True,
    update_dashboard: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    job_id = job.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("media job must include a non-empty job_id")
    summary_path = summary_dir / f"{job_id}.json"
    summary = build_run_summary(job, summary_path=summary_path)
    _write_json(summary_path, summary)
    summary_ref = attach_summary_provenance_ref(job, summary_path)
    if append_metric:
        append_run_summary_metric(summary, metrics_path)
    if update_dashboard:
        update_dashboard_snapshot(summary_dir, dashboard_path)
    return summary, summary_ref


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a consolidated autonomous media job run summary")
    parser.add_argument("--job-record", required=True, help="Path to the final media job JSON record")
    parser.add_argument("--summary-dir", default=str(DEFAULT_SUMMARY_DIR), help="Directory for <job_id>.json run summaries")
    parser.add_argument("--metrics-path", default=str(DEFAULT_METRICS_PATH), help="Metrics JSONL path")
    parser.add_argument("--dashboard-path", default=str(DEFAULT_DASHBOARD_PATH), help="Dashboard snapshot JSON path")
    parser.add_argument("--no-metric", action="store_true", help="Do not append registry/metrics.jsonl event")
    parser.add_argument("--no-dashboard", action="store_true", help="Do not refresh registry/dashboard_snapshot.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    job_record_path = Path(args.job_record)
    try:
        job = _load_json(job_record_path)
        summary, summary_ref = write_media_run_summary(
            job,
            summary_dir=Path(args.summary_dir),
            metrics_path=Path(args.metrics_path),
            dashboard_path=Path(args.dashboard_path),
            append_metric=not args.no_metric,
            update_dashboard=not args.no_dashboard,
        )
        _write_json(job_record_path, job)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    print(json.dumps({"summary_path": summary["summary_path"], "provenance_ref": summary_ref}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
