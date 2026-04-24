import pytest

from services.creative_planner import (
    ArtistProfile,
    CampaignContext,
    CreativePlanner,
    GenerationTrialOutcome,
    PriorOutcome,
)
from services.growth_ops.attribution import AttributionLayer, CampaignEvent, MonetizationLedgerEntry
from services.growth_ops.clip_contract import (
    CampaignMetadata,
    ClipAsset,
    ClipGenerationJobContract,
    VariantStrategy,
)
from services.growth_ops.crm_connectors import AudienceRecord, ConsentStateChange, FirstPartyCRMConnector
from services.growth_ops.experiment_runner import ExperimentRunner, ExperimentVariant, MetricEvent
from services.growth_ops.governance import CompliancePolicy, GovernanceGuardrails, OutreachAction


def test_creative_planner_generates_versioned_style_dna_generation_config() -> None:
    planner = CreativePlanner(style_dna_version="v2")
    plan = planner.generate_prompt_plan(
        campaign_context=CampaignContext(
            campaign_id="camp-44",
            objective="engagement",
            audience_segments=("fans", "new_listeners"),
            channels=("tiktok", "ig"),
            constraints=("brand_safe",),
        ),
        artist_profile=ArtistProfile(
            artist_id="artist-1",
            brand_voice="raw and cinematic",
            signature_styles=("grit", "minimal"),
            risk_tolerance=0.7,
        ),
        prior_outcomes=(
            PriorOutcome(
                strategy_id="style-a",
                quality_pass_rate=0.8,
                novelty_score=0.6,
                downstream_engagement=0.5,
            ),
            PriorOutcome(
                strategy_id="style-b",
                quality_pass_rate=0.5,
                novelty_score=0.9,
                downstream_engagement=0.4,
            ),
        ),
        generation_config={
            "model_version": "gen-2026.04",
            "prompt_template_version": "p3",
            "random_seed": 7,
            "creativity_profile": "exploratory",
            "style_constraints": ["no-logos"],
        },
    )

    assert plan.strategy_id == "style-a"
    assert plan.generation_config["style_dna_fingerprint"].startswith("v2:")
    assert plan.generation_config["style_dna_fingerprint_version"] == "v2"
    assert plan.generation_config["planning_strategy_id"] == "style-a"


def test_creative_planner_rewards_selection_and_promotion() -> None:
    planner = CreativePlanner()

    plan_a = planner.generate_prompt_plan(
        campaign_context=CampaignContext(campaign_id="camp-1", objective="engagement"),
        artist_profile=ArtistProfile(artist_id="artist-1", brand_voice="bold"),
        prior_outcomes=(PriorOutcome("strategy-a", 0.8, 0.8, 0.9),),
        generation_config={
            "model_version": "gen-1",
            "prompt_template_version": "p1",
            "random_seed": 3,
            "creativity_profile": "balanced",
            "style_constraints": ["clean"],
        },
    )
    plan_b = planner.generate_prompt_plan(
        campaign_context=CampaignContext(campaign_id="camp-1", objective="engagement"),
        artist_profile=ArtistProfile(artist_id="artist-1", brand_voice="bold"),
        prior_outcomes=(PriorOutcome("strategy-b", 0.5, 0.3, 0.2),),
        generation_config={
            "model_version": "gen-1",
            "prompt_template_version": "p1",
            "random_seed": 4,
            "creativity_profile": "balanced",
            "style_constraints": ["clean"],
        },
    )

    planner.store_generation_trial_outcome(
        GenerationTrialOutcome("trial-1", plan_a.plan_id, plan_a.strategy_id, True, 0.8, 0.9)
    )
    planner.store_generation_trial_outcome(
        GenerationTrialOutcome("trial-2", plan_a.plan_id, plan_a.strategy_id, True, 0.9, 1.0)
    )
    planner.store_generation_trial_outcome(
        GenerationTrialOutcome("trial-3", plan_b.plan_id, plan_b.strategy_id, False, 0.3, 0.2)
    )
    planner.store_generation_trial_outcome(
        GenerationTrialOutcome("trial-4", plan_b.plan_id, plan_b.strategy_id, False, 0.2, 0.1)
    )

    rewards = planner.compute_reward_signals()
    assert rewards[plan_a.strategy_id]["quality_pass_rate"] == 1.0
    assert rewards[plan_b.strategy_id]["quality_pass_rate"] == 0.0

    lifecycle = planner.promote_winner_and_archive_losers(
        experiment_id="exp-plan-1",
        minimum_sample_size=2,
        promotion_threshold=0.5,
    )
    assert lifecycle.promoted_strategy_id == plan_a.strategy_id
    assert plan_b.strategy_id in lifecycle.archived_strategy_ids
    assert lifecycle.decision["status"] == "promote"


