from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.governance import Actor, GovernanceControlPlane, GovernanceError


def _runtime_policy(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "genre_blend": {"max_components": 3, "banned_combinations": [["horror", "nursery"]]},
                "mood_arc": {"allowed": ["uplifting", "reflective", "dark"]},
                "lyrical_boundaries": {
                    "max_explicitness": 0.6,
                    "blocked_terms": ["hate_speech", "self_harm_instruction"],
                },
                "tempo_window": {"min_allowed": 60, "max_allowed": 180},
                "key_window": {"allowed_keys": ["C", "D", "E", "F", "G", "A", "B"]},
                "override_tiers": {
                    "safe": {"tier": 1, "approval_model": "Autonomous", "autonomy_actions": ["read_repo"]},
                    "standard": {
                        "tier": 2,
                        "approval_model": "Log + notify owner",
                        "autonomy_actions": ["commit_files"],
                    },
                    "elevated": {
                        "tier": 3,
                        "approval_model": "Human approval required",
                        "autonomy_actions": ["deploy_production"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def test_create_generation_strategy_writes_snapshot_and_provenance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADAAD_GOVERNANCE_HMAC_KEY", "gov-key")
    runtime_path = tmp_path / "control-runtime.json"
    _runtime_policy(runtime_path)

    plane = GovernanceControlPlane(
        ratification_store=tmp_path / "ratifications.jsonl",
        action_trail_store=tmp_path / "trail.jsonl",
        provenance_log_path=tmp_path / "provenance.jsonl",
        runtime_control_config_path=runtime_path,
        control_snapshot_store=tmp_path / "control_snapshots.jsonl",
    )

    strategy = plane.create_generation_strategy(
        actor=Actor(actor_id="operator:alice", role="operator"),
        override_level="standard",
        creative_constraints={
            "genre_blend": ["Pop", "Rock"],
            "mood_arc": ["uplifting", "reflective"],
            "lyrical_boundaries": {
                "max_explicitness": 0.2,
                "blocked_terms": ["hate_speech", "self_harm_instruction"],
                "theme_allowlist": ["resilience"],
            },
            "tempo_window": {"min_bpm": 100, "max_bpm": 120},
            "key_window": {"keys": ["C", "G"], "mode": "major"},
        },
    )

    assert strategy["override"]["tier"] == 2
    assert strategy["control_snapshot_ref"].startswith("ctl-")
    assert strategy["provenance_ref"].startswith("prov-")

    snapshots = GovernanceControlPlane._read_jsonl(tmp_path / "control_snapshots.jsonl", max_entries=None)
    assert snapshots[0]["snapshot_id"] == strategy["control_snapshot_ref"]
    assert "signature" in snapshots[0]

    provenance = GovernanceControlPlane._read_jsonl(tmp_path / "provenance.jsonl", max_entries=None)
    assert provenance[0]["event_type"] == "control_snapshot"
    assert provenance[0]["control_snapshot_ref"] == strategy["control_snapshot_ref"]


def test_create_generation_strategy_blocks_policy_unsafe_constraints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADAAD_GOVERNANCE_HMAC_KEY", "gov-key")
    runtime_path = tmp_path / "control-runtime.json"
    _runtime_policy(runtime_path)

    plane = GovernanceControlPlane(
        action_trail_store=tmp_path / "trail.jsonl",
        runtime_control_config_path=runtime_path,
    )

    with pytest.raises(GovernanceError, match="genre blend is policy-blocked"):
        plane.create_generation_strategy(
            actor=Actor(actor_id="operator:alice", role="operator"),
            creative_constraints={
                "genre_blend": ["nursery", "horror"],
                "mood_arc": ["uplifting"],
                "lyrical_boundaries": {
                    "max_explicitness": 0.2,
                    "blocked_terms": ["hate_speech", "self_harm_instruction"],
                },
                "tempo_window": {"min_bpm": 100, "max_bpm": 120},
                "key_window": {"keys": ["C"], "mode": "major"},
            },
        )
