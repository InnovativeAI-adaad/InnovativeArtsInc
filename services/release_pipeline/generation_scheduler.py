"""Scheduling and decision helpers for release-generation campaigns."""

from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]
_METRICS_PATH = _REPO_ROOT / "registry" / "metrics.jsonl"


@dataclass(frozen=True)
class CandidateGenerationPlan:
    plan_id: str
    provider: str
    model: str
    quality_likelihood: float
    estimated_cost_usd: float
    expected_latency_ms: int


@dataclass(frozen=True)
class ScoredGenerationPlan:
    candidate: CandidateGenerationPlan
    score: float
    quality_component: float
    cost_component: float
    latency_component: float


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def score_candidate_plan(
    candidate: CandidateGenerationPlan,
    *,
    max_cost_usd: float,
    max_latency_ms: int,
    quality_weight: float = 0.6,
    cost_weight: float = 0.25,
    latency_weight: float = 0.15,
) -> ScoredGenerationPlan:
    """Score a generation plan using weighted quality, cost efficiency, and latency efficiency."""
    normalized_quality = min(max(candidate.quality_likelihood, 0.0), 1.0)

    safe_max_cost = max(max_cost_usd, 0.01)
    safe_max_latency = max(max_latency_ms, 1)

    cost_ratio = max(candidate.estimated_cost_usd, 0.0) / safe_max_cost
    latency_ratio = max(candidate.expected_latency_ms, 0) / safe_max_latency

    cost_component = 1.0 / (1.0 + cost_ratio)
    latency_component = 1.0 / (1.0 + latency_ratio)

    score = (
        normalized_quality * quality_weight
        + cost_component * cost_weight
        + latency_component * latency_weight
    )
    return ScoredGenerationPlan(
        candidate=candidate,
        score=round(score, 6),
        quality_component=round(normalized_quality, 6),
        cost_component=round(cost_component, 6),
        latency_component=round(latency_component, 6),
    )


def resolve_model_provider_presets(*, campaign_budget_tier: str, release_urgency: str) -> dict[str, Any]:
    """Resolve primary/fallback provider-model presets by budget and urgency."""
    budget = campaign_budget_tier.strip().lower()
    urgency = release_urgency.strip().lower()

    presets = {
        "low": {
            "normal": {
                "primary": {"provider": "openai", "model": "gpt-4.1-mini"},
                "fallback": [
                    {"provider": "anthropic", "model": "claude-3.5-haiku"},
                    {"provider": "openai", "model": "gpt-4o-mini"},
                ],
            },
            "rush": {
                "primary": {"provider": "openai", "model": "gpt-4o-mini"},
                "fallback": [
                    {"provider": "anthropic", "model": "claude-3.5-haiku"},
                    {"provider": "openai", "model": "gpt-4.1-mini"},
                ],
            },
        },
        "mid": {
            "normal": {
                "primary": {"provider": "openai", "model": "gpt-4.1"},
                "fallback": [
                    {"provider": "anthropic", "model": "claude-3.7-sonnet"},
                    {"provider": "openai", "model": "gpt-4o"},
                ],
            },
            "rush": {
                "primary": {"provider": "openai", "model": "gpt-4o"},
                "fallback": [
                    {"provider": "anthropic", "model": "claude-3.7-sonnet"},
                    {"provider": "openai", "model": "gpt-4.1"},
                ],
            },
        },
        "high": {
            "normal": {
                "primary": {"provider": "openai", "model": "gpt-4.1"},
                "fallback": [
                    {"provider": "anthropic", "model": "claude-3.7-sonnet"},
                    {"provider": "openai", "model": "gpt-4o"},
                ],
            },
            "rush": {
                "primary": {"provider": "openai", "model": "gpt-4o"},
                "fallback": [
                    {"provider": "anthropic", "model": "claude-3.7-sonnet"},
                    {"provider": "openai", "model": "gpt-4.1"},
                ],
            },
        },
    }

    urgency_key = "rush" if urgency in {"rush", "urgent", "asap", "critical"} else "normal"
    budget_key = budget if budget in presets else "mid"
    return presets[budget_key][urgency_key]


def select_generation_plan(
    *,
    job_id: str,
    candidate_plans: list[CandidateGenerationPlan],
    campaign_budget_tier: str,
    release_urgency: str,
) -> dict[str, Any]:
    """Rank candidates, pick primary plan, and return scheduler decision artifact."""
    if not candidate_plans:
        raise ValueError("candidate_plans must not be empty")

    max_cost_usd = max(plan.estimated_cost_usd for plan in candidate_plans)
    max_latency_ms = max(plan.expected_latency_ms for plan in candidate_plans)

    scored = [
        score_candidate_plan(plan, max_cost_usd=max_cost_usd, max_latency_ms=max_latency_ms)
        for plan in candidate_plans
    ]
    ranked = sorted(scored, key=lambda item: item.score, reverse=True)
    selected = ranked[0]
    preset = resolve_model_provider_presets(
        campaign_budget_tier=campaign_budget_tier,
        release_urgency=release_urgency,
    )

    return {
        "scheduler_version": "1.0.0",
        "job_id": job_id,
        "scheduled_at": _utc_now_iso(),
        "selected_plan_id": selected.candidate.plan_id,
        "selected_provider": selected.candidate.provider,
        "selected_model": selected.candidate.model,
        "selected_score": selected.score,
        "provider_model_preset": preset,
        "ranking": [
            {
                "plan_id": item.candidate.plan_id,
                "provider": item.candidate.provider,
                "model": item.candidate.model,
                "score": item.score,
                "quality_component": item.quality_component,
                "cost_component": item.cost_component,
                "latency_component": item.latency_component,
                "estimated_cost_usd": item.candidate.estimated_cost_usd,
                "expected_latency_ms": item.candidate.expected_latency_ms,
            }
            for item in ranked
        ],
    }