def test_clip_generation_job_contract_payload() -> None:
    contract = ClipGenerationJobContract(
        job_id="job-1",
        assets=(
            ClipAsset(
                asset_id="asset-1",
                asset_type="video",
                uri="s3://bucket/video.mp4",
                duration_seconds=30,
            ),
        ),
        campaign=CampaignMetadata(
            campaign_id="campaign-1",
            release_id="release-99",
            channel="tiktok",
            objective="engagement",
            tags=("launch",),
        ),
        variant_strategy=VariantStrategy(
            strategy_id="strat-1",
            variant_count=3,
            max_duration_seconds=15,
            hooks=("first3sec",),
            cta_templates=("stream_now",),
        ),
    )

    payload = contract.to_payload()
    assert payload["campaign"]["release_id"] == "release-99"
    assert payload["variant_strategy"]["variant_count"] == 3


def test_experiment_runner_winner_promotion() -> None:
    runner = ExperimentRunner(
        experiment_id="exp-1",
        primary_metric="ctr",
        minimum_sample_size=2,
        promotion_threshold=0.2,
        variants=(
            ExperimentVariant(variant_id="A", allocation_weight=0.5),
            ExperimentVariant(variant_id="B", allocation_weight=0.5),
        ),
    )

    runner.ingest_metrics(
        [
            MetricEvent(variant_id="A", metric_name="ctr", value=0.22),
            MetricEvent(variant_id="A", metric_name="ctr", value=0.20),
            MetricEvent(variant_id="B", metric_name="ctr", value=0.10),
            MetricEvent(variant_id="B", metric_name="ctr", value=0.15),
        ]
    )

    decision = runner.promotion_decision()
    assert decision["status"] == "promote"
    assert decision["winner_variant_id"] == "A"


def test_experiment_runner_holds_when_winner_variant_has_insufficient_samples() -> None:
    runner = ExperimentRunner(
        experiment_id="exp-2",
        primary_metric="ctr",
        minimum_sample_size=4,
        promotion_threshold=0.2,
        variants=(
            ExperimentVariant(variant_id="A", allocation_weight=0.5),
            ExperimentVariant(variant_id="B", allocation_weight=0.5),
        ),
    )

    runner.ingest_metrics(
        [
            MetricEvent(variant_id="A", metric_name="ctr", value=0.21),
            MetricEvent(variant_id="A", metric_name="ctr", value=0.20),
            MetricEvent(variant_id="A", metric_name="ctr", value=0.19),
            MetricEvent(variant_id="A", metric_name="ctr", value=0.22),
            MetricEvent(variant_id="B", metric_name="ctr", value=0.90),
        ]
    )

    decision = runner.promotion_decision()
    assert decision["status"] == "hold"
    assert decision["winner_variant_id"] is None
    assert decision["reason"] == "insufficient_per_variant_sample"


