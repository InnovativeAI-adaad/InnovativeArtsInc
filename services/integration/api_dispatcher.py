from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


AdapterHandler = Callable[[dict[str, Any]], dict[str, Any]]


class DispatchError(RuntimeError):
    def __init__(self, *, error_type: str, message: str, retryable: bool | None = None) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


@dataclass(frozen=True)
class DispatchRequestEnvelope:
    operation: str
    job_id: str
    payload: dict[str, Any]
    provider: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class DispatchResponseEnvelope:
    operation: str
    job_id: str
    provider: str
    attempt: int
    idempotency_key: str
    result: dict[str, Any]
    terminal: bool = False


@dataclass(frozen=True)
class DispatchErrorEnvelope:
    operation: str
    job_id: str
    provider: str
    attempt: int
    idempotency_key: str
    error_type: str
    message: str
    retryable: bool
    terminal: bool


@dataclass
class ApiDispatcher:
    adapters: dict[str, dict[str, AdapterHandler]]
    project_root: Path = field(default_factory=lambda: Path("."))
    policy_path: Path = field(default_factory=lambda: Path("config/generation_policy.json"))
    runtime_overrides: dict[str, Any] | None = None
    sleep_fn: Callable[[float], None] = time.sleep

    def dispatch(self, request: DispatchRequestEnvelope) -> DispatchResponseEnvelope:
        policy = self._load_policy()
        route = self._resolve_route(policy=policy, request=request)
        provider = route["provider"]
        handler = self.adapters.get(request.operation, {}).get(provider)
        if handler is None:
            raise KeyError(f"No adapter handler for operation={request.operation} provider={provider}")

        retry_policy = policy.get("retry", {})
        max_attempts = int(retry_policy.get("max_attempts", 1))
        retryable_types = set(retry_policy.get("retryable_error_types", []))

        idempotency_key = request.idempotency_key or self._idempotency_key(request)
        cached = self._read_idempotent_success(idempotency_key=idempotency_key, operation=request.operation)
        if cached is not None:
            self._emit_telemetry({"event": "duplicate_suppressed", "operation": request.operation, "job_id": request.job_id, "provider": provider, "idempotency_key": idempotency_key})
            return DispatchResponseEnvelope(
                operation=request.operation,
                job_id=request.job_id,
                provider=provider,
                attempt=0,
                idempotency_key=idempotency_key,
                result=cached,
                terminal=True,
            )

        for attempt in range(1, max_attempts + 1):
            try:
                result = handler(request.payload)
                self._emit_attempt(
                    kind="success",
                    request=request,
                    provider=provider,
                    attempt=attempt,
                    idempotency_key=idempotency_key,
                    payload={"result": result},
                )
                return DispatchResponseEnvelope(request.operation, request.job_id, provider, attempt, idempotency_key, result, terminal=True)
            except DispatchError as err:
                retryable = err.retryable if err.retryable is not None else err.error_type in retryable_types
                terminal = attempt >= max_attempts or not retryable
                self._emit_attempt(
                    kind="error",
                    request=request,
                    provider=provider,
                    attempt=attempt,
                    idempotency_key=idempotency_key,
                    payload={"error_type": err.error_type, "message": str(err), "retryable": retryable, "terminal": terminal},
                )
                if terminal:
                    raise
                self.sleep_fn(self._backoff_seconds(attempt))

        raise RuntimeError("dispatch ended unexpectedly")

    def _load_policy(self) -> dict[str, Any]:
        path = self.project_root / self.policy_path
        policy = json.loads(path.read_text(encoding="utf-8"))
        if self.runtime_overrides:
            policy = _deep_merge(policy, self.runtime_overrides)
        return policy

    def _resolve_route(self, *, policy: dict[str, Any], request: DispatchRequestEnvelope) -> dict[str, Any]:
        ops = policy.get("operations", {})
        mapped = ops.get(request.operation, {})
        if request.provider:
            return {"provider": request.provider}
        if mapped.get("provider"):
            return mapped
        fallback = policy.get("fallback_order", [])
        if fallback:
            return fallback[0]
        raise KeyError(f"No routing policy for operation={request.operation}")

    def _idempotency_key(self, request: DispatchRequestEnvelope) -> str:
        base = {"operation": request.operation, "job_id": request.job_id, "payload": request.payload}
        return hashlib.sha256(json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _backoff_seconds(self, attempt: int) -> float:
        return min(0.1 * (2 ** (attempt - 1)), 1.0)

    def _emit_attempt(self, *, kind: str, request: DispatchRequestEnvelope, provider: str, attempt: int, idempotency_key: str, payload: dict[str, Any]) -> None:
        stamp = _utc_now()
        base = {
            "ts": stamp,
            "kind": kind,
            "operation": request.operation,
            "job_id": request.job_id,
            "provider": provider,
            "attempt": attempt,
            "idempotency_key": idempotency_key,
        }
        merged = {**base, **payload}
        self._emit_telemetry(merged)
        self._emit_provenance(merged)

    def _emit_telemetry(self, row: dict[str, Any]) -> None:
        path = self.project_root / "registry" / "metrics.jsonl"
        _append_jsonl(path, row)

    def _emit_provenance(self, row: dict[str, Any]) -> None:
        path = self.project_root / "registry" / "provenance_log.jsonl"
        _append_jsonl(path, row)

    def _read_idempotent_success(self, *, idempotency_key: str, operation: str) -> dict[str, Any] | None:
        path = self.project_root / "registry" / "provenance_log.jsonl"
        if not path.exists():
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("kind") == "success" and row.get("idempotency_key") == idempotency_key and row.get("operation") == operation:
                return row.get("result", {})
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
