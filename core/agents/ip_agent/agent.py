"""IPAgent baseline implementation with ADAAD-required agent signatures."""

from __future__ import annotations

from core.agents.execution_policy import execute_with_retry_policy
from core.agents.ip_agent.hasher import generate_provenance_entry


_DEF_NAME = "ip_agent"


def info() -> dict:
    return {
        "name": _DEF_NAME,
        "version": "0.2.0",
        "description": "Generates provenance metadata for creative assets.",
    }


def _run_once(payload: dict) -> dict:
    file_path = payload.get("file_path")
    asset_type = payload.get("asset_type", "unknown")
    if not file_path:
        return {"ok": False, "error": "file_path is required"}
    return {"ok": True, "entry": generate_provenance_entry(file_path, asset_type)}


def run(input=None) -> dict:
    payload = input or {}
    if payload.get("policy_control", True):
        return execute_with_retry_policy(
            agent_name="IPAgent",
            job_payload=payload,
            runner=_run_once,
        )
    try:
        return _run_once(payload)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "file_path": payload.get("file_path")}


def mutate(src: str) -> str:
    return src


def score(output: dict) -> float:
    if output.get("ok") and output.get("status") in {"completed", None}:
        return 1.0
    return 0.0
