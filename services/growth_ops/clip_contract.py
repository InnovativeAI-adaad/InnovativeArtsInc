from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ClipAsset:
    """Asset input required to produce a campaign clip variant."""

    asset_id: str
    asset_type: str
    uri: str
    duration_seconds: float

    def __post_init__(self) -> None:
        if not self.asset_id.strip():
            raise ValueError("asset_id must be a non-empty string")
        if not self.asset_type.strip():
            raise ValueError("asset_type must be a non-empty string")
        if not self.uri.strip():
            raise ValueError("uri must be a non-empty string")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be greater than zero")


@dataclass(frozen=True)
class CampaignMetadata:
    """Metadata context for a growth campaign clip job."""

    campaign_id: str
    release_id: str
    channel: str
    objective: str
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.campaign_id.strip():
            raise ValueError("campaign_id must be a non-empty string")
        if not self.release_id.strip():
            raise ValueError("release_id must be a non-empty string")
        if not self.channel.strip():
            raise ValueError("channel must be a non-empty string")
        if not self.objective.strip():
            raise ValueError("objective must be a non-empty string")


@dataclass(frozen=True)
class VariantStrategy:
    """Strategy configuration for generated clip variants."""

    strategy_id: str
    variant_count: int
    max_duration_seconds: float
    hooks: tuple[str, ...] = ()
    cta_templates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if self.variant_count < 1:
            raise ValueError("variant_count must be greater than zero")
        if self.max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than zero")


@dataclass(frozen=True)
class ClipGenerationJobContract:
    """Contract for clip generation jobs in growth operations."""

    job_id: str
    assets: tuple[ClipAsset, ...]
    campaign: CampaignMetadata
    variant_strategy: VariantStrategy
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id must be a non-empty string")
        if not self.assets:
            raise ValueError("assets must include at least one ClipAsset")

    def to_payload(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "assets": [
                {
                    "asset_id": asset.asset_id,
                    "asset_type": asset.asset_type,
                    "uri": asset.uri,
                    "duration_seconds": asset.duration_seconds,
                }
                for asset in self.assets
            ],
            "campaign": {
                "campaign_id": self.campaign.campaign_id,
                "release_id": self.campaign.release_id,
                "channel": self.campaign.channel,
                "objective": self.campaign.objective,
                "tags": list(self.campaign.tags),
            },
            "variant_strategy": {
                "strategy_id": self.variant_strategy.strategy_id,
                "variant_count": self.variant_strategy.variant_count,
                "max_duration_seconds": self.variant_strategy.max_duration_seconds,
                "hooks": list(self.variant_strategy.hooks),
                "cta_templates": list(self.variant_strategy.cta_templates),
            },
            "extras": self.extras,
        }
