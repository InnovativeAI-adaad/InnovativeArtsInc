from __future__ import annotations

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class CampaignEvent:
    event_id: str
    campaign_id: str
    release_id: str
    user_id: str
    event_type: str
    value: float = 0.0


@dataclass(frozen=True)
class MonetizationLedgerEntry:
    ledger_id: str
    release_id: str
    amount: float
    currency: str


class AttributionLayer:
    """Links campaign events to release IDs and monetization ledger entries."""

    def __init__(self) -> None:
        self._events: list[CampaignEvent] = []
        self._ledger: dict[str, list[MonetizationLedgerEntry]] = {}

    def record_event(self, event: CampaignEvent) -> None:
        if not event.event_id.strip():
            raise ValueError("event_id must be non-empty")
        if not event.release_id.strip():
            raise ValueError("release_id must be non-empty")
        self._events.append(event)

    def attach_ledger_entry(self, entry: MonetizationLedgerEntry) -> None:
        if not entry.release_id.strip():
            raise ValueError("release_id must be non-empty")
        if not entry.currency.strip():
            raise ValueError("currency must be non-empty")
        if not math.isfinite(entry.amount):
            raise ValueError("amount must be finite")

        currency = entry.currency.strip()
        if currency != currency.upper() or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("currency must be an uppercase ISO-style code")

        self._ledger.setdefault(entry.release_id, []).append(entry)

    def attributed_summary(self, release_id: str) -> dict[str, object]:
        release_events = [event for event in self._events if event.release_id == release_id]
        ledger_entries = self._ledger.get(release_id, [])

        totals_by_currency: dict[str, float] = {}
        for entry in ledger_entries:
            totals_by_currency[entry.currency] = totals_by_currency.get(entry.currency, 0.0) + entry.amount

        summary: dict[str, object] = {
            "release_id": release_id,
            "event_count": len(release_events),
            "events": [
                {
                    "event_id": event.event_id,
                    "campaign_id": event.campaign_id,
                    "user_id": event.user_id,
                    "event_type": event.event_type,
                    "value": event.value,
                }
                for event in release_events
            ],
            "ledger_entries": [
                {
                    "ledger_id": entry.ledger_id,
                    "amount": entry.amount,
                    "currency": entry.currency,
                }
                for entry in ledger_entries
            ],
            "totals_by_currency": totals_by_currency,
        }

        if len(totals_by_currency) == 1:
            summary["total_revenue"] = next(iter(totals_by_currency.values()))

        return summary
