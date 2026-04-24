from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class AudienceRecord:
    user_id: str
    email: str | None = None
    phone: str | None = None
    consent_email: bool = False
    consent_sms: bool = False
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.user_id.strip():
            raise ValueError("user_id must be non-empty")
        if not self.email and not self.phone:
            raise ValueError("At least one contact point (email/phone) is required")


@dataclass(frozen=True)
class ConsentStateChange:
    user_id: str
    channel: str
    consent_granted: bool
    changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        normalized_channel = self.channel.strip().lower()
        if normalized_channel not in {"email", "sms"}:
            raise ValueError("channel must be one of: email, sms")
        object.__setattr__(self, "channel", normalized_channel)


class FirstPartyCRMConnector:
    """Simple first-party audience capture + consent-state tracking connector."""

    def __init__(self, source_name: str) -> None:
        if not source_name.strip():
            raise ValueError("source_name must be non-empty")
        self.source_name = source_name
        self._audience: dict[str, AudienceRecord] = {}
        self._consent_events: list[ConsentStateChange] = []

    def capture_audience(self, record: AudienceRecord) -> None:
        self._audience[record.user_id] = record

    def update_consent(self, change: ConsentStateChange) -> None:
        current = self._audience.get(change.user_id)
        if current is None:
            raise ValueError(f"Cannot update consent for unknown user_id: {change.user_id}")

        if change.channel == "email":
            updated = AudienceRecord(
                user_id=current.user_id,
                email=current.email,
                phone=current.phone,
                consent_email=change.consent_granted,
                consent_sms=current.consent_sms,
                captured_at=current.captured_at,
            )
        else:
            updated = AudienceRecord(
                user_id=current.user_id,
                email=current.email,
                phone=current.phone,
                consent_email=current.consent_email,
                consent_sms=change.consent_granted,
                captured_at=current.captured_at,
            )
        self._audience[change.user_id] = updated
        self._consent_events.append(change)

    def export(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "audience": [
                {
                    "user_id": record.user_id,
                    "email": record.email,
                    "phone": record.phone,
                    "consent_email": record.consent_email,
                    "consent_sms": record.consent_sms,
                    "captured_at": record.captured_at.isoformat(),
                }
                for record in self._audience.values()
            ],
            "consent_events": [
                {
                    "user_id": event.user_id,
                    "channel": event.channel,
                    "consent_granted": event.consent_granted,
                    "changed_at": event.changed_at.isoformat(),
                }
                for event in self._consent_events
            ],
        }
