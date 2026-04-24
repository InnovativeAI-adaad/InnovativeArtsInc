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
