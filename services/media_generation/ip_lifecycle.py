"""IPAgent lifecycle gates for WF-005 autonomous media generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from core.agents.ip_agent import agent as ip_agent

DecisionStage = Literal["pre_generation", "post_generation"]


class IPGuardrailBlockedError(RuntimeError):
    """Raised when an IPAgent guardrail blocks lifecycle progression."""

    def __init__(self, *, stage: DecisionStage, artifact_ref: str, reason: str) -> None:
        super().__init__(f"IPAgent {stage} guardrail blocked lifecycle: {reason} ({artifact_ref})")
        self.stage = stage
        self.artifact_ref = artifact_ref
        self.reason = reason


def _relative_ref(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _decision_path(*, project_root: str | Path, stage: DecisionStage, job_id: str) -> Path:
    return Path(project_root) / "projects" / "jrt" / "metadata" / "ip_audits" / stage / f"{job_id}.json"


def _guardrail_from_decision(decision: str) -> str:
    return "pass" if decision == "pass" else "fail"


def _reason_from_audit(*, audit_result: dict[str, Any], stage: DecisionStage) -> str:
    decision = str(audit_result.get("decision", "block"))
    max_similarity = float(audit_result.get("max_similarity", 0.0) or 0.0)
    policy_version = str(audit_result.get("policy_version", "unknown"))
    if decision == "pass":
        return f"{stage} IPAgent audit passed under policy {policy_version}; max_similarity={max_similarity:.6f}"
    return f"{stage} IPAgent audit returned {decision} under policy {policy_version}; max_similarity={max_similarity:.6f}"


def _novelty_metrics_from_audit(audit_result: dict[str, Any]) -> dict[str, Any]:
    artifact = audit_result.get("audit_artifact") or {}
    max_similarity = float(audit_result.get("max_similarity", 0.0) or 0.0)
    return {
        "novelty_score": round(max(0.0, min(1.0, 1.0 - max_similarity)), 6),
        "max_similarity": round(max_similarity, 6),
        "confidence": round(float(audit_result.get("confidence", 0.0) or 0.0), 6),
        "method_results": artifact.get("method_results", []),
        "most_similar_ref": artifact.get("most_similar_ref"),
    }


def _write_normalized_decision(
    *,
    project_root: str | Path,
    stage: DecisionStage,
    job_id: str,
    audit_result: dict[str, Any],
) -> dict[str, Any]:
    root = Path(project_root)
    path = _decision_path(project_root=root, stage=stage, job_id=job_id)
    artifact_ref = _relative_ref(path, root)
    decision = str(audit_result.get("decision", "block"))
    normalized = {
        "decision_artifact_ref": artifact_ref,
        "novelty_metrics": _novelty_metrics_from_audit(audit_result),
        "guardrail_pass_fail": _guardrail_from_decision(decision),
        "policy_version": str(audit_result.get("policy_version", "unknown")),
        "reason": _reason_from_audit(audit_result=audit_result, stage=stage),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return normalized


def _require_pass(decision: dict[str, Any], *, stage: DecisionStage) -> None:
    if decision.get("guardrail_pass_fail") != "pass":
        raise IPGuardrailBlockedError(
            stage=stage,
            artifact_ref=str(decision.get("decision_artifact_ref")),
            reason=str(decision.get("reason", "guardrail failed")),
        )


def _pre_generation_candidate_metadata(
    *,
    prompt: str,
    style_profile: str | dict[str, Any],
    seed: int | str,
    length: int,
    tempo: int | None = None,
    key: str | None = None,
    provenance_refs: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "lifecycle_stage": "pre_generation",
        "prompt": prompt,
        "style_profile": style_profile,
        "seed": seed,
        "length": length,
        "tempo": tempo,
        "key": key,
        "provenance_refs": provenance_refs or [],
    }


def run_pre_generation_uniqueness_gate(
    *,
    project_root: str | Path,
    job_id: str,
    track_id: str,
    prompt: str,
    style_profile: str | dict[str, Any],
    seed: int | str,
    length: int,
    tempo: int | None = None,
    key: str | None = None,
    provenance_refs: list[Any] | None = None,
    provenance_log_path: str | Path | None = None,
    similarity_policy_path: str | Path | None = None,
    block_on_fail: bool = True,
) -> dict[str, Any]:
    """Run the pre-generation uniqueness strategy gate and persist its decision."""
    root = Path(project_root)
    audit_result = ip_agent.run_similarity_audit(
        {
            "job_id": job_id,
            "track_id": track_id,
            "render_metadata": _pre_generation_candidate_metadata(
                prompt=prompt,
                style_profile=style_profile,
                seed=seed,
                length=length,
                tempo=tempo,
                key=key,
                provenance_refs=provenance_refs,
            ),
            "provenance_log_path": str(provenance_log_path or (root / "registry" / "provenance_log.jsonl")),
            **({"similarity_policy_path": str(similarity_policy_path)} if similarity_policy_path else {}),
        }
    )
    decision = _write_normalized_decision(
        project_root=root,
        stage="pre_generation",
        job_id=job_id,
        audit_result=audit_result,
    )
    if block_on_fail:
        _require_pass(decision, stage="pre_generation")
    return decision


def audio_fingerprint_for_path(audio_path: str | Path) -> dict[str, Any]:
    """Return a deterministic fingerprint payload for a generated audio artifact."""
    path = Path(audio_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "algorithm": "sha256-bytes-v1",
        "sha256": digest,
        "byte_length": path.stat().st_size,
    }


def run_post_generation_similarity_audit(
    *,
    project_root: str | Path,
    job_id: str,
    track_id: str,
    render_metadata: dict[str, Any],
    audio_fingerprint: dict[str, Any] | str,
    provenance_refs: list[Any],
    provenance_log_path: str | Path | None = None,
    similarity_policy_path: str | Path | None = None,
    block_on_fail: bool = True,
) -> dict[str, Any]:
    """Run the post-generation similarity audit and persist its normalized decision."""
    root = Path(project_root)
    audit_result = ip_agent.run_similarity_audit(
        {
            "job_id": job_id,
            "track_id": track_id,
            "render_metadata": render_metadata,
            "audio_fingerprint": audio_fingerprint,
            "exclude_job_id": job_id,
            "exclude_track_id": track_id,
            "exclude_provider_generation_id": render_metadata.get("provider_generation_id"),
            "provenance_refs": provenance_refs,
            "provenance_log_path": str(provenance_log_path or (root / "registry" / "provenance_log.jsonl")),
            **({"similarity_policy_path": str(similarity_policy_path)} if similarity_policy_path else {}),
        }
    )
    decision = _write_normalized_decision(
        project_root=root,
        stage="post_generation",
        job_id=job_id,
        audit_result=audit_result,
    )
    if block_on_fail:
        _require_pass(decision, stage="post_generation")
    return decision


def decision_provenance_ref(decision: dict[str, Any], *, ref_type: str) -> dict[str, str]:
    """Convert a normalized IP decision artifact into a media-job provenance ref."""
    ref = str(decision["decision_artifact_ref"])
    return {
        "ref_type": ref_type,
        "ref_id": ref,
        "uri": ref,
    }
