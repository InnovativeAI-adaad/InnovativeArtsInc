"""Provenance hashing helpers for Sovereign Ledger assets."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Iterable


_REGISTRY_LOG = Path("registry/provenance_log.jsonl")


def _sha256_for_file(target: Path) -> str:
    if not target.exists():
        raise FileNotFoundError(
            f"File not found: '{target}'. Provide a valid path to an existing file."
        )
    if not target.is_file():
        raise ValueError(
            f"Path is not a file: '{target}'. Provide a path to a regular file, not a directory."
        )
    return hashlib.sha256(target.read_bytes()).hexdigest()


def generate_provenance_entry(
    file_path: str,
    *,
    job_id: str,
    track_id: str,
    agent: str,
    parent_artifact_hash: str | None = None,
) -> dict:
    """Generate a provenance entry with required sovereign-ledger fields."""
    target = Path(file_path)
    file_hash = _sha256_for_file(target)

    return {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "job_id": job_id,
        "track_id": track_id,
        "file": str(target),
        "sha256": file_hash,
        "agent": agent,
        "parent_artifact_hash": parent_artifact_hash,
    }


def append_provenance_entries(
    file_paths: Iterable[str],
    *,
    job_id: str,
    track_id: str,
    agent: str,
    parent_artifact_hash: str | None = None,
    log_path: str | Path = _REGISTRY_LOG,
) -> list[dict]:
    """Hash artifacts and append JSONL provenance entries.

    Raises any file or I/O exceptions so callers can stop pipeline completion.
    """
    entries = [
        generate_provenance_entry(
            file_path,
            job_id=job_id,
            track_id=track_id,
            agent=agent,
            parent_artifact_hash=parent_artifact_hash,
        )
        for file_path in file_paths
    ]

    registry_log = Path(log_path)
    registry_log.parent.mkdir(parents=True, exist_ok=True)

    with registry_log.open("a", encoding="utf-8") as stream:
        for entry in entries:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")

    return entries
