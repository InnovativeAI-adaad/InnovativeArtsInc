from __future__ import annotations

import json

from services.release_pipeline.generation_scheduler import (
    CandidateGenerationPlan,
    append_scheduler_dashboard_metrics,
    media_generation_adapter_config_from_decision,
    next_retry_target,
    run_scheduler_hook,
    select_fallback_provider_model,
    select_generation_plan,
)


def _candidate_plans() -> list[CandidateGenerationPlan]:
    return [
        CandidateGenerationPlan(
            plan_id="plan-fast-cheap",
            provider="openai",
            model="gpt-4o-mini",
            quality_likelihood=0.72,
            estimated_cost_usd=0.4,
            expected_latency_ms=600,
        ),
        CandidateGenerationPlan(
            plan_id="plan-balanced",
            provider="openai",
            model="gpt-4.1",
            quality_likelihood=0.89,
            estimated_cost_usd=0.9,
            expected_latency_ms=950,
            model_version="2026-01",
        ),
        CandidateGenerationPlan(
            plan_id="plan-alt-provider",
            provider="anthropic",
            model="claude-3.7-sonnet",
            quality_likelihood=0.86,
            estimated_cost_usd=0.8,
            expected_latency_ms=900,
        ),
    ]


def test_select_generation_plan_scores_and_ranks_candidates() -> None:
    decision = select_generation_plan(
        job_id="job-100",
        candidate_plans=_candidate_plans(),
        campaign_budget_tier="high",
        release_urgency="normal",
    )

    assert decision["selected_plan_id"] == "plan-fast-cheap"
    assert decision["selected_by_policy"] is True
    assert decision["policy_tier"] == "preview"
    assert isinstance(decision["estimated_cost"], float)
    assert any(item["model_version"] == "2026-01" for item in decision["ranking"])
    assert decision["ranking"][0]["score"] >= decision["ranking"][1]["score"]
    assert decision["provider_model_preset"]["primary"]["provider"]


def test_run_scheduler_hook_persists_rationale_to_metadata_with_provenance_ref() -> None:
    decision, metadata = run_scheduler_hook(
        job_id="job-101",
        candidate_plans=_candidate_plans(),
        campaign_budget_tier="mid",
        release_urgency="rush",
        job_metadata={"provenance_refs": ["prov://existing"]},
    )

    assert metadata["scheduler"]["selected_plan_id"] == decision["selected_plan_id"]
    assert metadata["scheduler"]["ranked_candidates"]
    assert len(metadata["provenance_refs"]) == 2
    assert metadata["provenance_refs"][1].startswith("scheduler://job-101/")


def test_select_fallback_provider_model_on_transient_failure() -> None:
    decision = select_generation_plan(
        job_id="job-102",
        candidate_plans=_candidate_plans(),
        campaign_budget_tier="high",
        release_urgency="normal",
    )

    fallback = select_fallback_provider_model(
        scheduler_decision=decision,
        transient_error=True,
        attempted_targets={(decision["selected_provider"], decision["selected_model"])},
    )

    assert fallback is not None
    assert (fallback["provider"], fallback["model"]) != (decision["selected_provider"], decision["selected_model"])


def test_append_scheduler_dashboard_metrics_writes_cost_and_approval_time(tmp_path, monkeypatch) -> None:
    metrics_path = tmp_path / "registry" / "metrics.jsonl"
    monkeypatch.setattr("services.release_pipeline.generation_scheduler._METRICS_PATH", metrics_path)

    records = append_scheduler_dashboard_metrics(
        job_id="job-103",
        approved_tracks=4,
        total_generation_cost_usd=12.0,
        queued_at_unix_ms=2_000,
        approved_at_unix_ms=8_500,
    )

    assert len(records) == 2
    lines = metrics_path.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    names = {row["metric_name"] for row in parsed}
    assert names == {"cost_per_approved_track", "time_to_approval_ms"}
    cost_entry = next(row for row in parsed if row["metric_name"] == "cost_per_approved_track")
    assert cost_entry["metric_value"] == 3.0


def test_select_fallback_provider_model_skips_malformed_ranking_rows() -> None:
    decision = {
        "selected_provider": "openai",
        "selected_model": "gpt-4.1",
        "ranking": [
            {"provider": None, "model": "gpt-4o"},
            {"provider": "None", "model": "gpt-4o"},
            {"provider": "  ", "model": "gpt-4o"},
            {"provider": "anthropic", "model": "claude-3.7-sonnet"},
        ],
        "provider_model_preset": {"fallback": []},
    }

    fallback = select_fallback_provider_model(
        scheduler_decision=decision,
        transient_error=True,
        attempted_targets={("openai", "gpt-4.1")},
    )

    assert fallback == {
        "provider": "anthropic",
        "model": "claude-3.7-sonnet",
        "source": "ranked_candidates",
    }


def test_select_fallback_provider_model_returns_none_for_only_malformed_targets() -> None:
    decision = {
        "selected_provider": "openai",
        "selected_model": "gpt-4.1",
        "ranking": [
            {"provider": "None", "model": "None"},
            {"provider": " ", "model": "gpt-4o"},
        ],
        "provider_model_preset": {
            "fallback": [
                {"provider": None, "model": "claude-3.7-sonnet"},
                {"provider": "None", "model": "claude-3.7-sonnet"},
                {"provider": "anthropic", "model": " "},
            ]
        },
    }

    fallback = select_fallback_provider_model(
        scheduler_decision=decision,
        transient_error=True,
        attempted_targets={("openai", "gpt-4.1")},
    )

    assert fallback is None


def test_media_generation_adapter_config_from_decision_includes_model_version() -> None:
    decision = select_generation_plan(
        job_id="job-104",
        candidate_plans=[
            CandidateGenerationPlan(
                plan_id="suno-high-quality",
                provider="suno",
                model="chirp-v4",
                model_version="v4",
                quality_likelihood=0.94,
                estimated_cost_usd=1.2,
                expected_latency_ms=1200,
            )
        ],
        campaign_budget_tier="high",
        release_urgency="normal",
    )

    config = media_generation_adapter_config_from_decision(decision, dry_run=True)

    assert config == {
        "provider_name": "suno",
        "model": "chirp-v4",
        "model_version": "v4",
        "dry_run": True,
    }


def test_policy_chooses_cheapest_valid_candidate() -> None:
    decision = select_generation_plan(
        job_id="job-105",
        candidate_plans=_candidate_plans(),
        campaign_budget_tier="mid",
        release_urgency="normal",
        policy_tier="preview",
    )

    assert decision["selected_provider"] == "openai"
    assert decision["selected_model"] == "gpt-4o-mini"


def test_next_retry_target_is_deterministic_and_respects_limits() -> None:
    decision = select_generation_plan(
        job_id="job-106",
        candidate_plans=_candidate_plans(),
        campaign_budget_tier="mid",
        release_urgency="normal",
    )

    retry1 = next_retry_target(
        scheduler_decision=decision,
        attempted_targets=[(decision["selected_provider"], decision["selected_model"])],
        failure_type="timeout",
        attempt_number=1,
    )
    assert retry1 is not None
    assert retry1["attempt"] == 2

    retry_blocked = next_retry_target(
        scheduler_decision=decision,
        attempted_targets=[(decision["selected_provider"], decision["selected_model"])],
        failure_type="fatal",
        attempt_number=1,
    )
    assert retry_blocked is None

    retry_exhausted = next_retry_target(
        scheduler_decision=decision,
        attempted_targets=[(decision["selected_provider"], decision["selected_model"])],
        failure_type="timeout",
        attempt_number=3,
    )
    assert retry_exhausted is None
