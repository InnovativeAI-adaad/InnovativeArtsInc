from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from .events import RightsEventType
from .ledger import LedgerEntry


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    gross: Decimal
    adjustments: Decimal
    payouts: Decimal
    net_outstanding: Decimal
    late_adjustments: tuple[str, ...]
    open_disputes: tuple[str, ...]
    replayed_entries: tuple[str, ...]
    replay_anomalies: tuple[str, ...]


def _amount(entry: LedgerEntry) -> Decimal:
    return Decimal(str(entry.payload.get("amount", "0")))


def build_reconciliation_report(entries: Iterable[LedgerEntry], as_of: datetime) -> ReconciliationReport:
    eligible = [entry for entry in entries if entry.occurred_at <= as_of]
    gross = Decimal("0")
    adjustments = Decimal("0")
    payouts = Decimal("0")
    late_adjustments: list[str] = []

    dispute_states: dict[str, str] = {}
    replayed_entries: list[str] = []
    replay_seen: set[str] = set()
    replay_anomalies: list[str] = []

    for entry in eligible:
        if entry.event_type in {RightsEventType.STREAM_REPORTED, RightsEventType.SYNC_LICENSED}:
            gross += _amount(entry)
        elif entry.event_type == RightsEventType.ADJUSTMENT_POSTED:
            adjustments += _amount(entry)
            period_end = entry.payload.get("applies_to")
            if period_end and period_end < entry.occurred_at.date().isoformat():
                late_adjustments.append(entry.entry_id)
        elif entry.event_type == RightsEventType.PAYOUT_ISSUED:
            payouts += _amount(entry)
        elif entry.event_type == RightsEventType.DISPUTE_OPENED:
            dispute_id = str(entry.payload.get("dispute_id", entry.entry_id))
            dispute_states[dispute_id] = "opened"
        elif entry.event_type == RightsEventType.DISPUTE_RESOLVED:
            dispute_id = str(entry.payload.get("dispute_id", entry.entry_id))
            dispute_states[dispute_id] = "resolved"
            for replay_id in entry.payload.get("replayed_entry_ids", []):
                replayed_entries.append(replay_id)
                if replay_id in replay_seen:
                    replay_anomalies.append(replay_id)
                replay_seen.add(replay_id)

    open_disputes = tuple(sorted(dispute_id for dispute_id, state in dispute_states.items() if state != "resolved"))
    return ReconciliationReport(
        gross=gross,
        adjustments=adjustments,
        payouts=payouts,
        net_outstanding=(gross + adjustments - payouts),
        late_adjustments=tuple(late_adjustments),
        open_disputes=open_disputes,
        replayed_entries=tuple(replayed_entries),
        replay_anomalies=tuple(replay_anomalies),
    )
