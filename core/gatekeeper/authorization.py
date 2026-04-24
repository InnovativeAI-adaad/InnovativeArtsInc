"""Scoped authorization validation for sensitive agent actions."""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

AUTHORIZATION_HMAC_KEY_ENV = "ADAAD_AUTHORIZATION_HMAC_KEY"
REQUIRED_AUTHORIZATION_FIELDS: tuple[str, ...] = (
    "actor_id",
    "role",
    "scopes",
    "issued_at",
    "signature",
)


class AuthorizationValidationError(ValueError):
    """Raised when an authorization payload is malformed or invalid."""


def _canonical_signature_payload(*, actor_id: str, role: str, scopes: str, issued_at: str) -> bytes:
    return (
        f"actor_id={actor_id}\n"
        f"role={role}\n"
        f"scopes={scopes}\n"
        f"issued_at={issued_at}\n"
    ).encode("utf-8")


def _parse_issued_at(raw_timestamp: str) -> datetime:
    parsed = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise AuthorizationValidationError("issued_at must include timezone information")
    return parsed.astimezone(timezone.utc)


def _scope_allows(scope_blob: str, required_scope: str) -> bool:
    scopes = [part.strip() for part in scope_blob.split(",") if part.strip()]
    return "*" in scopes or required_scope in scopes


def _require_hmac_key() -> bytes:
    key = os.getenv(AUTHORIZATION_HMAC_KEY_ENV)
    if not key:
        raise AuthorizationValidationError(
            f"missing authorization key env var: {AUTHORIZATION_HMAC_KEY_ENV}"
        )
    return key.encode("utf-8")


def validate_scoped_authorization(log_entry: dict[str, Any], required_scope: str) -> None:
    authorization = log_entry.get("authorization")
    if not isinstance(authorization, dict):
        raise AuthorizationValidationError("authorization must be a dict")

    for field in REQUIRED_AUTHORIZATION_FIELDS:
        value = authorization.get(field)
        if value in (None, ""):
            raise AuthorizationValidationError(f"missing required authorization field: {field}")

    actor_id = authorization["actor_id"]
    role = authorization["role"]
    scopes = authorization["scopes"]
    issued_at = authorization["issued_at"]
    signature = authorization["signature"]

    if not isinstance(actor_id, str) or not actor_id.strip():
        raise AuthorizationValidationError("actor_id must be a non-empty string")
    if not isinstance(role, str) or not role.strip():
        raise AuthorizationValidationError("role must be a non-empty string")
    if not isinstance(scopes, str) or not scopes.strip():
        raise AuthorizationValidationError("scopes must be a non-empty CSV string")
    if not isinstance(issued_at, str):
        raise AuthorizationValidationError("issued_at must be an ISO-8601 string")

    issued_at_dt = _parse_issued_at(issued_at)
    if issued_at_dt > datetime.now(timezone.utc):
        raise AuthorizationValidationError("issued_at cannot be in the future")

    if not _scope_allows(scopes, required_scope):
        raise AuthorizationValidationError(
            f"authorization scopes do not include required scope: {required_scope}"
        )

    if not isinstance(signature, str) or len(signature) != 64:
        raise AuthorizationValidationError("signature must be a 64-char hex digest")

    computed = hmac.new(
        _require_hmac_key(),
        _canonical_signature_payload(actor_id=actor_id, role=role, scopes=scopes, issued_at=issued_at),
        sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, signature):
        raise AuthorizationValidationError("authorization signature verification failed")
