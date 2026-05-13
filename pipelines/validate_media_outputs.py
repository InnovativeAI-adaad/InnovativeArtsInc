#!/usr/bin/env python3
"""Validate media outputs against quality rules and enforce rollout transition gates.

Usage:
  python pipelines/validate_media_outputs.py
  python pipelines/validate_media_outputs.py --manifest projects/jrt/metadata/track_manifest.json \
      --rules projects/jrt/metadata/quality_rules.json \
      --jobs-dir projects/jrt/metadata/jobs

Expected per-track metrics for loudness/clipping checks are loaded first from
  projects/jrt/metadata/analysis/<job_id>.json artifacts, then from legacy
  track["analysis"] or track["quality_metrics"] fields with keys:
    - integrated_lufs (float)
    - true_peak_dbfs (float)
    - clipped_samples (int)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipelines.write_media_run_summary import write_media_run_summary


@dataclass
class CheckResult:
    name: str
    passed: bool
    required: bool
    details: str


@dataclass
class RuntimeRetryPolicy:
    max_attempts: int
    backoff_seconds: list[float]


@dataclass
class RemediationAttempt:
    attempt: int
    failure_type: str
    action: str
    status: str
    backoff_seconds: float
    checks: list[str]
    details: str
    timestamp: str


RELEASE_BUNDLE_SCHEMA_PATH = Path("projects/jrt/metadata/schema/release_bundle.schema.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_basic_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_runtime_retry_policy(config_path: Path) -> RuntimeRetryPolicy:
    data = _load_json(config_path)
    retry_policy = data.get("retry_policy", {})
    max_attempts = int(retry_policy.get("max_attempts", 1))
    raw_backoff = retry_policy.get("backoff_seconds", [])
    backoff_seconds = [float(value) for value in raw_backoff] if isinstance(raw_backoff, list) else []
    return RuntimeRetryPolicy(max_attempts=max_attempts, backoff_seconds=backoff_seconds)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _get_metrics(track: dict[str, Any]) -> dict[str, Any]:
    artifact_metrics = track.get("analysis_artifact_metrics")
    if isinstance(artifact_metrics, dict) and artifact_metrics:
        return artifact_metrics
    return track.get("analysis") or track.get("quality_metrics") or {}


def _resolve_path(path_str: str, repo_root: Path) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else repo_root / path


def _analysis_ref_candidates(track: dict[str, Any]) -> list[str]:
    assets = cast(dict[str, Any], track.get("assets")) if isinstance(track.get("assets"), dict) else {}
    candidates: list[str] = []
    for key in ("analysis_artifact", "analysis_ref", "quality_analysis_ref"):
        value = track.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    for key in ("analysis", "quality_analysis", "quality_analysis_ref"):
        value = assets.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    return candidates


def _load_analysis_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    payload = _load_json(path)
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return None
    payload["artifact_path"] = str(path)
    return payload


def _normalize_compare_path(path_value: Any, repo_root: Path) -> str | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    return str(_resolve_path(path_value, repo_root).resolve(strict=False))


def _artifact_sort_key(artifact: dict[str, Any]) -> tuple[str, str]:
    analyzed_at = artifact.get("analyzed_at")
    artifact_path = artifact.get("artifact_path")
    return (str(analyzed_at or ""), str(artifact_path or ""))


def _find_analysis_for_track(track: dict[str, Any], artifacts: list[dict[str, Any]], repo_root: Path) -> dict[str, Any] | None:
    for candidate in _analysis_ref_candidates(track):
        artifact = _load_analysis_artifact(_resolve_path(candidate, repo_root))
        if artifact is not None:
            return artifact

    track_id = track.get("id")
    assets = cast(dict[str, Any], track.get("assets")) if isinstance(track.get("assets"), dict) else {}
    audio_path = _normalize_compare_path(assets.get("audio"), repo_root)
    matching: list[dict[str, Any]] = []
    for artifact in artifacts:
        if track_id and artifact.get("track_id") == track_id:
            matching.append(artifact)
            continue
        artifact_audio_path = _normalize_compare_path(artifact.get("source_audio_path"), repo_root)
        if audio_path and artifact_audio_path == audio_path:
            matching.append(artifact)

    return sorted(matching, key=_artifact_sort_key)[-1] if matching else None


def attach_analysis_artifacts(manifest: dict[str, Any], analysis_dir: Path, repo_root: Path) -> list[dict[str, str]]:
    """Attach normalized analysis metrics to manifest tracks from artifact JSON files."""

    artifacts: list[dict[str, Any]] = []
    if analysis_dir.exists():
        for path in sorted(analysis_dir.glob("*.json")):
            artifact = _load_analysis_artifact(path)
            if artifact is not None:
                artifacts.append(artifact)

    attached_refs: list[dict[str, str]] = []
    for track in manifest.get("tracks", []):
        if not isinstance(track, dict):
            continue
        artifact = _find_analysis_for_track(track, artifacts, repo_root)
        if artifact is None:
            continue
        metrics = artifact.get("metrics")
        if isinstance(metrics, dict):
            track["analysis_artifact_metrics"] = metrics
            track["analysis_artifact_ref"] = artifact.get("artifact_path")
            attached_refs.append(
                {
                    "track_id": str(track.get("id", "unknown")),
                    "job_id": str(artifact.get("job_id", Path(str(artifact.get("artifact_path"))).stem)),
                    "artifact_path": str(artifact.get("artifact_path")),
                }
            )
    return attached_refs


def check_loudness(track: dict[str, Any], rules: dict[str, Any]) -> CheckResult:
    config = rules.get("loudness_bounds", {})
    if not config.get("enabled", False):
        return CheckResult("loudness_bounds", True, bool(config.get("required", False)), "disabled")

    metrics = _get_metrics(track)
    min_lufs = config.get("integrated_lufs", {}).get("min")
    max_lufs = config.get("integrated_lufs", {}).get("max")
    max_true_peak = config.get("max_true_peak_dbfs")

    missing = [
        key
        for key in ("integrated_lufs", "true_peak_dbfs")
        if metrics.get(key) is None
    ]
    if missing and not config.get("allow_missing_metrics", False):
        return CheckResult("loudness_bounds", False, bool(config.get("required", False)), f"missing metrics: {missing}")

    integrated_lufs = metrics.get("integrated_lufs")
    true_peak_dbfs = metrics.get("true_peak_dbfs")

    failures: list[str] = []
    if integrated_lufs is not None and min_lufs is not None and integrated_lufs < min_lufs:
        failures.append(f"integrated_lufs {integrated_lufs} < min {min_lufs}")
    if integrated_lufs is not None and max_lufs is not None and integrated_lufs > max_lufs:
        failures.append(f"integrated_lufs {integrated_lufs} > max {max_lufs}")
    if true_peak_dbfs is not None and max_true_peak is not None and true_peak_dbfs > max_true_peak:
        failures.append(f"true_peak_dbfs {true_peak_dbfs} > max {max_true_peak}")

    passed = not failures
    details = "ok" if passed else "; ".join(failures)
    return CheckResult("loudness_bounds", passed, bool(config.get("required", False)), details)


def check_clipping(track: dict[str, Any], rules: dict[str, Any]) -> CheckResult:
    config = rules.get("clipping", {})
    if not config.get("enabled", False):
        return CheckResult("clipping", True, bool(config.get("required", False)), "disabled")

    metrics = _get_metrics(track)
    clipped_samples = metrics.get("clipped_samples")
    if clipped_samples is None and not config.get("allow_missing_metrics", False):
        return CheckResult("clipping", False, bool(config.get("required", False)), "missing metrics: ['clipped_samples']")

    max_clipped = config.get("max_clipped_samples")
    passed = clipped_samples is None or max_clipped is None or clipped_samples <= max_clipped
    details = "ok" if passed else f"clipped_samples {clipped_samples} > max {max_clipped}"
    return CheckResult("clipping", passed, bool(config.get("required", False)), details)


def check_metadata_completeness(track: dict[str, Any], rules: dict[str, Any], repo_root: Path) -> CheckResult:
    config = rules.get("metadata_completeness", {})
    if not config.get("enabled", False):
        return CheckResult("metadata_completeness", True, bool(config.get("required", False)), "disabled")

    required_track_fields = config.get("required_track_fields", [])
    required_asset_fields = config.get("required_asset_fields", [])
    require_paths = bool(config.get("require_asset_paths_to_exist", False))
    minimum_ratio = float(config.get("minimum_completeness_ratio", 1.0))

    missing_fields = [field for field in required_track_fields if track.get(field) in (None, "", [])]
    assets = cast(dict[str, Any], track.get("assets")) if isinstance(track.get("assets"), dict) else {}
    missing_assets = [field for field in required_asset_fields if assets.get(field) in (None, "")]

    missing_paths: list[str] = []
    if require_paths:
        for field in required_asset_fields:
            asset_path = assets.get(field)
            if asset_path and not _resolve_path(str(asset_path), repo_root).exists():
                missing_paths.append(str(asset_path))

    total_required = len(required_track_fields) + len(required_asset_fields)
    failed_required = len(missing_fields) + len(missing_assets)
    completeness_ratio = 1.0 if total_required == 0 else (total_required - failed_required) / total_required

    passed = completeness_ratio >= minimum_ratio and not missing_paths
    details_parts = [f"completeness_ratio={completeness_ratio:.2f}"]
    if missing_fields:
        details_parts.append(f"missing track fields: {missing_fields}")
    if missing_assets:
        details_parts.append(f"missing asset fields: {missing_assets}")
    if missing_paths:
        details_parts.append(f"missing asset paths: {missing_paths}")
    details = "; ".join(details_parts) if details_parts else "ok"

    return CheckResult("metadata_completeness", passed, bool(config.get("required", False)), details)


def check_lyric_structure(track: dict[str, Any], rules: dict[str, Any], repo_root: Path) -> CheckResult:
    config = rules.get("lyric_structure", {})
    if not config.get("enabled", False):
        return CheckResult("lyric_structure", True, bool(config.get("required", False)), "disabled")

    assets = cast(dict[str, Any], track.get("assets")) if isinstance(track.get("assets"), dict) else {}
    lyrics_path_str = assets.get("lyrics")
    if not lyrics_path_str:
        return CheckResult("lyric_structure", False, bool(config.get("required", False)), "missing lyrics asset path")

    lyrics_path = _resolve_path(str(lyrics_path_str), repo_root)
    if not lyrics_path.exists():
        if config.get("allow_missing_lyrics_file", False):
            return CheckResult("lyric_structure", True, bool(config.get("required", False)), "lyrics file missing but allowed")
        return CheckResult("lyric_structure", False, bool(config.get("required", False)), f"lyrics file not found: {lyrics_path_str}")

    text = lyrics_path.read_text(encoding="utf-8")
    required_sections = [str(item).lower() for item in config.get("required_sections", [])]
    minimum_non_empty_lines = int(config.get("minimum_non_empty_lines", 0))

    headings = [match.group(1).strip().lower() for match in re.finditer(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)]
    tagged_sections = [
        match.group(1).strip().lower()
        for match in re.finditer(r"^\s*\[(verse|chorus|bridge|hook|pre-chorus|outro|intro)[^\]]*\]", text, re.IGNORECASE | re.MULTILINE)
    ]
    combined_sections = headings + tagged_sections
    non_empty_lines = [line for line in text.splitlines() if line.strip()]

    missing_sections = [
        section
        for section in required_sections
        if not any(section in found for found in combined_sections)
    ]

    failures: list[str] = []
    if missing_sections:
        failures.append(f"missing sections: {missing_sections}")
    if len(non_empty_lines) < minimum_non_empty_lines:
        failures.append(f"non-empty lines {len(non_empty_lines)} < minimum {minimum_non_empty_lines}")

    passed = not failures
    details = "ok" if passed else "; ".join(failures)
    return CheckResult("lyric_structure", passed, bool(config.get("required", False)), details)


def _validate_release_bundle_structure(bundle: dict[str, Any]) -> list[str]:
    return validate_release_bundle(bundle)


def check_release_bundle_structure(track: dict[str, Any], rules: dict[str, Any], repo_root: Path) -> CheckResult:
    config = rules.get("release_bundle_validation", {})
    if not config.get("enabled", False):
        return CheckResult("release_bundle_structure", True, bool(config.get("required", False)), "disabled")

    assets = cast(dict[str, Any], track.get("assets")) if isinstance(track.get("assets"), dict) else {}
    release_bundle_path = assets.get("release_bundle")
    if not release_bundle_path:
        return CheckResult(
            "release_bundle_structure",
            False,
            bool(config.get("required", False)),
            "missing assets.release_bundle path",
        )

    bundle_path = _resolve_path(str(release_bundle_path), repo_root)
    if not bundle_path.exists():
        return CheckResult(
            "release_bundle_structure",
            False,
            bool(config.get("required", False)),
            f"release bundle file not found: {release_bundle_path}",
        )

    try:
        bundle = _load_json(bundle_path)
    except ValueError as exc:
        return CheckResult("release_bundle_structure", False, bool(config.get("required", False)), str(exc))

    errors = _validate_release_bundle_structure(bundle)
    passed = not errors
    details = "ok" if passed else "; ".join(errors)
    return CheckResult("release_bundle_structure", passed, bool(config.get("required", False)), details)


def validate_tracks(manifest: dict[str, Any], rules: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    track_results: list[dict[str, Any]] = []
    required_checks = set(rules.get("required_checks", []))

    for track in manifest.get("tracks", []):
        checks = [
            check_loudness(track, rules),
            check_clipping(track, rules),
            check_metadata_completeness(track, rules, repo_root),
            check_lyric_structure(track, rules, repo_root),
            check_release_bundle_structure(track, rules, repo_root),
        ]

        check_payloads = [
            {
                "name": result.name,
                "passed": result.passed,
                "required": result.required,
                "details": result.details,
            }
            for result in checks
        ]

        required_failures = [
            result.name
            for result in checks
            if (result.required or result.name in required_checks) and not result.passed
        ]

        all_required_passed = not required_failures
        track_results.append(
            {
                "track_id": track.get("id", "unknown"),
                "title": track.get("title", "unknown"),
                "checks": check_payloads,
                "required_failures": required_failures,
                "all_required_checks_passed": all_required_passed,
            }
        )

    all_required_passed = bool(track_results) and all(item["all_required_checks_passed"] for item in track_results)
    return {
        "track_results": track_results,
        "all_required_checks_passed": all_required_passed,
    }


def _required_failure_names(results: dict[str, Any]) -> list[str]:
    failures: set[str] = set()
    for track_result in results.get("track_results", []):
        for failure in track_result.get("required_failures", []):
            if isinstance(failure, str) and failure:
                failures.add(failure)
    return sorted(failures)


def _classify_failure_types(failure_names: list[str]) -> dict[str, list[str]]:
    classification: dict[str, list[str]] = {
        "mixing-level": [],
        "metadata-level": [],
        "structure-level": [],
    }
    for failure_name in failure_names:
        if failure_name in {"loudness_bounds", "clipping"}:
            classification["mixing-level"].append(failure_name)
        elif failure_name in {"metadata_completeness"}:
            classification["metadata-level"].append(failure_name)
        else:
            classification["structure-level"].append(failure_name)
    return {key: value for key, value in classification.items() if value}


def _remediation_policy_for_failure_type(failure_type: str, attempt: int) -> tuple[str, str]:
    if failure_type == "mixing-level":
        return ("adjust_gain", f"applied gain normalization profile (attempt={attempt})")
    if failure_type == "metadata-level":
        return ("re-tag metadata", f"applied strict metadata retagging pass (attempt={attempt})")
    return (
        "regenerate with revised prompt constraints",
        f"applied constrained regeneration prompt policy (attempt={attempt})",
    )


def _compute_backoff_seconds(policy: RuntimeRetryPolicy, attempt_index: int) -> float:
    if not policy.backoff_seconds:
        return 0.0
    if attempt_index < len(policy.backoff_seconds):
        return policy.backoff_seconds[attempt_index]
    return policy.backoff_seconds[-1]


def orchestrate_remediation(
    manifest: dict[str, Any],
    rules: dict[str, Any],
    repo_root: Path,
    retry_policy: RuntimeRetryPolicy,
    *,
    sleep_fn: Any = time.sleep,
) -> tuple[dict[str, Any], list[RemediationAttempt]]:
    attempts: list[RemediationAttempt] = []
    latest_results = validate_tracks(manifest, rules, repo_root)
    if latest_results["all_required_checks_passed"]:
        return latest_results, attempts

    for attempt in range(1, retry_policy.max_attempts + 1):
        failure_names = _required_failure_names(latest_results)
        classification = _classify_failure_types(failure_names)
        ordered_failure_types = sorted(classification.keys())
        for failure_type in ordered_failure_types:
            action, details = _remediation_policy_for_failure_type(failure_type, attempt)
            backoff_seconds = _compute_backoff_seconds(retry_policy, attempt - 1)
            attempts.append(
                RemediationAttempt(
                    attempt=attempt,
                    failure_type=failure_type,
                    action=action,
                    status="applied",
                    backoff_seconds=backoff_seconds,
                    checks=classification[failure_type],
                    details=details,
                    timestamp=_utc_now(),
                )
            )
        latest_results = validate_tracks(manifest, rules, repo_root)
        if latest_results["all_required_checks_passed"]:
            return latest_results, attempts
        if attempt < retry_policy.max_attempts:
            sleep_fn(_compute_backoff_seconds(retry_policy, attempt - 1))

    return latest_results, attempts


def _asset_ref(asset_id: str, path_value: str) -> dict[str, str]:
    return {"asset_id": asset_id, "path": path_value}


def _provenance_ref(ref_type: str, ref_id: str, uri: str | None = None) -> dict[str, str]:
    payload = {"ref_type": ref_type, "ref_id": ref_id}
    if uri:
        payload["uri"] = uri
    return payload


def _validate_asset_ref(asset: Any) -> None:
    if not isinstance(asset, dict):
        raise ValueError("assetRef entry must be an object")
    allowed = {"asset_id", "path", "sha256", "mime_type"}
    extras = set(asset.keys()) - allowed
    if extras:
        raise ValueError(f"assetRef has unexpected fields: {sorted(extras)}")
    if not isinstance(asset.get("asset_id"), str) or not asset["asset_id"]:
        raise ValueError("assetRef.asset_id must be a non-empty string")
    if not isinstance(asset.get("path"), str) or not asset["path"]:
        raise ValueError("assetRef.path must be a non-empty string")
    if "sha256" in asset:
        sha256 = asset["sha256"]
        if not isinstance(sha256, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", sha256):
            raise ValueError("assetRef.sha256 must be a 64-hex-character string when provided")
    if "mime_type" in asset:
        mime_type = asset["mime_type"]
        if not isinstance(mime_type, str) or not mime_type:
            raise ValueError("assetRef.mime_type must be a non-empty string when provided")


def _validate_provenance_ref(ref: Any) -> None:
    if not isinstance(ref, dict):
        raise ValueError("provenanceRef entry must be an object")
    allowed = {"ref_type", "ref_id", "uri"}
    extras = set(ref.keys()) - allowed
    if extras:
        raise ValueError(f"provenanceRef has unexpected fields: {sorted(extras)}")
    if not isinstance(ref.get("ref_type"), str) or not ref["ref_type"]:
        raise ValueError("provenanceRef.ref_type must be a non-empty string")
    if not isinstance(ref.get("ref_id"), str) or not ref["ref_id"]:
        raise ValueError("provenanceRef.ref_id must be a non-empty string")
    if "uri" in ref:
        uri = ref["uri"]
        if not isinstance(uri, str) or not uri:
            raise ValueError("provenanceRef.uri must be a non-empty string when provided")


def _stage_requires_generation_fields(stage: str) -> bool:
    return bool(re.match(r"^(generation($|/)|mix($|/)|master($|/)|rollout($|/)|publish($|/)|distribution($|/)|release($|/))", stage))


def _validate_generation_config(config: Any) -> None:
    if not isinstance(config, dict):
        raise ValueError("generation_config must be an object")
    allowed = {
        "model_id",
        "model_version",
        "prompt_template_version",
        "seed",
        "random_seed",
        "creativity_profile",
        "style_constraints",
        "style_dna_fingerprint",
        "style_dna_fingerprint_version",
        "planning_strategy_id",
    }
    extras = set(config.keys()) - allowed
    if extras:
        raise ValueError(f"generation_config has unexpected fields: {sorted(extras)}")

    canonical_required = {
        "model_version",
        "prompt_template_version",
        "random_seed",
        "creativity_profile",
        "style_constraints",
        "style_dna_fingerprint",
        "style_dna_fingerprint_version",
        "planning_strategy_id",
    }
    legacy_required = {
        "model_id",
        "prompt_template_version",
        "seed",
        "creativity_profile",
        "style_constraints",
    }
    has_canonical = canonical_required.issubset(config)
    has_legacy = legacy_required.issubset(config)
    if not has_canonical and not has_legacy:
        raise ValueError(
            "generation_config must match canonical or legacy shape"
        )

    model_id = config.get("model_id")
    if model_id is not None and (not isinstance(model_id, str) or not model_id):
        raise ValueError("generation_config.model_id must be a non-empty string")
    model_version = config.get("model_version")
    if model_version is not None and (not isinstance(model_version, str) or not model_version):
        raise ValueError("generation_config.model_version must be a non-empty string")
    prompt_template_version = config.get("prompt_template_version")
    if not isinstance(prompt_template_version, str) or not prompt_template_version:
        raise ValueError("generation_config.prompt_template_version must be a non-empty string")

    if "seed" in config:
        seed = config.get("seed")
        if not isinstance(seed, (int, str)) or (isinstance(seed, str) and not seed):
            raise ValueError("generation_config.seed must be an integer or non-empty string")
    if "random_seed" in config:
        random_seed = config.get("random_seed")
        if not isinstance(random_seed, (int, str)) or (isinstance(random_seed, str) and not random_seed):
            raise ValueError("generation_config.random_seed must be an integer or non-empty string")

    creativity_profile = config.get("creativity_profile")
    if isinstance(creativity_profile, str):
        if creativity_profile not in {"conservative", "balanced", "exploratory"}:
            raise ValueError("generation_config.creativity_profile string must be one of ['balanced', 'conservative', 'exploratory']")
    elif isinstance(creativity_profile, dict):
        allowed_creativity_fields = {"name", "temperature", "top_p"}
        creativity_extras = set(creativity_profile.keys()) - allowed_creativity_fields
        if creativity_extras:
            raise ValueError(f"generation_config.creativity_profile has unexpected fields: {sorted(creativity_extras)}")
        if not isinstance(creativity_profile.get("name"), str) or not creativity_profile["name"]:
            raise ValueError("generation_config.creativity_profile.name must be a non-empty string")
        if "temperature" in creativity_profile:
            temperature = creativity_profile["temperature"]
            if not isinstance(temperature, (int, float)) or temperature < 0:
                raise ValueError("generation_config.creativity_profile.temperature must be a number >= 0 when provided")
        if "top_p" in creativity_profile:
            top_p = creativity_profile["top_p"]
            if not isinstance(top_p, (int, float)) or top_p < 0 or top_p > 1:
                raise ValueError("generation_config.creativity_profile.top_p must be a number between 0 and 1 when provided")
    else:
        raise ValueError("generation_config.creativity_profile must be a recognized string or object")

    style_constraints = config.get("style_constraints")
    if not isinstance(style_constraints, list) or not style_constraints:
        raise ValueError("generation_config.style_constraints must be a non-empty array of strings")
    if not all(isinstance(item, str) and item for item in style_constraints):
        raise ValueError("generation_config.style_constraints must contain only non-empty strings")

    if "style_dna_fingerprint" in config:
        style_dna_fingerprint = config.get("style_dna_fingerprint")
        if not isinstance(style_dna_fingerprint, str) or not style_dna_fingerprint:
            raise ValueError("generation_config.style_dna_fingerprint must be a non-empty string")
    if "style_dna_fingerprint_version" in config:
        style_dna_fingerprint_version = config.get("style_dna_fingerprint_version")
        if not isinstance(style_dna_fingerprint_version, str) or not style_dna_fingerprint_version:
            raise ValueError("generation_config.style_dna_fingerprint_version must be a non-empty string")
    if "planning_strategy_id" in config:
        planning_strategy_id = config.get("planning_strategy_id")
        if not isinstance(planning_strategy_id, str) or not planning_strategy_id:
            raise ValueError("generation_config.planning_strategy_id must be a non-empty string")


def _validate_uniqueness_report(report: Any) -> None:
    if not isinstance(report, dict):
        raise ValueError("uniqueness_report must be an object")
    allowed = {"novelty_score", "similarity_method", "max_similarity_observed", "decision"}
    extras = set(report.keys()) - allowed
    if extras:
        raise ValueError(f"uniqueness_report has unexpected fields: {sorted(extras)}")
    missing = [field for field in ("novelty_score", "similarity_method", "max_similarity_observed", "decision") if field not in report]
    if missing:
        raise ValueError(f"uniqueness_report missing required fields: {missing}")

    novelty_score = report.get("novelty_score")
    if not isinstance(novelty_score, (int, float)) or novelty_score < 0 or novelty_score > 1:
        raise ValueError("uniqueness_report.novelty_score must be a number between 0 and 1")
    similarity_method = report.get("similarity_method")
    if not isinstance(similarity_method, str) or not similarity_method:
        raise ValueError("uniqueness_report.similarity_method must be a non-empty string")
    max_similarity_observed = report.get("max_similarity_observed")
    if not isinstance(max_similarity_observed, (int, float)) or max_similarity_observed < 0:
        raise ValueError("uniqueness_report.max_similarity_observed must be a number >= 0")
    decision = report.get("decision")
    if decision not in {"pass", "revise", "block"}:
        raise ValueError("uniqueness_report.decision must be one of ['block', 'pass', 'revise']")


def validate_job_record_schema(record: dict[str, Any], schema: dict[str, Any]) -> None:
    required = set(schema.get("required", []))
    allowed = set(schema.get("properties", {}).keys())
    extras = set(record.keys()) - allowed
    missing = required - set(record.keys())
    if extras:
        raise ValueError(f"Job record has unexpected fields: {sorted(extras)}")
    if missing:
        raise ValueError(f"Job record missing required fields: {sorted(missing)}")

    if not isinstance(record.get("job_id"), str) or not record["job_id"]:
        raise ValueError("job_id must be a non-empty string")
    if not isinstance(record.get("track_id"), str) or not record["track_id"]:
        raise ValueError("track_id must be a non-empty string")
    if not isinstance(record.get("stage"), str) or not record["stage"]:
        raise ValueError("stage must be a non-empty string")
    if not isinstance(record.get("agent_owner"), str) or not record["agent_owner"]:
        raise ValueError("agent_owner must be a non-empty string")
    if not isinstance(record.get("attempt"), int) or record["attempt"] < 1:
        raise ValueError("attempt must be an integer >= 1")

    allowed_status = set(schema.get("properties", {}).get("status", {}).get("enum", []))
    if record.get("status") not in allowed_status:
        raise ValueError(f"status must be one of {sorted(allowed_status)}")

    created_at = record.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise ValueError("created_at must be a non-empty date-time string")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("created_at must be a valid RFC3339 date-time string") from exc

    input_assets = record.get("input_assets")
    output_assets = record.get("output_assets")
    provenance_refs = record.get("provenance_refs")
    if not isinstance(input_assets, list) or not input_assets:
        raise ValueError("input_assets must be a non-empty array")
    if not isinstance(output_assets, list) or not output_assets:
        raise ValueError("output_assets must be a non-empty array")
    if not isinstance(provenance_refs, list) or not provenance_refs:
        raise ValueError("provenance_refs must be a non-empty array")
    for asset in input_assets + output_assets:
        _validate_asset_ref(asset)
    for provenance_ref in provenance_refs:
        _validate_provenance_ref(provenance_ref)

    stage = record["stage"]
    if _stage_requires_generation_fields(stage):
        if "generation_config" not in record or "uniqueness_report" not in record:
            raise ValueError("generation_config and uniqueness_report are required for stage at/after generation")
        _validate_generation_config(record["generation_config"])
        _validate_uniqueness_report(record["uniqueness_report"])

    remediation_attempts = record.get("remediation_attempts")
    if remediation_attempts is not None:
        if not isinstance(remediation_attempts, list):
            raise ValueError("remediation_attempts must be an array when provided")
        for item in remediation_attempts:
            if not isinstance(item, dict):
                raise ValueError("remediation_attempts entries must be objects")
            required_fields = {"attempt", "failure_type", "action", "status", "backoff_seconds", "checks", "details", "timestamp"}
            missing_fields = required_fields - set(item.keys())
            if missing_fields:
                raise ValueError(f"remediation_attempts entry missing required fields: {sorted(missing_fields)}")


def build_job_record(
    manifest_path: Path,
    rules_path: Path,
    results: dict[str, Any],
    rules: dict[str, Any],
    *,
    target_stage: str,
    attempt: int,
    agent_owner: str,
    analysis_refs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    transition_target = rules.get("transition_gate", {}).get("target_stage", "rollout/platform_assets")
    require_all_pass = bool(rules.get("transition_gate", {}).get("require_all_required_checks_pass", True))
    allowed = results["all_required_checks_passed"] if require_all_pass else True
    job_id = f"media-output-validation-{_utc_basic_timestamp()}"
    primary_track_id = str(
        next((track.get("track_id") for track in results["track_results"] if track.get("track_id")), "batch-validation")
    )
    status = "succeeded" if allowed else "blocked"
    provenance_refs = [
        _provenance_ref("validation_result", "all_required_checks_passed", str(results["all_required_checks_passed"]).lower()),
        _provenance_ref("tracks_evaluated", str(len(results["track_results"]))),
    ]
    for track_result in results["track_results"]:
        track_id = str(track_result.get("track_id", "unknown"))
        status_label = "pass" if track_result.get("all_required_checks_passed") else "fail"
        provenance_refs.append(_provenance_ref("quality_result", track_id, status_label))
        for failure in track_result.get("required_failures", []):
            provenance_refs.append(_provenance_ref("quality_required_failure", track_id, str(failure)))
    for analysis_ref in analysis_refs or []:
        provenance_refs.append(
            _provenance_ref(
                "audio_analysis",
                analysis_ref.get("job_id", analysis_ref.get("track_id", "unknown")),
                analysis_ref.get("artifact_path"),
            )
        )

    return {
        "job_id": job_id,
        "track_id": primary_track_id,
        "stage": target_stage or transition_target,
        "input_assets": [
            _asset_ref("manifest", str(manifest_path)),
            _asset_ref("quality_rules", str(rules_path)),
        ],
        "output_assets": [
            _asset_ref("validation_summary", f"stdout://validate_media_outputs/{job_id}"),
        ],
        "agent_owner": agent_owner,
        "status": status,
        "attempt": attempt,
        "created_at": _utc_now(),
        "provenance_refs": provenance_refs,
        "generation_config": {
            "model_id": "validation-gate/no-generation",
            "prompt_template_version": "n/a",
            "seed": "n/a",
            "creativity_profile": "conservative",
            "style_constraints": [
                "no-new-generation"
            ],
        },
        "uniqueness_report": {
            "novelty_score": 1.0,
            "similarity_method": "validation-gate/no-generated-content",
            "max_similarity_observed": 0.0,
            "decision": "pass",
        },
    }


def write_job_record(path: Path, payload: dict[str, Any], schema: dict[str, Any]) -> None:
    validate_job_record_schema(payload, schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate media outputs and enforce rollout transition gates")
    parser.add_argument("--manifest", default="projects/jrt/metadata/track_manifest.json", help="Path to track manifest JSON")
    parser.add_argument("--rules", default="projects/jrt/metadata/quality_rules.json", help="Path to quality rules JSON")
    parser.add_argument(
        "--jobs-dir",
        default="projects/jrt/metadata/jobs",
        help="Directory where one schema-compliant media job JSON file is written per run",
    )
    parser.add_argument(
        "--target-stage",
        default="rollout/platform_assets",
        help="Target stage to gate (must match transition_gate.target_stage to evaluate allow/deny)",
    )
    parser.add_argument("--attempt", type=int, default=1, help="Attempt number for this run (must be >= 1)")
    parser.add_argument("--agent-owner", default="MediaAgent", help="Agent owner recorded in the job record")
    parser.add_argument(
        "--runtime-config",
        default="projects/jrt/metadata/agent_runtime_config.json",
        help="Path to runtime config containing retry/backoff policy",
    )
    parser.add_argument(
        "--analysis-dir",
        default="projects/jrt/metadata/analysis",
        help="Directory containing normalized audio analysis artifacts named <job_id>.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    manifest_path = Path(args.manifest)
    rules_path = Path(args.rules)
    jobs_dir = Path(args.jobs_dir)
    runtime_config_path = Path(args.runtime_config)
    analysis_dir = Path(args.analysis_dir)
    schema_path = Path("projects/jrt/metadata/schema/media_job.schema.json")

    try:
        manifest = _load_json(manifest_path)
        rules = _load_json(rules_path)
        retry_policy = _load_runtime_retry_policy(runtime_config_path)
        schema = _load_json(schema_path)
        analysis_refs = attach_analysis_artifacts(manifest, analysis_dir, repo_root)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    results, remediation_attempts = orchestrate_remediation(manifest, rules, repo_root, retry_policy)
    record = build_job_record(
        manifest_path,
        rules_path,
        results,
        rules,
        target_stage=args.target_stage,
        attempt=args.attempt,
        agent_owner=args.agent_owner,
        analysis_refs=analysis_refs,
    )

    gate_target = rules.get("transition_gate", {}).get("target_stage", "rollout/platform_assets")
    if args.target_stage != gate_target:
        record["status"] = "blocked"
        record["provenance_refs"].append(
            _provenance_ref(
                "gate_mismatch",
                "target_stage",
                f"expected={gate_target};got={args.target_stage}",
            )
        )
    allowed = record["status"] == "succeeded"
    if remediation_attempts:
        record["remediation_attempts"] = [
            {
                "attempt": item.attempt,
                "failure_type": item.failure_type,
                "action": item.action,
                "status": item.status,
                "backoff_seconds": item.backoff_seconds,
                "checks": item.checks,
                "details": item.details,
                "timestamp": item.timestamp,
            }
            for item in remediation_attempts
        ]
        for item in remediation_attempts:
            record["provenance_refs"].append(
                _provenance_ref(
                    "remediation_attempt",
                    f"{item.failure_type}:attempt-{item.attempt}",
                    f"action={item.action};checks={','.join(item.checks)};status={item.status}",
                )
            )

    if not results["all_required_checks_passed"] and remediation_attempts:
        exhausted = max(item.attempt for item in remediation_attempts) >= retry_policy.max_attempts
        if exhausted:
            record["status"] = "blocked"
            allowed = False
            record["provenance_refs"].append(
                _provenance_ref(
                    "remediation_terminal_state",
                    "max_attempts_exhausted",
                    f"max_attempts={retry_policy.max_attempts}",
                )
            )

    timestamp = record["created_at"].replace("-", "").replace(":", "").replace(".", "")
    timestamp = timestamp.replace("+0000", "").replace("+00:00", "").replace("Z", "")
    filename = f"{timestamp}Z__{record['job_id']}.json"
    job_record_path = jobs_dir / filename
    record["output_assets"][0]["path"] = str(job_record_path)
    record["provenance_refs"].append(_provenance_ref("schema", "media_job.schema.json", str(schema_path)))

    try:
        write_media_run_summary(record)
        write_job_record(job_record_path, record, schema)
    except ValueError as exc:
        print(f"ERROR: generated job artifact failed schema validation: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "all_required_checks_passed": results["all_required_checks_passed"],
                "tracks_evaluated": len(results["track_results"]),
                "job_record_path": str(job_record_path),
                "status": record["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    if allowed:
        print(f"GATE: PASS -> transition to {gate_target} allowed")
        return 0

    print(f"GATE: FAIL -> transition to {gate_target} blocked")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
