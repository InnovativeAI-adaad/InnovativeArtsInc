"""Release pipeline service package."""

from .adapters import (
    AdapterSubmissionResult,
    DSPSubmissionAdapter,
    PRORegistrationAdapter,
    StubDSPSubmissionAdapter,
    StubPRORegistrationAdapter,
)
from .generation_scheduler import (
    CandidateGenerationPlan,
    ScoredGenerationPlan,
    append_scheduler_dashboard_metrics,
    persist_scheduler_decision_metadata,
    resolve_model_provider_presets,
    run_scheduler_hook,
    score_candidate_plan,
    select_fallback_provider_model,
    select_generation_plan,
)
from .service import (
    build_release_bundle,
    generate_split_sheet,
    schedule_generation_job,
    sign_artifact_reference,
)

__all__ = [
    "AdapterSubmissionResult",
    "DSPSubmissionAdapter",
    "PRORegistrationAdapter",
    "StubDSPSubmissionAdapter",
    "StubPRORegistrationAdapter",
    "CandidateGenerationPlan",
    "ScoredGenerationPlan",
    "append_scheduler_dashboard_metrics",
    "persist_scheduler_decision_metadata",
    "resolve_model_provider_presets",
    "run_scheduler_hook",
    "score_candidate_plan",
    "select_fallback_provider_model",
    "select_generation_plan",
    "build_release_bundle",
    "generate_split_sheet",
    "schedule_generation_job",
    "sign_artifact_reference",
]
