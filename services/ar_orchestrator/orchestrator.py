from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.gatekeeper.ratification import RatificationValidationError, validate_ratification

DECISION_REJECT = "reject"
DECISION_REVISE = "revise"
DECISION_ESCALATE_TO_HUMAN = "escalate_to_human"
DECISION_APPROVE_FOR_RELEASE_PREP = "approve_for_release_prep"

REQUIRED_INGEST_FIELDS: tuple[str, ...] = (
    "audio_demo_url",
    "artist_profile",
    "campaign_context",
)


@dataclass(frozen=True)
class DecisionContext:
    job_id: str
    features: dict[str, float]
    novelty_score: float
    risk_score: float
    confidence_score: float


class AROrchestratorError(ValueError):
    """Raised for fail-closed orchestration failures."""


class AROrchestrator:
    """Demo ingestion, extraction, scoring, policy, and provenance emission."""

    def __init__(
        self,
        *,
        registry_dir: Path = Path("registry"),
        queue_path: Path = Path("registry/ar_demo_queue.jsonl"),
    ) -> None:
        self.registry_dir = registry_dir
        self.queue_path = queue_path
        self.artifact_path = registry_dir / "ar_demo_decisions.jsonl"
        self.provenance_log_path = registry_dir / "provenance_log.jsonl"
        self.dead_letter_path = registry_dir / "ar_demo_queue_failed.jsonl"

    def ingest_demo_endpoint(self, payload: dict[str, Any]) -> dict[str, Any]:
        for field in REQUIRED_INGEST_FIELDS:
            value = payload.get(field)
            if value in (None, ""):
                raise AROrchestratorError(f"missing required ingest field: {field}")

        job = {
            "job_id": payload.get("job_id") or f"demo-{uuid4().hex}",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "audio_demo_url": payload["audio_demo_url"],
            "artist_profile": payload["artist_profile"],
            "campaign_context": payload["campaign_context"],
            "ratification": payload.get("ratification"),
        }
        self._append_jsonl(self.queue_path, job)
        return {"ok": True, "job_id": job["job_id"], "queue_path": str(self.queue_path)}

    def consume_queue(self) -> dict[str, Any]:
        if not self.queue_path.exists():
            return {"artifacts": [], "failure_summary": {"count": 0, "jobs": []}}

        artifacts: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        remaining_lines: list[str] = []

        with self.queue_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                stripped_line = raw_line.strip()
                if not stripped_line:
                    continue

                job: dict[str, Any] | None = None
                try:
                    job = json.loads(stripped_line)
                    artifacts.append(self.process_demo(job))
                except Exception as exc:  # noqa: BLE001 - fail-open queue consumption by line
                    remaining_lines.append(stripped_line)
                    failure_entry = {
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                        "line_number": line_number,
                        "job_id": str(job.get("job_id", "unknown")) if isinstance(job, dict) else "unknown",
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                        "raw_job": stripped_line,
                    }
                    failures.append(failure_entry)
                    self._append_jsonl(self.dead_letter_path, failure_entry)

        self._atomic_rewrite_queue(remaining_lines)
        return {"artifacts": artifacts, "failure_summary": {"count": len(failures), "jobs": failures}}

    def process_demo(self, job: dict[str, Any]) -> dict[str, Any]:
        features = self.extract_features(job)
        novelty_score, risk_score, confidence_score = self.score_novelty_risk(features)
        context = DecisionContext(
            job_id=job["job_id"],
            features=features,
            novelty_score=novelty_score,
            risk_score=risk_score,
            confidence_score=confidence_score,
        )

        decision, reasons = self.apply_decision_policy(context)
        if decision == DECISION_APPROVE_FOR_RELEASE_PREP:
            self._require_signing_ratification(job)

        artifact = self._build_artifact(job=job, context=context, decision=decision, reasons=reasons)
        provenance_ref = self._write_artifact_and_provenance(artifact)
        artifact["immutable_provenance_ref"] = provenance_ref
        return artifact

    def extract_features(self, job: dict[str, Any]) -> dict[str, float]:
        artist_profile = job.get("artist_profile")
        campaign_context = job.get("campaign_context")

        if not isinstance(artist_profile, dict) or not isinstance(campaign_context, dict):
            raise AROrchestratorError("artist_profile and campaign_context must be objects")

        required_artist_fields = ("genre", "audience_size", "brand_safety_tier")
        required_campaign_fields = ("goal", "region", "budget_tier")
        for field in required_artist_fields:
            if artist_profile.get(field) in (None, ""):
                raise AROrchestratorError(f"missing artist_profile metadata: {field}")
        for field in required_campaign_fields:
            if campaign_context.get(field) in (None, ""):
                raise AROrchestratorError(f"missing campaign_context metadata: {field}")

        audio_url = str(job.get("audio_demo_url", ""))
        if not audio_url:
            raise AROrchestratorError("missing audio_demo_url")

        audio_seed = int(sha256(audio_url.encode("utf-8")).hexdigest()[:8], 16)
        metadata_seed = int(
            sha256(json.dumps({"artist": artist_profile, "campaign": campaign_context}, sort_keys=True).encode("utf-8")).hexdigest()[:8],
            16,
        )

        return {
            "audio_vector": (audio_seed % 1000) / 1000,
            "metadata_vector": (metadata_seed % 1000) / 1000,
            "brand_safety_factor": 1.0 if artist_profile["brand_safety_tier"] == "strict" else 0.65,
            "campaign_budget_factor": 0.9 if campaign_context["budget_tier"] == "high" else 0.6,
        }

    def score_novelty_risk(self, features: dict[str, float]) -> tuple[float, float, float]:
        novelty = round((features["audio_vector"] * 0.7) + (features["metadata_vector"] * 0.3), 4)
        risk = round(1 - ((features["brand_safety_factor"] * 0.6) + (features["campaign_budget_factor"] * 0.4)), 4)
        confidence = round(abs(features["audio_vector"] - features["metadata_vector"]), 4)
        return novelty, risk, confidence

    def apply_decision_policy(self, context: DecisionContext) -> tuple[str, list[str]]:
        reasons: list[str] = []

        if context.confidence_score < 0.15:
            reasons.append("low-confidence predictions require manual handling")
            return DECISION_ESCALATE_TO_HUMAN, reasons

        if context.risk_score >= 0.55:
            reasons.append("risk score is above hard threshold")
            return DECISION_REJECT, reasons

        if context.novelty_score < 0.35:
            reasons.append("novelty score below release threshold")
            return DECISION_REVISE, reasons

        reasons.append("scores satisfy release preparation constraints")
        return DECISION_APPROVE_FOR_RELEASE_PREP, reasons

    def _require_signing_ratification(self, job: dict[str, Any]) -> None:
        try:
            validate_ratification(job, required_scope="release_signoff")
        except RatificationValidationError as exc:
            raise AROrchestratorError(f"release sign-off requires valid ratification: {exc}") from exc

    def _build_artifact(
        self,
        *,
        job: dict[str, Any],
        context: DecisionContext,
        decision: str,
        reasons: list[str],
    ) -> dict[str, Any]:
        return {
            "artifact_id": f"ar-artifact-{uuid4().hex}",
            "job_id": context.job_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input": {
                "audio_demo_url": job["audio_demo_url"],
                "artist_profile": job["artist_profile"],
                "campaign_context": job["campaign_context"],
            },
            "feature_vectors": context.features,
            "score_breakdown": {
                "novelty_score": context.novelty_score,
                "risk_score": context.risk_score,
                "confidence_score": context.confidence_score,
            },
            "decision": decision,
            "reasons": reasons,
            "provenance": {
                "policy_version": "ar_orchestrator/1.0.0",
                "ratification_required_for_signing": decision == DECISION_APPROVE_FOR_RELEASE_PREP,
            },
        }

    def _write_artifact_and_provenance(self, artifact: dict[str, Any]) -> str:
        canonical_artifact = json.dumps(artifact, sort_keys=True, separators=(",", ":"))
        immutable_ref = f"prov:{sha256(canonical_artifact.encode('utf-8')).hexdigest()}"

        self._append_jsonl(self.artifact_path, artifact)
        self._append_jsonl(
            self.provenance_log_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "artifact_id": artifact["artifact_id"],
                "job_id": artifact["job_id"],
                "immutable_ref": immutable_ref,
                "source": "services/ar_orchestrator/orchestrator.py",
            },
        )
        return immutable_ref

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _atomic_rewrite_queue(self, lines: list[str]) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.queue_path.with_name(f"{self.queue_path.name}.{uuid4().hex}.tmp")
        payload = "".join(f"{line}\n" for line in lines)
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(self.queue_path)
