from __future__ import annotations

from abc import ABC, abstractmethod
import csv
from dataclasses import dataclass
from decimal import Decimal
import json
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PayoutRecord:
    payout_id: str
    payee_id: str
    amount: Decimal
    currency: str
    track_provenance_id: str
    job_provenance_id: str


class PayoutExporter(ABC):
    @abstractmethod
    def export(self, payouts: list[PayoutRecord], output_path: Path) -> Path:
        raise NotImplementedError


class TraditionalAccountingExporter(PayoutExporter):
    def export(self, payouts: list[PayoutRecord], output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "payout_id",
                    "payee_id",
                    "amount",
                    "currency",
                    "track_provenance_id",
                    "job_provenance_id",
                ],
            )
            writer.writeheader()
            for payout in payouts:
                writer.writerow(
                    {
                        "payout_id": payout.payout_id,
                        "payee_id": payout.payee_id,
                        "amount": f"{payout.amount:.2f}",
                        "currency": payout.currency,
                        "track_provenance_id": payout.track_provenance_id,
                        "job_provenance_id": payout.job_provenance_id,
                    }
                )
        return output_path


class OnChainPayoutWriter(PayoutExporter):
    FEATURE_FLAG = "RIGHTS_LEDGER_ENABLE_ONCHAIN_WRITER"

    @classmethod
    def is_enabled(cls) -> bool:
        return os.getenv(cls.FEATURE_FLAG, "").lower() in {"1", "true", "yes"}

    def export(self, payouts: list[PayoutRecord], output_path: Path) -> Path:
        if not self.is_enabled():
            raise RuntimeError("on-chain payout writer is disabled by feature flag")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            for payout in payouts:
                handle.write(
                    json.dumps(
                        {
                            "type": "payout_transfer",
                            "payout_id": payout.payout_id,
                            "to": payout.payee_id,
                            "amount": str(payout.amount),
                            "currency": payout.currency,
                            "track_provenance_id": payout.track_provenance_id,
                            "job_provenance_id": payout.job_provenance_id,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        return output_path
