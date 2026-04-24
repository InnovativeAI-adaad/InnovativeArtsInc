from __future__ import annotations

import hmac
import json
from hashlib import sha256
from pathlib import Path

from core.agents.execution_policy import execute_with_retry_policy


def _write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "retry_policy": {"max_attempts": 3, "backoff_seconds": [0, 0, 0]},
                "failure_classes": {
                    "transient": ["TimeoutError"],
                    "deterministic": ["ValueError"],
                },
            }
        ),
        encoding="utf-8",
    )


def _authorization_signature(key: str, actor_id: str, role: str, scopes: str, issued_at: str) -> str:
    payload = (
        f"actor_id={actor_id}\n"
        f"role={role}\n"
        f"scopes={scopes}\n"
        f"issued_at={issued_at}\n"
    ).encode("utf-8")
    return hmac.new(key.encode("utf-8"), payload, sha256).hexdigest()


def test_quarantine_creates_incident_and_repair_lineage(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    _write_config(config)

    def failing_runner(payload: dict) -> dict:
        raise TimeoutError("network blip")

    result = execute_with_retry_policy(
        agent_name="MutationAgent",
        job_payload={"job_id": "job-1", "mutation_intensity": 4},
        runner=failing_runner,
        config_path=config,
        sleep_fn=lambda _: None,
        incident_dir=tmp_path / "incidents",
    )

    assert result["status"] == "quarantine"
    assert result["repair"]["lineage"]["repaired_from_attempt_id"] is not None
    assert result["repair"]["parameters"]["mutation_intensity"] == 3

    incident_path = Path(result["incident_path"])
    assert incident_path.exists()
    incident = json.loads(incident_path.read_text(encoding="utf-8"))
    assert incident["status"] == "quarantine"
    assert incident["repair"]["lineage"]["all_failed_attempt_ids"]


def test_media_agent_repair_hook_defaults(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    _write_config(config)

    def bad_runner(payload: dict) -> dict:
        raise TimeoutError("downstream")

    result = execute_with_retry_policy(
        agent_name="MediaAgent",
        job_payload={"job_id": "job-2", "max_parallel": 8},
        runner=bad_runner,
        config_path=config,
        sleep_fn=lambda _: None,
        incident_dir=tmp_path / "incidents",
    )

    assert result["status"] == "quarantine"
    assert result["repair"]["parameters"]["max_parallel"] == 1
    assert result["repair"]["parameters"]["transcode_profile"] == "safe_fallback"


def test_level_3_action_requires_valid_ratification(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config.json"
    _write_config(config)
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", "ratify-key")
    monkeypatch.setenv("ADAAD_AUTHORIZATION_HMAC_KEY", "auth-key")

    runner_calls = {"count": 0}

    def guarded_runner(payload: dict) -> dict:
        runner_calls["count"] += 1
        return {"ok": True}

    result = execute_with_retry_policy(
        agent_name="ReleaseAgent",
        job_payload={"job_id": "job-3", "action": "deploy_production", "tier": 3},
        runner=guarded_runner,
        config_path=config,
        sleep_fn=lambda _: None,
        incident_dir=tmp_path / "incidents",
    )

    assert result["status"] == "quarantine"
    assert runner_calls["count"] == 0
    assert "ratification validation failed" in result["attempts"][0]["error"]


def test_level_3_action_requires_valid_authorization(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config.json"
    _write_config(config)

    ratify_key = "ratify-key"
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", ratify_key)
    monkeypatch.setenv("ADAAD_AUTHORIZATION_HMAC_KEY", "auth-key")

    ratifier_id = "owner:alice"
    ratified_at = "2026-04-20T10:00:00+00:00"
    scope = "deploy_production"
    rat_sig_payload = (
        f"ratifier_id={ratifier_id}\nratified_at={ratified_at}\nscope={scope}\n".encode("utf-8")
    )
    signature = hmac.new(ratify_key.encode("utf-8"), rat_sig_payload, sha256).hexdigest()

    runner_calls = {"count": 0}

    def guarded_runner(payload: dict) -> dict:
        runner_calls["count"] += 1
        return {"ok": True}

    result = execute_with_retry_policy(
        agent_name="ReleaseAgent",
        job_payload={
            "job_id": "job-auth-missing",
            "action": "deploy_production",
            "tier": "level_3",
            "ratification": {
                "human_ratified": True,
                "ratifier_id": ratifier_id,
                "ratified_at": ratified_at,
                "scope": scope,
                "signature": signature,
            },
        },
        runner=guarded_runner,
        config_path=config,
        sleep_fn=lambda _: None,
        incident_dir=tmp_path / "incidents",
    )

    assert result["status"] == "quarantine"
    assert runner_calls["count"] == 0
    assert "authorization validation failed" in result["attempts"][0]["error"]


def test_level_3_action_with_valid_ratification_and_authorization_runs(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config.json"
    _write_config(config)

    ratify_key = "ratify-key"
    auth_key = "auth-key"
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", ratify_key)
    monkeypatch.setenv("ADAAD_AUTHORIZATION_HMAC_KEY", auth_key)

    ratifier_id = "owner:alice"
    ratified_at = "2026-04-20T10:00:00+00:00"
    scope = "deploy_production"
    rat_sig_payload = f"ratifier_id={ratifier_id}\nratified_at={ratified_at}\nscope={scope}\n".encode("utf-8")
    rat_signature = hmac.new(ratify_key.encode("utf-8"), rat_sig_payload, sha256).hexdigest()

    actor_id = "reviewer:bob"
    role = "reviewer"
    issued_at = "2026-04-20T10:01:00+00:00"
    auth_signature = _authorization_signature(auth_key, actor_id, role, scope, issued_at)

    runner_calls = {"count": 0}

    def guarded_runner(payload: dict) -> dict:
        runner_calls["count"] += 1
        return {"ok": True, "result": "done"}

    result = execute_with_retry_policy(
        agent_name="ReleaseAgent",
        job_payload={
            "job_id": "job-4",
            "action": "deploy_production",
            "tier": "level_3",
            "ratification": {
                "human_ratified": True,
                "ratifier_id": ratifier_id,
                "ratified_at": ratified_at,
                "scope": scope,
                "signature": rat_signature,
            },
            "authorization": {
                "actor_id": actor_id,
                "role": role,
                "scopes": scope,
                "issued_at": issued_at,
                "signature": auth_signature,
            },
        },
        runner=guarded_runner,
        config_path=config,
        sleep_fn=lambda _: None,
        incident_dir=tmp_path / "incidents",
    )

    assert result["ok"] is True
    assert runner_calls["count"] == 1
