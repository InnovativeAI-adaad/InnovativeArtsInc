"""Audio quality analysis utilities for media-generation outputs.

The analyzer intentionally has a small standard-library core so validation can run in
CI without native DSP dependencies. For PCM WAV sources it computes the metrics used
by ``projects/jrt/metadata/quality_rules.json`` directly. For encoded formats or
provider-measured values, callers can supply a normalized metrics payload or a JSON
sidecar with the same metric keys.
"""

from __future__ import annotations

import json
import math
import struct
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

QUALITY_METRIC_KEYS = (
    "integrated_lufs",
    "true_peak_dbfs",
    "clipped_samples",
    "duration_seconds",
    "sample_rate_hz",
    "channel_count",
    "stereo_width",
)


@dataclass(frozen=True)
class AudioMetrics:
    """Normalized measured audio values consumed by quality gates."""

    integrated_lufs: float | None
    true_peak_dbfs: float | None
    clipped_samples: int | None
    duration_seconds: float | None
    sample_rate_hz: int | None
    channel_count: int | None
    stereo_width: float | None = None

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "integrated_lufs": self.integrated_lufs,
            "true_peak_dbfs": self.true_peak_dbfs,
            "clipped_samples": self.clipped_samples,
            "duration_seconds": self.duration_seconds,
            "sample_rate_hz": self.sample_rate_hz,
            "channel_count": self.channel_count,
            "stereo_width": self.stereo_width,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(float(value))
    return None


def normalize_metrics(values: dict[str, Any] | None) -> AudioMetrics:
    """Normalize provider/imported metric names to the quality-rules contract."""

    values = values or {}
    aliases = {
        "integrated_lufs": ("integrated_lufs", "lufs", "integrated_loudness_lufs"),
        "true_peak_dbfs": ("true_peak_dbfs", "max_true_peak_dbfs", "true_peak"),
        "clipped_samples": ("clipped_samples", "clipping_count", "clip_count", "clipped_sample_count"),
        "duration_seconds": ("duration_seconds", "duration", "duration_sec"),
        "sample_rate_hz": ("sample_rate_hz", "sample_rate", "sample_rate_hertz"),
        "channel_count": ("channel_count", "channels", "num_channels"),
        "stereo_width": ("stereo_width", "stereo_width_correlation"),
    }

    def first(metric_name: str) -> Any:
        for key in aliases[metric_name]:
            if key in values:
                return values[key]
        return None

    return AudioMetrics(
        integrated_lufs=_coerce_float(first("integrated_lufs")),
        true_peak_dbfs=_coerce_float(first("true_peak_dbfs")),
        clipped_samples=_coerce_int(first("clipped_samples")),
        duration_seconds=_coerce_float(first("duration_seconds")),
        sample_rate_hz=_coerce_int(first("sample_rate_hz")),
        channel_count=_coerce_int(first("channel_count")),
        stereo_width=_coerce_float(first("stereo_width")),
    )


def _pcm_samples(frame_bytes: bytes, sample_width: int) -> Iterable[tuple[int, int]]:
    """Yield signed sample values with the positive full-scale value."""

    if sample_width == 1:
        for byte in frame_bytes:
            yield byte - 128, 127
        return
    if sample_width == 2:
        for (sample,) in struct.iter_unpack("<h", frame_bytes):
            yield sample, 32767
        return
    if sample_width == 3:
        for idx in range(0, len(frame_bytes), 3):
            chunk = frame_bytes[idx : idx + 3]
            if len(chunk) < 3:
                break
            sign = b"\xff" if chunk[2] & 0x80 else b"\x00"
            yield int.from_bytes(chunk + sign, byteorder="little", signed=True), 8388607
        return
    if sample_width == 4:
        for (sample,) in struct.iter_unpack("<i", frame_bytes):
            yield sample, 2147483647
        return
    raise ValueError(f"unsupported PCM sample width: {sample_width} bytes")


