from __future__ import annotations

import json
from pathlib import Path

from pipelines.write_media_run_summary import write_media_run_summary


def _job_record() -> dict:
    return {
        "job_id": "job-summary-001",
        "track_id": "track-001",
        "stage": "rollout/platform_assets",
        "status": "succeeded",
        "attempt": 2,
        "created_at": "2026-05-13T00:00:00Z",
        "input_assets": [{"asset_id": "manifest", "path": "manifest.json"}],
        "output_assets": [{"asset_id": "master", "path": "master.wav"}],
        "agent_owner": "MediaAgent",
        "provenance_refs": [
            {"ref_type": "validation_result", "ref_id": "all_required_checks_passed", "uri": "true"},
            {"ref_type": "tracks_evaluated", "ref_id": "1"},
            {"ref_type": "campaign_plan", "ref_id": "approved", "uri": "planner://plan-001"},
            {"ref_type": "rights_ledger", "ref_id": "balanced", "uri": "ledger://job-summary-001"},
        ],
        "generation_config": {
            "model_id": "music-model-1",
            "prompt_template_version": "prompt-v1",
            "seed": 123,
            "creativity_profile": "balanced",
            "style_constraints": ["red-dirt"],
        },
        "uniqueness_report": {
            "novelty_score": 0.98,
            "similarity_method": "embedding",
            "max_similarity_observed": 0.02,
            "decision": "pass",
        },
        "remediation_attempts": [
            {
                "attempt": 1,
                "failure_type": "mixing-level",
                "action": "adjust_gain",
                "status": "applied",
                "backoff_seconds": 1.0,
                "checks": ["loudness_bounds"],
                "details": "normalized",
                "timestamp": "2026-05-13T00:00:01Z",
            }
        ],
    }


def test_write_media_run_summary_persists_artifacts_metrics_dashboard_and_provenance(tmp_path: Path) -> None:
    summary_dir = tmp_path / "projects" / "jrt" / "metadata" / "run_summaries"
    metrics_path = tmp_path / "registry" / "metrics.jsonl"
    dashboard_path = tmp_path / "registry" / "dashboard_snapshot.json"
    job = _job_record()

    summary, summary_ref = write_media_run_summary(
        job,
        summary_dir=summary_dir,
        metrics_path=metrics_path,
        dashboard_path=dashboard_path,
    )

    summary_path = summary_dir / "job-summary-001.json"
    assert summary_path.exists()
    persisted = json.loads(summary_path.read_text(encoding="utf-8"))
    assert persisted["job_id"] == "job-summary-001"
    assert persisted["retry_counts"]["total_retries"] == 2
    assert persisted["provider_model_ids"][0]["model_id"] == "music-model-1"
    assert persisted["pre_generation_gate_decision"]["decision"] == "allowed"
    assert persisted["post_generation_gate_decision"]["decision"] == "passed"
    assert persisted["quality_results"]["all_required_checks_passed"] is True
    assert persisted["release_bundle_validation"]["status"] == "passed"
    assert persisted["campaign_plan_status"]["status"] == "approved"
    assert persisted["rights_ledger_status"]["status"] == "balanced"
    assert persisted["job_flags"]["generated"] is True
    assert persisted["job_flags"]["release_ready"] is True

    assert summary_ref in job["provenance_refs"]
    assert summary_ref == {
        "ref_type": "run_summary",
        "ref_id": "job-summary-001",
        "uri": str(summary_path),
    }

    metric = json.loads(metrics_path.read_text(encoding="utf-8").strip())
    assert metric["stage"] == "media_run.summary"
    assert metric["job_id"] == "job-summary-001"
    assert metric["release_ready"] is True

    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert dashboard["media_job_counts"] == {
        "generated": 1,
        "blocked": 0,
        "failed": 0,
        "release_ready": 1,
        "published": 0,
    }
    assert summary["summary_path"] == str(summary_path)
