#!/usr/bin/env python3
"""CI quality gates for schema, media dry-run, and authorization checks."""

from __future__ import annotations

import argparse
import hmac
import importlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.agents.execution_policy import execute_with_retry_policy
from services.media_generation.adapters import StubGenAudioAdapter
from services.media_generation.service import generate_music_for_wf005

SCHEMA_DIR = REPO_ROOT / "projects" / "jrt" / "metadata" / "schema"
MEDIA_JOB_SCHEMA = SCHEMA_DIR / "media_job.schema.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_targets() -> list[Path]:
    """Return required and future release/campaign schema files without duplicates."""
    targets = [MEDIA_JOB_SCHEMA]
    for pattern in ("*release*.schema.json", "*campaign*.schema.json"):
        targets.extend(sorted(SCHEMA_DIR.glob(pattern)))
    return list(dict.fromkeys(targets))


def _jsonschema_module() -> Any | None:
    if importlib.util.find_spec("jsonschema") is None:
        return None
    return importlib.import_module("jsonschema")


def _validator_for_schema(schema_path: Path) -> Any | None:
    schema = _load_json(schema_path)
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        return None
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def validate_schema_files() -> None:
    missing = [path for path in _schema_targets() if not path.exists()]
    if missing:
        raise SystemExit("Missing required schema file(s): " + ", ".join(str(path) for path in missing))

    for schema_path in _schema_targets():
        _load_json(schema_path)
        validator = _validator_for_schema(schema_path)
        if validator is None:
            print(
                f"VALID SCHEMA JSON: {schema_path.relative_to(REPO_ROOT)} "
                "(jsonschema package unavailable; CI installs it for full Draft 2020-12 checks)"
            )
        else:
            print(f"VALID SCHEMA: {schema_path.relative_to(REPO_ROOT)}")


def _manual_media_job_errors(job_record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "job_id",
        "track_id",
        "stage",
        "input_assets",
        "output_assets",
        "agent_owner",
        "status",
        "attempt",
        "created_at",
        "provenance_refs",
    ]
    for field in required:
        if field not in job_record:
            errors.append(f"missing required field: {field}")
    if job_record.get("status") not in {"queued", "running", "succeeded", "failed", "blocked"}:
        errors.append("status is not one of the schema enum values")
    if not isinstance(job_record.get("attempt"), int) or job_record.get("attempt", 0) < 1:
        errors.append("attempt must be an integer >= 1")
    if not isinstance(job_record.get("created_at"), str) or not job_record["created_at"].endswith("Z"):
        errors.append("created_at must be an ISO-8601 UTC timestamp")
    for field in ("input_assets", "output_assets"):
        assets = job_record.get(field)
        if not isinstance(assets, list) or not assets:
            errors.append(f"{field} must be a non-empty list")
            continue
        for index, asset in enumerate(assets):
            if not isinstance(asset, dict):
                errors.append(f"{field}[{index}] must be an object")
                continue
            if not asset.get("asset_id") or not asset.get("path"):
                errors.append(f"{field}[{index}] must include asset_id and path")
            digest = asset.get("sha256")
            if digest is not None and not re.fullmatch(r"[A-Fa-f0-9]{64}", str(digest)):
                errors.append(f"{field}[{index}].sha256 must be a 64-character hex digest")
    provenance_refs = job_record.get("provenance_refs")
    if not isinstance(provenance_refs, list) or not provenance_refs:
        errors.append("provenance_refs must be a non-empty list")
    else:
        for index, ref in enumerate(provenance_refs):
            if not isinstance(ref, dict) or not ref.get("ref_type") or not ref.get("ref_id"):
                errors.append(f"provenance_refs[{index}] must include ref_type and ref_id")
    return errors


