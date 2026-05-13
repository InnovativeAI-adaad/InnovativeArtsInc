"""Register release rights into the append-only rights ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Iterable

from .events import RightsEventType
from .ledger import LedgerEntry, RightsLedger, serialize_ledger_entry

DEFAULT_PROVENANCE_LOG_PATH = Path("registry/provenance_log.jsonl")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ValueError(f"provenance log not found: {path}") from exc

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL in {path} line {line_number}: {exc}") from exc
        if isinstance(value, dict):
            records.append(value)
    return records


def _record_track_keys(record: dict[str, Any]) -> set[str]:
    keys = {
        "track_id",
        "asset_id",
        "media_id",
        "work_id",
        "release_track_id",
        "id",
    }
    return {str(record[key]) for key in keys if record.get(key)}


def _record_provenance_id(record: dict[str, Any]) -> str | None:
    for key in ("track_provenance_id", "provenance_id", "id"):
        value = record.get(key)
        if value:
            return str(value)
    return None


def _track_id(master: dict[str, Any], index: int) -> str:
    for key in ("track_id", "id", "asset_id"):
        value = master.get(key)
        if value:
            return str(value)
    raise ValueError(f"masters[{index}] missing track_id")


def _provenance_by_track(provenance_log_path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for record in _read_jsonl(provenance_log_path):
        provenance_id = _record_provenance_id(record)
        if not provenance_id:
            continue
        for key in _record_track_keys(record):
            mapping[key] = provenance_id
    return mapping


def _decimal_percent(raw: Any, *, participant_index: int) -> Decimal:
    if raw in (None, ""):
        raise ValueError(f"participants[{participant_index}] ownership_percent is required")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"participants[{participant_index}] ownership_percent must be numeric") from exc
    if value <= 0 or value > 100:
        raise ValueError(f"participants[{participant_index}] ownership_percent must be > 0 and <= 100")
    return value


def validate_split_sheet_ownership(split_sheet: dict[str, Any]) -> None:
    """Block readiness if participant ownership percentages are missing or invalid."""
    participants = split_sheet.get("participants")
    if not isinstance(participants, list) or not participants:
        raise ValueError("split_sheet participants must be a non-empty array")

    total = Decimal("0")
    for index, participant in enumerate(participants):
        if not isinstance(participant, dict):
            raise ValueError(f"participants[{index}] must be an object")
        if not participant.get("party") and not participant.get("contributor_id") and not participant.get("name"):
            raise ValueError(f"participants[{index}] must identify a party")
        total += _decimal_percent(participant.get("ownership_percent"), participant_index=index)

    if total.quantize(Decimal("0.00001")) != Decimal("100.00000"):
        raise ValueError(f"ownership_percent total must equal 100.0, got {total}")


def _participant_id(participant: dict[str, Any], index: int) -> str:
    for key in ("contributor_id", "party_id", "party", "name"):
        value = participant.get(key)
        if value:
            return str(value)
    return f"participant-{index + 1}"


def _publishing_percent(participant: dict[str, Any]) -> Any:
    return participant.get("publishing_percent", participant.get("ownership_percent"))


def _append_jsonl(entries: Iterable[LedgerEntry], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(serialize_ledger_entry(entry), sort_keys=True) + "\n")
    return output_path


def register_release_rights(
    *,
    release_bundle: dict[str, Any],
    split_sheet: dict[str, Any],
    output_path: Path,
    provenance_log_path: Path = DEFAULT_PROVENANCE_LOG_PATH,
    ledger_id: str | None = None,
    job_provenance_id: str | None = None,
    occurred_at: datetime | None = None,
) -> tuple[RightsLedger, Path]:
    """Register a release bundle and split sheet in the rights ledger JSONL stream.

    The function emits release-readiness events for work creation, master
    registration, contributor splits, publishing splits, and provenance binding.
    It raises ``ValueError`` before writing anything if ownership percentages are
    missing, invalid, or do not total 100%.
    """
    validate_split_sheet_ownership(split_sheet)

    release_id = str(release_bundle.get("release_id") or split_sheet.get("release_id") or "")
    if not release_id:
        raise ValueError("release_id is required")

    masters = release_bundle.get("masters")
    if not isinstance(masters, list) or not masters:
        raise ValueError("release_bundle masters must be a non-empty array")

    provenance_map = _provenance_by_track(provenance_log_path)
    track_ids = [_track_id(master, index) for index, master in enumerate(masters)]
    missing = [track_id for track_id in track_ids if track_id not in provenance_map]
    if missing:
        raise ValueError(f"missing track provenance IDs in {provenance_log_path}: {missing}")

    occurred_at = occurred_at or _utc_now()
    if occurred_at.tzinfo is None:
        raise ValueError("occurred_at must be timezone-aware")

    ledger = RightsLedger(ledger_id or f"rights-ledger:{release_id}")
    job_id = job_provenance_id or f"release-registration:{release_id}"
    participants = split_sheet["participants"]
    primary_track_provenance_id = provenance_map[track_ids[0]]

    ledger.append(
        event_type=RightsEventType.WORK_CREATED,
        track_provenance_id=primary_track_provenance_id,
        job_provenance_id=job_id,
        occurred_at=occurred_at,
        payload={
            "release_id": release_id,
            "title": release_bundle.get("title"),
            "artist_name": release_bundle.get("artist_name"),
            "split_sheet_id": split_sheet.get("split_sheet_id"),
            "identifiers": release_bundle.get("identifiers", {}),
        },
    )

    for master, track_id in zip(masters, track_ids, strict=True):
        track_provenance_id = provenance_map[track_id]
        ledger.append(
            event_type=RightsEventType.MASTER_REGISTERED,
            track_provenance_id=track_provenance_id,
            job_provenance_id=job_id,
            occurred_at=occurred_at,
            payload={
                "release_id": release_id,
                "track_id": track_id,
                "master": dict(master),
                "identifiers": release_bundle.get("identifiers", {}),
            },
        )
        ledger.append(
            event_type=RightsEventType.PROVENANCE_BOUND,
            track_provenance_id=track_provenance_id,
            job_provenance_id=job_id,
            occurred_at=occurred_at,
            payload={
                "release_id": release_id,
                "track_id": track_id,
                "track_provenance_id": track_provenance_id,
                "provenance_log_path": str(provenance_log_path),
            },
        )

    for index, participant in enumerate(participants):
        participant_id = _participant_id(participant, index)
        ledger.append(
            event_type=RightsEventType.CONTRIBUTOR_SPLIT_REGISTERED,
            track_provenance_id=primary_track_provenance_id,
            job_provenance_id=job_id,
            occurred_at=occurred_at,
            payload={
                "release_id": release_id,
                "split_sheet_id": split_sheet.get("split_sheet_id"),
                "participant_id": participant_id,
                "participant": dict(participant),
                "ownership_percent": str(participant["ownership_percent"]),
            },
        )
        ledger.append(
            event_type=RightsEventType.PUBLISHING_SPLIT_REGISTERED,
            track_provenance_id=primary_track_provenance_id,
            job_provenance_id=job_id,
            occurred_at=occurred_at,
            payload={
                "release_id": release_id,
                "split_sheet_id": split_sheet.get("split_sheet_id"),
                "participant_id": participant_id,
                "publishing_percent": str(_publishing_percent(participant)),
            },
        )

    _append_jsonl(ledger.entries, output_path)
    return ledger, output_path
