"""Post-release growth planning fed by canonical release bundles."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from services.growth_ops.attribution import AttributionLayer, CampaignEvent
from services.growth_ops.clip_contract import (
    CampaignMetadata,
    ClipAsset,
    ClipGenerationJobContract,
    VariantStrategy,
)
from services.growth_ops.experiment_runner import ExperimentRunner, ExperimentVariant
from services.growth_ops.governance import CompliancePolicy, GovernanceGuardrails, OutreachAction


BUDGET_TIERS = {"starter", "growth", "scale"}
CHANNEL_DEFAULT_MAX_DURATIONS = {
    "tiktok": 15.0,
    "instagram_reels": 15.0,
    "youtube_shorts": 30.0,
    "shorts": 30.0,
    "spotify_marquee": 30.0,
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "campaign"


def _digest_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _repo_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _normalize_channels(channels: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(channel.strip() for channel in channels if channel.strip()))
    if not normalized:
        raise ValueError("channel_list must contain at least one non-empty channel")
    return normalized


def _extract_release_assets(release_bundle: dict[str, Any]) -> tuple[ClipAsset, ...]:
    source_assets: list[dict[str, Any]] = []
    source_assets.extend(release_bundle.get("masters", []) or [])
    source_assets.extend(release_bundle.get("stems", []) or [])

    clip_assets: list[ClipAsset] = []
    for index, asset in enumerate(source_assets, start=1):
        uri = str(asset.get("uri") or asset.get("storage_uri") or asset.get("path") or "").strip()
        if not uri:
            continue
        asset_id = str(
            asset.get("asset_id")
            or asset.get("track_id")
            or asset.get("stem_id")
            or f"release-asset-{index}"
        )
        asset_type = str(asset.get("asset_type") or asset.get("type") or "audio")
        duration = float(asset.get("duration_seconds") or asset.get("duration") or 30.0)
        clip_assets.append(
            ClipAsset(
                asset_id=asset_id,
                asset_type=asset_type,
                uri=uri,
                duration_seconds=duration,
            )
        )

    if not clip_assets:
        release_id = str(release_bundle.get("release_id") or "unknown-release")
        clip_assets.append(
            ClipAsset(
                asset_id=f"{release_id}-release-bundle",
                asset_type="release_bundle",
                uri=f"registry://releases/{release_id}-bundle.json",
                duration_seconds=30.0,
            )
        )
    return tuple(clip_assets)


def _caption_variants(title: str, artist_name: str, objective: str, target_audience: str) -> list[dict[str, str]]:
    return [
        {
            "variant_id": "caption-a",
            "angle": "hook_first",
            "text": f"{artist_name} just released {title}. If you are into {target_audience}, tap in now.",
        },
        {
            "variant_id": "caption-b",
            "angle": "objective_first",
            "text": f"Help push {title} toward {objective}: save it, share it, and send it to one friend.",
        },
    ]


def _hashtags(title: str, artist_name: str, target_audience: str, objective: str) -> list[str]:
    seeds = (title, artist_name, target_audience, objective, "newmusic", "independentartist")
    tags: list[str] = []
    for seed in seeds:
        tag = re.sub(r"[^A-Za-z0-9]", "", seed.title())
        if tag:
            tags.append(f"#{tag}")
    return list(dict.fromkeys(tags))[:8]


def _budget_settings(budget_tier: str) -> dict[str, float | int | str]:
    settings = {
        "starter": {"creator_count": 3, "minimum_sample_size": 50, "promotion_threshold": 0.03, "risk_score": 45},
        "growth": {"creator_count": 8, "minimum_sample_size": 100, "promotion_threshold": 0.04, "risk_score": 65},
        "scale": {"creator_count": 20, "minimum_sample_size": 250, "promotion_threshold": 0.05, "risk_score": 85},
    }
    return settings[budget_tier]


def _append_campaign_reference(release_bundle: dict[str, Any], campaign_ref: dict[str, str]) -> None:
    artifacts = release_bundle.setdefault("artifacts", {})
    refs = artifacts.setdefault("campaign_plan_refs", [])
    if campaign_ref not in refs:
        refs.append(campaign_ref)

    provenance_refs = release_bundle.setdefault("provenance_refs", [])
    provenance_ref = {
        "ref_type": "campaign_plan",
        "ref_id": campaign_ref["artifact_id"],
        "uri": campaign_ref["storage_uri"],
    }
    if provenance_ref not in provenance_refs:
        provenance_refs.append(provenance_ref)


def build_campaign_plan(
    *,
    release_bundle: dict[str, Any],
    target_audience: str,
    channel_list: Iterable[str],
    budget_tier: str,
    campaign_objective: str,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    """Build and persist a post-release growth plan for a release bundle.

    The function consumes the canonical release bundle, creates growth artifacts,
    writes them to ``projects/jrt/metadata/campaigns/<release_id>.json``, and
    appends the campaign artifact reference to the release bundle's artifact and
    provenance reference collections.
    """
    release_id = str(release_bundle.get("release_id") or "").strip()
    if not release_id:
        raise ValueError("release_bundle.release_id must be non-empty")
    if not target_audience.strip():
        raise ValueError("target_audience must be non-empty")
    if not campaign_objective.strip():
        raise ValueError("campaign_objective must be non-empty")

    normalized_budget_tier = budget_tier.strip().lower()
    if normalized_budget_tier not in BUDGET_TIERS:
        raise ValueError(f"budget_tier must be one of {sorted(BUDGET_TIERS)}")

    channels = _normalize_channels(channel_list)
    root = Path(repo_root)
    campaign_dir = root / "projects" / "jrt" / "metadata" / "campaigns"
    campaign_dir.mkdir(parents=True, exist_ok=True)
    campaign_path = campaign_dir / f"{release_id}.json"

    title = str(release_bundle.get("title") or release_id)
    artist_name = str(release_bundle.get("artist_name") or "Unknown Artist")
    objective_slug = _slug(campaign_objective)
    campaign_id = f"{release_id}-{objective_slug}-growth"
    settings = _budget_settings(normalized_budget_tier)
    assets = _extract_release_assets(release_bundle)

    clip_jobs = []
    experiments = []
    attribution = AttributionLayer()
    guardrails = GovernanceGuardrails(
        CompliancePolicy(
            policy_id="growth-outreach-v1",
            required_checks=("consent_validation", "brand_safety", "platform_terms_review"),
        )
    )

    for channel in channels:
        channel_slug = _slug(channel)
        campaign_metadata = CampaignMetadata(
            campaign_id=campaign_id,
            release_id=release_id,
            channel=channel,
            objective=campaign_objective,
            tags=(normalized_budget_tier, objective_slug),
        )
        strategy = VariantStrategy(
            strategy_id=f"{campaign_id}-{channel_slug}-clip-strategy",
            variant_count=3,
            max_duration_seconds=CHANNEL_DEFAULT_MAX_DURATIONS.get(channel_slug, 20.0),
            hooks=("first_three_seconds", "chorus/payoff", "creator_reaction"),
            cta_templates=("stream_now", "save_this_release", "share_with_a_friend"),
        )
        clip_contract = ClipGenerationJobContract(
            job_id=f"{campaign_id}-{channel_slug}-clips",
            assets=assets,
            campaign=campaign_metadata,
            variant_strategy=strategy,
            extras={
                "target_audience": target_audience,
                "source_release_bundle_id": release_id,
                "budget_tier": normalized_budget_tier,
            },
        )
        clip_jobs.append(clip_contract.to_payload())

        experiment = ExperimentRunner(
            experiment_id=f"{campaign_id}-{channel_slug}-ab",
            primary_metric="click_through_rate",
            minimum_sample_size=int(settings["minimum_sample_size"]),
            promotion_threshold=float(settings["promotion_threshold"]),
            variants=(
                ExperimentVariant(variant_id=f"{channel_slug}-hook-a", allocation_weight=0.5),
                ExperimentVariant(variant_id=f"{channel_slug}-hook-b", allocation_weight=0.5),
            ),
        )
        experiments.append(
            {
                "experiment_id": experiment.experiment_id,
                "channel": channel,
                "primary_metric": experiment.primary_metric,
                "minimum_sample_size": experiment.minimum_sample_size,
                "promotion_threshold": experiment.promotion_threshold,
                "variants": [
                    {"variant_id": variant.variant_id, "allocation_weight": variant.allocation_weight}
                    for variant in experiment.variants
                ],
                "initial_decision": experiment.promotion_decision(),
            }
        )

        attribution.record_event(
            CampaignEvent(
                event_id=f"{campaign_id}-{channel_slug}-planned-impression",
                campaign_id=campaign_id,
                release_id=release_id,
                user_id="planned-audience",
                event_type="planned_impression",
            )
        )

    campaign_ref = {
        "artifact_type": "campaign_plan",
        "artifact_id": f"{release_id}-campaign-plan",
        "storage_uri": f"registry://projects/jrt/metadata/campaigns/{release_id}.json",
    }

    outreach_action = OutreachAction(
        action_id="paid_influencer_outreach",
        channel="creator_outreach",
        risk_score=int(settings["risk_score"]),
        audience_size=max(1, int(settings["creator_count"])),
    )
    governance_report = guardrails.evaluate(
        outreach_action,
        completed_checks={"consent_validation", "brand_safety", "platform_terms_review"},
        approved_by_human=False,
    )

    plan = {
        "schema_version": "1.0.0",
        "campaign_id": campaign_id,
        "release_id": release_id,
        "source_release_bundle": {
            "release_id": release_id,
            "title": title,
            "artist_name": artist_name,
            "bundle_sha256": release_bundle.get("artifacts", {}).get("bundle_sha256", ""),
        },
        "target_audience": target_audience,
        "channels": list(channels),
        "budget_tier": normalized_budget_tier,
        "campaign_objective": campaign_objective,
        "artifacts": {
            "short_clips": clip_jobs,
            "captions": _caption_variants(title, artist_name, campaign_objective, target_audience),
            "hashtags": _hashtags(title, artist_name, target_audience, campaign_objective),
            "utm_conventions": {
                "source": "channel_slug",
                "medium": "post_release_growth",
                "campaign": campaign_id,
                "content": "{channel}-{variant_id}",
                "term": _slug(target_audience),
                "example": f"utm_source={_slug(channels[0])}&utm_medium=post_release_growth&utm_campaign={campaign_id}&utm_content={_slug(channels[0])}-hook-a",
            },
            "creator_outreach": {
                "creator_count": settings["creator_count"],
                "brief": f"Invite creators who reach {target_audience} to react to or soundtrack content with {title}.",
                "channels": list(channels),
                "governance": governance_report,
            },
            "ab_experiment_plans": experiments,
            "attribution_seed": attribution.attributed_summary(release_id),
        },
        "artifact_ref": campaign_ref,
    }
    campaign_ref["sha256"] = _digest_payload(plan)
    plan["artifact_ref"] = campaign_ref

    campaign_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    _append_campaign_reference(release_bundle, campaign_ref)
    plan["artifact_ref"]["path"] = _repo_path(campaign_path, root)
    return plan
