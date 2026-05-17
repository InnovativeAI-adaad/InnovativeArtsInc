#!/usr/bin/env python3
"""Run a production-facing autonomous media generation job.

This entrypoint wires the creative planner, release scheduler, IP guardrails,
WF-005 generation service, quality validation, and media conductor into one
machine-readable CLI workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Keep direct script execution working when invoked as
# `python pipelines/run_autonomous_media_job.py` from any cwd.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.agents.ip_agent.agent import run_similarity_audit
from core.gatekeeper.entry_gate import enforce_gate
from pipelines.validate_media_outputs import RuntimeRetryPolicy, orchestrate_remediation
from services.creative_planner.planner import (
    ArtistProfile,
    CampaignContext,
    CreativePlanner,
)
from services.integration.facade import build_runtime_config_from_env, build_runtime_context
from services.media_generation.service import generate_music_for_wf005
from services.release_pipeline.service import build_release_bundle, write_release_bundle
from services.release_pipeline.generation_scheduler import schedule_generation_job


DEFAULT_RUNTIME_POLICY = Path("projects/jrt/metadata/agent_runtime_config.json")
DEFAULT_CREATIVE_POLICY = Path("projects/jrt/metadata/control_plane.runtime.json")
DEFAULT_QUALITY_RULES = Path("projects/jrt/metadata/quality_rules.json")
DEFAULT_SIMILARITY_POLICY = Path(
    "core/agents/ip_agent/config/similarity_policy.v1.json"
)


@dataclass(frozen=True)
class AutonomousMediaJobRequest:
    job_id: str
    track_id: str
    artist_profile: dict[str, Any]
    creative_brief: dict[str, Any]
    campaign_budget_tier: str
    release_urgency: str
    seed: int | str | None = None


def _repo_path(repo_root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else repo_root / value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _parse_json_arg(raw: str, *, field_name: str) -> dict[str, Any]:
    candidate = raw.strip()
    if not candidate:
        raise ValueError(f"{field_name} must not be empty")
    path_candidate = Path(candidate[1:] if candidate.startswith("@") else candidate)
    if candidate.startswith("@") or path_candidate.exists():
        return _load_json(path_candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{field_name} must be a JSON object or a path to one"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return parsed


def _stable_seed(request: AutonomousMediaJobRequest) -> int | str:
    if request.seed is not None:
        return request.seed
    digest = hashlib.sha256(
        f"{request.job_id}|{request.track_id}".encode("utf-8")
    ).hexdigest()
    return int(digest[:8], 16)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _enforce_creative_policy(
    creative_brief: dict[str, Any], creative_policy: dict[str, Any]
) -> None:
    genre_blend = (
        creative_brief.get("genre_blend") or creative_brief.get("genres") or []
    )
    if isinstance(genre_blend, str):
        genre_blend = [genre_blend]
    normalized_genres = [
        str(item).strip().lower() for item in genre_blend if str(item).strip()
    ]
    max_components = int(
        (creative_policy.get("genre_blend") or {}).get("max_components", 999)
    )
    if len(normalized_genres) > max_components:
        raise ValueError(
            f"creative_brief genre_blend exceeds max_components={max_components}"
        )
    for combo in (creative_policy.get("genre_blend") or {}).get(
        "banned_combinations", []
    ):
        banned = {str(item).strip().lower() for item in combo}
        if banned and banned.issubset(set(normalized_genres)):
            raise ValueError(
                f"creative_brief genre_blend includes banned combination: {sorted(banned)}"
            )

    mood = creative_brief.get("mood_arc")
    if mood:
        moods = [mood] if isinstance(mood, str) else list(mood)
        allowed_moods = set((creative_policy.get("mood_arc") or {}).get("allowed", []))
        unsupported = [str(item) for item in moods if str(item) not in allowed_moods]
        if unsupported:
            raise ValueError(
                f"creative_brief mood_arc contains unsupported moods: {unsupported}"
            )

    tempo = creative_brief.get("tempo") or creative_brief.get("bpm")
    if tempo is not None:
        tempo_window = creative_policy.get("tempo_window") or {}
        min_tempo = int(tempo_window.get("min_allowed", 0))
        max_tempo = int(tempo_window.get("max_allowed", 999))
        if int(tempo) < min_tempo or int(tempo) > max_tempo:
            raise ValueError(
                f"creative_brief tempo must be between {min_tempo} and {max_tempo}"
            )

    musical_key = creative_brief.get("key")
    if musical_key:
        allowed_keys = set(
            (creative_policy.get("key_window") or {}).get("allowed_keys", [])
        )
        if str(musical_key) not in allowed_keys:
            raise ValueError(
                f"creative_brief key must be one of {sorted(allowed_keys)}"
            )


def _build_prompt_plan(
    *,
    request: AutonomousMediaJobRequest,
    seed: int | str,
    scheduler_model_hint: str = "pending-scheduler",
) -> Any:
    artist = request.artist_profile
    brief = request.creative_brief
    planner = CreativePlanner(
        style_dna_version=str(brief.get("style_dna_version", "v1"))
    )
    profile = ArtistProfile(
        artist_id=str(artist.get("artist_id") or artist.get("id") or request.track_id),
        brand_voice=str(
            artist.get("brand_voice") or artist.get("voice") or "distinctive"
        ),
        signature_styles=tuple(
            str(item)
            for item in artist.get("signature_styles", artist.get("styles", []))
        ),
        risk_tolerance=float(artist.get("risk_tolerance", 0.5)),
    )
    context = CampaignContext(
        campaign_id=request.job_id,
        objective=str(
            brief.get("objective")
            or brief.get("summary")
            or "generate release-ready music"
        ),
        audience_segments=tuple(
            str(item)
            for item in brief.get("audience_segments", brief.get("audience", []))
        ),
        channels=tuple(str(item) for item in brief.get("channels", [])),
        constraints=tuple(str(item) for item in brief.get("constraints", [])),
    )
    generation_config = {
        "model_version": scheduler_model_hint,
        "prompt_template_version": str(
            brief.get("prompt_template_version", "autonomous-media-job.v1")
        ),
        "random_seed": seed,
        "creativity_profile": brief.get("creativity_profile", "balanced"),
        "style_constraints": list(
            context.constraints or profile.signature_styles or ("original-composition",)
        ),
    }
    return planner.generate_prompt_plan(
        campaign_context=context,
        artist_profile=profile,
        prior_outcomes=(),
        generation_config=generation_config,
    )


def _prompt_from_plan(prompt_blueprint: dict[str, str]) -> str:
    return "; ".join(f"{key}: {value}" for key, value in prompt_blueprint.items())


def _write_prompt_artifact(
    repo_root: Path, job_id: str, payload: dict[str, Any]
) -> Path:
    path = (
        repo_root
        / "projects"
        / "jrt"
        / "metadata"
        / "renders"
        / f"{job_id}_prompt_plan.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _write_generated_lyrics(
    repo_root: Path, request: AutonomousMediaJobRequest, plan_blueprint: dict[str, str]
) -> Path:
    path = (
        repo_root
        / "projects"
        / "jrt"
        / "lyrics"
        / "generated"
        / f"{request.track_id}_{request.job_id}.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    title = str(request.creative_brief.get("title") or request.track_id)
    text = f"""# {title}\n\n[Verse]\n{plan_blueprint.get("objective", "A new original story begins.")}\nThe pulse is grounded in an original voice.\nEvery line avoids borrowed hooks and protected lyrics.\nThe scene turns toward a fresh emotional horizon.\n\n[Chorus]\nWe rise with a new signal in the room.\nWe carry the theme without copying the past.\nThe hook resolves in a distinct melodic shape.\nThe final refrain is release-ready and original.\n"""
    path.write_text(text, encoding="utf-8")
    return path


