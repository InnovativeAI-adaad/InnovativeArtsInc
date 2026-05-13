"""Autonomous WF-005 generation lifecycle CLI with IPAgent gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from services.media_conductor import MediaConductor, MediaConductorPaths
from services.media_generation.ip_lifecycle import (
    IPGuardrailBlockedError,
    audio_fingerprint_for_path,
    decision_provenance_ref,
    run_post_generation_similarity_audit,
    run_pre_generation_uniqueness_gate,
)
from services.media_generation.service import generate_music_for_wf005


def _parse_style_profile(raw: str) -> str | dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return parsed if isinstance(parsed, dict) else raw


def _asset_ref(asset_type: str, path: str) -> dict[str, str]:
    return {"asset_id": f"{asset_type}:{Path(path).name}", "path": path}


def _media_conductor_paths(root: Path) -> MediaConductorPaths:
    schema_path = root / "projects/jrt/metadata/schema/media_job.schema.json"
    if not schema_path.exists():
        schema_path = Path(__file__).resolve().parents[2] / "projects/jrt/metadata/schema/media_job.schema.json"
    jobs_dir = root / "projects/jrt/metadata/jobs"
    return MediaConductorPaths(
        repo_root=root,
        jobs_dir=jobs_dir,
        schema_path=schema_path,
        checkpoints_dir=jobs_dir / "checkpoints",
    )


def run_autonomous_generation_lifecycle(
    *,
    project_root: str | Path,
    job_id: str,
    track_id: str,
    prompt: str,
    style_profile: str | dict[str, Any],
    seed: int | str,
    length: int,
    tempo: int | None = None,
    key: str | None = None,
    uniqueness_report_ref: str | None = None,
    input_assets: list[dict[str, Any]] | None = None,
    provenance_refs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Run WF-005 generation with pre/post IPAgent gates around media creation.

    The lifecycle fails closed: pre-generation failure prevents media generation;
    post-generation failure prevents cataloging, tagging, release bundling, and
    distribution by stopping before the media conductor/catalog lifecycle emits a
    succeeded media job.
    """
    root = Path(project_root)
    media_provenance_refs = list(provenance_refs or [])

    pre_decision = run_pre_generation_uniqueness_gate(
        project_root=root,
        job_id=job_id,
        track_id=track_id,
        prompt=prompt,
        style_profile=style_profile,
        seed=seed,
        length=length,
        tempo=tempo,
        key=key,
        provenance_refs=media_provenance_refs,
        block_on_fail=True,
    )
    pre_ref = decision_provenance_ref(pre_decision, ref_type="ip_pre_generation_decision")
    media_provenance_refs.append(pre_ref)

    generation_result = generate_music_for_wf005(
        prompt=prompt,
        style_profile=style_profile,
        seed=seed,
        length=length,
        tempo=tempo,
        key=key,
        uniqueness_report_ref=uniqueness_report_ref or pre_decision["decision_artifact_ref"],
        project_root=root,
    )

    fingerprint = audio_fingerprint_for_path(generation_result["audio_path"])
    post_decision = run_post_generation_similarity_audit(
        project_root=root,
        job_id=job_id,
        track_id=track_id,
        render_metadata=generation_result["render_metadata"],
        audio_fingerprint=fingerprint,
        provenance_refs=media_provenance_refs,
        block_on_fail=True,
    )
    post_ref = decision_provenance_ref(post_decision, ref_type="ip_post_generation_decision")
    media_provenance_refs.append(post_ref)

    conductor = MediaConductor(
        paths=_media_conductor_paths(root),
        actor="autonomous-run-cli",
    )
    conductor_checkpoint = conductor.run(
        job_id=job_id,
        track_id=track_id,
        input_assets=input_assets or [_asset_ref("prompt", f"prompt://{job_id}")],
        output_assets=[_asset_ref("audio", generation_result["audio_path"])],
        provenance_refs=media_provenance_refs,
        agent_owner="MediaAgent",
    )

    return {
        "ok": True,
        "job_id": job_id,
        "track_id": track_id,
        "generation_result": generation_result,
        "audio_fingerprint": fingerprint,
        "pre_generation_decision": pre_decision,
        "post_generation_decision": post_decision,
        "provenance_refs": media_provenance_refs,
        "media_conductor": conductor_checkpoint,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run autonomous WF-005 generation with IPAgent lifecycle gates")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--track-id", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--style-profile", required=True, help="Style profile string or JSON object")
    parser.add_argument("--seed", required=True)
    parser.add_argument("--length", required=True, type=int)
    parser.add_argument("--tempo", type=int)
    parser.add_argument("--key")
    parser.add_argument("--uniqueness-report-ref")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_autonomous_generation_lifecycle(
            project_root=args.project_root,
            job_id=args.job_id,
            track_id=args.track_id,
            prompt=args.prompt,
            style_profile=_parse_style_profile(args.style_profile),
            seed=args.seed,
            length=args.length,
            tempo=args.tempo,
            key=args.key,
            uniqueness_report_ref=args.uniqueness_report_ref,
        )
    except IPGuardrailBlockedError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "stage": exc.stage, "artifact_ref": exc.artifact_ref}, indent=2))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
