from __future__ import annotations

import hmac
from hashlib import sha256

from core.gatekeeper.entry_gate import enforce_gate


def _auth_sig(key: str, actor_id: str, role: str, scopes: str, issued_at: str) -> str:
    payload = f"actor_id={actor_id}\nrole={role}\nscopes={scopes}\nissued_at={issued_at}\n".encode()
    return hmac.new(key.encode(), payload, sha256).hexdigest()


def _rat_sig(key: str, ratifier_id: str, ratified_at: str, scope: str) -> str:
    payload = f"ratifier_id={ratifier_id}\nratified_at={ratified_at}\nscope={scope}\n".encode()
    return hmac.new(key.encode(), payload, sha256).hexdigest()


def test_enforce_gate_denies_invalid_authorization(monkeypatch) -> None:
    monkeypatch.setenv("ADAAD_AUTHORIZATION_HMAC_KEY", "auth")
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", "rat")
    decision = enforce_gate("deploy_production", "actor", {"ratification": {}})
    assert decision["allowed"] is False
    assert decision["reason_code"] == "AUTHORIZATION_DENIED"


def test_enforce_gate_allows_with_valid_payload(monkeypatch) -> None:
    monkeypatch.setenv("ADAAD_AUTHORIZATION_HMAC_KEY", "auth")
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", "rat")
    scope = "run_autonomous_media_job"
    issued_at = "2026-04-20T10:01:00+00:00"
    ratified_at = "2026-04-20T10:00:00+00:00"
    decision = enforce_gate(
        scope,
        "runner",
        {
            "authorization": {
                "actor_id": "reviewer:bob",
                "role": "reviewer",
                "scopes": scope,
                "issued_at": issued_at,
                "signature": _auth_sig("auth", "reviewer:bob", "reviewer", scope, issued_at),
            },
            "ratification": {
                "human_ratified": True,
                "ratifier_id": "owner:alice",
                "ratified_at": ratified_at,
                "scope": scope,
                "signature": _rat_sig("rat", "owner:alice", ratified_at, scope),
            },
        },
    )
    assert decision["allowed"] is True
    assert decision["reason_code"] == "ALLOW"
