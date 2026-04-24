"""Release pipeline service for canonical release bundles and split sheets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "release_id": release_id,
        "title": title,
        "artist_name": artist_name,
        "created_at": _utc_now_iso(),
        "identifiers": {
            "isrc": isrc or "ISRC-TBD",
            "upc": upc or "UPC-TBD",
        },
        "masters": masters,
        "stems": stems,
        "credits": credits,
        "rights_metadata": rights_metadata,
        "artifacts": {
            "bundle_sha256": "",
            "split_sheet_refs": [],
        },
    }


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
