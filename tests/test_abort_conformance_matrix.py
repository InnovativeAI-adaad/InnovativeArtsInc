from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agents.execution_policy import execute_with_retry_policy
from core.agents.ip_agent import agent as ip_agent
from core.agents.ip_agent.hasher import append_provenance_entries
from core.gatekeeper.abort import HardAbortError


REQUIRED_FIELDS = {"policy_version", "action_id", "reason_code", "correlation_id"}


@pytest.mark.parametrize(
    ("name", "invoke", "expected_action_id", "reason_code", "raises"),
    [
        (
            "denied_production_render",
            lambda log_path, reason_code: execute_with_retry_policy(
                agent_name="MediaAgent",
                job_payload={
                    "job_id": "job-denied-render",
                    "policy_version": "1.0.0",
                    "deny_level3_action": True,
                    "deny_reason_code": reason_code,
                    "provenance_id": "prov-render-001",
                    "agent_log_path": str(log_path),
                },
                runner=lambda payload: {"ok": True},
            ),
            "level3.production_render",
            "L3_RENDER_POLICY_DENIED",
            True,
        ),
        (
            "denied_registry_write",
            lambda log_path, reason_code: append_provenance_entries(
                [],
                job_id="job-denied-registry",
                track_id="track-1",
                agent="ip_agent",
                deny_reason_code=reason_code,
                policy_version="1.0.0",
                correlation_id="prov-registry-001",
                agent_log_path=str(log_path),
            ),
            "level3.registry_write",
            "L3_REGISTRY_WRITE_DENIED",
            True,
        ),
        (
            "denied_legal_registry_write",
            lambda log_path, reason_code: ip_agent.run(
                {
                    "job_id": "job-denied-legal",
                    "track_id": "track-denied-legal",
                    "output_files": ["registry/provenance_log.jsonl"],
                    "deny_level3_action": True,
                    "deny_reason_code": reason_code,
                    "policy_version": "1.0.0",
                    "provenance_id": "prov-legal-001",
                    "agent_log_path": str(log_path),
                }
            ),
            "level3.production_render_registry_write",
            "L3_LEGAL_REGISTRY_WRITE_DENIED",
            False,
        ),
    ],
)
def test_abort_conformance_matrix(
    tmp_path: Path,
    name: str,
    invoke,
    expected_action_id: str,
    reason_code: str,
    raises: bool,
) -> None:
    log_path = tmp_path / "AGENT_LOG.md"
    log_path.write_text("# test log\n", encoding="utf-8")

    if raises:
        with pytest.raises(HardAbortError) as exc_info:
            invoke(log_path, reason_code)
        failure = exc_info.value.failure
    else:
        failure = invoke(log_path, reason_code)

    assert failure["ok"] is False, name
    assert failure["status"] == "aborted", name
    assert failure["reason_code"] == reason_code, name
    assert failure["action_id"] == expected_action_id, name

    text = log_path.read_text(encoding="utf-8")
    marker = "### ABORT-EVENT\n```json\n"
    assert marker in text, name
    json_blob = text.split(marker)[-1].split("\n```", 1)[0]
    event = json.loads(json_blob)

    assert REQUIRED_FIELDS.issubset(event.keys()), name
    assert event["policy_version"] == "1.0.0", name
    assert event["action_id"] == expected_action_id, name
    assert event["reason_code"] == reason_code, name
    assert event["correlation_id"], name
