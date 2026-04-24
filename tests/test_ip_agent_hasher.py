from __future__ import annotations

import json
from pathlib import Path

from core.agents.ip_agent.hasher import append_provenance_entries


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_append_provenance_entries_deduplicates_by_stable_key(tmp_path: Path) -> None:
    artifact = tmp_path / "track.wav"
    artifact.write_bytes(b"v1")
    log_path = tmp_path / "provenance.jsonl"

    first = append_provenance_entries(
        [str(artifact)],
        job_id="job-1",
        track_id="track-a",
        agent="ip_agent",
        retry_attempt=0,
        log_path=log_path,
    )
    second = append_provenance_entries(
        [str(artifact)],
        job_id="job-1",
        track_id="track-a",
        agent="ip_agent",
        retry_attempt=1,
        log_path=log_path,
    )

    assert len(first) == 1
    assert second == []
    logged = _read_jsonl(log_path)
    assert len(logged) == 1


def test_append_provenance_entries_allows_new_hash_for_same_file(tmp_path: Path) -> None:
    artifact = tmp_path / "track.wav"
    artifact.write_bytes(b"v1")
    log_path = tmp_path / "provenance.jsonl"

    append_provenance_entries(
        [str(artifact)],
        job_id="job-1",
        track_id="track-a",
        agent="ip_agent",
        retry_attempt=0,
        log_path=log_path,
    )

    artifact.write_bytes(b"v2")
    second = append_provenance_entries(
        [str(artifact)],
        job_id="job-1",
        track_id="track-a",
        agent="ip_agent",
        retry_attempt=1,
        log_path=log_path,
    )

    assert len(second) == 1
    assert second[0]["retry_attempt"] == 1
    assert second[0]["is_retry"] is True
    logged = _read_jsonl(log_path)
    assert len(logged) == 2
    assert logged[0]["sha256"] != logged[1]["sha256"]
