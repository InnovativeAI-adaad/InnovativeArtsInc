from __future__ import annotations

import json

import pytest

from services.ar_orchestrator.orchestrator import (
    DECISION_APPROVE_FOR_RELEASE_PREP,
    DECISION_ESCALATE_TO_HUMAN,
    AROrchestrator,
    AROrchestratorError,
)


def _valid_payload() -> dict:
    return {
        "job_id": "demo-123",
        "audio_demo_url": "https://cdn.example.com/demo.wav",
        "artist_profile": {
            "genre": "alt-pop",
            "audience_size": "mid",
            "brand_safety_tier": "strict",
        },
        "campaign_context": {
            "goal": "awareness",
            "region": "us",
            "budget_tier": "high",
        },
    }


def test_fail_closed_on_missing_metadata(tmp_path) -> None:
    orchestrator = AROrchestrator(registry_dir=tmp_path / "registry", queue_path=tmp_path / "queue.jsonl")
    payload = _valid_payload()
    del payload["artist_profile"]["genre"]

    with pytest.raises(AROrchestratorError):
        orchestrator.process_demo(payload)


def test_fail_closed_on_low_confidence_prediction(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = AROrchestrator(registry_dir=tmp_path / "registry", queue_path=tmp_path / "queue.jsonl")

    def forced_scores(_features: dict[str, float]) -> tuple[float, float, float]:
        return 0.82, 0.21, 0.05

    monkeypatch.setattr(orchestrator, "score_novelty_risk", forced_scores)

    artifact = orchestrator.process_demo(_valid_payload())
    assert artifact["decision"] == DECISION_ESCALATE_TO_HUMAN
    assert "low-confidence" in artifact["reasons"][0]


def test_fail_closed_when_ratification_absent_for_signing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = AROrchestrator(registry_dir=tmp_path / "registry", queue_path=tmp_path / "queue.jsonl")

    def forced_scores(_features: dict[str, float]) -> tuple[float, float, float]:
        return 0.88, 0.15, 0.4

    monkeypatch.setattr(orchestrator, "score_novelty_risk", forced_scores)

    payload = _valid_payload()
    with pytest.raises(AROrchestratorError, match="requires valid ratification"):
        orchestrator.process_demo(payload)


def test_writes_structured_artifact_and_registry_provenance(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = AROrchestrator(registry_dir=tmp_path / "registry", queue_path=tmp_path / "queue.jsonl")

    monkeypatch.setattr(orchestrator, "_require_signing_ratification", lambda _job: None)

    def forced_scores(_features: dict[str, float]) -> tuple[float, float, float]:
        return 0.9, 0.1, 0.5

    monkeypatch.setattr(orchestrator, "score_novelty_risk", forced_scores)

    artifact = orchestrator.process_demo(_valid_payload())

    assert artifact["decision"] == DECISION_APPROVE_FOR_RELEASE_PREP
    assert artifact["immutable_provenance_ref"].startswith("prov:")

    artifact_log = (tmp_path / "registry" / "ar_demo_decisions.jsonl").read_text(encoding="utf-8")
    assert json.loads(artifact_log.splitlines()[0])["artifact_id"] == artifact["artifact_id"]

    provenance_log = (tmp_path / "registry" / "provenance_log.jsonl").read_text(encoding="utf-8")
    assert "immutable_ref" in provenance_log


def test_consume_queue_keeps_failed_jobs_and_writes_dead_letter(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    queue_path = tmp_path / "registry" / "ar_demo_queue.jsonl"
    orchestrator = AROrchestrator(registry_dir=tmp_path / "registry", queue_path=queue_path)

    first_job = {"job_id": "job-success"}
    second_job = {"job_id": "job-fail"}
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(f"{json.dumps(first_job)}\n{json.dumps(second_job)}\n", encoding="utf-8")

    def fake_process_demo(job: dict) -> dict:
        if job["job_id"] == "job-fail":
            raise AROrchestratorError("synthetic failure")
        return {"job_id": job["job_id"], "artifact_id": "artifact-1"}

    monkeypatch.setattr(orchestrator, "process_demo", fake_process_demo)

    result = orchestrator.consume_queue()

    assert result["artifacts"] == [{"job_id": "job-success", "artifact_id": "artifact-1"}]
    assert result["failure_summary"]["count"] == 1
    assert result["failure_summary"]["jobs"][0]["job_id"] == "job-fail"
    assert result["failure_summary"]["jobs"][0]["error_type"] == "AROrchestratorError"

    remaining_lines = queue_path.read_text(encoding="utf-8").splitlines()
    assert remaining_lines == [json.dumps(second_job)]

    dead_letter_lines = (tmp_path / "registry" / "ar_demo_queue_failed.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(dead_letter_lines) == 1
    dead_letter_entry = json.loads(dead_letter_lines[0])
    assert dead_letter_entry["job_id"] == "job-fail"
    assert dead_letter_entry["error_message"] == "synthetic failure"


def test_consume_queue_rerun_does_not_duplicate_successful_artifact_writes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue_path = tmp_path / "registry" / "ar_demo_queue.jsonl"
    orchestrator = AROrchestrator(registry_dir=tmp_path / "registry", queue_path=queue_path)
    monkeypatch.setattr(orchestrator, "_require_signing_ratification", lambda _job: None)

    successful_job = _valid_payload() | {"job_id": "job-success"}
    failing_job = _valid_payload() | {"job_id": "job-fail"}
    del failing_job["artist_profile"]["genre"]
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(f"{json.dumps(successful_job)}\n{json.dumps(failing_job)}\n", encoding="utf-8")

    first_run = orchestrator.consume_queue()
    assert len(first_run["artifacts"]) == 1
    assert first_run["failure_summary"]["count"] == 1

    second_run = orchestrator.consume_queue()
    assert second_run["artifacts"] == []
    assert second_run["failure_summary"]["count"] == 1

    artifact_lines = (tmp_path / "registry" / "ar_demo_decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(artifact_lines) == 1
