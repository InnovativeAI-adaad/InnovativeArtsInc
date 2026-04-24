from __future__ import annotations

import hmac
import os
from hashlib import sha256

import pytest

from core.gatekeeper.ratification import RatificationValidationError, validate_ratification


def _signature(key: str, ratifier_id: str, ratified_at: str, scope: str) -> str:
    payload = f"ratifier_id={ratifier_id}\nratified_at={ratified_at}\nscope={scope}\n".encode("utf-8")
    return hmac.new(key.encode("utf-8"), payload, sha256).hexdigest()


def _base_entry(scope: str = "deploy_production") -> dict:
    key = os.environ["ADAAD_RATIFICATION_HMAC_KEY"]
    ratifier_id = "owner:alice"
    ratified_at = "2026-04-20T10:00:00+00:00"
    return {
        "entry_id": "000123",
        "human_ratified": "true",
        "ratification": {
            "human_ratified": True,
            "ratifier_id": ratifier_id,
            "ratified_at": ratified_at,
            "scope": scope,
            "signature": _signature(key, ratifier_id, ratified_at, scope),
        },
    }


def test_validate_ratification_positive_case(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", "ratification-test-key")
    entry = _base_entry(scope="deploy_production,publish_release")

    validate_ratification(entry, required_scope="deploy_production")


def test_validate_ratification_rejects_missing_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", "ratification-test-key")
    entry = _base_entry()
    del entry["ratification"]["ratifier_id"]

    with pytest.raises(RatificationValidationError):
        validate_ratification(entry, required_scope="deploy_production")


def test_validate_ratification_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", "ratification-test-key")
    entry = _base_entry()
    entry["ratification"]["signature"] = "0" * 64

    with pytest.raises(RatificationValidationError):
        validate_ratification(entry, required_scope="deploy_production")


def test_validate_ratification_rejects_scope_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", "ratification-test-key")
    entry = _base_entry(scope="publish_release")

    with pytest.raises(RatificationValidationError):
        validate_ratification(entry, required_scope="deploy_production")


def test_validate_ratification_rejects_non_true_human_ratified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAAD_RATIFICATION_HMAC_KEY", "ratification-test-key")
    entry = _base_entry()
    entry["ratification"]["human_ratified"] = "true"

    with pytest.raises(RatificationValidationError):
        validate_ratification(entry, required_scope="deploy_production")
