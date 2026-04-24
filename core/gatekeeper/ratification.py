"""Ratification validation for Level 3 agent actions."""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

RATIFICATION_HMAC_KEY_ENV = "ADAAD_RATIFICATION_HMAC_KEY"
REQUIRED_RATIFICATION_FIELDS: tuple[str, ...] = (
    "human_ratified",
    "ratifier_id",
    "ratified_at",
    "signature",
    "scope",
)


class RatificationValidationError(ValueError):
    """Raised when a ratification payload is missing fields or fails validation."""


def _canonical_signature_payload(*, ratifier_id: str, ratified_at: str, scope: str) -> bytes:
    return (
        f"ratifier_id={ratifier_id}\n"
        f"ratified_at={ratified_at}\n"
        f"scope={scope}\n"
    ).encode("utf-8")


def _parse_ratified_at(raw_timestamp: str) -> datetime:
    parsed = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RatificationValidationError("ratified_at must include timezone information")
    return parsed.astimezone(timezone.utc)


def _scope_allows(scope: str, required_scope: str) -> bool:
    if scope == "*":
        return True
    scopes = [part.strip() for part in scope.split(",") if part.strip()]
    return required_scope in scopes


def _require_hmac_key() -> bytes:
    key = os.getenv(RATIFICATION_HMAC_KEY_ENV)
    if not key:
        raise RatificationValidationError(
            f"missing ratification key env var: {RATIFICATION_HMAC_KEY_ENV}"
        )
    return key.encode("utf-8")


def validate_ratification(log_entry: dict[str, Any], required_scope: str) -> None:
    """Validate ratification payload for cryptographic and semantic integrity.

    Fail-closed behavior:
      - missing fields raise RatificationValidationError
      - semantic mismatches raise RatificationValidationError
      - invalid signature raises RatificationValidationError
    """
    ratification = log_entry.get("ratification")
    if not isinstance(ratification, dict):
        raise RatificationValidationError("ratification must be a dict")

    for field in REQUIRED_RATIFICATION_FIELDS:
        value = ratification.get(field)
        if value in (None, ""):
            raise RatificationValidationError(f"missing required ratification field: {field}")

    if ratification["human_ratified"] is not True:
        raise RatificationValidationError("human_ratified must be true")

    ratifier_id = ratification["ratifier_id"]
    if not isinstance(ratifier_id, str) or not ratifier_id.strip():
        raise RatificationValidationError("ratifier_id must be a non-empty string")

    ratified_at = ratification["ratified_at"]
    if not isinstance(ratified_at, str):
        raise RatificationValidationError("ratified_at must be an ISO-8601 string")
    ratified_at_dt = _parse_ratified_at(ratified_at)
    if ratified_at_dt > datetime.now(timezone.utc):
        raise RatificationValidationError("ratified_at cannot be in the future")

    scope = ratification["scope"]
    if not isinstance(scope, str) or not scope.strip():
        raise RatificationValidationError("scope must be a non-empty string")
    if not _scope_allows(scope, required_scope):
        raise RatificationValidationError(
            f"ratification scope does not include required scope: {required_scope}"
        )

    signature = ratification["signature"]
    if not isinstance(signature, str) or len(signature) != 64:
        raise RatificationValidationError("signature must be a 64-char hex digest")

    computed = hmac.new(
        _require_hmac_key(),
        _canonical_signature_payload(ratifier_id=ratifier_id, ratified_at=ratified_at, scope=scope),
        sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, signature):
        raise RatificationValidationError("ratification signature verification failed")