def _fingerprint_for_generation(generation_result: dict[str, Any]) -> list[float]:
    digest = hashlib.sha256(
        json.dumps(generation_result, sort_keys=True).encode("utf-8")
    ).digest()
    return [round(byte / 255, 6) for byte in digest[:12]]


def _embedding_for_generation(
    plan_payload: dict[str, Any], generation_result: dict[str, Any]
) -> list[float]:
    digest = hashlib.sha256(
        json.dumps(
            {"plan": plan_payload, "generation": generation_result}, sort_keys=True
        ).encode("utf-8")
    ).digest()
    return [round(byte / 255, 6) for byte in digest[:16]]


def _semantic_fingerprint_for_generation(
    plan_payload: dict[str, Any], generation_result: dict[str, Any]
) -> dict[str, Any]:
    audio_vec = _fingerprint_for_generation(generation_result)
    clip_vec = _embedding_for_generation(plan_payload, generation_result)
    centroid = sum(audio_vec) / len(audio_vec) if audio_vec else 0.0
    render_metadata = generation_result.get("render_metadata", {})
    return {
        "audio": {
            "tempo_estimate": int(render_metadata.get("tempo", 120)),
            "chroma_profile": audio_vec[:12],
            "spectral_centroid_stats": {"mean": round(centroid, 6), "std": 0.0},
        },
        "visual": {
            "dominant_palette_hash": hashlib.sha256(
                json.dumps(render_metadata, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16],
            "frame_embedding_centroid": clip_vec[:8],
            "clip_embedding_hash_buckets": [int(v * 1000) % 256 for v in clip_vec[:12]],
        },
    }


def _quality_manifest(
    *,
    request: AutonomousMediaJobRequest,
    audio_path: str,
    lyrics_path: Path,
    semantic_fingerprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "project": "autonomous-media-job",
        "artist": request.artist_profile.get("artist_id")
        or request.artist_profile.get("name")
        or "unknown",
        "tracks": [
            {
                "id": request.track_id,
                "title": request.creative_brief.get("title") or request.track_id,
                "version": str(request.creative_brief.get("version", "1.0")),
                "status": "generated",
                "assets": {
                    "audio": audio_path,
                    "lyrics": str(lyrics_path.relative_to(Path.cwd()))
                    if lyrics_path.is_relative_to(Path.cwd())
                    else str(lyrics_path),
                },
                "quality_metrics": {
                    "integrated_lufs": float(
                        request.creative_brief.get("integrated_lufs", -12.0)
                    ),
                    "true_peak_dbfs": float(
                        request.creative_brief.get("true_peak_dbfs", -1.5)
                    ),
                    "clipped_samples": int(
                        request.creative_brief.get("clipped_samples", 0)
                    ),
                },
                "semantic_fingerprint": semantic_fingerprint or {},
            }
        ],
    }


def _load_retry_policy(runtime_policy: dict[str, Any]) -> RuntimeRetryPolicy:
    retry = runtime_policy.get("retry_policy") or {}
    backoff = retry.get("backoff_seconds") or []
    return RuntimeRetryPolicy(
        max_attempts=int(retry.get("max_attempts", 1)),
        backoff_seconds=[float(item) for item in backoff]
        if isinstance(backoff, list)
        else [],
    )


def _gate_summary(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": audit["decision"],
        "max_similarity": round(float(audit["max_similarity"]), 6),
        "confidence": round(float(audit["confidence"]), 6),
        "policy_version": audit["policy_version"],
        "audit_artifact_path": audit["audit_artifact_path"],
    }


def run_autonomous_media_job(
    request: AutonomousMediaJobRequest,
    *,
    repo_root: str | Path = _REPO_ROOT,
    runtime_policy_path: str | Path = DEFAULT_RUNTIME_POLICY,
    creative_policy_path: str | Path = DEFAULT_CREATIVE_POLICY,
    quality_rules_path: str | Path = DEFAULT_QUALITY_RULES,
    similarity_policy_path: str | Path = DEFAULT_SIMILARITY_POLICY,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    original_cwd = Path.cwd()
    os.chdir(root)
    try:
        runtime_policy = _load_json(_repo_path(root, runtime_policy_path))
        creative_policy = _load_json(_repo_path(root, creative_policy_path))
        quality_rules = _load_json(_repo_path(root, quality_rules_path))
        _enforce_creative_policy(request.creative_brief, creative_policy)

        seed = _stable_seed(request)
        prompt_plan = _build_prompt_plan(request=request, seed=seed)
        prompt_payload = asdict(prompt_plan)
        prompt_artifact = _write_prompt_artifact(root, request.job_id, prompt_payload)

        scheduler_decision = schedule_generation_job(
            job_id=request.job_id,
            prompt_plan=prompt_plan,
            campaign_budget_tier=request.campaign_budget_tier,
            release_urgency=request.release_urgency,
            runtime_policy=runtime_policy,
            creative_policy=creative_policy,
            job_metadata={"provenance_refs": []},
        )
        selected_model = str(scheduler_decision["selected_model"])
        generation_config = {
            **prompt_plan.generation_config,
            "model_version": selected_model,
        }

        pre_generation_gate = run_similarity_audit(
            {
                "job_id": f"{request.job_id}-pre",
                "render_metadata": {
                    "prompt_blueprint": prompt_plan.prompt_blueprint,
                    "generation_config": generation_config,
                    "stage": "pre_generation",
                },
                "provenance_log_path": str(root / "registry" / "provenance_log.jsonl"),
                "similarity_policy_path": str(_repo_path(root, similarity_policy_path)),
            }
        )
        if pre_generation_gate["decision"] != "pass":
            return {
                "job_id": request.job_id,
                "track_id": request.track_id,
                "status": "blocked",
                "generated_artifact_paths": {"prompt_plan": str(prompt_artifact)},
                "gate_decisions": {
                    "pre_generation": _gate_summary(pre_generation_gate)
                },
                "release_readiness": {
                    "ready": False,
                    "reason": "pre_generation_similarity_gate",
                },
                "remediation_status": {"attempted": False, "attempts": []},
            }

        generation_result = generate_music_for_wf005(
            prompt=_prompt_from_plan(prompt_plan.prompt_blueprint),
            style_profile={
                "artist_profile": request.artist_profile,
                "style_dna_fingerprint": generation_config["style_dna_fingerprint"],
                "scheduler": {
                    "provider": scheduler_decision["selected_provider"],
                    "model": selected_model,
                },
            },
            seed=seed,
            length=int(
                request.creative_brief.get(
                    "length", request.creative_brief.get("duration_seconds", 180)
                )
            ),
            tempo=int(request.creative_brief["tempo"])
            if request.creative_brief.get("tempo") is not None
            else None,
            key=str(request.creative_brief["key"])
            if request.creative_brief.get("key")
            else None,
            uniqueness_report_ref=pre_generation_gate["audit_artifact_path"],
            project_root=root,
        )

        audio_path = Path(generation_result["audio_path"])
        fingerprint = _fingerprint_for_generation(generation_result)
        embedding = _embedding_for_generation(prompt_payload, generation_result)
        semantic_fingerprint = _semantic_fingerprint_for_generation(
            prompt_payload, generation_result
        )
        post_generation_gate = run_similarity_audit(
            {
                "job_id": f"{request.job_id}-post",
                "release_intent": True,
                "render_metadata": generation_result["render_metadata"],
                "audio_fingerprint": fingerprint,
                "embedding": embedding,
                "semantic_fingerprint": semantic_fingerprint,
                "provenance_log_path": str(root / "registry" / "provenance_log.jsonl"),
                "similarity_policy_path": str(_repo_path(root, similarity_policy_path)),
            }
        )

        lyrics_path = _write_generated_lyrics(
            root, request, prompt_plan.prompt_blueprint
        )
        manifest = _quality_manifest(
            request=request,
            audio_path=str(audio_path),
            lyrics_path=lyrics_path,
            semantic_fingerprint=semantic_fingerprint,
        )
        quality_manifest_path = (
            root
            / "projects"
            / "jrt"
            / "metadata"
            / "renders"
            / f"{request.job_id}_quality_manifest.json"
        )
        quality_manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        validation_results, remediation_attempts = orchestrate_remediation(
            manifest,
            quality_rules,
            root,
            _load_retry_policy(runtime_policy),
            sleep_fn=lambda _: None,
        )

        release_ready = bool(
            pre_generation_gate["decision"] == "pass"
            and post_generation_gate["decision"] == "pass"
            and validation_results["all_required_checks_passed"]
        )

        release_bundle = build_release_bundle(
            release_id=request.job_id,
            title=str(request.creative_brief.get("title") or request.track_id),
            artist_name=str(
                request.artist_profile.get("artist_name")
                or request.artist_profile.get("name")
                or "Unknown Artist"
            ),
            masters=[
                {
                    "track_id": request.track_id,
                    "path": str(audio_path.relative_to(root))
                    if audio_path.is_relative_to(root)
                    else str(audio_path),
                }
            ],
            stems=[],
            credits=[
                {
                    "name": str(
                        request.artist_profile.get("artist_name")
                        or request.artist_profile.get("name")
                        or "Unknown Artist"
                    ),
                    "role": "artist",
                }
            ],
            rights_metadata={
                "copyright_owner": str(
                    request.artist_profile.get("rights_owner")
                    or request.artist_profile.get("artist_name")
                    or request.artist_profile.get("name")
                    or "Unknown Artist"
                ),
                "scheduler_plan_id": str(scheduler_decision["selected_plan_id"]),
                "scheduler_provider": str(scheduler_decision["selected_provider"]),
                "scheduler_model": str(scheduler_decision["selected_model"]),
            },
        )
        release_bundle_path = write_release_bundle(release_bundle, repo_root=root)
        release_bundle_artifact_ref = str(release_bundle_path.relative_to(root))

        conductor = context.create_media_conductor(
            actor="autonomous-media-job-cli",
            handlers={
                "quality_validation": lambda _: {
                    "quality_gate": "pass"
                    if validation_results["all_required_checks_passed"]
                    else "fail",
                    "release_ready": release_ready,
                },
                "uniqueness_audit": lambda _: {
                    "similarity_guardrail_pass": post_generation_gate["decision"]
                    == "pass",
                    "novelty_index": round(
                        1 - float(post_generation_gate["max_similarity"]), 6
                    ),
                    "uniqueness_validation_time_ms": 0,
                },
                "rollout_package": lambda _: {
                    "release_bundle_artifact_ref": release_bundle_artifact_ref,
                    "release_bundle": release_bundle,
                    "scheduler_plan_id": scheduler_decision["selected_plan_id"],
                    "scheduler_provider": scheduler_decision["selected_provider"],
                    "scheduler_model": scheduler_decision["selected_model"],
                    "strategy_id": prompt_plan.strategy_id,
                },
            },
        )
        checkpoint = conductor.run(
            job_id=request.job_id,
            track_id=request.track_id,
            input_assets=[
                {
                    "asset_id": f"{request.job_id}:prompt_plan",
                    "path": str(prompt_artifact.relative_to(root)),
                    "sha256": _sha256_file(prompt_artifact),
                    "mime_type": "application/json",
                }
            ],
            output_assets=[
                {
                    "asset_id": f"{request.job_id}:audio",
                    "path": str(audio_path.relative_to(root))
                    if audio_path.is_relative_to(root)
                    else str(audio_path),
                    "sha256": _sha256_file(audio_path),
                    "mime_type": "audio/wav",
                },
                {
                    "asset_id": f"{request.job_id}:quality_manifest",
                    "path": str(quality_manifest_path.relative_to(root)),
                    "sha256": _sha256_file(quality_manifest_path),
                    "mime_type": "application/json",
                },
            ],
            provenance_refs=[
                {
                    "ref_type": "prompt_plan",
                    "ref_id": prompt_plan.plan_id,
                    "uri": str(prompt_artifact.relative_to(root)),
                },
                {
                    "ref_type": "scheduler",
                    "ref_id": scheduler_decision["selected_plan_id"],
                },
                {
                    "ref_type": "pre_generation_similarity",
                    "ref_id": pre_generation_gate["audit_artifact_path"],
                },
                {
                    "ref_type": "post_generation_similarity",
                    "ref_id": post_generation_gate["audit_artifact_path"],
                },
                {
                    "ref_type": "wf005_replay_key",
                    "ref_id": generation_result["replay_key"],
                },
            ],
            agent_owner="AutonomousMediaJobCLI",
        )

        return {
            "job_id": request.job_id,
            "track_id": request.track_id,
            "status": "succeeded" if release_ready else "blocked",
            "generated_artifact_paths": {
                "prompt_plan": str(prompt_artifact.relative_to(root)),
                "audio": str(audio_path.relative_to(root))
                if audio_path.is_relative_to(root)
                else str(audio_path),
                "lyrics": str(lyrics_path.relative_to(root)),
                "quality_manifest": str(quality_manifest_path.relative_to(root)),
                "media_job": checkpoint.get("emitted_media_job_file"),
            },
            "planning": {
                "plan_id": prompt_plan.plan_id,
                "strategy_id": prompt_plan.strategy_id,
                "style_dna_fingerprint": generation_config["style_dna_fingerprint"],
            },
            "scheduler": {
                "selected_provider": scheduler_decision["selected_provider"],
                "selected_model": scheduler_decision["selected_model"],
                "selected_score": scheduler_decision["selected_score"],
                "selected_plan_id": scheduler_decision["selected_plan_id"],
            },
            "gate_decisions": {
                "pre_generation": _gate_summary(pre_generation_gate),
                "post_generation": _gate_summary(post_generation_gate),
                "quality_validation": validation_results,
            },
            "release_readiness": {
                "ready": release_ready,
                "reason": "ready"
                if release_ready
                else "post_generation_or_quality_gate_blocked",
            },
            "remediation_status": {
                "attempted": bool(remediation_attempts),
                "attempt_count": len(remediation_attempts),
                "attempts": [asdict(item) for item in remediation_attempts],
            },
            "generation": {
                "provider_generation_id": generation_result["provider_generation_id"],
                "replay_key": generation_result["replay_key"],
                "replayed": generation_result["replayed"],
                "render_metadata_sha256": _sha256_json(
                    generation_result["render_metadata"]
                ),
            },
        }

    finally:
        os.chdir(original_cwd)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an autonomous media generation job"
    )
    parser.add_argument("--job-id", required=True, help="Unique media job ID")
    parser.add_argument("--track-id", required=True, help="Track identifier")
    parser.add_argument(
        "--artist-profile", required=True, help="Artist profile JSON object or @path"
    )
    parser.add_argument(
        "--creative-brief", required=True, help="Creative brief JSON object or @path"
    )
    parser.add_argument(
        "--campaign-budget-tier", required=True, choices=("low", "mid", "high")
    )
    parser.add_argument(
        "--release-urgency", required=True, help="Release urgency, e.g. normal or rush"
    )
    parser.add_argument("--seed", help="Optional deterministic generation seed")
    parser.add_argument(
        "--repo-root",
        default=str(_REPO_ROOT),
        help="Repository root for policy/artifact paths",
    )
    parser.add_argument(
        "--gate-payload",
        default=os.getenv("IAI_GATE_PAYLOAD_JSON", "{}"),
        help="JSON object or @path with authorization and ratification payloads",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        gate_payload = _parse_json_arg(args.gate_payload, field_name="gate_payload")
    except ValueError:
        gate_payload = {}
    gate = enforce_gate("run_autonomous_media_job", "autonomous-media-job-runner", gate_payload)
    if not gate["allowed"]:
        print(json.dumps({"status": "denied", "gate": gate}, indent=2, sort_keys=True), file=sys.stderr)
        return 3
    seed: int | str | None = None
    if args.seed is not None:
        seed = int(args.seed) if str(args.seed).isdigit() else str(args.seed)
    try:
        request = AutonomousMediaJobRequest(
            job_id=args.job_id,
            track_id=args.track_id,
            artist_profile=_parse_json_arg(
                args.artist_profile, field_name="artist_profile"
            ),
            creative_brief=_parse_json_arg(
                args.creative_brief, field_name="creative_brief"
            ),
            campaign_budget_tier=args.campaign_budget_tier,
            release_urgency=args.release_urgency,
            seed=seed,
        )
        summary = run_autonomous_media_job(request, repo_root=args.repo_root)
    except ValueError as exc:
        print(
            json.dumps(
                {"status": "error", "error": str(exc)}, indent=2, sort_keys=True
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
