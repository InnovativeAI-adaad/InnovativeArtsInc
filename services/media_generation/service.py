"""Orchestration service for WF-005 auditable music generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from services.generation import SceneGenerationContract

from .adapters import MediaGenerationAdapter, StubGenAudioAdapter, build_media_generation_adapter_from_scheduler
from .audio_analysis import write_analysis_artifact
from .visuals import generate_visual_params


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
    job_id: str | None = None,
    uniqueness_report_ref: str,
    provider: MediaGenerationAdapter | None = None,
    scheduler_decision: dict[str, Any] | None = None,
    dry_run: bool | None = None,
    project_root: str | Path = ".",
) -> dict[str, Any]:
    """Callable WF-005 entrypoint that enforces replay and provenance conventions."""
    replay_payload = {
        "prompt": prompt,
        "style_profile": style_profile,
        "seed": seed,
        "duration": length,
        "tempo": tempo,
        "key": key,
    }
    replay_key = hashlib.sha256(json.dumps(replay_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    scene_contract = SceneGenerationContract(
        replay_key=replay_key,
        seed=seed,
        job_id=job_id or replay_key,
        prompt=prompt,
        style_profile=style_profile,
        duration=length,
        tempo=tempo,
        key=key,
    )

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

    active_provider = provider or (
        build_media_generation_adapter_from_scheduler(scheduler_decision, dry_run=dry_run)
        if scheduler_decision
        else StubGenAudioAdapter()
    )
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

    visual_result = generate_visual_params(scene_contract)

    analysis_artifact = write_analysis_artifact(
        audio_path=provider_result.audio_path,
        job_id=replay_key,
        artifact_dir=root / "projects" / "jrt" / "metadata" / "analysis",
    )

    response = {
        "audio_path": provider_result.audio_path,
        "render_metadata": provider_result.render_metadata,
        "provider_generation_id": provider_result.provider_generation_id,
        "uniqueness_report_ref": uniqueness_report_ref,
        "analysis_artifact": analysis_artifact["artifact_path"],
        "replay_key": replay_key,
        "scene_contract": scene_contract.as_payload(),
        "visual_request": visual_result["visual_request"],
        "visual_request_payload_hash": visual_result["visual_request_payload_hash"],
        "replayed": False,
    }

    render_record = {
        "contract": scene_contract.as_payload(),
        "replay_key": replay_key,
        "result": response,
    }
    render_record_path.write_text(json.dumps(render_record, indent=2, sort_keys=True), encoding="utf-8")

    provenance_entry = {
        "workflow": "WF-005",
        "stage": "generate_scene_media",
        "replay_key": replay_key,
        "audio_path": provider_result.audio_path,
        "provider_generation_id": provider_result.provider_generation_id,
        "uniqueness_report_ref": uniqueness_report_ref,
        "render_record": str(render_record_path),
        "analysis_artifact": analysis_artifact["artifact_path"],
        "provider_name": provider_result.render_metadata.get("provider_name"),
        "model": provider_result.render_metadata.get("model"),
        "model_version": provider_result.render_metadata.get("model_version"),
        "audio_request_payload_hash": provider_result.render_metadata.get("request_payload_hash"),
        "visual_request_payload_hash": visual_result["visual_request_payload_hash"],
        "generation_timestamp": provider_result.render_metadata.get("generation_timestamp"),
        "render_metadata": provider_result.render_metadata,
    }
    _append_provenance_if_missing(root / "registry" / "provenance_log.jsonl", provenance_entry)

    return response