def _validate_media_job(job_record: dict[str, Any], *, label: str) -> None:
    validator = _validator_for_schema(MEDIA_JOB_SCHEMA)
    if validator is None:
        errors = _manual_media_job_errors(job_record)
    else:
        errors = [
            f"{list(error.path)}: {error.message}"
            for error in sorted(validator.iter_errors(job_record), key=lambda error: list(error.path))
        ]
    if errors:
        raise SystemExit(f"Generated media job metadata failed validation for {label}: {'; '.join(errors)}")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_dry_run_media_job() -> None:
    """Exercise the autonomous media path with the deterministic StubGenAudioAdapter."""
    with tempfile.TemporaryDirectory(prefix="iai-ci-media-job-") as tmp:
        project_root = Path(tmp)
        result = generate_music_for_wf005(
            prompt="CI dry-run cinematic pulse with restrained percussion",
            style_profile={"name": "ci.quality_gate.v1", "temperature": 0},
            seed="ci-quality-gate-seed",
            length=16,
            tempo=96,
            key="A minor",
            uniqueness_report_ref="registry/reports/ci-uniqueness-dry-run.json",
            provider=StubGenAudioAdapter(),
            project_root=project_root,
        )

        render_metadata_path = (
            project_root / "projects" / "jrt" / "metadata" / "renders" / f"{result['replay_key']}.json"
        )
        if not render_metadata_path.exists():
            raise SystemExit(f"Dry-run render metadata was not emitted: {render_metadata_path}")
        if not Path(result["audio_path"]).exists():
            raise SystemExit(f"Dry-run audio artifact was not emitted: {result['audio_path']}")

        media_job = {
            "job_id": f"ci-media-{result['replay_key'][:12]}",
            "track_id": "jrt-ci-dry-run",
            "stage": "generate_music",
            "input_assets": [
                {
                    "asset_id": "ci-prompt-contract",
                    "path": str(render_metadata_path.relative_to(project_root)),
                    "sha256": result["replay_key"],
                    "mime_type": "application/json",
                }
            ],
            "output_assets": [
                {
                    "asset_id": "ci-stub-audio",
                    "path": str(Path(result["audio_path"]).relative_to(project_root)),
                    "sha256": sha256(Path(result["audio_path"]).read_bytes()).hexdigest(),
                    "mime_type": "audio/wav",
                }
            ],
            "agent_owner": "ci-quality-gates",
            "status": "succeeded",
            "attempt": 1,
            "created_at": _utc_now_iso(),
            "provenance_refs": [
                {
                    "ref_type": "provenance_log",
                    "ref_id": "ci-provenance-log",
                    "uri": "registry/provenance_log.jsonl",
                }
            ],
            "generation_config": {
                "model_version": result["render_metadata"]["model"],
                "prompt_template_version": "ci-dry-run-v1",
                "random_seed": "ci-quality-gate-seed",
                "creativity_profile": {"name": "ci.quality_gate.v1", "temperature": 0},
                "style_constraints": ["deterministic", "stubbed", "no-external-provider"],
            },
        }
        _validate_media_job(media_job, label="StubGenAudioAdapter dry-run")
        print("VALID MEDIA JOB: StubGenAudioAdapter dry-run metadata validates")


def _write_runtime_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "retry_policy": {"max_attempts": 2, "backoff_seconds": [0, 0]},
                "failure_classes": {
                    "transient": ["TimeoutError"],
                    "deterministic": ["ValueError", "DeterministicAgentError"],
                },
            }
        ),
        encoding="utf-8",
    )


def _ratification_signature(key: str, ratifier_id: str, ratified_at: str, scope: str) -> str:
    payload = f"ratifier_id={ratifier_id}\nratified_at={ratified_at}\nscope={scope}\n".encode("utf-8")
    return hmac.new(key.encode("utf-8"), payload, sha256).hexdigest()


def _authorization_signature(key: str, actor_id: str, role: str, scopes: str, issued_at: str) -> str:
    payload = f"actor_id={actor_id}\nrole={role}\nscopes={scopes}\nissued_at={issued_at}\n".encode("utf-8")
    return hmac.new(key.encode("utf-8"), payload, sha256).hexdigest()