def analyze_pcm_wav(audio_path: str | Path) -> AudioMetrics:
    """Compute normalized metrics for PCM WAV audio.

    Integrated LUFS is an ungated BS.1770-style approximation from RMS power. True
    peak is represented by the highest decoded sample peak because inter-sample peak
    estimation requires an oversampling DSP dependency that is intentionally optional.
    """

    path = Path(audio_path)
    with wave.open(str(path), "rb") as wav:
        channel_count = wav.getnchannels()
        sample_rate_hz = wav.getframerate()
        sample_width = wav.getsampwidth()
        frame_count = wav.getnframes()
        frame_bytes = wav.readframes(frame_count)

    duration_seconds = frame_count / sample_rate_hz if sample_rate_hz else 0.0
    sample_rows = list(_pcm_samples(frame_bytes, sample_width))
    if not sample_rows:
        return AudioMetrics(None, None, None, duration_seconds, sample_rate_hz, channel_count, None)

    normalized: list[float] = [max(-1.0, min(1.0, sample / full_scale)) for sample, full_scale in sample_rows]
    clipped_samples = sum(1 for sample, full_scale in sample_rows if abs(sample) >= full_scale)
    peak = max(abs(value) for value in normalized)
    true_peak_dbfs = 20.0 * math.log10(peak) if peak > 0 else -math.inf
    mean_square = sum(value * value for value in normalized) / len(normalized)
    integrated_lufs = -math.inf if mean_square <= 0 else -0.691 + 10.0 * math.log10(mean_square)

    stereo_width: float | None = None
    if channel_count == 2 and len(normalized) >= 2:
        left = normalized[0::2]
        right = normalized[1::2]
        mid_energy = sum(((l + r) * 0.5) ** 2 for l, r in zip(left, right))
        side_energy = sum(((l - r) * 0.5) ** 2 for l, r in zip(left, right))
        stereo_width = side_energy / mid_energy if mid_energy > 0 else (1.0 if side_energy > 0 else 0.0)

    return AudioMetrics(
        integrated_lufs=round(integrated_lufs, 3) if math.isfinite(integrated_lufs) else None,
        true_peak_dbfs=round(true_peak_dbfs, 3) if math.isfinite(true_peak_dbfs) else None,
        clipped_samples=clipped_samples,
        duration_seconds=round(duration_seconds, 6),
        sample_rate_hz=sample_rate_hz,
        channel_count=channel_count,
        stereo_width=round(stereo_width, 6) if stereo_width is not None else None,
    )


def _load_sidecar_metrics(audio_path: Path) -> dict[str, Any] | None:
    sidecar_candidates = [
        audio_path.with_suffix(audio_path.suffix + ".analysis.json"),
        audio_path.with_suffix(".analysis.json"),
    ]
    for candidate in sidecar_candidates:
        if candidate.exists():
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else payload
            if isinstance(metrics, dict):
                return metrics
    return None


def analyze_audio_file(audio_path: str | Path, measured_values: dict[str, Any] | None = None) -> tuple[AudioMetrics, list[str]]:
    """Analyze a file directly or import supplied/provider-sidecar measurements."""

    path = Path(audio_path)
    warnings: list[str] = []
    if measured_values:
        return normalize_metrics(measured_values), warnings

    sidecar_metrics = _load_sidecar_metrics(path)
    if sidecar_metrics is not None:
        return normalize_metrics(sidecar_metrics), warnings

    try:
        return analyze_pcm_wav(path), warnings
    except (wave.Error, EOFError, ValueError) as exc:
        warnings.append(f"direct PCM WAV analysis unavailable for {path}: {exc}")
        return normalize_metrics(None), warnings


def write_analysis_artifact(
    *,
    audio_path: str | Path,
    job_id: str,
    artifact_dir: str | Path = "projects/jrt/metadata/analysis",
    track_id: str | None = None,
    measured_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write ``<artifact_dir>/<job_id>.json`` with normalized quality metrics."""

    metrics, warnings = analyze_audio_file(audio_path, measured_values=measured_values)
    payload = {
        "schema_version": "1.0.0",
        "artifact_type": "audio_analysis",
        "job_id": job_id,
        "track_id": track_id,
        "source_audio_path": str(audio_path),
        "analyzed_at": _utc_now(),
        "metrics": metrics.as_dict(),
        "status": "complete" if not warnings else "partial",
        "warnings": warnings,
    }
    target_dir = Path(artifact_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = target_dir / f"{job_id}.json"
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["artifact_path"] = str(artifact_path)
    return payload
