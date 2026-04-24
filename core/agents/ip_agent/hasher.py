"""Provenance hashing helpers for Sovereign Ledger assets."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path


def generate_provenance_entry(file_path: str, asset_type: str) -> dict:
    """Generate a provenance entry containing SHA-256 and timestamp metadata."""
    target = Path(file_path)
    if not target.exists():
        raise FileNotFoundError(
            f"File not found: '{file_path}'. Provide a valid path to an existing file."
        )
    if not target.is_file():
        raise ValueError(
            f"Path is not a file: '{file_path}'. Provide a path to a regular file, not a directory."
        )

    file_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "file": str(target),
        "type": asset_type,
        "sha256": file_hash,
        "authority": "HUMAN-0",
    }
