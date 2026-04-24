#!/usr/bin/env python3
"""Validate media outputs against quality rules and enforce rollout transition gates.

Usage:
  python pipelines/validate_media_outputs.py
  python pipelines/validate_media_outputs.py --manifest projects/jrt/metadata/track_manifest.json \
      --rules projects/jrt/metadata/quality_rules.json \
      --job-records projects/jrt/metadata/job_records.jsonl

Expected optional per-track metrics for loudness/clipping checks:
  track["analysis"] or track["quality_metrics"] with keys:
    - integrated_lufs (float)
    - true_peak_dbfs (float)
    - clipped_samples (int)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    name: str
    passed: bool
    required: bool
    details: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _get_metrics(track: dict[str, Any]) -> dict[str, Any]:
    return track.get("analysis") or track.get("quality_metrics") or {}


def _resolve_path(path_str: str, repo_root: Path) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else repo_root / path


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
    assets = track.get("assets") if isinstance(track.get("assets"), dict) else {}
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

    assets = track.get("assets") if isinstance(track.get("assets"), dict) else {}
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


def validate_tracks(manifest: dict[str, Any], rules: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    track_results: list[dict[str, Any]] = []
    required_checks = set(rules.get("required_checks", []))

    for track in manifest.get("tracks", []):
        checks = [
            check_loudness(track, rules),
            check_clipping(track, rules),
            check_metadata_completeness(track, rules, repo_root),
            check_lyric_structure(track, rules, repo_root),
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


def write_job_record(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def build_job_record(manifest_path: Path, rules_path: Path, results: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    transition_target = rules.get("transition_gate", {}).get("target_stage", "rollout/platform_assets")
    require_all_pass = bool(rules.get("transition_gate", {}).get("require_all_required_checks_pass", True))
    allowed = results["all_required_checks_passed"] if require_all_pass else True

    return {
        "job_type": "media_output_validation",
        "timestamp": _utc_now(),
        "manifest_path": str(manifest_path),
        "rules_path": str(rules_path),
        "summary": {
            "all_required_checks_passed": results["all_required_checks_passed"],
            "tracks_evaluated": len(results["track_results"]),
        },
        "tracks": results["track_results"],
        "transition_gate": {
            "target_stage": transition_target,
            "allowed": allowed,
            "reason": "all required checks passed" if allowed else "one or more required checks failed",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate media outputs and enforce rollout transition gates")
    parser.add_argument("--manifest", default="projects/jrt/metadata/track_manifest.json", help="Path to track manifest JSON")
    parser.add_argument("--rules", default="projects/jrt/metadata/quality_rules.json", help="Path to quality rules JSON")
    parser.add_argument(
        "--job-records",
        default="projects/jrt/metadata/job_records.jsonl",
        help="JSONL file where validation pass/fail job records are appended",
    )
    parser.add_argument(
        "--target-stage",
        default="rollout/platform_assets",
        help="Target stage to gate (must match transition_gate.target_stage to evaluate allow/deny)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    manifest_path = Path(args.manifest)
    rules_path = Path(args.rules)
    job_records_path = Path(args.job_records)

    try:
        manifest = _load_json(manifest_path)
        rules = _load_json(rules_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    results = validate_tracks(manifest, rules, repo_root)
    record = build_job_record(manifest_path, rules_path, results, rules)

    gate_target = rules.get("transition_gate", {}).get("target_stage", "rollout/platform_assets")
    if args.target_stage != gate_target:
        record["transition_gate"]["allowed"] = False
        record["transition_gate"]["reason"] = (
            f"target stage mismatch: expected '{gate_target}', got '{args.target_stage}'"
        )

    write_job_record(job_records_path, record)

    allowed = bool(record["transition_gate"]["allowed"])
    print(json.dumps(record["summary"], indent=2, sort_keys=True))
    if allowed:
        print(f"GATE: PASS -> transition to {record['transition_gate']['target_stage']} allowed")
        return 0

    print(f"GATE: FAIL -> transition to {record['transition_gate']['target_stage']} blocked")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
