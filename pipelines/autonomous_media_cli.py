#!/usr/bin/env python3
"""Command line entrypoint for governed autonomous media conductor runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from core.gatekeeper.entry_gate import enforce_gate
from services.media_conductor.service import MediaConductorError, run_media_conductor


def _load_json_arg(value: str) -> Any:
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def _asset_ref(asset_id: str, path: str) -> dict[str, str]:
    return {"asset_id": asset_id, "path": path}


def _default_job_id() -> str:
    return os.getenv("IAI_MEDIA_JOB_ID", "dry-run-job")


def _default_track_id() -> str:
    return os.getenv("IAI_MEDIA_TRACK_ID", "track-demo")


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", default=os.getenv("IAI_REPO_ROOT", "."), help="Repository root path")
    parser.add_argument("--job-id", default=_default_job_id(), help="Media job identifier")
    parser.add_argument("--track-id", default=_default_track_id(), help="Canonical track identifier")
    parser.add_argument("--actor", default=os.getenv("IAI_MEDIA_ACTOR", "media-conductor"), help="Actor recorded in transition history")
    parser.add_argument("--gate-payload", default=os.getenv("IAI_GATE_PAYLOAD_JSON", "{}"), help="JSON object or path with authorization and ratification payloads")
    parser.add_argument("--agent-owner", default=os.getenv("IAI_AGENT_OWNER", "MediaAgent"), help="Agent owner recorded on emitted job")
    parser.add_argument("--attempt", type=int, default=int(os.getenv("IAI_MEDIA_ATTEMPT", "1")), help="Attempt number")
    parser.add_argument(
        "--input-assets",
        default=os.getenv("IAI_INPUT_ASSETS_JSON"),
        help="JSON array or path to JSON array of input asset refs",
    )
    parser.add_argument(
        "--output-assets",
        default=os.getenv("IAI_OUTPUT_ASSETS_JSON"),
        help="JSON array or path to JSON array of output asset refs",
    )
    parser.add_argument(
        "--provenance-refs",
        default=os.getenv("IAI_PROVENANCE_REFS_JSON"),
        help="JSON array or path to JSON array of provenance refs",
    )


def _resolve_run_payload(args: argparse.Namespace) -> dict[str, Any]:
    input_assets = (
        _load_json_arg(args.input_assets)
        if args.input_assets
        else [_asset_ref("prompt-package", f"projects/jrt/metadata/{args.track_id}/prompt.json")]
    )
    output_assets = (
        _load_json_arg(args.output_assets)
        if args.output_assets
        else [_asset_ref("rollout-package", f"projects/jrt/metadata/{args.track_id}/rollout.json")]
    )
    provenance_refs = (
        _load_json_arg(args.provenance_refs)
        if args.provenance_refs
        else [{"ref_type": "registry", "ref_id": args.job_id, "uri": "registry/provenance_log.jsonl"}]
    )
    return {
        "repo_root": args.repo_root,
        "job_id": args.job_id,
        "track_id": args.track_id,
        "input_assets": input_assets,
        "output_assets": output_assets,
        "provenance_refs": provenance_refs,
        "actor": args.actor,
        "agent_owner": args.agent_owner,
        "attempt": args.attempt,
    }


def _cmd_dry_run(args: argparse.Namespace) -> int:
    decision = enforce_gate("autonomous_media_cli.dry_run", args.actor, _load_json_arg(args.gate_payload))
    if not decision["allowed"]:
        print(json.dumps({"status": "denied", "gate": decision}, indent=2, sort_keys=True), file=sys.stderr)
        return 3
    payload = _resolve_run_payload(args)
    schema_path = Path(payload["repo_root"]) / "projects" / "jrt" / "metadata" / "schema" / "media_job.schema.json"
    if not schema_path.exists():
        print(f"ERROR: media job schema not found: {schema_path}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "mode": "dry-run",
                "would_execute": "services.media_conductor.service.run_media_conductor",
                "payload": payload,
                "writes_files": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    decision = enforce_gate("autonomous_media_cli.run", args.actor, _load_json_arg(args.gate_payload))
    if not decision["allowed"]:
        print(json.dumps({"status": "denied", "gate": decision}, indent=2, sort_keys=True), file=sys.stderr)
        return 3
    payload = _resolve_run_payload(args)
    if args.require_agent_enabled and os.getenv("AGENT_ENABLED", "true").lower() != "true":
        print("ERROR: AGENT_ENABLED is not true; refusing production run.", file=sys.stderr)
        return 2

    try:
        result = run_media_conductor(**payload)
    except (MediaConductorError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"mode": "production-run", "result": result}, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("dry-run", help="Validate and display a run plan without writing files")
    _add_common_run_args(dry_run)
    dry_run.set_defaults(func=_cmd_dry_run)

    run = subparsers.add_parser("run", help="Execute the media conductor and emit governed job artifacts")
    _add_common_run_args(run)
    run.add_argument(
        "--require-agent-enabled",
        action="store_true",
        help="Fail closed unless AGENT_ENABLED=true in the environment",
    )
    run.set_defaults(func=_cmd_run)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
