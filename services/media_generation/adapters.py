"""Provider adapter contracts for deterministic media generation."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import struct
import wave
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _truthy_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _deterministic_stub_wav_bytes(*, entropy_source: str, duration_seconds: int, sample_rate_hz: int = 44_100) -> bytes:
    entropy_digest = hashlib.sha256(entropy_source.encode("utf-8")).digest()
    entropy_int = int.from_bytes(entropy_digest[:8], "little")

    frame_count = sample_rate_hz * duration_seconds
    amplitude = 0.2
    base_frequency = 180 + (entropy_digest[8] % 220)
    phase_offset = (entropy_int % sample_rate_hz) / sample_rate_hz

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate_hz)
        frames = bytearray()

        lcg_state = entropy_int or 1
        for frame_idx in range(frame_count):
            lcg_state = (1664525 * lcg_state + 1013904223) & 0xFFFFFFFF
            jitter = ((lcg_state >> 16) & 0xFF) / 255.0 - 0.5
            t = (frame_idx / sample_rate_hz) + phase_offset
            sample_value = math.sin(2 * math.pi * (base_frequency + (jitter * 2.5)) * t)
            sample = int(32767 * amplitude * sample_value)
            frames.extend(struct.pack("<hh", sample, sample))

        wav.writeframes(bytes(frames))

    wav_bytes = buf.getvalue()
    marker = f"STUB_AUDIO|entropy={entropy_digest.hex()}".encode("utf-8")
    return wav_bytes + marker


@dataclass(frozen=True)
class ProviderGenerationResult:
    """Normalized output returned by all provider adapters."""

    audio_path: str
    render_metadata: dict[str, Any]
    provider_generation_id: str


class MediaGenerationAdapter(Protocol):
    """Contract for provider-backed audio generation."""

    provider_name: str

    def generate(
        self,
        *,
        prompt: str,
        style_profile: str | dict[str, Any],
        seed: int | str,
        length: int,
        output_dir: Path,
        replay_key: str,
        tempo: int | None = None,
        key: str | None = None,
        brand_profile: dict[str, Any] | None = None,
        brand_profile_id: str | None = None,
        brand_profile_hash: str | None = None,
    ) -> ProviderGenerationResult:
        """Generate a render for the provided contract payload."""


@dataclass(frozen=True)
class ProviderCredentials:
    """Provider credential material loaded from runtime configuration only."""

    api_key: str
    endpoint: str | None = None


class MissingProviderCredentialsError(RuntimeError):
    """Raised when a live provider adapter is used without runtime credentials."""


class ProviderRequestError(RuntimeError):
    """Raised when a provider request fails or returns an unsupported payload."""


def _build_render_settings(
    *,
    prompt: str,
    style_profile: str | dict[str, Any],
    seed: int | str,
    length: int,
    tempo: int | None,
    key: str | None,
    brand_profile: dict[str, Any] | None = None,
    brand_profile_id: str | None = None,
    brand_profile_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "style_profile": style_profile,
        "seed": seed,
        "length": length,
        "tempo": tempo,
        "key": key,
        "brand_profile": brand_profile,
        "brand_profile_id": brand_profile_id,
        "brand_profile_hash": brand_profile_hash,
    }


def _build_provider_payload(*, render_settings: dict[str, Any], model: str, model_version: str | None) -> dict[str, Any]:
    payload = {
        "prompt": render_settings["prompt"],
        "style_profile": render_settings["style_profile"],
        "brand_profile": render_settings["brand_profile"],
        "brand_profile_id": render_settings["brand_profile_id"],
        "brand_profile_hash": render_settings["brand_profile_hash"],
        "seed": render_settings["seed"],
        "duration_seconds": render_settings["length"],
        "tempo": render_settings["tempo"],
        "key": render_settings["key"],
        "model": model,
    }
    if model_version:
        payload["model_version"] = model_version
    return payload


def _metadata(
    *,
    provider_name: str,
    provider_generation_id: str,
    model: str,
    model_version: str | None,
    request_payload: dict[str, Any],
    render_settings: dict[str, Any],
    generation_timestamp: str,
    dry_run: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "provider": provider_name,
        "provider_name": provider_name,
        "provider_generation_id": provider_generation_id,
        "model": model,
        "model_version": model_version,
        "request_payload_hash": _canonical_digest(request_payload),
        "generated_at": generation_timestamp,
        "generation_timestamp": generation_timestamp,
        "dry_run": dry_run,
        "render_settings": render_settings,
    }
    if extra:
        metadata.update(extra)
    return metadata


class StubGenAudioAdapter:
    """Deterministic local adapter used for tests and WF-005 integration wiring."""

    provider_name = "stub_genaudio"
    model = "stub-genaudio-v1"
    model_version = "1.0.0"

    def generate(
        self,
        *,
        prompt: str,
        style_profile: str | dict[str, Any],
        seed: int | str,
        length: int,
        output_dir: Path,
        replay_key: str,
        tempo: int | None = None,
        key: str | None = None,
        brand_profile: dict[str, Any] | None = None,
        brand_profile_id: str | None = None,
        brand_profile_hash: str | None = None,
    ) -> ProviderGenerationResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = output_dir / f"{replay_key}.wav"

        render_settings = {
            "prompt": prompt,
            "style_profile": style_profile,
            "seed": seed,
            "length": length,
            "tempo": tempo,
            "key": key,
        }
        provider_generation_id = f"{self.provider_name}:{_canonical_digest(render_settings)[:16]}"
        render_settings = _build_render_settings(
            prompt=prompt,
            style_profile=style_profile,
            seed=seed,
            length=length,
            tempo=tempo,
            key=key,
            brand_profile=brand_profile,
            brand_profile_id=brand_profile_id,
            brand_profile_hash=brand_profile_hash,
        )
        request_payload = _build_provider_payload(
            render_settings=render_settings,
            model=self.model,
            model_version=self.model_version,
        )
        request_payload_hash = _canonical_digest(request_payload)
        provider_generation_id = f"{self.provider_name}:{request_payload_hash[:16]}"
        entropy_source = json.dumps(
            {
                "provider": self.provider_name,
                "provider_generation_id": provider_generation_id,
                "replay_key": replay_key,
                "seed": seed,
                "job_id": replay_key,
                "request_payload_hash": request_payload_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        duration_seconds = max(1, min(int(length), 5))
        audio_path.write_bytes(
            _deterministic_stub_wav_bytes(entropy_source=entropy_source, duration_seconds=duration_seconds, sample_rate_hz=sample_rate_hz)
        )

        return ProviderGenerationResult(
            audio_path=str(audio_path),
            provider_generation_id=provider_generation_id,
            render_metadata=_metadata(
                provider_name=self.provider_name,
                provider_generation_id=provider_generation_id,
                model=self.model,
                model_version=self.model_version,
                request_payload=request_payload,
                render_settings=render_settings,
                generation_timestamp=_utc_now_iso(),
                dry_run=True,
                extra={"generation_mode": generation_mode, "sample_rate_hz": sample_rate_hz, "visual_quality_tier": visual_quality_tier, "visual_keyframes": 3 if generation_mode == "preview" else 12},
            ),
        )


class _HttpAudioProviderAdapter:
    """Base adapter for production HTTP audio generation providers."""

    provider_name: str
    default_model: str
    default_model_version: str | None
    api_key_env: str
    endpoint_env: str
    default_endpoint: str
    auth_scheme = "Bearer"

    def __init__(
        self,
        *,
        model: str | None = None,
        model_version: str | None = None,
        credentials: ProviderCredentials | None = None,
        dry_run: bool | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.model = model or self.default_model
        self.model_version = model_version if model_version is not None else self.default_model_version
        self.credentials = credentials
        self.dry_run = _truthy_env(os.getenv("MEDIA_GENERATION_DRY_RUN")) if dry_run is None else dry_run
        self.timeout_seconds = timeout_seconds

    def _credentials(self) -> ProviderCredentials:
        if self.credentials:
            return self.credentials

        api_key = os.getenv(self.api_key_env)
        endpoint = os.getenv(self.endpoint_env, self.default_endpoint)
        if not api_key:
            raise MissingProviderCredentialsError(
                f"{self.provider_name} requires {self.api_key_env} in the environment or a secrets provider"
            )
        return ProviderCredentials(api_key=api_key, endpoint=endpoint)

    def generate(
        self,
        *,
        prompt: str,
        style_profile: str | dict[str, Any],
        seed: int | str,
        length: int,
        output_dir: Path,
        replay_key: str,
        tempo: int | None = None,
        key: str | None = None,
        brand_profile: dict[str, Any] | None = None,
        brand_profile_id: str | None = None,
        brand_profile_hash: str | None = None,
    ) -> ProviderGenerationResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        render_settings = _build_render_settings(
            prompt=prompt,
            style_profile=style_profile,
            seed=seed,
            length=length,
            tempo=tempo,
            key=key,
            brand_profile=brand_profile,
            brand_profile_id=brand_profile_id,
            brand_profile_hash=brand_profile_hash,
        )
        request_payload = _build_provider_payload(
            render_settings=render_settings,
            model=self.model,
            model_version=self.model_version,
        )
        request_payload_hash = _canonical_digest(request_payload)
        generation_timestamp = _utc_now_iso()

        if self.dry_run:
            return self._dry_run_result(
                output_dir=output_dir,
                replay_key=replay_key,
                request_payload=request_payload,
                request_payload_hash=request_payload_hash,
                render_settings=render_settings,
                generation_timestamp=generation_timestamp,
                generation_mode=generation_mode,
                sample_rate_hz=sample_rate_hz,
                visual_quality_tier=visual_quality_tier,
            )

        credentials = self._credentials()
        response_payload = self._post_generation_request(credentials=credentials, payload=request_payload)
        provider_generation_id = str(
            response_payload.get("id")
            or response_payload.get("generation_id")
            or response_payload.get("prediction", {}).get("id")
            or f"{self.provider_name}:{request_payload_hash[:16]}"
        )
        audio_path = self._persist_audio_response(
            output_dir=output_dir,
            replay_key=replay_key,
            response_payload=response_payload,
        )
        return ProviderGenerationResult(
            audio_path=str(audio_path),
            provider_generation_id=provider_generation_id,
            render_metadata=_metadata(
                provider_name=self.provider_name,
                provider_generation_id=provider_generation_id,
                model=self.model,
                model_version=self.model_version,
                request_payload=request_payload,
                render_settings=render_settings,
                generation_timestamp=generation_timestamp,
                dry_run=False,
                extra={
                    "provider_response_keys": sorted(response_payload.keys()),
                    "provider_endpoint": credentials.endpoint,
                },
            ),
        )

    def _dry_run_result(
        self,
        *,
        output_dir: Path,
        replay_key: str,
        request_payload: dict[str, Any],
        request_payload_hash: str,
        render_settings: dict[str, Any],
        generation_timestamp: str,
        generation_mode: str,
        sample_rate_hz: int,
        visual_quality_tier: str,
    ) -> ProviderGenerationResult:
        audio_path = output_dir / f"{replay_key}.wav"
        provider_generation_id = f"{self.provider_name}:dry-run:{request_payload_hash[:16]}"
        audio_path.write_bytes(
            (
                f"DRY_RUN_AUDIO|provider={self.provider_name}|model={self.model}|"
                f"generation={provider_generation_id}|replay={replay_key}"
            ).encode("utf-8")
        )
        return ProviderGenerationResult(
            audio_path=str(audio_path),
            provider_generation_id=provider_generation_id,
            render_metadata=_metadata(
                provider_name=self.provider_name,
                provider_generation_id=provider_generation_id,
                model=self.model,
                model_version=self.model_version,
                request_payload=request_payload,
                render_settings=render_settings,
                generation_timestamp=generation_timestamp,
                dry_run=True,
                extra={"generation_mode": generation_mode, "sample_rate_hz": sample_rate_hz, "visual_quality_tier": visual_quality_tier, "visual_keyframes": 3 if generation_mode == "preview" else 12},
            ),
        )

    def _post_generation_request(self, *, credentials: ProviderCredentials, payload: dict[str, Any]) -> dict[str, Any]:
        if not credentials.endpoint:
            raise MissingProviderCredentialsError(f"{self.provider_name} requires a configured endpoint")

        request = urllib.request.Request(
            credentials.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"{self.auth_scheme} {credentials.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ProviderRequestError(f"{self.provider_name} request failed: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderRequestError(f"{self.provider_name} returned non-JSON response") from exc
        if not isinstance(parsed, dict):
            raise ProviderRequestError(f"{self.provider_name} returned unsupported response payload")
        return parsed

    def _persist_audio_response(self, *, output_dir: Path, replay_key: str, response_payload: dict[str, Any]) -> Path:
        audio_path = output_dir / f"{replay_key}.wav"
        audio_b64 = response_payload.get("audio_base64") or response_payload.get("audio")
        if isinstance(audio_b64, str) and audio_b64.strip():
            try:
                audio_path.write_bytes(base64.b64decode(audio_b64))
            except ValueError as exc:
                raise ProviderRequestError(f"{self.provider_name} returned invalid base64 audio") from exc
            return audio_path

        audio_url = response_payload.get("audio_url") or response_payload.get("url")
        output = response_payload.get("output")
        if not audio_url and isinstance(output, list) and output:
            audio_url = output[0]
        if not audio_url and isinstance(output, str):
            audio_url = output
        if isinstance(audio_url, str) and audio_url.strip():
            with urllib.request.urlopen(audio_url, timeout=self.timeout_seconds) as response:
                audio_path.write_bytes(response.read())
            return audio_path

        raise ProviderRequestError(
            f"{self.provider_name} response did not include audio_base64, audio_url, url, or output"
        )


class SunoAdapter(_HttpAudioProviderAdapter):
    """Production Suno-compatible adapter; credentials are loaded at runtime."""

    provider_name = "suno"
    default_model = "chirp-v4"
    default_model_version = "v4"
    api_key_env = "SUNO_API_KEY"
    endpoint_env = "SUNO_GENERATION_ENDPOINT"
    default_endpoint = ""


class UdioAdapter(_HttpAudioProviderAdapter):
    """Production Udio-compatible adapter; credentials are loaded at runtime."""

    provider_name = "udio"
    default_model = "udio-v1"
    default_model_version = "v1"
    api_key_env = "UDIO_API_KEY"
    endpoint_env = "UDIO_GENERATION_ENDPOINT"
    default_endpoint = ""


class ReplicateAudioAdapter(_HttpAudioProviderAdapter):
    """Production Replicate adapter for audio models; credentials are loaded at runtime."""

    provider_name = "replicate"
    default_model = "meta/musicgen"
    default_model_version = "stereo-melody-large"
    api_key_env = "REPLICATE_API_TOKEN"
    endpoint_env = "REPLICATE_GENERATION_ENDPOINT"
    default_endpoint = "https://api.replicate.com/v1/predictions"

_PROVIDER_ADAPTERS: dict[str, type[_HttpAudioProviderAdapter]] = {
    SunoAdapter.provider_name: SunoAdapter,
    UdioAdapter.provider_name: UdioAdapter,
    ReplicateAudioAdapter.provider_name: ReplicateAudioAdapter,
}
_PROVIDER_ALIASES = {
    "replicate_audio": "replicate",
    "musicgen": "replicate",
    "meta/musicgen": "replicate",
    "stub": "stub_genaudio",
    "stub_genaudio": "stub_genaudio",
}


def _normalize_provider_name(provider_name: str | None) -> str:
    normalized = (provider_name or "").strip().lower().replace("-", "_")
    return _PROVIDER_ALIASES.get(normalized, normalized)


def build_media_generation_adapter(
    *,
    provider_name: str | None = None,
    model: str | None = None,
    model_version: str | None = None,
    dry_run: bool | None = None,
) -> MediaGenerationAdapter:
    """Build an adapter from scheduler/provider selection metadata."""
    normalized_provider = _normalize_provider_name(provider_name or os.getenv("MEDIA_GENERATION_PROVIDER"))
    use_dry_run = _truthy_env(os.getenv("MEDIA_GENERATION_DRY_RUN")) if dry_run is None else dry_run
    if not normalized_provider or normalized_provider == StubGenAudioAdapter.provider_name:
        return StubGenAudioAdapter()

    adapter_cls = _PROVIDER_ADAPTERS.get(normalized_provider)
    if adapter_cls is None:
        if use_dry_run:
            return StubGenAudioAdapter()
        supported = ", ".join(sorted([*_PROVIDER_ADAPTERS, StubGenAudioAdapter.provider_name]))
        raise ValueError(f"Unsupported media generation provider '{provider_name}'. Supported providers: {supported}")
    return adapter_cls(model=model, model_version=model_version, dry_run=use_dry_run)


def build_media_generation_adapter_from_scheduler(
    scheduler_decision: dict[str, Any] | None,
    *,
    dry_run: bool | None = None,
) -> MediaGenerationAdapter:
    """Build an adapter from a release scheduler decision artifact."""
    scheduler_decision = scheduler_decision or {}
    provider_name = scheduler_decision.get("selected_provider")
    model = scheduler_decision.get("selected_model")
    model_version = scheduler_decision.get("selected_model_version")

    if not provider_name:
        preset = scheduler_decision.get("provider_model_preset") or {}
        primary = preset.get("primary") or {}
        provider_name = primary.get("provider")
        model = model or primary.get("model")
        model_version = model_version or primary.get("model_version")

    return build_media_generation_adapter(
        provider_name=provider_name,
        model=model,
        model_version=model_version,
        dry_run=dry_run,
    )
