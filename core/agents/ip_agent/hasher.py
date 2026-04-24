"""Provenance hashing helpers for Sovereign Ledger assets."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Iterable

from core.gatekeeper.abort import hard_abort


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


def _provenance_dedup_key(entry: dict) -> str:
    """Return a stable key used to suppress duplicate provenance rows."""
    return "|".join(
        [
            str(entry.get("job_id", "")),
            str(entry.get("track_id", "")),
            str(entry.get("file", "")),
            str(entry.get("sha256", "")),
        ]
    )


def _existing_dedup_keys(registry_log: Path) -> set[str]:
    """Stream JSONL log rows and return known dedup keys."""
    if not registry_log.exists():
        return set()

    seen: set[str] = set()
    with registry_log.open("r", encoding="utf-8") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.add(_provenance_dedup_key(entry))
    return seen


def generate_provenance_entry(
    file_path: str,
    *,
    job_id: str,
    track_id: str,
    agent: str,
    parent_artifact_hash: str | None = None,
    retry_attempt: int = 0,
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
        "retry_attempt": retry_attempt,
        "is_retry": retry_attempt > 0,
    }


def append_provenance_entries(
    file_paths: Iterable[str],
    *,
    job_id: str,
    track_id: str,
    agent: str,
    parent_artifact_hash: str | None = None,
    retry_attempt: int = 0,
    log_path: str | Path = _REGISTRY_LOG,
    deny_reason_code: str | None = None,
    policy_version: str = "1.0.0",
    correlation_id: str | None = None,
    agent_log_path: str | Path = "AGENT_LOG.md",
) -> list[dict]:
    """Hash artifacts and append JSONL provenance entries.

    Deduplication is stable across retries by keying on
    ``job_id + track_id + file + sha256``. Existing rows are streamed
    from disk into a set for O(1) duplicate checks during append.

    Raises any file or I/O exceptions so callers can stop pipeline completion.
    """
    if deny_reason_code:
        hard_abort(
            "level3.registry_write",
            deny_reason_code,
            {
                "policy_version": policy_version,
                "job_id": job_id,
                "provenance_id": correlation_id or job_id,
                "agent": agent,
                "agent_log_path": str(agent_log_path),
            },
        )

    entries = [
        generate_provenance_entry(
            file_path,
            job_id=job_id,
            track_id=track_id,
            agent=agent,
            parent_artifact_hash=parent_artifact_hash,
            retry_attempt=retry_attempt,
        )
        for file_path in file_paths
    ]

    registry_log = Path(log_path)
    registry_log.parent.mkdir(parents=True, exist_ok=True)
    seen_keys = _existing_dedup_keys(registry_log)

    appended_entries: list[dict] = []
    with registry_log.open("a", encoding="utf-8") as stream:
        for entry in entries:
            dedup_key = _provenance_dedup_key(entry)
            if dedup_key in seen_keys:
                continue
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
            seen_keys.add(dedup_key)
            appended_entries.append(entry)

    return appended_entries
