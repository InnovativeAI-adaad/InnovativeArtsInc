"""Hard-abort handling for denied high-risk actions."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

_DEFAULT_POLICY_VERSION = "1.0.0"
_DEFAULT_LOG_PATH = Path("AGENT_LOG.md")


class HardAbortError(RuntimeError):
    """Raised when a policy-denied action must be blocked immediately."""

    def __init__(self, failure: dict[str, Any]):
        super().__init__(f"{failure['reason_code']}:{failure['action_id']}")
        self.failure = failure


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return repr(value)


def _append_abort_event(event: dict[str, Any], *, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n### ABORT-EVENT\n")
        handle.write("```json\n")
        handle.write(json.dumps(event, sort_keys=True, default=_json_default) + "\n")
        handle.write("```\n")


def hard_abort(action_id: str, reason_code: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Emit immutable abort audit event, return failure object, then raise HardAbortError."""
    context = dict(context or {})
    policy_version = str(context.get("policy_version", _DEFAULT_POLICY_VERSION))
    correlation_id = str(
        context.get("correlation_id")
        or context.get("provenance_id")
        or context.get("job_id")
        or uuid4()
    )

    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    event = {
        "event_type": "hard_abort",
        "timestamp": timestamp,
        "policy_version": policy_version,
        "action_id": action_id,
        "reason_code": reason_code,
        "correlation_id": correlation_id,
        "context": context,
    }
    log_path = Path(str(context.get("agent_log_path", _DEFAULT_LOG_PATH)))
    _append_abort_event(event, log_path=log_path)

    failure = {
        "ok": False,
        "status": "aborted",
        "stage_result_code": f"failure:abort:{reason_code.lower()}",
        "error": f"Denied action '{action_id}' via hard abort ({reason_code})",
        "policy_version": policy_version,
        "action_id": action_id,
        "reason_code": reason_code,
        "correlation_id": correlation_id,
        "provenance_id": str(context.get("provenance_id", correlation_id)),
    }
    raise HardAbortError(failure)
