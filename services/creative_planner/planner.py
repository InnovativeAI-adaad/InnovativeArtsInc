from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.growth_ops.experiment_runner import ExperimentRunner, ExperimentVariant, MetricEvent


@dataclass(frozen=True)
class CampaignContext:
    campaign_id: str
    objective: str
    audience_segments: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.campaign_id.strip():
            raise ValueError("campaign_id must be non-empty")
        if not self.objective.strip():
            raise ValueError("objective must be non-empty")


@dataclass(frozen=True)
class ArtistProfile:
    artist_id: str
    brand_voice: str
    signature_styles: tuple[str, ...] = ()
    risk_tolerance: float = 0.5

    def __post_init__(self) -> None:
        if not self.artist_id.strip():
            raise ValueError("artist_id must be non-empty")
        if not self.brand_voice.strip():
            raise ValueError("brand_voice must be non-empty")
        if self.risk_tolerance < 0 or self.risk_tolerance > 1:
            raise ValueError("risk_tolerance must be between 0 and 1")


@dataclass(frozen=True)
class PriorOutcome:
    strategy_id: str
    quality_pass_rate: float
    novelty_score: float
    downstream_engagement: float

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        if self.quality_pass_rate < 0 or self.quality_pass_rate > 1:
            raise ValueError("quality_pass_rate must be between 0 and 1")
        if self.novelty_score < 0 or self.novelty_score > 1:
            raise ValueError("novelty_score must be between 0 and 1")
        if self.downstream_engagement < 0:
            raise ValueError("downstream_engagement must be >= 0")


@dataclass(frozen=True)
class StyleDNAFingerprint:
    version: str
    fingerprint: str
    dimensions: dict[str, float]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must be non-empty")
        if not self.fingerprint.strip():
            raise ValueError("fingerprint must be non-empty")


@dataclass(frozen=True)
class PromptPlan:
    plan_id: str
    campaign_id: str
    strategy_id: str
    prompt_blueprint: dict[str, str]
    generation_config: dict[str, Any]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class GenerationTrialOutcome:
    trial_id: str
    plan_id: str
    strategy_id: str
    quality_passed: bool
    novelty_score: float
    downstream_engagement: float

    def __post_init__(self) -> None:
        if not self.trial_id.strip():
            raise ValueError("trial_id must be non-empty")
        if not self.plan_id.strip():
            raise ValueError("plan_id must be non-empty")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        if self.novelty_score < 0 or self.novelty_score > 1:
            raise ValueError("novelty_score must be between 0 and 1")
        if self.downstream_engagement < 0:
            raise ValueError("downstream_engagement must be >= 0")


@dataclass(frozen=True)
class StrategyLifecycleDecision:
    promoted_strategy_id: str | None
    archived_strategy_ids: tuple[str, ...]
    decision: dict[str, str | float | None]
    provenance: dict[str, Any]