def assert_policy_gates_fail_closed() -> None:
    """Fail CI if Level 3/policy-gated stages can run without authorization."""
    with tempfile.TemporaryDirectory(prefix="iai-ci-policy-gate-") as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "agent_runtime_config.json"
        _write_runtime_config(config_path)

        old_ratification = os.environ.get("ADAAD_RATIFICATION_HMAC_KEY")
        old_authorization = os.environ.get("ADAAD_AUTHORIZATION_HMAC_KEY")
        os.environ["ADAAD_RATIFICATION_HMAC_KEY"] = "ci-ratification-key"
        os.environ["ADAAD_AUTHORIZATION_HMAC_KEY"] = "ci-authorization-key"
        try:
            runner_calls = {"count": 0}

            def guarded_runner(payload: dict[str, Any]) -> dict[str, Any]:
                runner_calls["count"] += 1
                return {"ok": True, "payload": payload}

            blocked_result = execute_with_retry_policy(
                agent_name="ReleaseAgent",
                job_payload={"job_id": "ci-missing-auth", "action": "deploy_production", "tier": "level_3"},
                runner=guarded_runner,
                config_path=config_path,
                sleep_fn=lambda _: None,
                incident_dir=tmp_path / "incidents",
            )
            if blocked_result.get("status") != "quarantine" or runner_calls["count"] != 0:
                raise SystemExit("Policy gate bypass detected: Level 3 action ran without authorization")

            scope = "deploy_production"
            ratified_at = "2026-04-20T10:00:00+00:00"
            issued_at = "2026-04-20T10:01:00+00:00"
            allowed_result = execute_with_retry_policy(
                agent_name="ReleaseAgent",
                job_payload={
                    "job_id": "ci-authorized",
                    "action": "deploy_production",
                    "tier": "level_3",
                    "ratification": {
                        "human_ratified": True,
                        "ratifier_id": "owner:ci",
                        "ratified_at": ratified_at,
                        "scope": scope,
                        "signature": _ratification_signature(
                            "ci-ratification-key", "owner:ci", ratified_at, scope
                        ),
                    },
                    "authorization": {
                        "actor_id": "reviewer:ci",
                        "role": "reviewer",
                        "scopes": scope,
                        "issued_at": issued_at,
                        "signature": _authorization_signature(
                            "ci-authorization-key", "reviewer:ci", "reviewer", scope, issued_at
                        ),
                    },
                },
                runner=guarded_runner,
                config_path=config_path,
                sleep_fn=lambda _: None,
                incident_dir=tmp_path / "incidents",
            )
            if allowed_result.get("status") != "completed" or runner_calls["count"] != 1:
                raise SystemExit("Policy gate rejected a correctly authorized Level 3 action")
        finally:
            if old_ratification is None:
                os.environ.pop("ADAAD_RATIFICATION_HMAC_KEY", None)
            else:
                os.environ["ADAAD_RATIFICATION_HMAC_KEY"] = old_ratification
            if old_authorization is None:
                os.environ.pop("ADAAD_AUTHORIZATION_HMAC_KEY", None)
            else:
                os.environ["ADAAD_AUTHORIZATION_HMAC_KEY"] = old_authorization

    print("VALID POLICY GATE: Level 3 actions fail closed without authorization")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-only", action="store_true", help="Validate schema files only")
    parser.add_argument("--dry-run-media-job", action="store_true", help="Run and validate stub media dry-run")
    parser.add_argument("--policy-authorization", action="store_true", help="Assert policy gates fail closed")
    args = parser.parse_args()

    if not any((args.schema_only, args.dry_run_media_job, args.policy_authorization)):
        validate_schema_files()
        run_dry_run_media_job()
        assert_policy_gates_fail_closed()
        return 0

    if args.schema_only:
        validate_schema_files()
    if args.dry_run_media_job:
        run_dry_run_media_job()
    if args.policy_authorization:
        assert_policy_gates_fail_closed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
