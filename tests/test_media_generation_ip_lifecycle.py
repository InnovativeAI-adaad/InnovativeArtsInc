from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.media_generation.autonomous_run import run_autonomous_generation_lifecycle
from services.media_generation.ip_lifecycle import (
    IPGuardrailBlockedError,
    run_pre_generation_uniqueness_gate,
)


def _audit(decision: str = "pass", max_similarity: float = 0.1) -> dict:
    return {
        "decision": decision,
        "max_similarity": max_similarity,
        "confidence": max_similarity,
        "policy_version": "test-policy-v1",
        "audit_artifact_path": "registry/similarity_audits/job.json",
        "audit_artifact": {
            "method_results": [
                {"method": "metadata", "score": max_similarity, "method_version": "test"}
            ],
            "most_similar_ref": None,
        },
    }


def test_pre_generation_gate_writes_normalized_stable_decision(tmp_path: Path) -> None:
    with patch("services.media_generation.ip_lifecycle.ip_agent.run_similarity_audit", return_value=_audit()):
        decision = run_pre_generation_uniqueness_gate(
            project_root=tmp_path,
            job_id="job-001",
            track_id="track-001",
            prompt="noir piano",
            style_profile="jrt.noir.v1",
            seed=42,
            length=64,
        )

    expected_ref = "projects/jrt/metadata/ip_audits/pre_generation/job-001.json"
    assert decision == json.loads((tmp_path / expected_ref).read_text(encoding="utf-8"))
    assert set(decision) == {
        "decision_artifact_ref",
        "novelty_metrics",
        "guardrail_pass_fail",
        "policy_version",
        "reason",
    }
    assert decision["decision_artifact_ref"] == expected_ref
    assert decision["guardrail_pass_fail"] == "pass"
    assert decision["novelty_metrics"]["novelty_score"] == 0.9


def test_pre_generation_failure_blocks_media_generation(tmp_path: Path) -> None:
    with patch("services.media_generation.ip_lifecycle.ip_agent.run_similarity_audit", return_value=_audit("block", 0.95)):
        with patch("services.media_generation.autonomous_run.generate_music_for_wf005") as generate:
            with pytest.raises(IPGuardrailBlockedError):
                run_autonomous_generation_lifecycle(
                    project_root=tmp_path,
                    job_id="job-blocked-pre",
                    track_id="track-001",
                    prompt="too similar",
                    style_profile="jrt.noir.v1",
                    seed=42,
                    length=64,
                )

    generate.assert_not_called()
    assert (tmp_path / "projects/jrt/metadata/ip_audits/pre_generation/job-blocked-pre.json").exists()
    assert not (tmp_path / "projects/jrt/audio/generated").exists()


def test_autonomous_lifecycle_adds_both_ip_decisions_to_media_job(tmp_path: Path) -> None:
    with patch("services.media_generation.ip_lifecycle.ip_agent.run_similarity_audit", return_value=_audit()):
        result = run_autonomous_generation_lifecycle(
            project_root=tmp_path,
            job_id="job-allow",
            track_id="track-001",
            prompt="original cinematic noir piano",
            style_profile={"profile": "jrt.noir.v1"},
            seed=7,
            length=32,
        )

    assert result["ok"] is True
    pre_ref = "projects/jrt/metadata/ip_audits/pre_generation/job-allow.json"
    post_ref = "projects/jrt/metadata/ip_audits/post_generation/job-allow.json"
    assert (tmp_path / pre_ref).exists()
    assert (tmp_path / post_ref).exists()

    job_files = list((tmp_path / "projects/jrt/metadata/jobs").glob("*.json"))
    assert len(job_files) == 1
    media_job = json.loads(job_files[0].read_text(encoding="utf-8"))
    assert {ref["ref_id"] for ref in media_job["provenance_refs"]} >= {pre_ref, post_ref}


def test_post_generation_failure_blocks_cataloging_and_job_emission(tmp_path: Path) -> None:
    with patch(
        "services.media_generation.ip_lifecycle.ip_agent.run_similarity_audit",
        side_effect=[_audit("pass", 0.1), _audit("revise", 0.8)],
    ):
        with pytest.raises(IPGuardrailBlockedError):
            run_autonomous_generation_lifecycle(
                project_root=tmp_path,
                job_id="job-blocked-post",
                track_id="track-001",
                prompt="later too similar",
                style_profile="jrt.noir.v1",
                seed=99,
                length=32,
            )

    assert (tmp_path / "projects/jrt/audio/generated").exists()
    assert (tmp_path / "projects/jrt/metadata/ip_audits/post_generation/job-blocked-post.json").exists()
    jobs_dir = tmp_path / "projects/jrt/metadata/jobs"
    emitted_jobs = list(jobs_dir.glob("*.json")) if jobs_dir.exists() else []
    assert emitted_jobs == []
