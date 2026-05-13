from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

from services.media_generation.audio_analysis import analyze_pcm_wav, write_analysis_artifact


def _write_tone(path: Path) -> None:
    sample_rate = 44_100
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for idx in range(sample_rate):
            sample = int(32767 * 0.2 * math.sin(2 * math.pi * 440 * idx / sample_rate))
            frames.extend(struct.pack("<hh", sample, sample))
        wav.writeframes(bytes(frames))


def test_wav_analysis_emits_quality_rule_metrics(tmp_path: Path) -> None:
    audio_path = tmp_path / "tone.wav"
    _write_tone(audio_path)

    metrics = analyze_pcm_wav(audio_path)

    assert metrics.sample_rate_hz == 44_100
    assert metrics.channel_count == 2
    assert metrics.duration_seconds == 1.0
    assert metrics.clipped_samples == 0
    assert metrics.true_peak_dbfs is not None and metrics.true_peak_dbfs < -1.0
    assert metrics.integrated_lufs is not None
    assert metrics.stereo_width == 0.0


def test_write_analysis_artifact_normalizes_imported_metrics(tmp_path: Path) -> None:
    artifact = write_analysis_artifact(
        audio_path="encoded-master.mp3",
        job_id="job-123",
        track_id="trk-123",
        artifact_dir=tmp_path,
        measured_values={
            "integrated_loudness_lufs": -12.5,
            "max_true_peak_dbfs": -1.2,
            "clip_count": 0,
            "duration": 184.25,
            "sample_rate": 48_000,
            "channels": 2,
            "stereo_width": 0.31,
        },
    )

    payload = json.loads((tmp_path / "job-123.json").read_text(encoding="utf-8"))
    assert artifact["artifact_path"].endswith("job-123.json")
    assert payload["metrics"]["integrated_lufs"] == -12.5
    assert payload["metrics"]["true_peak_dbfs"] == -1.2
    assert payload["metrics"]["clipped_samples"] == 0
    assert payload["metrics"]["sample_rate_hz"] == 48_000


def test_validation_pipeline_consumes_analysis_artifact_and_records_provenance(tmp_path: Path) -> None:
    lyrics_path = tmp_path / "lyrics.md"
    lyrics_path.write_text(
        "# Verse\nline 1\nline 2\nline 3\nline 4\n# Chorus\nline 5\nline 6\nline 7\nline 8\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    rules_path = tmp_path / "rules.json"
    runtime_config_path = tmp_path / "runtime_config.json"
    analysis_dir = tmp_path / "analysis"
    jobs_dir = tmp_path / "jobs"

    manifest_path.write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "id": "trk-pass",
                        "title": "Artifact Track",
                        "version": "v1",
                        "status": "final",
                        "assets": {"audio": "masters/trk-pass.wav", "lyrics": str(lyrics_path)},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rules_path.write_text(
        json.dumps(
            {
                "required_checks": ["loudness_bounds", "clipping", "metadata_completeness", "lyric_structure"],
                "transition_gate": {"target_stage": "rollout/platform_assets", "require_all_required_checks_pass": True},
                "loudness_bounds": {
                    "enabled": True,
                    "required": True,
                    "integrated_lufs": {"min": -16.0, "max": -9.0},
                    "max_true_peak_dbfs": -1.0,
                    "allow_missing_metrics": False,
                },
                "clipping": {"enabled": True, "required": True, "max_clipped_samples": 0, "allow_missing_metrics": False},
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
                    "allow_missing_lyrics_file": False,
                },
            }
        ),
        encoding="utf-8",
    )
    runtime_config_path.write_text(json.dumps({"retry_policy": {"max_attempts": 1, "backoff_seconds": [0]}}), encoding="utf-8")
    write_analysis_artifact(
        audio_path="masters/trk-pass.wav",
        job_id="analysis-job-1",
        track_id="trk-pass",
        artifact_dir=analysis_dir,
        measured_values={"integrated_lufs": -12.0, "true_peak_dbfs": -1.5, "clipped_samples": 0, "duration_seconds": 120, "sample_rate_hz": 44100, "channel_count": 2},
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
            "--analysis-dir",
            str(analysis_dir),
            "--jobs-dir",
            str(jobs_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(next(jobs_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["status"] == "succeeded"
    assert any(ref["ref_type"] == "audio_analysis" and ref["ref_id"] == "analysis-job-1" for ref in payload["provenance_refs"])
    assert any(ref["ref_type"] == "quality_result" and ref["ref_id"] == "trk-pass" and ref["uri"] == "pass" for ref in payload["provenance_refs"])