@dataclass
class CreativePlanner:
    style_dna_version: str = "v1"
    _plans: dict[str, PromptPlan] = field(default_factory=dict)
    _trial_outcomes: list[GenerationTrialOutcome] = field(default_factory=list)

    def generate_prompt_plan(
        self,
        campaign_context: CampaignContext,
        artist_profile: ArtistProfile,
        prior_outcomes: tuple[PriorOutcome, ...],
        generation_config: dict[str, Any],
    ) -> PromptPlan:
        strategy_id = self._select_strategy(prior_outcomes)
        style_dna = self._encode_style_dna_fingerprint(campaign_context, artist_profile, strategy_id)

        plan_id = f"plan-{campaign_context.campaign_id}-{len(self._plans) + 1}"
        blueprint = {
            "objective": campaign_context.objective,
            "brand_voice": artist_profile.brand_voice,
            "audience": ", ".join(campaign_context.audience_segments) or "broad",
            "style_reference": ", ".join(artist_profile.signature_styles) or "default",
            "constraints": ", ".join(campaign_context.constraints) or "none",
        }

        plan_generation_config = {
            **generation_config,
            "style_dna_fingerprint": style_dna.fingerprint,
            "style_dna_fingerprint_version": style_dna.version,
            "planning_strategy_id": strategy_id,
        }

        plan = PromptPlan(
            plan_id=plan_id,
            campaign_id=campaign_context.campaign_id,
            strategy_id=strategy_id,
            prompt_blueprint=blueprint,
            generation_config=plan_generation_config,
            provenance={
                "source": "services/creative_planner/planner.py",
                "created_at": self._utc_now(),
                "prior_outcomes_count": len(prior_outcomes),
            },
        )
        self._plans[plan_id] = plan
        return plan

    def store_generation_trial_outcome(self, outcome: GenerationTrialOutcome) -> None:
        known_plan = self._plans.get(outcome.plan_id)
        if known_plan is None:
            raise ValueError(f"Unknown plan_id: {outcome.plan_id}")
        if known_plan.strategy_id != outcome.strategy_id:
            raise ValueError("strategy_id must match the strategy selected in the referenced plan")
        self._trial_outcomes.append(outcome)

    def compute_reward_signals(self) -> dict[str, dict[str, float]]:
        grouped: dict[str, list[GenerationTrialOutcome]] = {}
        for outcome in self._trial_outcomes:
            grouped.setdefault(outcome.strategy_id, []).append(outcome)

        summary: dict[str, dict[str, float]] = {}
        for strategy_id, outcomes in grouped.items():
            trial_count = len(outcomes)
            quality_pass_rate = sum(1 for outcome in outcomes if outcome.quality_passed) / trial_count
            novelty_avg = sum(outcome.novelty_score for outcome in outcomes) / trial_count
            downstream_engagement_avg = sum(outcome.downstream_engagement for outcome in outcomes) / trial_count
            reward_score = (
                (quality_pass_rate * 0.5)
                + (novelty_avg * 0.25)
                + (downstream_engagement_avg * 0.25)
            )
            summary[strategy_id] = {
                "trial_count": float(trial_count),
                "quality_pass_rate": quality_pass_rate,
                "novelty_avg": novelty_avg,
                "downstream_engagement_avg": downstream_engagement_avg,
                "reward_score": reward_score,
            }
        return summary

    def run_variant_selection(
        self,
        *,
        experiment_id: str,
        minimum_sample_size: int,
        promotion_threshold: float,
    ) -> dict[str, str | float | None]:
        reward_signals = self.compute_reward_signals()
        if len(reward_signals) < 2:
            return {
                "experiment_id": experiment_id,
                "status": "hold",
                "winner_variant_id": None,
                "reason": "insufficient_variants",
            }

        runner = ExperimentRunner(
            experiment_id=experiment_id,
            primary_metric="reward",
            minimum_sample_size=minimum_sample_size,
            promotion_threshold=promotion_threshold,
            variants=tuple(
                ExperimentVariant(variant_id=strategy_id, allocation_weight=1.0 / len(reward_signals))
                for strategy_id in reward_signals
            ),
        )

        events = [
            MetricEvent(variant_id=outcome.strategy_id, metric_name="reward", value=reward_signals[outcome.strategy_id]["reward_score"])
            for outcome in self._trial_outcomes
            if outcome.strategy_id in reward_signals
        ]
        runner.ingest_metrics(events)
        return runner.promotion_decision()

    def promote_winner_and_archive_losers(
        self,
        *,
        experiment_id: str,
        minimum_sample_size: int,
        promotion_threshold: float,
    ) -> StrategyLifecycleDecision:
        decision = self.run_variant_selection(
            experiment_id=experiment_id,
            minimum_sample_size=minimum_sample_size,
            promotion_threshold=promotion_threshold,
        )
        winner = decision.get("winner_variant_id")
        strategy_ids = {plan.strategy_id for plan in self._plans.values()}

        if isinstance(winner, str):
            archived = tuple(sorted(strategy_id for strategy_id in strategy_ids if strategy_id != winner))
        else:
            archived = tuple()

        return StrategyLifecycleDecision(
            promoted_strategy_id=winner if isinstance(winner, str) else None,
            archived_strategy_ids=archived,
            decision=decision,
            provenance={
                "experiment_id": experiment_id,
                "evaluated_strategies": sorted(strategy_ids),
                "evaluated_at": self._utc_now(),
            },
        )

    def _select_strategy(self, prior_outcomes: tuple[PriorOutcome, ...]) -> str:
        if not prior_outcomes:
            return "default-strategy"
        ranked = sorted(
            prior_outcomes,
            key=lambda outcome: (outcome.quality_pass_rate * 0.5) + (outcome.novelty_score * 0.25) + (outcome.downstream_engagement * 0.25),
            reverse=True,
        )
        return ranked[0].strategy_id

    def _encode_style_dna_fingerprint(
        self,
        campaign_context: CampaignContext,
        artist_profile: ArtistProfile,
        strategy_id: str,
    ) -> StyleDNAFingerprint:
        raw = "|".join(
            [
                campaign_context.campaign_id,
                campaign_context.objective,
                artist_profile.artist_id,
                artist_profile.brand_voice,
                strategy_id,
                ",".join(sorted(artist_profile.signature_styles)),
            ]
        )
        digest = sha256(raw.encode("utf-8")).hexdigest()
        fingerprint = f"{self.style_dna_version}:{digest}"
        return StyleDNAFingerprint(
            version=self.style_dna_version,
            fingerprint=fingerprint,
            dimensions={
                "risk_tolerance": artist_profile.risk_tolerance,
                "channel_count": float(len(campaign_context.channels)),
                "constraint_count": float(len(campaign_context.constraints)),
            },
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
