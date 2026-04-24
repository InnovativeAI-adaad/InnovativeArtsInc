from __future__ import annotations

from dataclasses import dataclass


HIGH_RISK_OUTREACH_ACTIONS = {
    "bulk_sms",
    "bulk_email",
    "paid_influencer_outreach",
    "cross_border_data_export",
}


@dataclass(frozen=True)
class OutreachAction:
    action_id: str
    channel: str
    risk_score: int
    audience_size: int


@dataclass(frozen=True)
class CompliancePolicy:
    policy_id: str
    required_checks: tuple[str, ...]


class GovernanceGuardrails:
    """High-risk approvals and policy compliance checks for outreach actions."""

    def __init__(self, policy: CompliancePolicy) -> None:
        if not policy.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        self.policy = policy

    def requires_human_approval(self, action: OutreachAction) -> bool:
        return action.action_id in HIGH_RISK_OUTREACH_ACTIONS or action.risk_score >= 80

    def run_policy_checks(self, action: OutreachAction, completed_checks: set[str]) -> dict[str, object]:
        missing = [check for check in self.policy.required_checks if check not in completed_checks]
        is_compliant = not missing and action.audience_size > 0 and action.channel.strip() != ""
        return {
            "policy_id": self.policy.policy_id,
            "action_id": action.action_id,
            "is_compliant": is_compliant,
            "missing_checks": missing,
            "requires_human_approval": self.requires_human_approval(action),
        }

    def evaluate(self, action: OutreachAction, completed_checks: set[str], approved_by_human: bool) -> dict[str, object]:
        report = self.run_policy_checks(action, completed_checks)
        if not report["is_compliant"]:
            return {**report, "status": "blocked", "reason": "policy_non_compliant"}

        if report["requires_human_approval"] and not approved_by_human:
            return {**report, "status": "blocked", "reason": "human_approval_required"}

        return {**report, "status": "approved", "reason": "guardrails_satisfied"}
