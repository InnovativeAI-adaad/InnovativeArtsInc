from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_validation_pipeline_blocks_after_remediation_attempts_exhausted(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    rules_path = tmp_path / "rules.json"
    runtime_config_path = tmp_path / "runtime_config.json"
    jobs_dir = tmp_path / "jobs"

    manifest_path.write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "id": "trk-001",
                        "title": "Broken Track",
                        "version": "v1",
                        "status": "draft",
                        "assets": {},
                        "analysis": {
                            "integrated_lufs": -25.0,
                            "true_peak_dbfs": 0.2,
                            "clipped_samples": 12,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rules_path.write_text(
        json.dumps(
            {
                "required_checks": [
                    "loudness_bounds",
                    "clipping",
                    "metadata_completeness",
                    "lyric_structure",
                ],
                "transition_gate": {
                    "target_stage": "rollout/platform_assets",
                    "require_all_required_checks_pass": True,
                },
                "loudness_bounds": {
                    "enabled": True,
                    "required": True,
                    "integrated_lufs": {"min": -16.0, "max": -9.0},
                    "max_true_peak_dbfs": -1.0,
                },
                "clipping": {
                    "enabled": True,
                    "required": True,
                    "max_clipped_samples": 0,
                },
                "metadata_completeness": {
                    "enabled": True,
                    "required": True,
                    "required_track_fields": ["id", "title", "version", "status", "assets"],
                    "required_asset_fields": ["audio", "lyrics"],
                    "require_asset_paths_to_exist": False,
                    "minimum_completeness_ratio": 1.0,
                },
                "lyric_structure": {
                    "enabled": True,
                    "required": True,
                    "required_sections": ["verse", "chorus"],
                    "minimum_non_empty_lines": 8,
                },
                "release_bundle_validation": {
                    "enabled": False,
                    "required": False,
                },
            }
        ),
        encoding="utf-8",
    )

    runtime_config_path.write_text(
        json.dumps(
            {
                "retry_policy": {"max_attempts": 2, "backoff_seconds": [0, 0]},
                "failure_classes": {"transient": [], "deterministic": []},
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "pipelines/validate_media_outputs.py",
            "--manifest",
            str(manifest_path),
            "--rules",
            str(rules_path),
            "--runtime-config",
            str(runtime_config_path),
            "--jobs-dir",
            str(jobs_dir),
            "--target-stage",
            "rollout/platform_assets",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    job_records = sorted(jobs_dir.glob("*.json"))
    assert len(job_records) == 1

    payload = json.loads(job_records[0].read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert len(payload["remediation_attempts"]) == 6
    assert any(ref["ref_type"] == "remediation_terminal_state" for ref in payload["provenance_refs"])