def test_experiment_runner_promotes_when_all_variants_meet_sample_threshold() -> None:
    runner = ExperimentRunner(
        experiment_id="exp-3",
        primary_metric="ctr",
        minimum_sample_size=2,
        promotion_threshold=0.2,
        variants=(
            ExperimentVariant(variant_id="A", allocation_weight=0.5),
            ExperimentVariant(variant_id="B", allocation_weight=0.5),
        ),
    )

    runner.ingest_metrics(
        [
            MetricEvent(variant_id="A", metric_name="ctr", value=0.25),
            MetricEvent(variant_id="A", metric_name="ctr", value=0.22),
            MetricEvent(variant_id="B", metric_name="ctr", value=0.20),
            MetricEvent(variant_id="B", metric_name="ctr", value=0.21),
        ]
    )

    decision = runner.promotion_decision()
    assert decision["status"] == "promote"
    assert decision["winner_variant_id"] == "A"
    assert decision["reason"] == "threshold_passed"


def test_crm_connector_consent_updates() -> None:
    connector = FirstPartyCRMConnector(source_name="webform")
    connector.capture_audience(
        AudienceRecord(user_id="u1", email="user@example.com", consent_email=True)
    )
    connector.update_consent(
        ConsentStateChange(user_id="u1", channel="sms", consent_granted=True)
    )

    exported = connector.export()
    assert exported["audience"][0]["consent_sms"] is True
    assert exported["consent_events"][0]["channel"] == "sms"


def test_attribution_links_events_to_ledger() -> None:
    layer = AttributionLayer()
    layer.record_event(
        CampaignEvent(
            event_id="evt-1",
            campaign_id="camp-1",
            release_id="release-1",
            user_id="u1",
            event_type="click",
            value=1.0,
        )
    )
    layer.attach_ledger_entry(
        MonetizationLedgerEntry(
            ledger_id="led-1",
            release_id="release-1",
            amount=12.5,
            currency="USD",
        )
    )

    summary = layer.attributed_summary("release-1")
    assert summary["event_count"] == 1
    assert summary["totals_by_currency"] == {"USD": 12.5}
    assert summary["total_revenue"] == 12.5


def test_attribution_mixed_currency_omits_scalar_total() -> None:
    layer = AttributionLayer()
    layer.attach_ledger_entry(
        MonetizationLedgerEntry(
            ledger_id="led-1",
            release_id="release-2",
            amount=10.0,
            currency="USD",
        )
    )
    layer.attach_ledger_entry(
        MonetizationLedgerEntry(
            ledger_id="led-2",
            release_id="release-2",
            amount=8.0,
            currency="EUR",
        )
    )

    summary = layer.attributed_summary("release-2")
    assert summary["totals_by_currency"] == {"USD": 10.0, "EUR": 8.0}
    assert "total_revenue" not in summary


def test_attribution_rejects_non_finite_or_non_normalized_currency() -> None:
    layer = AttributionLayer()

    with pytest.raises(ValueError, match="amount must be finite"):
        layer.attach_ledger_entry(
            MonetizationLedgerEntry(
                ledger_id="led-1",
                release_id="release-3",
                amount=float("inf"),
                currency="USD",
            )
        )

    with pytest.raises(ValueError, match="uppercase ISO-style"):
        layer.attach_ledger_entry(
            MonetizationLedgerEntry(
                ledger_id="led-2",
                release_id="release-3",
                amount=2.0,
                currency="usd",
            )
        )


def test_governance_guardrails_require_human_for_high_risk() -> None:
    guardrails = GovernanceGuardrails(
        policy=CompliancePolicy(
            policy_id="policy-1",
            required_checks=("consent_validation", "quiet_hours", "opt_out_link"),
        )
    )
    action = OutreachAction(
        action_id="bulk_sms",
        channel="sms",
        risk_score=85,
        audience_size=5000,
    )

    blocked = guardrails.evaluate(
        action,
        completed_checks={"consent_validation", "quiet_hours", "opt_out_link"},
        approved_by_human=False,
    )
    approved = guardrails.evaluate(
        action,
        completed_checks={"consent_validation", "quiet_hours", "opt_out_link"},
        approved_by_human=True,
    )

    assert blocked["status"] == "blocked"
    assert approved["status"] == "approved"
