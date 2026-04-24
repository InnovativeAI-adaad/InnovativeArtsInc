"""Provider adapter contracts for deterministic media generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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
    ) -> ProviderGenerationResult:
        """Generate a render for the provided contract payload."""


class StubGenAudioAdapter:
    """Deterministic local adapter used for tests and WF-005 integration wiring."""

    provider_name = "stub_genaudio"

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
        audio_path.write_bytes(
            f"STUB_AUDIO|provider={self.provider_name}|generation={provider_generation_id}|replay={replay_key}".encode(
                "utf-8"
            )
        )

        return ProviderGenerationResult(
            audio_path=str(audio_path),
            provider_generation_id=provider_generation_id,
            render_metadata={
                "provider": self.provider_name,
                "provider_generation_id": provider_generation_id,
                "model": "stub-genaudio-v1",
                "generated_at": _utc_now_iso(),
                "render_settings": render_settings,
            },
        )
