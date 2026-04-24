from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from services.rights_ledger import (
    OnChainPayoutWriter,
    PayoutRecord,
    RightsEventType,
    RightsLedger,
    SplitEngine,
    TraditionalAccountingExporter,
    build_reconciliation_report,
)


def test_event_types_and_append_only_chain() -> None:
    ledger = RightsLedger("ledger-1")
    first = ledger.append(
        event_type=RightsEventType.STREAM_REPORTED,
        track_provenance_id="track-prov-1",
        job_provenance_id="job-prov-1",
        payload={"amount": "12.50"},
        occurred_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    second = ledger.append(
        event_type=RightsEventType.SYNC_LICENSED,
        track_provenance_id="track-prov-1",
        job_provenance_id="job-prov-2",
        payload={"amount": "100.00"},
        occurred_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )

    assert first.entry_id != second.entry_id
    assert second.prev_entry_id == first.entry_id
    assert ledger.verify_chain()


def test_split_engine_effective_date_and_rounding() -> None:
    engine = SplitEngine()
    engine.register_version(effective_date=date(2026, 1, 1), splits={"artist": "0.5", "label": "0.5"})
    engine.register_version(effective_date=date(2026, 3, 1), splits={"artist": "0.3333", "label": "0.6667"})

    jan_allocations = engine.allocate(amount=Decimal("10.01"), as_of=date(2026, 2, 1))
    mar_allocations = engine.allocate(amount=Decimal("10.01"), as_of=date(2026, 3, 15))

    assert jan_allocations == {"artist": Decimal("5.01"), "label": Decimal("5.00")}
    assert mar_allocations["artist"] + mar_allocations["label"] == Decimal("10.01")
    assert mar_allocations == {"artist": Decimal("3.34"), "label": Decimal("6.67")}


def test_payout_exporters_and_feature_flag(monkeypatch, tmp_path) -> None:
    payouts = [
        PayoutRecord(
            payout_id="payout-1",
            payee_id="artist-wallet",
            amount=Decimal("15.25"),
            currency="USD",
            track_provenance_id="track-prov-1",
            job_provenance_id="job-prov-3",
        )
    ]

    csv_path = TraditionalAccountingExporter().export(payouts, tmp_path / "payouts.csv")
    assert csv_path.read_text(encoding="utf-8").splitlines()[0].startswith("payout_id,payee_id")

    writer = OnChainPayoutWriter()
    monkeypatch.delenv(OnChainPayoutWriter.FEATURE_FLAG, raising=False)
    try:
        writer.export(payouts, tmp_path / "payouts.jsonl")
        assert False, "expected disabled feature flag to raise"
    except RuntimeError:
        pass

    monkeypatch.setenv(OnChainPayoutWriter.FEATURE_FLAG, "true")
    jsonl_path = writer.export(payouts, tmp_path / "payouts.jsonl")
    assert "payout_transfer" in jsonl_path.read_text(encoding="utf-8")


def test_reconciliation_late_adjustments_and_dispute_replays() -> None:
    ledger = RightsLedger("ledger-2")
    ledger.append(
        event_type=RightsEventType.STREAM_REPORTED,
        track_provenance_id="track-prov-2",
        job_provenance_id="job-prov-10",
        payload={"amount": "20.00"},
        occurred_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    original_adjustment = ledger.append(
        event_type=RightsEventType.ADJUSTMENT_POSTED,
        track_provenance_id="track-prov-2",
        job_provenance_id="job-prov-11",
        payload={"amount": "-2.00", "applies_to": "2026-03-31"},
        occurred_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )
    ledger.append(
        event_type=RightsEventType.PAYOUT_ISSUED,
        track_provenance_id="track-prov-2",
        job_provenance_id="job-prov-12",
        payload={"amount": "10.00"},
        occurred_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    )
    ledger.append(
        event_type=RightsEventType.DISPUTE_OPENED,
        track_provenance_id="track-prov-2",
        job_provenance_id="job-prov-13",
        payload={"dispute_id": "disp-1"},
        occurred_at=datetime(2026, 4, 21, 3, tzinfo=timezone.utc),
    )
    ledger.append(
        event_type=RightsEventType.DISPUTE_RESOLVED,
        track_provenance_id="track-prov-2",
        job_provenance_id="job-prov-14",
        payload={"dispute_id": "disp-1", "replayed_entry_ids": [original_adjustment.entry_id]},
        occurred_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
    )
    ledger.append(
        event_type=RightsEventType.DISPUTE_RESOLVED,
        track_provenance_id="track-prov-2",
        job_provenance_id="job-prov-15",
        payload={"dispute_id": "disp-1", "replayed_entry_ids": [original_adjustment.entry_id]},
        occurred_at=datetime(2026, 4, 23, tzinfo=timezone.utc),
    )

    report = build_reconciliation_report(ledger.entries, as_of=datetime(2026, 4, 24, tzinfo=timezone.utc))

    assert report.gross == Decimal("20.00")
    assert report.adjustments == Decimal("-2.00")
    assert report.payouts == Decimal("10.00")
    assert report.net_outstanding == Decimal("8.00")
    assert len(report.late_adjustments) == 1
    assert report.open_disputes == ()
    assert report.replayed_entries == (original_adjustment.entry_id, original_adjustment.entry_id)
    assert report.replay_anomalies == (original_adjustment.entry_id,)
