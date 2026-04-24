from __future__ import annotations

from pathlib import Path

import pytest

from core.gatekeeper.policy_loader import PolicyParseError, load_policy, parse_policy_rules


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_policy_rules_accepts_valid_fixture() -> None:
    data = (FIXTURE_DIR / "policy_valid.md").read_text(encoding="utf-8")
    policy = parse_policy_rules(data)

    assert set(policy) == {"read_repo", "merge_pr_main"}
    assert policy["read_repo"].risk_level == "low"
    assert policy["merge_pr_main"].requires_human_ratification is True


def test_parse_policy_rules_rejects_missing_fields() -> None:
    data = (FIXTURE_DIR / "policy_invalid_missing_field.md").read_text(encoding="utf-8")

    with pytest.raises(PolicyParseError, match="expected 4 pipe-delimited fields"):
        parse_policy_rules(data)


def test_parse_policy_rules_rejects_bad_boolean() -> None:
    data = (FIXTURE_DIR / "policy_invalid_bad_boolean.md").read_text(encoding="utf-8")

    with pytest.raises(PolicyParseError, match="must be 'true' or 'false'"):
        parse_policy_rules(data)


def test_load_policy_reads_autonomy_doc() -> None:
    policy = load_policy()

    assert "read_repo" in policy
    assert "merge_pr_main" in policy
