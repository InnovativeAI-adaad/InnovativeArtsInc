"""Execution policy primitives for agent retries, quarantine, and repair lineage."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from core.gatekeeper.ratification import RatificationValidationError, validate_ratification


CONFIG_PATH = Path("projects/jrt/metadata/agent_runtime_config.json")
INCIDENT_DIR = Path("projects/jrt/metadata/incidents")


LEVEL_3_ACTIONS: frozenset[str] = frozenset(
    {
        "merge_pr_main",
        "deploy_production",
        "modify_secrets_or_env",
        "delete_branch_or_file",
        "modify_ci_cd",
        "publish_release",
        "modify_governance_docs",
    }
)


def _is_level_3_action(job_payload: dict[str, Any]) -> bool:
    action = job_payload.get("action")
    if isinstance(action, str) and action in LEVEL_3_ACTIONS:
        return True

    tier = str(job_payload.get("tier", "")).strip().lower()
    return tier in {"3", "tier3", "tier_3", "level3", "level_3", "level 3"}


def _run_pre_execution_checks(job_payload: dict[str, Any]) -> None:
    if not _is_level_3_action(job_payload):
        return

    required_scope = job_payload.get("required_scope") or job_payload.get("action") or "level_3"
    if not isinstance(required_scope, str) or not required_scope:
        raise DeterministicAgentError("required_scope must be provided for Level 3 actions")

    try:
        validate_ratification(job_payload, required_scope=required_scope)
    except RatificationValidationError as exc:
        raise DeterministicAgentError(f"ratification validation failed: {exc}") from exc

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_seconds: list[float]


@dataclass(frozen=True)
class FailureClasses:
    transient: set[str]
    deterministic: set[str]


class RetryableAgentError(Exception):
    """Errors that can be retried under transient policy."""


class DeterministicAgentError(Exception):
    """Errors that should not be retried under deterministic policy."""


RepairHook = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
AgentRunner = Callable[[dict[str, Any]], dict[str, Any]]


def load_runtime_config(config_path: Path = CONFIG_PATH) -> tuple[RetryPolicy, FailureClasses]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    retry = data["retry_policy"]
    classes = data["failure_classes"]
    return (
        RetryPolicy(
            max_attempts=int(retry["max_attempts"]),
            backoff_seconds=[float(v) for v in retry["backoff_seconds"]],
        ),
        FailureClasses(
            transient=set(classes["transient"]),
            deterministic=set(classes["deterministic"]),
        ),
    )


def classify_failure(exc: Exception, classes: FailureClasses) -> str:
    name = exc.__class__.__name__
    if name in classes.transient:
        return "transient"
    if name in classes.deterministic:
        return "deterministic"
    if isinstance(exc, RetryableAgentError):
        return "transient"
    if isinstance(exc, DeterministicAgentError):
        return "deterministic"
    return "deterministic"


def _compute_backoff(policy: RetryPolicy, attempt_index: int) -> float:
    if not policy.backoff_seconds:
        return 0.0
    if attempt_index < len(policy.backoff_seconds):
        return policy.backoff_seconds[attempt_index]
    return policy.backoff_seconds[-1]


def _emit_incident(artifact: dict[str, Any], incident_dir: Path = INCIDENT_DIR) -> Path:
    incident_dir.mkdir(parents=True, exist_ok=True)
    incident_id = artifact["incident_id"]
    path = incident_dir / f"{incident_id}.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _default_repair(agent_name: str, params: dict[str, Any], reason: dict[str, Any]) -> dict[str, Any]:
    if agent_name == "MutationAgent":
        return {
            **params,
            "mutation_intensity": max(1, int(params.get("mutation_intensity", 3)) - 1),
            "retry_mode": "conservative",
            "repair_context": reason,
        }
    if agent_name == "MediaAgent":
        return {
            **params,
            "transcode_profile": params.get("transcode_profile", "safe_fallback"),
            "max_parallel": min(1, int(params.get("max_parallel", 2))),
            "repair_context": reason,
        }
    return {**params, "repair_context": reason}


def execute_with_retry_policy(
    *,
    agent_name: str,
    job_payload: dict[str, Any],
    runner: AgentRunner,
    repair_hooks: dict[str, RepairHook] | None = None,
    config_path: Path = CONFIG_PATH,
    sleep_fn: Callable[[float], None] = time.sleep,
    incident_dir: Path = INCIDENT_DIR,
) -> dict[str, Any]:
    repair_hooks = repair_hooks or {}
    retry_policy, failure_classes = load_runtime_config(config_path)

    job_id = job_payload.get("job_id") or str(uuid4())
    attempts: list[dict[str, Any]] = []
    failed_attempt_ids: list[str] = []

    for attempt in range(1, retry_policy.max_attempts + 1):
        attempt_id = str(uuid4())
        try:
            _run_pre_execution_checks(job_payload)
            result = runner(job_payload)
            if result.get("ok"):
                return {
                    "ok": True,
                    "status": "completed",
                    "job_id": job_id,
                    "agent": agent_name,
                    "attempts": attempts + [{"attempt_id": attempt_id, "result": result}],
                    "lineage": {
                        "job_id": job_id,
                        "previous_failed_attempt_ids": failed_attempt_ids,
                    },
                }
            raise DeterministicAgentError(result.get("error", "Agent returned non-ok result"))
        except Exception as exc:  # noqa: BLE001
            failure_class = classify_failure(exc, failure_classes)
            attempts.append(
                {
                    "attempt_id": attempt_id,
                    "failure_class": failure_class,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
            failed_attempt_ids.append(attempt_id)
            if failure_class == "deterministic":
                break
            if attempt < retry_policy.max_attempts:
                sleep_fn(_compute_backoff(retry_policy, attempt - 1))

    status = "quarantine"
    incident_id = f"inc-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:10]}"

    lineage = {
        "job_id": job_id,
        "failed_attempt_ids": failed_attempt_ids,
        "repair_parent_attempt_id": failed_attempt_ids[-1] if failed_attempt_ids else None,
    }

    latest_failure = attempts[-1] if attempts else {}
    reason = {
        "status": status,
        "failure_class": latest_failure.get("failure_class", "deterministic"),
        "error_type": latest_failure.get("error_type", "UnknownError"),
    }

    hook = repair_hooks.get(agent_name)
    repaired_payload = (
        hook(job_payload, reason)
        if hook
        else _default_repair(agent_name=agent_name, params=job_payload, reason=reason)
    )

    repair_attempt = {
        "attempt_id": str(uuid4()),
        "agent": agent_name,
        "status": "repair_scheduled",
        "parameters": repaired_payload,
        "lineage": {
            "repaired_from_attempt_id": lineage["repair_parent_attempt_id"],
            "all_failed_attempt_ids": failed_attempt_ids,
        },
    }

    artifact = {
        "incident_id": incident_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "job": {
            "job_id": job_id,
            "agent": agent_name,
            "input": job_payload,
        },
        "attempts": attempts,
        "lineage": lineage,
        "repair": repair_attempt,
    }

    path = _emit_incident(artifact, incident_dir=incident_dir)
    return {
        "ok": False,
        "status": status,
        "job_id": job_id,
        "agent": agent_name,
        "incident_path": str(path),
        "incident_id": incident_id,
        "attempts": attempts,
        "repair": repair_attempt,
        "lineage": lineage,
    }
