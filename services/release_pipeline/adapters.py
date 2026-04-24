"""Provider adapter interfaces for release delivery integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AdapterSubmissionResult:
    provider: str
    accepted: bool
    external_reference_id: str
    message: str


class DSPSubmissionAdapter(Protocol):
    """Adapter contract for submitting release bundles to a DSP provider."""

    provider_name: str

    def submit_release_bundle(self, release_bundle: dict) -> AdapterSubmissionResult:
        """Submit a canonical release bundle payload to the provider."""


class PRORegistrationAdapter(Protocol):
    """Adapter contract for registering works with a PRO provider."""

    provider_name: str

    def register_work(self, release_bundle: dict, split_sheet: dict) -> AdapterSubmissionResult:
        """Register work ownership/splits for royalties collection."""


class StubDSPSubmissionAdapter:
    """Stub adapter that always returns a deterministic accepted response."""

    provider_name = "stub_dsp"

    def submit_release_bundle(self, release_bundle: dict) -> AdapterSubmissionResult:
        release_id = str(release_bundle.get("release_id", "unknown-release"))
        return AdapterSubmissionResult(
            provider=self.provider_name,
            accepted=True,
            external_reference_id=f"{self.provider_name}:{release_id}",
            message="stubbed submission accepted",
        )


class StubPRORegistrationAdapter:
    """Stub adapter that always returns a deterministic accepted response."""

    provider_name = "stub_pro"

    def register_work(self, release_bundle: dict, split_sheet: dict) -> AdapterSubmissionResult:
        release_id = str(release_bundle.get("release_id", "unknown-release"))
        split_sheet_id = str(split_sheet.get("split_sheet_id", "unknown-split-sheet"))
        return AdapterSubmissionResult(
            provider=self.provider_name,
            accepted=True,
            external_reference_id=f"{self.provider_name}:{release_id}:{split_sheet_id}",
            message="stubbed registration accepted",
        )
