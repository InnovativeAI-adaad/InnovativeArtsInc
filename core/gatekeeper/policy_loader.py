from __future__ import annotations

from pathlib import Path

from core.gatekeeper.models import PolicyRule


AUTONOMY_DOC_PATH = Path("AUTONOMY.md")
_POLICY_START = "POLICY_START"
_POLICY_END = "POLICY_END"
_EXPECTED_HEADER = "action_id|risk_level|requires_human_ratification|abort_mode"


class PolicyParseError(ValueError):
    """Raised when the AUTONOMY policy section is malformed."""


def _extract_policy_block(doc_text: str) -> str:
    lines = doc_text.splitlines()
    start_lines = [idx for idx, line in enumerate(lines) if line.strip() == _POLICY_START]
    end_lines = [idx for idx, line in enumerate(lines) if line.strip() == _POLICY_END]

    if len(start_lines) != 1 or len(end_lines) != 1:
        raise PolicyParseError(
            f"Expected exactly one {_POLICY_START}/{_POLICY_END} pair; found start={len(start_lines)}, end={len(end_lines)}."
        )

    start_idx = start_lines[0]
    end_idx = end_lines[0]
    if start_idx >= end_idx:
        raise PolicyParseError(f"{_POLICY_START} must appear before {_POLICY_END}.")

    return "\n".join(lines[start_idx + 1 : end_idx]).strip()


def _parse_bool(value: str, line_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise PolicyParseError(
        f"Line {line_number}: requires_human_ratification must be 'true' or 'false', got '{value}'."
    )


def parse_policy_rules(doc_text: str) -> dict[str, PolicyRule]:
    block = _extract_policy_block(doc_text)
    lines = [line.strip() for line in block.splitlines() if line.strip() and not line.strip().startswith("#")]

    if not lines:
        raise PolicyParseError("Policy block is empty.")
    if lines[0] != _EXPECTED_HEADER:
        raise PolicyParseError(
            "Policy header mismatch. Expected "
            f"'{_EXPECTED_HEADER}', got '{lines[0]}'."
        )

    policy: dict[str, PolicyRule] = {}
    for idx, line in enumerate(lines[1:], start=2):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            raise PolicyParseError(
                f"Line {idx}: expected 4 pipe-delimited fields, got {len(parts)} in '{line}'."
            )

        action_id, risk_level, requires_human_raw, abort_mode = parts
        rule = PolicyRule(
            action_id=action_id,
            risk_level=risk_level,
            requires_human_ratification=_parse_bool(requires_human_raw, idx),
            abort_mode=abort_mode,
        )

        if rule.action_id in policy:
            raise PolicyParseError(f"Line {idx}: duplicate action_id '{rule.action_id}'.")
        policy[rule.action_id] = rule

    if not policy:
        raise PolicyParseError("Policy block must include at least one rule entry.")
    return policy


def load_policy(autonomy_doc_path: Path = AUTONOMY_DOC_PATH) -> dict[str, PolicyRule]:
    if not autonomy_doc_path.exists():
        raise FileNotFoundError(f"AUTONOMY policy document not found: {autonomy_doc_path}")
    return parse_policy_rules(autonomy_doc_path.read_text(encoding="utf-8"))
