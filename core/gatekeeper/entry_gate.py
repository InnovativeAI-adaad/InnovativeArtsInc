"""Shared gate-entry wrapper for authorization and ratification checks."""

from __future__ import annotations

from typing import Any

from core.gatekeeper.authorization import (
    AuthorizationValidationError,
    validate_scoped_authorization,
)
from core.gatekeeper.ratification import (
    RatificationValidationError,
    validate_ratification,
)


def enforce_gate(action_name: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate gate requirements and return a structured allow/deny decision."""
    if not isinstance(action_name, str) or not action_name.strip():
        return {
            "allowed": False,
            "reason_code": "INVALID_ACTION_NAME",
            "message": "action_name must be a non-empty string",
        }
    if not isinstance(actor, str) or not actor.strip():
        return {
            "allowed": False,
            "reason_code": "INVALID_ACTOR",
            "message": "actor must be a non-empty string",
        }
    if not isinstance(payload, dict):
        return {
            "allowed": False,
            "reason_code": "INVALID_PAYLOAD",
            "message": "payload must be a dict",
        }

    gate_payload = dict(payload)
    gate_payload.setdefault("actor", actor)

    try:
        validate_scoped_authorization(gate_payload, required_scope=action_name)
    except AuthorizationValidationError as exc:
        return {
            "allowed": False,
            "reason_code": "AUTHORIZATION_DENIED",
            "message": str(exc),
            "action": action_name,
            "actor": actor,
        }

    try:
        validate_ratification(gate_payload, required_scope=action_name)
    except RatificationValidationError as exc:
        return {
            "allowed": False,
            "reason_code": "RATIFICATION_DENIED",
            "message": str(exc),
            "action": action_name,
            "actor": actor,
        }

    return {"allowed": True, "reason_code": "ALLOW", "action": action_name, "actor": actor}

