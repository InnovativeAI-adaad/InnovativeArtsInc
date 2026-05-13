"""Governance authorization and decision artifacts for autonomous media stages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.gatekeeper.authorization import (
    AuthorizationValidationError,
    validate_scoped_authorization,
)
from core.gatekeeper.ratification import RatificationValidationError, validate_ratification

MEDIA_ACTION_POLICY_PATH = Path("projects/jrt/metadata/media_action_policy.json")


class MediaGovernanceError(RuntimeError):
    """Raised when a media stage is blocked by governance policy."""


@dataclass(frozen=True)
class GovernanceDecision:
    decision_id: str
    stage: str
    action_id: str
    decision: str
    artifact_path: Path
    artifact_sha256: str

    def as_provenance_ref(self, repo_root: Path) -> dict[str, str]:
        return {
            "ref_type": "governance_decision",
            "ref_id": self.decision_id,
            "uri": str(self.artifact_path.relative_to(repo_root)),
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_media_action_policy(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    path = root / MEDIA_ACTION_POLICY_PATH
    if not path.exists():
        fallback = Path.cwd() / MEDIA_ACTION_POLICY_PATH
        if fallback.exists():
            path = fallback
        else:
            raise MediaGovernanceError(f"media action policy not found: {path}")
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MediaGovernanceError(f"media action policy is malformed JSON: {path}") from exc
    if not isinstance(policy.get("stages"), dict):
        raise MediaGovernanceError("media action policy must define a stages object")
    return policy


def authorize_media_stage(
    *,
    repo_root: str | Path,
    job_id: str,
    stage: str,
    actor: str,
    authorization: dict[str, Any] | None = None,
    ratification: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> GovernanceDecision:
    """Authorize a media stage and emit a hash-linked allow/block artifact.

    Level 1/2 stages are allowed after policy classification. Level 3 or explicitly
    ratified stages fail closed unless scoped authorization and HUMAN-0 ratification
    validate through the shared gatekeeper modules.
    """
    root = Path(repo_root)
    policy = load_media_action_policy(root)
    stage_policy = policy["stages"].get(stage)

    errors: list[str] = []
    if not isinstance(stage_policy, dict):
        stage_policy = {
            "action_id": "unclassified",
            "operation": stage,
            "tier": 3,
            "required_scope": stage,
            "elevated_action": True,
            "requires_human_ratification": True,
            "rationale": "Unclassified media stages fail closed under GOVERNANCE.md.",
        }
        errors.append("TIER_UNCLASSIFIED")

    required_scope = str(
        stage_policy.get("required_scope") or stage_policy.get("action_id") or stage
    )
    tier = int(stage_policy.get("tier", 3))
    requires_human = bool(stage_policy.get("requires_human_ratification") or tier >= 3)

    if requires_human:
        validation_payload = {
            "action": stage_policy.get("action_id"),
            "tier": tier,
            "required_scope": required_scope,
            "authorization": authorization,
            "ratification": ratification,
        }
        try:
            validate_ratification(validation_payload, required_scope=required_scope)
        except RatificationValidationError as exc:
            errors.append(f"ratification validation failed: {exc}")
        try:
            validate_scoped_authorization(validation_payload, required_scope=required_scope)
        except AuthorizationValidationError as exc:
            errors.append(f"authorization validation failed: {exc}")

    decision = "blocked" if errors else "allowed"
    artifact_path, artifact_sha = _write_decision_artifact(
        repo_root=root,
        policy=policy,
        job_id=job_id,
        stage=stage,
        actor=actor,
        stage_policy=stage_policy,
        decision=decision,
        errors=errors,
        metadata=metadata or {},
    )
    governance_decision = GovernanceDecision(
        decision_id=artifact_path.stem,
        stage=stage,
        action_id=str(stage_policy.get("action_id", "unclassified")),
        decision=decision,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha,
    )
    if errors:
        raise MediaGovernanceError(
            f"media stage {stage!r} blocked by governance: {'; '.join(errors)}; "
            f"decision_ref={governance_decision.decision_id}"
        )
    return governance_decision


def _write_decision_artifact(
    *,
    repo_root: Path,
    policy: dict[str, Any],
    job_id: str,
    stage: str,
    actor: str,
    stage_policy: dict[str, Any],
    decision: str,
    errors: list[str],
    metadata: dict[str, Any],
) -> tuple[Path, str]:
    artifact_config = policy.get("decision_artifact", {})
    artifact_dir = repo_root / artifact_config.get(
        "directory", "projects/jrt/metadata/governance_decisions"
    )
    chain_head_path = repo_root / artifact_config.get(
        "chain_head", "projects/jrt/metadata/governance_decisions/chain_head.json"
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    previous_sha: str | None = None
    if chain_head_path.exists():
        try:
            chain_head = json.loads(chain_head_path.read_text(encoding="utf-8"))
            previous_sha = chain_head.get("artifact_sha256")
        except json.JSONDecodeError:
            previous_sha = None

    decision_id = f"govdec-{uuid4().hex[:12]}"
    artifact = {
        "schema_version": "1.0.0",
        "decision_id": decision_id,
        "policy_id": policy.get("policy_id"),
        "policy_version": policy.get("schema_version"),
        "job_id": job_id,
        "stage": stage,
        "action_id": stage_policy.get("action_id"),
        "operation": stage_policy.get("operation"),
        "tier": stage_policy.get("tier"),
        "required_scope": stage_policy.get("required_scope"),
        "elevated_action": bool(stage_policy.get("elevated_action")),
        "requires_human_ratification": bool(stage_policy.get("requires_human_ratification")),
        "decision": decision,
        "errors": errors,
        "actor": actor,
        "decided_at": _utc_now_iso(),
        "rationale": stage_policy.get("rationale"),
        "metadata": metadata,
        "previous_decision_sha256": previous_sha,
    }
    artifact_sha = _canonical_sha256(artifact)
    artifact["artifact_sha256"] = artifact_sha

    artifact_path = artifact_dir / f"{decision_id}.json"
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    chain_head_path.write_text(
        json.dumps(
            {
                "decision_id": decision_id,
                "artifact_sha256": artifact_sha,
                "updated_at": artifact["decided_at"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact_path, artifact_sha
