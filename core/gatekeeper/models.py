from __future__ import annotations

from dataclasses import dataclass


_ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
_ALLOWED_ABORT_MODES = {"continue", "quarantine", "hard_stop"}


@dataclass(frozen=True)
class PolicyRule:
    action_id: str
    risk_level: str
    requires_human_ratification: bool
    abort_mode: str

    def __post_init__(self) -> None:
        normalized_action_id = self.action_id.strip()
        if not normalized_action_id:
            raise ValueError("action_id must be a non-empty string")
        object.__setattr__(self, "action_id", normalized_action_id)

        normalized_risk = self.risk_level.strip().lower()
        if normalized_risk not in _ALLOWED_RISK_LEVELS:
            raise ValueError(
                f"risk_level must be one of {sorted(_ALLOWED_RISK_LEVELS)}, got '{self.risk_level}'"
            )
        object.__setattr__(self, "risk_level", normalized_risk)

        normalized_abort_mode = self.abort_mode.strip().lower()
        if normalized_abort_mode not in _ALLOWED_ABORT_MODES:
            raise ValueError(
                f"abort_mode must be one of {sorted(_ALLOWED_ABORT_MODES)}, got '{self.abort_mode}'"
            )
        object.__setattr__(self, "abort_mode", normalized_abort_mode)
