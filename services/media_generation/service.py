"""Orchestration service for WF-005 auditable music generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import MediaGenerationAdapter, StubGenAudioAdapter


@dataclass(frozen=True)
class ReplayContract:
    """Deterministic replay key contract for media generation."""

    prompt: str
    style_profile: str | dict[str, Any]
    seed: int | str
    length: int
    tempo: int | None = None
    key: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "style_profile": self.style_profile,
            "seed": self.seed,
            "length": self.length,
            "tempo": self.tempo,
            "key": self.key,
        }

    def deterministic_key(self) -> str:
        canonical = json.dumps(self.as_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _append_provenance_if_missing(provenance_log_path: Path, entry: dict[str, Any]) -> None:
    provenance_log_path.parent.mkdir(parents=True, exist_ok=True)
    dedupe_key = f"{entry['workflow']}|{entry['replay_key']}|{entry['audio_path']}"
    if provenance_log_path.exists():
        with provenance_log_path.open("r", encoding="utf-8") as existing:
            for line in existing:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                existing_key = f"{row.get('workflow')}|{row.get('replay_key')}|{row.get('audio_path')}"
                if existing_key == dedupe_key:
                    return

    with provenance_log_path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(entry, sort_keys=True) + "\n")


def generate_music_for_wf005(
    *,
    prompt: str,
    style_profile: str | dict[str, Any],
    seed: int | str,
    length: int,
    tempo: int | None = None,
    key: str | None = None,
    uniqueness_report_ref: str,
    provider: MediaGenerationAdapter | None = None,
    project_root: str | Path = ".",
) -> dict[str, Any]:
    """Callable WF-005 entrypoint that enforces replay and provenance conventions."""
    replay_contract = ReplayContract(
        prompt=prompt,
        style_profile=style_profile,
        seed=seed,
        length=length,
        tempo=tempo,
        key=key,
    )
    replay_key = replay_contract.deterministic_key()

    root = Path(project_root)
    audio_dir = root / "projects" / "jrt" / "audio" / "generated"
    metadata_dir = root / "projects" / "jrt" / "metadata" / "renders"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    render_record_path = metadata_dir / f"{replay_key}.json"

    if render_record_path.exists():
        cached = json.loads(render_record_path.read_text(encoding="utf-8"))
        response = cached["result"]
        response["replayed"] = True
        return response

    active_provider = provider or StubGenAudioAdapter()
    provider_result = active_provider.generate(
        prompt=prompt,
        style_profile=style_profile,
        seed=seed,
        length=length,
        tempo=tempo,
        key=key,
        output_dir=audio_dir,
        replay_key=replay_key,
    )

    response = {
        "audio_path": provider_result.audio_path,
        "render_metadata": provider_result.render_metadata,
        "provider_generation_id": provider_result.provider_generation_id,
        "uniqueness_report_ref": uniqueness_report_ref,
        "replay_key": replay_key,
        "replayed": False,
    }

    render_record = {
        "contract": replay_contract.as_payload(),
        "replay_key": replay_key,
        "result": response,
    }
    render_record_path.write_text(json.dumps(render_record, indent=2, sort_keys=True), encoding="utf-8")

    provenance_entry = {
        "workflow": "WF-005",
        "stage": "generate_music",
        "replay_key": replay_key,
        "audio_path": provider_result.audio_path,
        "provider_generation_id": provider_result.provider_generation_id,
        "uniqueness_report_ref": uniqueness_report_ref,
        "render_record": str(render_record_path),
    }
    _append_provenance_if_missing(root / "registry" / "provenance_log.jsonl", provenance_entry)

    return response
