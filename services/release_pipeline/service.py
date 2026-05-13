"""Release pipeline service for canonical release bundles and split sheets."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from .generation_scheduler import CandidateGenerationPlan, run_scheduler_hook

RELEASE_BUNDLE_SCHEMA_VERSION = "1.0.0"
RELEASE_BUNDLE_SCHEMA_RELATIVE_PATH = Path("projects/jrt/metadata/schema/release_bundle.schema.json")
RELEASE_BUNDLE_RELEASES_RELATIVE_DIR = Path("projects/jrt/metadata/releases")
_HEX_64_RE = re.compile(r"^[A-Fa-f0-9]{64}$")
_ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$|^ISRC-TBD$")
_UPC_RE = re.compile(r"^[0-9]{12,14}$|^UPC-TBD$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _default_release_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _basic_artifact_ref(item: dict[str, Any], *, default_ref_type: str) -> dict[str, Any]:
    """Normalize existing asset dictionaries into distributor-facing artifact refs."""
    ref_id = item.get("ref_id") or item.get("asset_id") or item.get("track_id") or item.get("id")
    uri = item.get("uri") or item.get("storage_uri") or item.get("asset_ref") or item.get("path")
    normalized: dict[str, Any] = {
        "ref_type": str(item.get("ref_type") or item.get("artifact_type") or default_ref_type),
        "ref_id": str(ref_id or uri or default_ref_type),
        "uri": str(uri or ref_id or default_ref_type),
    }
    if item.get("sha256"):
        normalized["sha256"] = item["sha256"]
    if item.get("mime_type"):
        normalized["mime_type"] = item["mime_type"]
    return normalized


def _release_bundle_digest_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    payload = dict(bundle)
    payload["bundle_sha256"] = ""
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict):
        payload["artifacts"] = dict(artifacts)
        payload["artifacts"]["bundle_sha256"] = ""
    return payload


def _release_bundle_path(repo_root: str | Path, release_id: str) -> Path:
    safe_release_id = re.sub(r"[^A-Za-z0-9._-]+", "-", release_id).strip("-._") or "release"
    return Path(repo_root) / RELEASE_BUNDLE_RELEASES_RELATIVE_DIR / f"{safe_release_id}.release_bundle.json"


@dataclass(frozen=True)
class SignedArtifactReference:
    artifact_type: str
    artifact_id: str
    storage_uri: str
    sha256: str
    signature: str
    signer: str
    signed_at: str

    def as_dict(self) -> dict[str, str]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "storage_uri": self.storage_uri,
            "sha256": self.sha256,
            "signature": self.signature,
            "signer": self.signer,
            "signed_at": self.signed_at,
        }


def sign_artifact_reference(
    *,
    artifact_type: str,
    artifact_id: str,
    storage_uri: str,
    artifact_payload: dict[str, Any],
    signer: str,
) -> SignedArtifactReference:
    sha256 = _digest_payload(artifact_payload)
    signature_seed = f"{signer}|{artifact_type}|{artifact_id}|{sha256}".encode("utf-8")
    signature = hashlib.sha256(signature_seed).hexdigest()
    return SignedArtifactReference(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        storage_uri=storage_uri,
        sha256=sha256,
        signature=signature,
        signer=signer,
        signed_at=_utc_now_iso(),
    )


def validate_release_bundle(bundle: dict[str, Any]) -> list[str]:
    """Validate a release bundle against the distributor-ready release contract."""
    errors: list[str] = []
    required_top_level = (
        "schema_version",
        "release_id",
        "status",
        "release_title",
        "artist",
        "contributors",
        "isrc",
        "upc",
        "label",
        "copyright",
        "publishing",
        "explicit",
        "language",
        "genre",
        "territories",
        "release_date",
        "master_audio_refs",
        "artwork_refs",
        "lyrics_refs",
        "split_sheet_refs",
        "bundle_sha256",
    )
    for field in required_top_level:
        if field not in bundle:
            errors.append(f"missing top-level field: {field}")

    for field in ("schema_version", "release_id", "release_title", "artist", "label", "language", "genre"):
        value = bundle.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string")

    if bundle.get("status") not in {"draft", "ready"}:
        errors.append("status must be one of ['draft', 'ready']")

    if not isinstance(bundle.get("explicit"), bool):
        errors.append("explicit must be a boolean")

    isrc = bundle.get("isrc")
    if not isinstance(isrc, str) or not _ISRC_RE.match(isrc):
        errors.append("isrc must be a valid 12-character ISRC or ISRC-TBD")

    upc = bundle.get("upc")
    if not isinstance(upc, str) or not _UPC_RE.match(upc):
        errors.append("upc must be 12-14 digits or UPC-TBD")

    release_date = bundle.get("release_date")
    if not isinstance(release_date, str) or not _DATE_RE.match(release_date):
        errors.append("release_date must be YYYY-MM-DD")

    copyright_payload = bundle.get("copyright")
    if not isinstance(copyright_payload, dict) or not copyright_payload:
        errors.append("copyright must be a non-empty object")
    else:
        for key in ("owner", "year", "notice"):
            if not copyright_payload.get(key):
                errors.append(f"copyright.{key} is required")

    publishing = bundle.get("publishing")
    if not isinstance(publishing, dict) or not publishing:
        errors.append("publishing must be a non-empty object")
    else:
        for key in ("publisher", "administrator"):
            if not publishing.get(key):
                errors.append(f"publishing.{key} is required")

    for field in (
        "contributors",
        "territories",
        "master_audio_refs",
        "artwork_refs",
        "lyrics_refs",
        "split_sheet_refs",
    ):
        value = bundle.get(field)
        if not isinstance(value, list) or not value:
            errors.append(f"{field} must be a non-empty array")

    for idx, contributor in enumerate(bundle.get("contributors") or []):
        if not isinstance(contributor, dict):
            errors.append(f"contributors[{idx}] must be an object")
            continue
        for key in ("name", "role"):
            if not contributor.get(key):
                errors.append(f"contributors[{idx}].{key} is required")

    for field in ("master_audio_refs", "artwork_refs", "lyrics_refs"):
        for idx, ref in enumerate(bundle.get(field) or []):
            if not isinstance(ref, dict):
                errors.append(f"{field}[{idx}] must be an object")
                continue
            for key in ("ref_type", "ref_id", "uri"):
                if not ref.get(key):
                    errors.append(f"{field}[{idx}].{key} is required")
            sha256 = ref.get("sha256")
            if sha256 is not None and (not isinstance(sha256, str) or not _HEX_64_RE.match(sha256)):
                errors.append(f"{field}[{idx}].sha256 must be 64 hex characters")

    for idx, ref in enumerate(bundle.get("split_sheet_refs") or []):
        if not isinstance(ref, dict):
            errors.append(f"split_sheet_refs[{idx}] must be an object")
            continue
        for key in ("artifact_type", "artifact_id", "storage_uri", "sha256", "signature", "signer", "signed_at"):
            if not ref.get(key):
                errors.append(f"split_sheet_refs[{idx}].{key} is required")
        for key in ("sha256", "signature"):
            value = ref.get(key)
            if value is not None and (not isinstance(value, str) or not _HEX_64_RE.match(value)):
                errors.append(f"split_sheet_refs[{idx}].{key} must be 64 hex characters")

    bundle_sha256 = bundle.get("bundle_sha256")
    if not isinstance(bundle_sha256, str) or not _HEX_64_RE.match(bundle_sha256):
        errors.append("bundle_sha256 must be 64 hex characters")
    else:
        expected = _digest_payload(_release_bundle_digest_payload(bundle))
        if bundle_sha256 != expected:
            errors.append("bundle_sha256 does not match bundle payload")

    return errors


def assert_release_bundle_ready(bundle: dict[str, Any]) -> None:
    """Raise ValueError unless the bundle can be marked distributor-ready."""
    errors = validate_release_bundle(bundle)
    if errors:
        raise ValueError("release bundle is not ready: " + "; ".join(errors))
    if bundle.get("status") != "ready":
        raise ValueError("release bundle status must be 'ready'")


def write_release_bundle(bundle: dict[str, Any], *, repo_root: str | Path) -> Path:
    """Persist a validated release bundle under projects/jrt/metadata/releases/."""
    assert_release_bundle_ready(bundle)
    target = _release_bundle_path(repo_root, str(bundle["release_id"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return target


def build_release_bundle(
    *,
    release_id: str,
    title: str,
    artist_name: str,
    masters: list[dict[str, Any]],
    stems: list[dict[str, Any]],
    credits: list[dict[str, Any]],
    rights_metadata: dict[str, Any],
    isrc: str | None = None,
    upc: str | None = None,
    label: str | None = None,
    publishing: dict[str, Any] | None = None,
    explicit: bool = False,
    language: str = "en",
    genre: str = "Pop",
    territories: list[str] | None = None,
    release_date: str | None = None,
    artwork_refs: list[dict[str, Any]] | None = None,
    lyrics_refs: list[dict[str, Any]] | None = None,
    split_sheet_refs: list[dict[str, Any]] | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    copyright_owner = str(
        rights_metadata.get("copyright_owner")
        or rights_metadata.get("owner")
        or label
        or artist_name
    )
    copyright_year = int(rights_metadata.get("copyright_year") or datetime.now(timezone.utc).year)
    copyright_notice = str(
        rights_metadata.get("copyright_notice")
        or f"© {copyright_year} {copyright_owner}. All rights reserved."
    )
    publishing_payload = publishing or rights_metadata.get("publishing") or {}
    publishing_payload = {
        "publisher": str(publishing_payload.get("publisher") or rights_metadata.get("publisher") or copyright_owner),
        "administrator": str(
            publishing_payload.get("administrator")
            or rights_metadata.get("publishing_administrator")
            or copyright_owner
        ),
        **{k: v for k, v in publishing_payload.items() if k not in {"publisher", "administrator"}},
    }
    split_refs = split_sheet_refs or rights_metadata.get("split_sheet_refs") or []
    if not split_refs:
        split_refs = [
            sign_artifact_reference(
                artifact_type="split_sheet",
                artifact_id=f"{release_id}-split-sheet",
                storage_uri=f"registry://split-sheets/{release_id}.json",
                artifact_payload={"release_id": release_id, "credits": credits, "rights_metadata": rights_metadata},
                signer="release-pipeline",
            ).as_dict()
        ]

    bundle = {
        "schema_version": RELEASE_BUNDLE_SCHEMA_VERSION,
        "release_id": release_id,
        "status": "draft",
        "release_title": title,
        "title": title,
        "artist": artist_name,
        "artist_name": artist_name,
        "contributors": credits,
        "credits": credits,
        "isrc": isrc or "ISRC-TBD",
        "upc": upc or "UPC-TBD",
        "identifiers": {
            "isrc": isrc or "ISRC-TBD",
            "upc": upc or "UPC-TBD",
        },
        "label": label or copyright_owner,
        "copyright": {
            "owner": copyright_owner,
            "year": copyright_year,
            "notice": copyright_notice,
        },
        "publishing": publishing_payload,
        "explicit": explicit,
        "language": language,
        "genre": genre,
        "territories": territories or ["WORLDWIDE"],
        "release_date": release_date or _default_release_date(),
        "master_audio_refs": [_basic_artifact_ref(master, default_ref_type="master_audio") for master in masters],
        "artwork_refs": [_basic_artifact_ref(ref, default_ref_type="artwork") for ref in (artwork_refs or [{"ref_id": f"{release_id}-artwork", "uri": f"registry://artwork/{release_id}.jpg"}])],
        "lyrics_refs": [_basic_artifact_ref(ref, default_ref_type="lyrics") for ref in (lyrics_refs or [{"ref_id": f"{release_id}-lyrics", "uri": f"registry://lyrics/{release_id}.txt"}])],
        "split_sheet_refs": split_refs,
        "created_at": _utc_now_iso(),
        "masters": masters,
        "stems": stems,
        "rights_metadata": rights_metadata,
        "artifacts": {
            "bundle_sha256": "",
            "split_sheet_refs": split_refs,
        },
        "bundle_sha256": "",
    }
    bundle["status"] = "ready"
    bundle["bundle_sha256"] = _digest_payload(_release_bundle_digest_payload(bundle))
    bundle["artifacts"]["bundle_sha256"] = bundle["bundle_sha256"]

    assert_release_bundle_ready(bundle)
    if repo_root is not None:
        write_release_bundle(bundle, repo_root=repo_root)
    return bundle


def generate_split_sheet(
    *,
    release_id: str,
    ownership_metadata: list[dict[str, Any]],
    signer: str,
    storage_uri: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    if not ownership_metadata:
        raise ValueError("ownership_metadata must not be empty")

    total_points = sum(float(item.get("ownership_percent", 0)) for item in ownership_metadata)
    if round(total_points, 5) != 100.0:
        raise ValueError(f"ownership_percent total must equal 100.0, got {total_points}")

    split_sheet = {
        "schema_version": "1.0.0",
        "split_sheet_id": f"{release_id}-split-sheet",
        "release_id": release_id,
        "created_at": _utc_now_iso(),
        "participants": ownership_metadata,
        "verification": {
            "method": "sha256",
            "ownership_total_percent": round(total_points, 5),
        },
    }

    signed_ref = sign_artifact_reference(
        artifact_type="split_sheet",
        artifact_id=split_sheet["split_sheet_id"],
        storage_uri=storage_uri,
        artifact_payload=split_sheet,
        signer=signer,
    )
    return split_sheet, signed_ref.as_dict()


def schedule_generation_job(
    *,
    job_id: str,
    candidate_plans: list[CandidateGenerationPlan],
    campaign_budget_tier: str,
    release_urgency: str,
    job_metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run generation scheduler hook and persist rationale into job metadata."""
    return run_scheduler_hook(
        job_id=job_id,
        candidate_plans=candidate_plans,
        campaign_budget_tier=campaign_budget_tier,
        release_urgency=release_urgency,
        job_metadata=job_metadata or {},
    )
