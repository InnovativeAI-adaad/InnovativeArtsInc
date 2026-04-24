import pytest

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
        minimum_sample_size=4,
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
