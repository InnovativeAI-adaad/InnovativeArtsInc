from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ExperimentVariant:
    variant_id: str
    allocation_weight: float

    def __post_init__(self) -> None:
        if not self.variant_id.strip():
            raise ValueError("variant_id must be non-empty")
        if self.allocation_weight <= 0:
            raise ValueError("allocation_weight must be greater than zero")


@dataclass(frozen=True)
class MetricEvent:
    variant_id: str
    metric_name: str
    value: float


@dataclass
class ExperimentRunner:
    """Runs A/B or multi-armed tests with metric ingestion and promotion rules."""

    experiment_id: str
    primary_metric: str
    minimum_sample_size: int
    promotion_threshold: float
    variants: tuple[ExperimentVariant, ...]
    event_log: list[MetricEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.experiment_id.strip():
            raise ValueError("experiment_id must be non-empty")
        if not self.primary_metric.strip():
            raise ValueError("primary_metric must be non-empty")
        if self.minimum_sample_size < 1:
            raise ValueError("minimum_sample_size must be at least 1")
        if self.promotion_threshold <= 0:
            raise ValueError("promotion_threshold must be greater than zero")
        if len(self.variants) < 2:
            raise ValueError("variants must include at least two variants")

    def ingest_metrics(self, events: Iterable[MetricEvent]) -> None:
        valid_ids = {variant.variant_id for variant in self.variants}
        for event in events:
            if event.variant_id not in valid_ids:
                raise ValueError(f"Unknown variant_id: {event.variant_id}")
            self.event_log.append(event)

    def summarize_metric(self) -> dict[str, float]:
        sums: dict[str, float] = {variant.variant_id: 0.0 for variant in self.variants}
        counts: dict[str, int] = {variant.variant_id: 0 for variant in self.variants}

        for event in self.event_log:
            if event.metric_name != self.primary_metric:
                continue
            sums[event.variant_id] += event.value
            counts[event.variant_id] += 1

        return {
            variant_id: (sums[variant_id] / counts[variant_id]) if counts[variant_id] else 0.0
            for variant_id in sums
        }

    def _primary_metric_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {variant.variant_id: 0 for variant in self.variants}
        for event in self.event_log:
            if event.metric_name == self.primary_metric:
                counts[event.variant_id] += 1
        return counts

    def choose_winner(self) -> str | None:
        scores = self.summarize_metric()
        per_variant_counts = self._primary_metric_counts()
        sample_size = sum(per_variant_counts.values())
        if sample_size < self.minimum_sample_size:
            return None

        if any(count < self.minimum_sample_size for count in per_variant_counts.values()):
            return None

        winner_id, winner_score = max(scores.items(), key=lambda item: item[1])
        if winner_score < self.promotion_threshold:
            return None
        return winner_id

    def promotion_decision(self) -> dict[str, str | float | None]:
        winner = self.choose_winner()
        if winner is None:
            per_variant_counts = self._primary_metric_counts()
            sample_size = sum(per_variant_counts.values())
            if sample_size < self.minimum_sample_size:
                reason = "insufficient_signal"
            elif any(count < self.minimum_sample_size for count in per_variant_counts.values()):
                reason = "insufficient_per_variant_sample"
            else:
                reason = "insufficient_signal"
            return {
                "experiment_id": self.experiment_id,
                "status": "hold",
                "winner_variant_id": None,
                "reason": reason,
            }
        return {
            "experiment_id": self.experiment_id,
            "status": "promote",
            "winner_variant_id": winner,
            "reason": "threshold_passed",
        }
