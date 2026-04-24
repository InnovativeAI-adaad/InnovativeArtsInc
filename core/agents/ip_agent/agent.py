"""IPAgent baseline implementation with ADAAD-required agent signatures."""

from __future__ import annotations

from core.agents.ip_agent.hasher import generate_provenance_entry


_DEF_NAME = "ip_agent"


def info() -> dict:
    return {
        "name": _DEF_NAME,
        "version": "0.1.0",
        "description": "Generates provenance metadata for creative assets.",
    }


def run(input=None) -> dict:
    payload = input or {}
    file_path = payload.get("file_path")
    asset_type = payload.get("asset_type", "unknown")
    if not file_path:
        return {"ok": False, "error": "file_path is required"}
    try:
        return {"ok": True, "entry": generate_provenance_entry(file_path, asset_type)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "file_path": file_path}


def mutate(src: str) -> str:
    return src


def score(output: dict) -> float:
    if output.get("ok") and output.get("entry"):
        return 1.0
    return 0.0
