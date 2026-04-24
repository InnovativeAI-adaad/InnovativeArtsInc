"""Governance control-plane backend primitives."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.agents.execution_policy import LEVEL_3_ACTIONS
from core.gatekeeper.creative_policy import (
    ConstraintPolicyError,
    enforce_policy_safe_constraints,
    map_override_to_tier,
    validate_creative_constraints,
)

ACTION_TRAIL_KEY_ENV = "ADAAD_GOVERNANCE_HMAC_KEY"
CONTROL_SNAPSHOT_KEY_ENV = "ADAAD_CONTROL_SNAPSHOT_HMAC_KEY"
LOGGER = logging.getLogger(__name__)


class GovernanceError(ValueError):
    """Raised when governance actions fail validation."""


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: str


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "operator": {"audit.read", "ratification.request", "override.retry"},
    "reviewer": {
        "audit.read",
        "ratification.request",
        "ratification.approve",
        "ratification.reject",
        "override.approve",
        "override.reject",
        "override.retry",
    },
    "owner": {
        "audit.read",
        "ratification.request",
        "ratification.approve",
        "ratification.reject",
        "override.approve",
        "override.reject",
        "override.retry",
        "override.quarantine_release",
    },
}

OVERRIDE_TO_PERMISSION = {
    "approve": "override.approve",
    "reject": "override.reject",
    "retry": "override.retry",
    "quarantine_release": "override.quarantine_release",
}


class GovernanceControlPlane:
    def __init__(
        self,
        *,
        ratification_store: Path = Path("registry/ratification_requests.jsonl"),
        action_trail_store: Path = Path("registry/governance_action_trail.jsonl"),
        agent_log_path: Path = Path("AGENT_LOG.md"),
        provenance_log_path: Path = Path("registry/provenance_log.jsonl"),
        incidents_dir: Path = Path("projects/jrt/metadata/incidents"),
        similarity_audit_dir: Path = Path("registry/similarity_audits"),
        runtime_control_config_path: Path = Path("projects/jrt/metadata/control_plane.runtime.json"),
        control_snapshot_store: Path = Path("projects/jrt/metadata/control_snapshots.jsonl"),
    ) -> None:
        self.ratification_store = ratification_store
        self.action_trail_store = action_trail_store
        self.agent_log_path = agent_log_path
        self.provenance_log_path = provenance_log_path
        self.incidents_dir = incidents_dir
        self.similarity_audit_dir = similarity_audit_dir
        self.runtime_control_config_path = runtime_control_config_path
        self.control_snapshot_store = control_snapshot_store

    def create_ratification_request(
        self,
        *,
        actor: Actor,
        action: str,
        reason: str,
        requested_scope: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._authorize(actor, "ratification.request")
        scope = requested_scope or action
        if action not in LEVEL_3_ACTIONS:
            raise GovernanceError(f"action '{action}' is not a Level 3 action")
        self._require_reason(reason)

        now = self._now_iso()
        request = {
            "request_id": f"rat-{uuid4().hex[:12]}",
            "status": "pending",
            "action": action,
            "required_scope": scope,
            "requested_by": actor.actor_id,
            "requested_role": actor.role,
            "reason": reason,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }
        self._append_jsonl(self.ratification_store, request)
        self._record_signed_action(actor=actor, event_type="ratification_request.create", payload=request)
        return request

    def approve_ratification_request(
        self,
        *,
        actor: Actor,
        request_id: str,
        reason: str,
        approved_scope: str | None = None,
    ) -> dict[str, Any]:
        self._authorize(actor, "ratification.approve")
        self._require_reason(reason)
        return self._update_ratification(
            actor=actor,
            request_id=request_id,
            status="approved",
            reason=reason,
            resolved_scope=approved_scope,
        )

    def reject_ratification_request(self, *, actor: Actor, request_id: str, reason: str) -> dict[str, Any]:
        self._authorize(actor, "ratification.reject")
        self._require_reason(reason)
        return self._update_ratification(
            actor=actor,
            request_id=request_id,
            status="rejected",
            reason=reason,
            resolved_scope=None,
        )

    def apply_manual_override(
        self,
        *,
        actor: Actor,
        override_action: str,
        target_id: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        permission = OVERRIDE_TO_PERMISSION.get(override_action)
        if permission is None:
            raise GovernanceError(f"unsupported override action: {override_action}")
        self._authorize(actor, permission)
        self._require_reason(reason)

        event = {
            "override_id": f"ovr-{uuid4().hex[:12]}",
            "override_action": override_action,
            "target_id": target_id,
            "reason": reason,
            "metadata": metadata or {},
            "performed_at": self._now_iso(),
        }
        self._record_signed_action(actor=actor, event_type="manual_override", payload=event)
        return event

    def create_generation_strategy(
        self,
        *,
        actor: Actor,
        creative_constraints: dict[str, Any],
        override_level: str = "standard",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._authorize(actor, "override.retry")
        runtime_policy = self._load_runtime_control_policy()

        try:
            validated_constraints = validate_creative_constraints(
                creative_constraints,
                runtime_policy=runtime_policy,
            )
            override_policy = map_override_to_tier(override_level, runtime_policy=runtime_policy)
        except ConstraintPolicyError as exc:
            raise GovernanceError(str(exc)) from exc

        tempo_window = validated_constraints["tempo_window"]
        target_bpm = int(round((tempo_window["min_bpm"] + tempo_window["max_bpm"]) / 2))
        strategy_payload = {
            "strategy_id": f"strat-{uuid4().hex[:12]}",
            "created_at": self._now_iso(),
            "created_by": actor.actor_id,
            "constraints": validated_constraints,
            "override": override_policy,
            "generation_strategy": {
                "target_bpm": target_bpm,
                "candidate_keys": validated_constraints["key_window"]["keys"],
                "mood_schedule": validated_constraints["mood_arc"],
            },
            "metadata": metadata or {},
        }

        try:
            enforce_policy_safe_constraints(strategy_payload, runtime_policy=runtime_policy)
        except ConstraintPolicyError as exc:
            raise GovernanceError(str(exc)) from exc

        snapshot = self._store_signed_control_snapshot(actor=actor, strategy_payload=strategy_payload)
        strategy_payload["control_snapshot_ref"] = snapshot["snapshot_id"]
        strategy_payload["provenance_ref"] = snapshot["provenance_event_id"]
        self._record_signed_action(actor=actor, event_type="control_strategy.create", payload=strategy_payload)
        return strategy_payload

    def read_audit_explorer(self, *, actor: Actor, max_entries: int = 20) -> dict[str, Any]:
        self._authorize(actor, "audit.read")
        view = {
            "agent_log": self._read_agent_log_excerpt(max_lines=max_entries),
            "provenance_events": self._read_jsonl(self.provenance_log_path, max_entries=max_entries),
            "incidents": self._read_incident_summaries(max_entries=max_entries),
            "similarity_audits": self._read_similarity_audits(max_entries=max_entries),
        }
        self._record_signed_action(actor=actor, event_type="audit_explorer.read", payload={"max_entries": max_entries})
        return view

    def _update_ratification(
        self,
        *,
        actor: Actor,
        request_id: str,
        status: str,
        reason: str,
        resolved_scope: str | None,
    ) -> dict[str, Any]:
        requests = self._read_jsonl(self.ratification_store, max_entries=None)
        if not requests:
            raise GovernanceError("ratification request store is empty")

        updated: dict[str, Any] | None = None
        for request in requests:
            if request.get("request_id") != request_id:
                continue
            if request.get("status") != "pending":
                raise GovernanceError(f"request is not pending: {request_id}")
            request["status"] = status
            request["decision_reason"] = reason
            request["decided_by"] = actor.actor_id
            request["decider_role"] = actor.role
            request["updated_at"] = self._now_iso()
            if resolved_scope:
                request["approved_scope"] = resolved_scope
            updated = request
            break

        if updated is None:
            raise GovernanceError(f"unknown request id: {request_id}")

        self._write_jsonl(self.ratification_store, requests)
        self._record_signed_action(actor=actor, event_type=f"ratification_request.{status}", payload=updated)
        return updated

    def _record_signed_action(self, *, actor: Actor, event_type: str, payload: dict[str, Any]) -> None:
        key = os.getenv(ACTION_TRAIL_KEY_ENV)
        if not key:
            raise GovernanceError(f"missing governance key env var: {ACTION_TRAIL_KEY_ENV}")

        event = {
            "event_id": f"gov-{uuid4().hex[:12]}",
            "event_type": event_type,
            "actor_id": actor.actor_id,
            "actor_role": actor.role,
            "timestamp": self._now_iso(),
            "payload": payload,
        }

        canonical = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        event["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
        event["signature"] = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        self._append_jsonl(self.action_trail_store, event)

    def _authorize(self, actor: Actor, permission: str) -> None:
        allowed = ROLE_PERMISSIONS.get(actor.role)
        if allowed is None:
            raise GovernanceError(f"unknown role: {actor.role}")
        if permission not in allowed:
            raise GovernanceError(f"role '{actor.role}' lacks permission '{permission}'")

    @staticmethod
    def _require_reason(reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise GovernanceError("reason is required and must be non-empty")

    @staticmethod
    def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")

    def _load_runtime_control_policy(self) -> dict[str, Any]:
        if not self.runtime_control_config_path.exists():
            raise GovernanceError(
                f"runtime control config not found: {self.runtime_control_config_path}"
            )
        try:
            return json.loads(self.runtime_control_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GovernanceError(
                f"runtime control config is malformed JSON: {self.runtime_control_config_path}"
            ) from exc

    def _store_signed_control_snapshot(
        self,
        *,
        actor: Actor,
        strategy_payload: dict[str, Any],
    ) -> dict[str, Any]:
        key = os.getenv(CONTROL_SNAPSHOT_KEY_ENV) or os.getenv(ACTION_TRAIL_KEY_ENV)
        if not key:
            raise GovernanceError(
                f"missing governance key env var: {CONTROL_SNAPSHOT_KEY_ENV} or {ACTION_TRAIL_KEY_ENV}"
            )

        snapshot = {
            "snapshot_id": f"ctl-{uuid4().hex[:12]}",
            "captured_at": self._now_iso(),
            "actor_id": actor.actor_id,
            "actor_role": actor.role,
            "strategy_payload": strategy_payload,
        }
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        snapshot["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
        snapshot["signature"] = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        self._append_jsonl(self.control_snapshot_store, snapshot)

        provenance_event = {
            "event_id": f"prov-{uuid4().hex[:12]}",
            "event_type": "control_snapshot",
            "timestamp": self._now_iso(),
            "control_snapshot_ref": snapshot["snapshot_id"],
            "control_payload_sha256": snapshot["payload_sha256"],
            "strategy_id": strategy_payload.get("strategy_id"),
        }
        self._append_jsonl(self.provenance_log_path, provenance_event)
        return {
            "snapshot_id": snapshot["snapshot_id"],
            "provenance_event_id": provenance_event["event_id"],
        }

    @staticmethod
    def _read_jsonl(path: Path, *, max_entries: int | None = 20) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        skipped_malformed_records = 0

        if max_entries is None:
            rows: list[dict[str, Any]] = []
            with path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rows.append(json.loads(raw))
                    except json.JSONDecodeError:
                        skipped_malformed_records += 1
                        continue
            if skipped_malformed_records:
                LOGGER.debug("Skipped %d malformed JSONL record(s) from %s", skipped_malformed_records, path)
            return rows

        rows = deque(maxlen=max_entries)
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rows.append(json.loads(raw))
                except json.JSONDecodeError:
                    skipped_malformed_records += 1
                    continue
        if skipped_malformed_records:
            LOGGER.debug("Skipped %d malformed JSONL record(s) from %s", skipped_malformed_records, path)
        return list(rows)

    def _read_agent_log_excerpt(self, *, max_lines: int) -> list[str]:
        if not self.agent_log_path.exists():
            return []
        lines = self.agent_log_path.read_text(encoding="utf-8").splitlines()
        return lines[-max_lines:]

    def _read_incident_summaries(self, *, max_entries: int) -> list[dict[str, Any]]:
        if not self.incidents_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        skipped_incident_files = 0
        for path in sorted(self.incidents_dir.glob("*.json"))[-max_entries:]:
            try:
                incident = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                skipped_incident_files += 1
                continue
            results.append(
                {
                    "incident_id": incident.get("incident_id"),
                    "status": incident.get("status"),
                    "timestamp": incident.get("timestamp"),
                    "path": str(path),
                }
            )
        if skipped_incident_files:
            LOGGER.debug("Skipped %d malformed incident file(s) in %s", skipped_incident_files, self.incidents_dir)
        return results

    def _read_similarity_audits(self, *, max_entries: int) -> list[dict[str, Any]]:
        if not self.similarity_audit_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        skipped_audit_files = 0
        for path in sorted(self.similarity_audit_dir.glob("*.json"))[-max_entries:]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                skipped_audit_files += 1
                continue
            results.append(
                {
                    "job_id": payload.get("job_id"),
                    "decision": payload.get("decision"),
                    "max_similarity": payload.get("max_similarity"),
                    "path": str(path),
                }
            )
        if skipped_audit_files:
            LOGGER.debug("Skipped %d malformed similarity audit file(s) in %s", skipped_audit_files, self.similarity_audit_dir)
        return results

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
