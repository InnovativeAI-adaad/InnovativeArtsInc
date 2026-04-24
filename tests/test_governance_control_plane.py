from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.governance import Actor, GovernanceControlPlane, GovernanceError


def _seed_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def test_ratification_request_approval_and_signed_action_trail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADAAD_GOVERNANCE_HMAC_KEY", "gov-key")
    plane = GovernanceControlPlane(
        ratification_store=tmp_path / "ratifications.jsonl",
        action_trail_store=tmp_path / "trail.jsonl",
        agent_log_path=tmp_path / "AGENT_LOG.md",
        provenance_log_path=tmp_path / "provenance.jsonl",
        incidents_dir=tmp_path / "incidents",
        similarity_audit_dir=tmp_path / "similarity",
    )

    request = plane.create_ratification_request(
        actor=Actor(actor_id="operator:alice", role="operator"),
        action="deploy_production",
        reason="Release window approved",
    )

    approved = plane.approve_ratification_request(
        actor=Actor(actor_id="reviewer:bob", role="reviewer"),
        request_id=request["request_id"],
        reason="Confirmed deploy checklist",
        approved_scope="deploy_production",
    )

    assert approved["status"] == "approved"
    trail = plane._read_jsonl(tmp_path / "trail.jsonl", max_entries=None)
    assert len(trail) == 2
    assert all("signature" in event for event in trail)


def test_manual_override_requires_reason_and_permissions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADAAD_GOVERNANCE_HMAC_KEY", "gov-key")
    plane = GovernanceControlPlane(
        ratification_store=tmp_path / "ratifications.jsonl",
        action_trail_store=tmp_path / "trail.jsonl",
    )

    with pytest.raises(GovernanceError):
        plane.apply_manual_override(
            actor=Actor(actor_id="owner:carol", role="owner"),
            override_action="quarantine_release",
            target_id="release-1",
            reason="",
        )

    with pytest.raises(GovernanceError):
        plane.apply_manual_override(
            actor=Actor(actor_id="operator:alice", role="operator"),
            override_action="quarantine_release",
            target_id="release-1",
            reason="Detected production anomaly",
        )


def test_read_only_audit_explorer_returns_expected_sources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADAAD_GOVERNANCE_HMAC_KEY", "gov-key")
    agent_log = tmp_path / "AGENT_LOG.md"
    agent_log.write_text("line-a\nline-b\nline-c\n", encoding="utf-8")

    provenance_path = tmp_path / "provenance.jsonl"
    _seed_jsonl(provenance_path, [{"event_id": "p1"}, {"event_id": "p2"}])

    incidents_dir = tmp_path / "incidents"
    incidents_dir.mkdir(parents=True)
    (incidents_dir / "i1.json").write_text(
        json.dumps({"incident_id": "inc-1", "status": "quarantine", "timestamp": "2026-04-20T00:00:00+00:00"}),
        encoding="utf-8",
    )

    similarity_dir = tmp_path / "similarity"
    similarity_dir.mkdir(parents=True)
    (similarity_dir / "s1.json").write_text(
        json.dumps({"job_id": "job-1", "decision": "pass", "max_similarity": 0.12}),
        encoding="utf-8",
    )

    plane = GovernanceControlPlane(
        ratification_store=tmp_path / "ratifications.jsonl",
        action_trail_store=tmp_path / "trail.jsonl",
        agent_log_path=agent_log,
        provenance_log_path=provenance_path,
        incidents_dir=incidents_dir,
        similarity_audit_dir=similarity_dir,
    )

    view = plane.read_audit_explorer(actor=Actor(actor_id="reviewer:bob", role="reviewer"), max_entries=2)
    assert view["agent_log"] == ["line-b", "line-c"]
    assert len(view["provenance_events"]) == 2
    assert view["incidents"][0]["incident_id"] == "inc-1"
    assert view["similarity_audits"][0]["decision"] == "pass"