def persist_scheduler_decision_metadata(
    *,
    job_metadata: dict[str, Any],
    scheduler_decision: dict[str, Any],
    provenance_ref: str | None = None,
) -> dict[str, Any]:
    """Persist scheduler rationale to job metadata and provenance references."""
    metadata = dict(job_metadata)
    provenance_refs = list(metadata.get("provenance_refs") or [])
    if provenance_ref:
        provenance_refs.append(provenance_ref)

    metadata["provenance_refs"] = provenance_refs
    metadata["scheduler"] = {
        "scheduler_version": scheduler_decision.get("scheduler_version", "1.0.0"),
        "selected_plan_id": scheduler_decision["selected_plan_id"],
        "selected_provider": scheduler_decision["selected_provider"],
        "selected_model": scheduler_decision["selected_model"],
        "selected_score": scheduler_decision["selected_score"],
        "provider_model_preset": scheduler_decision["provider_model_preset"],
        "ranked_candidates": scheduler_decision["ranking"],
        "scheduled_at": scheduler_decision["scheduled_at"],
    }
    return metadata


def select_fallback_provider_model(
    *,
    scheduler_decision: dict[str, Any],
    transient_error: bool,
    attempted_targets: set[tuple[str, str]] | None = None,
) -> dict[str, str] | None:
    """Select the next provider/model target after a transient failure."""
    if not transient_error:
        return None

    def _validated_pair(provider: Any, model: Any) -> tuple[str, str] | None:
        if not isinstance(provider, str) or not isinstance(model, str):
            return None

        provider_value = provider.strip()
        model_value = model.strip()
        if not provider_value or not model_value:
            return None
        if provider_value == "None" or model_value == "None":
            return None
        return provider_value, model_value

    attempted = {
        (str(provider).strip(), str(model).strip())
        for provider, model in (attempted_targets or set())
    }
    primary = _validated_pair(
        scheduler_decision.get("selected_provider"),
        scheduler_decision.get("selected_model"),
    )
    if primary is not None:
        attempted.add(primary)

    ranking = scheduler_decision.get("ranking") or []
    for candidate in ranking:
        pair = _validated_pair(candidate.get("provider"), candidate.get("model"))
        if pair is None:
            continue
        if pair not in attempted:
            return {"provider": pair[0], "model": pair[1], "source": "ranked_candidates"}

    preset = scheduler_decision.get("provider_model_preset") or {}
    for fallback in preset.get("fallback") or []:
        pair = _validated_pair(fallback.get("provider"), fallback.get("model"))
        if pair is None:
            continue
        if pair not in attempted:
            return {"provider": pair[0], "model": pair[1], "source": "preset_fallback"}

    return None


def append_scheduler_dashboard_metrics(
    *,
    job_id: str,
    approved_tracks: int,
    total_generation_cost_usd: float,
    queued_at_unix_ms: int,
    approved_at_unix_ms: int,
) -> list[dict[str, Any]]:
    """Append release scheduler dashboard metrics to registry/metrics.jsonl."""
    _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    elapsed_ms = max(approved_at_unix_ms - queued_at_unix_ms, 0)
    safe_approved_tracks = max(approved_tracks, 1)
    cost_per_approved_track = total_generation_cost_usd / safe_approved_tracks

    records = [
        {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "job_id": job_id,
            "stage": "release_pipeline.scheduler",
            "metric_name": "cost_per_approved_track",
            "metric_value": round(cost_per_approved_track, 6),
            "units": "usd_per_track",
            "approved_tracks": approved_tracks,
            "total_generation_cost_usd": round(total_generation_cost_usd, 6),
        },
        {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "job_id": job_id,
            "stage": "release_pipeline.scheduler",
            "metric_name": "time_to_approval_ms",
            "metric_value": elapsed_ms,
            "units": "ms",
            "queued_at_unix_ms": queued_at_unix_ms,
            "approved_at_unix_ms": approved_at_unix_ms,
        },
    ]

    with _METRICS_PATH.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return records


def run_scheduler_hook(
    *,
    job_id: str,
    candidate_plans: list[CandidateGenerationPlan],
    campaign_budget_tier: str,
    release_urgency: str,
    job_metadata: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Release-pipeline hook that selects a plan and persists scheduler rationale metadata."""
    started_at = time.perf_counter()
    decision = select_generation_plan(
        job_id=job_id,
        candidate_plans=candidate_plans,
        campaign_budget_tier=campaign_budget_tier,
        release_urgency=release_urgency,
    )
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    provenance_ref = (
        f"scheduler://{job_id}/{decision['selected_plan_id']}"
        f"?provider={decision['selected_provider']}&model={decision['selected_model']}"
    )
    metadata = persist_scheduler_decision_metadata(
        job_metadata=job_metadata,
        scheduler_decision=decision,
        provenance_ref=provenance_ref,
    )
    metadata.setdefault("scheduler", {})["decision_latency_ms"] = elapsed_ms
    return decision, metadata
