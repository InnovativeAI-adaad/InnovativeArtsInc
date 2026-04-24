#!/usr/bin/env python3
"""Validate the AGENT_LOG.md HMAC chain.

Minimal usage:
  python pipelines/validate_agent_log_chain.py
  python pipelines/validate_agent_log_chain.py --log AGENT_LOG.md

The validator checks:
  1) entry_id values are strictly monotonic (+1) and zero-padded to 6 digits.
  2) prev_digest of entry N matches entry_digest of entry N-1 (GENESIS for first).
  3) entry_digest matches HMAC-SHA256 recomputation from canonical fields.
"""

from __future__ import annotations

import argparse
import os
import hmac
import re
import sys
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

DEFAULT_HMAC_KEY_ENV = "ADAAD_HMAC_KEY"
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Entry:
    heading_id: int
    entry_id: str
    timestamp: str
    action: str
    tier: str
    iai_g1: str
    iai_g2: str
    iai_g3: str
    prev_digest: str
    entry_digest: str
    human_ratified: str
    notes: str


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def canonical_payload(entry: Entry) -> bytes:
    rows = [
        ("entry_id", entry.entry_id),
        ("timestamp", entry.timestamp),
        ("action", entry.action),
        ("tier", entry.tier),
        ("IAI-G1", entry.iai_g1),
        ("IAI-G2", entry.iai_g2),
        ("IAI-G3", entry.iai_g3),
        ("prev_digest", entry.prev_digest),
        ("human_ratified", entry.human_ratified),
        ("notes", entry.notes),
    ]
    payload = "\n".join(f"{key}={_normalize(value)}" for key, value in rows) + "\n"
    return payload.encode("utf-8")


def recompute_digest(entry: Entry, hmac_key: bytes) -> str:
    return hmac.new(hmac_key, canonical_payload(entry), sha256).hexdigest()


def _extract_required(block: str, key: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}:\s*(.*)$", re.MULTILINE)
    match = pattern.search(block)
    if not match:
        raise ValueError(f"missing '{key}'")
    return match.group(1).rstrip()


def parse_entries(log_text: str) -> list[Entry]:
    heading_re = re.compile(r"^### ENTRY-(\d{6})\s*$", re.MULTILINE)
    code_re = re.compile(r"```\n(.*?)\n```", re.DOTALL)
    headings = list(heading_re.finditer(log_text))

    entries: list[Entry] = []
    for idx, heading in enumerate(headings):
        start = heading.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(log_text)
        section = log_text[start:end]
        code_match = code_re.search(section)
        if not code_match:
            raise ValueError(f"ENTRY-{heading.group(1)} missing fenced entry block")
        block = code_match.group(1)
        heading_id = int(heading.group(1))

        entry = Entry(
            heading_id=heading_id,
            entry_id=_extract_required(block, "entry_id"),
            timestamp=_extract_required(block, "timestamp"),
            action=_extract_required(block, "action"),
            tier=_extract_required(block, "tier"),
            iai_g1=_extract_required(block, "IAI-G1"),
            iai_g2=_extract_required(block, "IAI-G2"),
            iai_g3=_extract_required(block, "IAI-G3"),
            prev_digest=_extract_required(block, "prev_digest"),
            entry_digest=_extract_required(block, "entry_digest"),
            human_ratified=_extract_required(block, "human_ratified"),
            notes=_extract_required(block, "notes"),
        )
        entries.append(entry)

    if not entries:
        raise ValueError("no entries found")
    return entries


def validate(entries: list[Entry], hmac_key: bytes) -> list[str]:
    errors: list[str] = []
    previous_digest: str | None = None
    previous_id: int | None = None

    for index, entry in enumerate(entries, start=1):
        expected_id = f"{index:06d}"

        if entry.heading_id != index:
            errors.append(
                f"ENTRY heading mismatch: expected ENTRY-{expected_id}, found ENTRY-{entry.heading_id:06d}"
            )

        if entry.entry_id != expected_id:
            errors.append(
                f"entry_id mismatch at ENTRY-{expected_id}: expected {expected_id}, found {entry.entry_id}"
            )

        if not re.fullmatch(r"\d{6}", entry.entry_id):
            errors.append(f"entry_id format invalid at ENTRY-{expected_id}: '{entry.entry_id}'")

        current_num = int(entry.entry_id) if re.fullmatch(r"\d{6}", entry.entry_id) else None
        if previous_id is not None and current_num is not None and current_num != previous_id + 1:
            errors.append(
                f"entry_id not monotonic at ENTRY-{expected_id}: previous {previous_id:06d}, current {current_num:06d}"
            )
        if current_num is not None:
            previous_id = current_num

        expected_prev = "GENESIS" if index == 1 else previous_digest
        if entry.prev_digest != expected_prev:
            errors.append(
                f"prev_digest mismatch at ENTRY-{expected_id}: expected {expected_prev}, found {entry.prev_digest}"
            )

        if not DIGEST_RE.fullmatch(entry.entry_digest):
            errors.append(f"entry_digest format invalid at ENTRY-{expected_id}: '{entry.entry_digest}'")
        else:
            computed = recompute_digest(entry, hmac_key)
            if computed != entry.entry_digest:
                errors.append(
                    f"entry_digest mismatch at ENTRY-{expected_id}: expected {computed}, found {entry.entry_digest}"
                )

        previous_digest = entry.entry_digest

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AGENT_LOG.md HMAC chain invariants")
    parser.add_argument("--log", default="AGENT_LOG.md", help="Path to AGENT_LOG.md")
    parser.add_argument(
        "--hmac-key-env",
        default=DEFAULT_HMAC_KEY_ENV,
        help=(
            "Environment variable name containing the AGENT_LOG HMAC key "
            f"(default: {DEFAULT_HMAC_KEY_ENV})"
        ),
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"ERROR: log file not found: {log_path}", file=sys.stderr)
        return 2
    hmac_key = os.getenv(args.hmac_key_env)
    if not hmac_key:
        print(
            f"ERROR: required HMAC key env var '{args.hmac_key_env}' is not set; refusing to validate.",
            file=sys.stderr,
        )
        return 2

    try:
        entries = parse_entries(log_path.read_text(encoding="utf-8"))
        errors = validate(entries, hmac_key.encode("utf-8"))
    except ValueError as exc:
        print(f"INVALID: {exc}")
        return 1

    if errors:
        print("INVALID: chain check failed")
        for err in errors:
            print(f" - {err}")
        return 1

    print(f"VALID: {len(entries)} entries verified in {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
