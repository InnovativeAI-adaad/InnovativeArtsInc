from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class SplitVersion:
    effective_date: date
    splits: Mapping[str, Decimal]


class SplitEngine:
    def __init__(self) -> None:
        self._versions: list[SplitVersion] = []

    def register_version(self, *, effective_date: date, splits: dict[str, Decimal | str | float]) -> SplitVersion:
        normalized: dict[str, Decimal] = {}
        for payee_id, ratio in splits.items():
            normalized[payee_id] = Decimal(str(ratio))
        total = sum(normalized.values(), Decimal("0"))
        if total != Decimal("1"):
            raise ValueError(f"split ratio must equal 1, got {total}")
        if any(value < 0 for value in normalized.values()):
            raise ValueError("split values must be non-negative")

        version = SplitVersion(effective_date=effective_date, splits=MappingProxyType(normalized))
        self._versions.append(version)
        self._versions.sort(key=lambda v: v.effective_date)
        return version

    def split_for_date(self, as_of: date) -> SplitVersion:
        candidates = [version for version in self._versions if version.effective_date <= as_of]
        if not candidates:
            raise LookupError(f"no split configured for {as_of.isoformat()}")
        return candidates[-1]

    def allocate(self, *, amount: Decimal | str | float, as_of: date, precision: str = "0.01") -> dict[str, Decimal]:
        version = self.split_for_date(as_of)
        amount_dec = Decimal(str(amount))
        quantum = Decimal(precision)

        allocations: dict[str, Decimal] = {}
        remainders: list[tuple[str, Decimal]] = []
        total_allocated = Decimal("0")

        for payee_id in sorted(version.splits):
            raw = amount_dec * version.splits[payee_id]
            rounded = raw.quantize(quantum, rounding=ROUND_DOWN)
            allocations[payee_id] = rounded
            total_allocated += rounded
            remainders.append((payee_id, raw - rounded))

        leftover = amount_dec - total_allocated
        tick = quantum
        remainders.sort(key=lambda item: (-item[1], item[0]))

        idx = 0
        while leftover >= tick and remainders:
            payee_id = remainders[idx % len(remainders)][0]
            allocations[payee_id] += tick
            leftover -= tick
            idx += 1

        return allocations
