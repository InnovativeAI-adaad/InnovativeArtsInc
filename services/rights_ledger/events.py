from __future__ import annotations

from enum import Enum


class RightsEventType(str, Enum):
    STREAM_REPORTED = "stream_reported"
    SYNC_LICENSED = "sync_licensed"
    ADJUSTMENT_POSTED = "adjustment_posted"
    PAYOUT_ISSUED = "payout_issued"
    DISPUTE_OPENED = "dispute_opened"
    DISPUTE_RESOLVED = "dispute_resolved"


ALL_RIGHTS_EVENT_TYPES = tuple(event.value for event in RightsEventType)
