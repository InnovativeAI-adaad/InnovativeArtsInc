from __future__ import annotations

import json
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
