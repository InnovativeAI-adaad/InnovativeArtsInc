from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

from .events import RightsEventType


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entry_id(seed: dict[str, Any]) -> str:
    return sha256(_canonical_json(seed).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    entry_id: str
    ledger_id: str
    sequence: int
    event_type: RightsEventType
    occurred_at: datetime
    track_provenance_id: str
    job_provenance_id: str
    payload: Mapping[str, Any]
    prev_entry_id: str | None


class RightsLedger:
    def __init__(self, ledger_id: str) -> None:
        self.ledger_id = ledger_id
        self._entries: list[LedgerEntry] = []

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    def append(
        self,
        *,
        event_type: RightsEventType,
        track_provenance_id: str,
        job_provenance_id: str,
        payload: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> LedgerEntry:
        if not track_provenance_id or not job_provenance_id:
            raise ValueError("track_provenance_id and job_provenance_id are required")

        sequence = len(self._entries) + 1
        prev_entry_id = self._entries[-1].entry_id if self._entries else None
        occurred_at = occurred_at or datetime.now(tz=timezone.utc)
        if occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")

        payload_copy = dict(payload)
        seed = {
            "ledger_id": self.ledger_id,
            "sequence": sequence,
            "event_type": event_type.value,
            "occurred_at": occurred_at.isoformat(),
            "track_provenance_id": track_provenance_id,
            "job_provenance_id": job_provenance_id,
            "payload": payload_copy,
            "prev_entry_id": prev_entry_id,
        }

        entry = LedgerEntry(
            entry_id=_entry_id(seed),
            ledger_id=self.ledger_id,
            sequence=sequence,
            event_type=event_type,
            occurred_at=occurred_at,
            track_provenance_id=track_provenance_id,
            job_provenance_id=job_provenance_id,
            payload=MappingProxyType(payload_copy),
            prev_entry_id=prev_entry_id,
        )
        self._entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        prev: str | None = None
        for expected_sequence, entry in enumerate(self._entries, start=1):
            if entry.sequence != expected_sequence:
                return False
            if entry.prev_entry_id != prev:
                return False
            seed = {
                "ledger_id": entry.ledger_id,
                "sequence": entry.sequence,
                "event_type": entry.event_type.value,
                "occurred_at": entry.occurred_at.isoformat(),
                "track_provenance_id": entry.track_provenance_id,
                "job_provenance_id": entry.job_provenance_id,
                "payload": dict(entry.payload),
                "prev_entry_id": entry.prev_entry_id,
            }
            if _entry_id(seed) != entry.entry_id:
                return False
            prev = entry.entry_id
        return True
