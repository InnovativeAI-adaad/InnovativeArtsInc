from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipelines.run_autonomous_media_job import (
    AutonomousMediaJobRequest,
    run_autonomous_media_job,
)
from services.release_pipeline.generation_scheduler import schedule_generation_job


def _copy_runtime_files(root: Path) -> None:
    for relative in (
        "projects/jrt/metadata/agent_runtime_config.json",
        "projects/jrt/metadata/control_plane.runtime.json",
        "projects/jrt/metadata/quality_rules.json",
        "projects/jrt/metadata/schema/media_job.schema.json",
        "core/agents/ip_agent/config/similarity_policy.v1.json",
    ):
        source = _REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (root / "registry").mkdir(parents=True, exist_ok=True)
    (root / "registry" / "provenance_log.jsonl").write_text("", encoding="utf-8")


def _request(job_id: str = "job-autonomous-test") -> AutonomousMediaJobRequest:
    return AutonomousMediaJobRequest(
        job_id=job_id,
        track_id="JRT-AUTO-001",
        artist_profile={
            "artist_id": "jrt",
            "brand_voice": "red dirt testimony with industrial gospel grit",
            "signature_styles": ["industrial gospel", "red dirt"],
            "risk_tolerance": 0.35,
        },
        creative_brief={
            "title": "Autonomous Test Signal",
            "objective": "create a release-ready original validation render",
            "audience_segments": ["core fans"],
            "channels": ["streaming"],
            "constraints": ["original-composition", "no protected lyric reuse"],
            "genre_blend": ["red dirt", "industrial gospel"],
            "mood_arc": "uplifting",
            "tempo": 104,
            "key": "C",
            "length": 24,
        },
        campaign_budget_tier="mid",
        release_urgency="normal",
        seed=77,
    )


def test_schedule_generation_job_returns_provider_model_strategy() -> None:
    decision = schedule_generation_job(
        job_id="job-scheduler-entrypoint",
        prompt_plan={"plan_id": "plan-entrypoint"},
        campaign_budget_tier="mid",
        release_urgency="rush",
        runtime_policy={"retry_policy": {"max_attempts": 1}},
        creative_policy={"tempo_window": {"min_allowed": 60, "max_allowed": 180}},
    )

    assert decision["selected_provider"]
    assert decision["selected_model"]
    assert decision["selected_plan_id"].startswith("plan-entrypoint-")
    assert decision["runtime_policy_loaded"] is True
    assert decision["creative_policy_loaded"] is True
    assert decision["job_metadata"]["scheduler"]["ranked_candidates"]


def test_run_autonomous_media_job_emits_machine_readable_summary_and_media_job(
    tmp_path, monkeypatch
) -> None:
    _copy_runtime_files(tmp_path)
    monkeypatch.chdir(tmp_path)

    summary = run_autonomous_media_job(_request(), repo_root=tmp_path)

    assert summary["status"] == "succeeded"
    assert summary["release_readiness"] == {"ready": True, "reason": "ready"}
    assert summary["gate_decisions"]["pre_generation"]["decision"] == "pass"
    assert summary["gate_decisions"]["post_generation"]["decision"] == "pass"
    assert (
        summary["gate_decisions"]["quality_validation"]["all_required_checks_passed"]
        is True
    )
    assert summary["remediation_status"]["attempted"] is False

    artifacts = summary["generated_artifact_paths"]
    for key in ("prompt_plan", "audio", "lyrics", "quality_manifest", "media_job"):
        assert artifacts[key]
        assert (tmp_path / artifacts[key]).exists()

    media_job = json.loads(
        (tmp_path / artifacts["media_job"]).read_text(encoding="utf-8")
    )
    assert media_job["job_id"] == "job-autonomous-test"
    assert media_job["track_id"] == "JRT-AUTO-001"
    assert media_job["output_assets"]
