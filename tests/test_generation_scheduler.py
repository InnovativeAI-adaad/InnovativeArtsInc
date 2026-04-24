from __future__ import annotations

import json

from services.release_pipeline.generation_scheduler import (
    CandidateGenerationPlan,
    append_scheduler_dashboard_metrics,
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

    assert decision["selected_plan_id"] == "plan-balanced"
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
