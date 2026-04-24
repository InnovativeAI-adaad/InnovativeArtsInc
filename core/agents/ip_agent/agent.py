"""IPAgent baseline implementation with ADAAD-required agent signatures."""

from __future__ import annotations

import datetime as dt
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.gatekeeper.abort import HardAbortError, hard_abort
from core.agents.ip_agent.hasher import append_provenance_entries
from core.agents.ip_agent.telemetry import append_stage_metric


_DEF_NAME = "ip_agent"
_STAGE_RUN = "ip_agent.run"
_STAGE_UNIQUENESS_AUDIT = "ip_agent.uniqueness_audit"
_SIMILARITY_AUDIT_DIR = Path("registry/similarity_audits")
_DEFAULT_POLICY_PATH = Path("core/agents/ip_agent/config/similarity_policy.v1.json")


@dataclass(frozen=True)
class SimilarityMethodResult:
    method: str
    version: str
    model_id: str | None
    score: float
    threshold: float
    required_for_release_intent: bool


@dataclass(frozen=True)
class SimilarityPolicy:
    version: str
    threshold_source: str
    revise_threshold: float
    block_threshold: float
    confidence_floor: float
    decision_policy: str
    method_weights: dict[str, float]
    required_methods_release_intent: set[str]
    strategy_versions: dict[str, str]
    strategy_model_ids: dict[str, str | None]


class SimilarityStrategy:
    method = "base"

    def __init__(self, *, version: str, model_id: str | None = None) -> None:
        self.version = version
        self.model_id = model_id

    def score(self, candidate: Any, prior: Any) -> float | None:
        raise NotImplementedError


class MetadataSimilarityStrategy(SimilarityStrategy):
    method = "metadata"

    def score(self, candidate: Any, prior: Any) -> float | None:
        if candidate is None or prior is None:
            return None
        return _jaccard_similarity(candidate, prior)


class FingerprintSimilarityStrategy(SimilarityStrategy):
    method = "fingerprint"

    def score(self, candidate: Any, prior: Any) -> float | None:
        if candidate is None or prior is None:
            return None

        left_vec = _to_float_vector(candidate)
        right_vec = _to_float_vector(prior)
        if left_vec is not None and right_vec is not None:
            return _cosine_similarity(left_vec, right_vec)
        return _jaccard_similarity(candidate, prior)


class EmbeddingSimilarityStrategy(SimilarityStrategy):
    method = "embedding"

    def score(self, candidate: Any, prior: Any) -> float | None:
        if candidate is None or prior is None:
            return None

        left_vec = _to_float_vector(candidate)
        right_vec = _to_float_vector(prior)
        if left_vec is None or right_vec is None:
            return None
        return _cosine_similarity(left_vec, right_vec)


def info() -> dict:
    return {
        "name": _DEF_NAME,
        "version": "0.4.0",
        "description": "Generates provenance metadata for creative assets.",
    }


def _record_stage(
    *,
    job_id: str,
    stage: str,
    started_at: float,
    result: str,
    fitness_score: float,
) -> None:
    append_stage_metric(
        job_id=job_id,
        stage=stage,
        duration_ms=int((time.perf_counter() - started_at) * 1000),
        result=result,
        fitness_score=fitness_score,
    )


def _emit_uniqueness_audit_stage(payload: dict[str, Any], *, job_id: str) -> None:
    uniqueness_validation_time_ms = payload.get("uniqueness_validation_time_ms")
    novelty_index = payload.get("novelty_index")
    similarity_guardrail_pass = payload.get("similarity_guardrail_pass")

    if uniqueness_validation_time_ms is None and novelty_index is None and similarity_guardrail_pass is None:
        return

    duration_ms = int(uniqueness_validation_time_ms or 0)
    fitness_score = float(novelty_index) if novelty_index is not None else 0.0
    append_stage_metric(
        job_id=job_id,
        stage=_STAGE_UNIQUENESS_AUDIT,
        duration_ms=duration_ms,
        result="success" if similarity_guardrail_pass is not False else "failure:similarity_guardrail_failed",
        fitness_score=fitness_score,
        uniqueness_validation_time_ms=duration_ms,
        novelty_index=novelty_index,
        similarity_guardrail_pass=similarity_guardrail_pass,
    )


def _flatten_tokens(value: Any, *, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        tokens: set[str] = set()
        for key, nested in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            tokens.update(_flatten_tokens(nested, prefix=child_prefix))
        return tokens
    if isinstance(value, list):
        tokens: set[str] = set()
        for index, nested in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            tokens.update(_flatten_tokens(nested, prefix=child_prefix))
        return tokens
    return {f"{prefix}={value}" if prefix else str(value)}


def _jaccard_similarity(left: Any, right: Any) -> float:
    left_tokens = _flatten_tokens(left)
    right_tokens = _flatten_tokens(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union if union else 0.0


def _to_float_vector(value: Any) -> list[float] | None:
    if isinstance(value, list) and value:
        vector: list[float] = []
        for item in value:
            if not isinstance(item, (int, float)):
                return None
            vector.append(float(item))
        return vector
    return None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    max_len = max(len(left), len(right))
    padded_left = left + ([0.0] * (max_len - len(left)))
    padded_right = right + ([0.0] * (max_len - len(right)))

    numerator = sum(a * b for a, b in zip(padded_left, padded_right))
    left_norm = math.sqrt(sum(a * a for a in padded_left))
    right_norm = math.sqrt(sum(b * b for b in padded_right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _load_json_file(path_value: Any) -> Any:
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_candidate_render_metadata(payload: dict) -> Any:
    if "render_metadata" in payload:
        return payload["render_metadata"]
    return _load_json_file(payload.get("render_metadata_path"))


def _load_candidate_audio_fingerprint(payload: dict) -> Any:
    if "audio_fingerprint" in payload:
        return payload["audio_fingerprint"]
    loaded = _load_json_file(payload.get("audio_fingerprint_path"))
    if loaded is not None:
        return loaded
    raw_path = payload.get("audio_fingerprint_path")
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _load_candidate_embedding(payload: dict) -> Any:
    if "embedding" in payload:
        return payload["embedding"]
    return _load_json_file(payload.get("embedding_path"))


def _extract_prior_signature(entry: dict) -> tuple[Any, Any, Any]:
    render_metadata = entry.get("render_metadata")
    audio_fingerprint = entry.get("audio_fingerprint")
    embedding = entry.get("embedding")

    if render_metadata is None and audio_fingerprint is None and embedding is None:
        file_value = entry.get("file")
        if file_value:
            loaded = _load_json_file(file_value)
            if isinstance(loaded, dict):
                render_metadata = loaded.get("render_metadata")
                audio_fingerprint = loaded.get("audio_fingerprint")
                embedding = loaded.get("embedding")

    return render_metadata, audio_fingerprint, embedding


def _read_provenance_entries(log_path: str) -> list[dict]:
    path = Path(log_path)
    if not path.exists():
        return []

    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
    return entries


def _load_similarity_policy(payload: dict) -> SimilarityPolicy:
    policy_path = Path(str(payload.get("similarity_policy_path") or _DEFAULT_POLICY_PATH))
    if not policy_path.exists() or not policy_path.is_file():
        raise ValueError(f"Similarity policy file is missing: {policy_path}")
    try:
        raw_policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Similarity policy file is invalid: {policy_path}") from exc

    thresholds = raw_policy.get("thresholds") or {}
    methods = raw_policy.get("methods") or {}
    raw_method_weights = raw_policy.get("method_weights") or {}
    required_methods = {
        name for name, method_cfg in methods.items() if bool((method_cfg or {}).get("required_for_release_intent"))
    }
    method_weights = {
        name: float(weight) for name, weight in raw_method_weights.items() if isinstance(weight, (int, float))
    }
    strategy_versions = {name: str((cfg or {}).get("version", "unknown")) for name, cfg in methods.items()}
    strategy_model_ids = {name: (cfg or {}).get("model_id") for name, cfg in methods.items()}

    return SimilarityPolicy(
        version=str(raw_policy.get("version") or "unknown"),
        threshold_source=str(policy_path),
        revise_threshold=float(thresholds.get("revise")),
        block_threshold=float(thresholds.get("block")),
        confidence_floor=float(raw_policy.get("confidence_floor", 0.0)),
        decision_policy=str(raw_policy.get("decision_policy", "max_similarity")),
        method_weights=method_weights,
        required_methods_release_intent=required_methods,
        strategy_versions=strategy_versions,
        strategy_model_ids=strategy_model_ids,
    )


def _is_release_intent(payload: dict) -> bool:
    if bool(payload.get("release_intent")):
        return True
    value = str(payload.get("intent_stage") or payload.get("stage") or "").strip().lower()
    return value in {"release", "release_intent", "release-intent", "production_release"}


def _ensure_release_similarity_inputs(
    payload: dict,
    *,
    policy: SimilarityPolicy,
    candidate_inputs: dict[str, Any],
) -> None:
    if not _is_release_intent(payload):
        return

    missing = [
        method for method in sorted(policy.required_methods_release_intent) if candidate_inputs.get(method) is None
    ]
    if missing:
        raise ValueError(
            "Missing required similarity inputs for release-intent stage: " + ", ".join(missing)
        )


def _build_strategies(policy: SimilarityPolicy) -> list[SimilarityStrategy]:
    return [
        MetadataSimilarityStrategy(
            version=policy.strategy_versions.get("metadata", "unknown"),
            model_id=policy.strategy_model_ids.get("metadata"),
        ),
        FingerprintSimilarityStrategy(
            version=policy.strategy_versions.get("fingerprint", "unknown"),
            model_id=policy.strategy_model_ids.get("fingerprint"),
        ),
        EmbeddingSimilarityStrategy(
            version=policy.strategy_versions.get("embedding", "unknown"),
            model_id=policy.strategy_model_ids.get("embedding"),
        ),
    ]


def _evaluate_similarity_decision(
    method_scores_by_entry: list[tuple[list[SimilarityMethodResult], dict[str, Any] | None]],
    policy: SimilarityPolicy,
) -> tuple[str, float, list[SimilarityMethodResult], dict[str, Any] | None, dict[str, Any]]:
    revise_threshold = policy.revise_threshold
    block_threshold = policy.block_threshold
    policy_mode = policy.decision_policy if policy.decision_policy in {
        "max_similarity",
        "required_methods_all_pass",
        "weighted_mean",
    } else "max_similarity"

    if not method_scores_by_entry:
        return (
            "pass",
            0.0,
            [],
            None,
            {
                "policy_mode": policy_mode,
                "contributing_methods": [],
                "required_method_breaches": [],
                "fallback_to_max_similarity": policy_mode != policy.decision_policy,
            },
        )

    best_entry_methods: list[SimilarityMethodResult] = []
    best_entry_ref: dict[str, Any] | None = None
    aggregate_score = 0.0
    contributing_methods: list[dict[str, Any]] = []
    required_method_breaches: list[dict[str, Any]] = []

    if policy_mode == "weighted_mean":
        best_weighted_mean = -1.0
        for methods, entry_ref in method_scores_by_entry:
            weighted_values: list[tuple[SimilarityMethodResult, float]] = []
            total_weight = 0.0
            for result in methods:
                weight = policy.method_weights.get(result.method, 1.0)
                if weight <= 0:
                    continue
                weighted_values.append((result, weight))
                total_weight += weight
            if not weighted_values:
                continue
            weighted_mean = sum(result.score * weight for result, weight in weighted_values) / total_weight
            if weighted_mean > best_weighted_mean:
                best_weighted_mean = weighted_mean
                aggregate_score = weighted_mean
                best_entry_methods = methods
                best_entry_ref = entry_ref
                contributing_methods = [
                    {
                        "method": result.method,
                        "score": round(result.score, 6),
                        "weight": round(weight, 6),
                        "weighted_contribution": round((result.score * weight) / total_weight, 6),
                    }
                    for result, weight in weighted_values
                ]
    else:
        for methods, entry_ref in method_scores_by_entry:
            entry_max = max(result.score for result in methods)
            if entry_max > aggregate_score:
                aggregate_score = entry_max
                best_entry_methods = methods
                best_entry_ref = entry_ref
                contributing_methods = [
                    {
                        "method": result.method,
                        "score": round(result.score, 6),
                    }
                    for result in methods
                    if result.score == entry_max
                ]

    if policy_mode == "required_methods_all_pass":
        highest_required_scores: dict[str, SimilarityMethodResult] = {}
        for methods, _entry_ref in method_scores_by_entry:
            for result in methods:
                if result.method not in policy.required_methods_release_intent:
                    continue
                previous = highest_required_scores.get(result.method)
                if previous is None or result.score > previous.score:
                    highest_required_scores[result.method] = result

        for method_name in sorted(policy.required_methods_release_intent):
            result = highest_required_scores.get(method_name)
            if result is None:
                continue
            if result.score >= revise_threshold:
                required_method_breaches.append(
                    {
                        "method": result.method,
                        "score": round(result.score, 6),
                        "threshold_breached": "block" if result.score >= block_threshold else "revise",
                    }
                )

        if any(item["threshold_breached"] == "block" for item in required_method_breaches):
            decision = "block"
        elif required_method_breaches:
            decision = "revise"
        else:
            decision = "pass"
    else:
        if aggregate_score >= block_threshold:
            decision = "block"
        elif aggregate_score >= revise_threshold:
            decision = "revise"
        else:
            decision = "pass"

    return (
        decision,
        aggregate_score,
        best_entry_methods,
        best_entry_ref,
        {
            "policy_mode": policy_mode,
            "contributing_methods": contributing_methods,
            "required_method_breaches": required_method_breaches,
            "fallback_to_max_similarity": policy_mode != policy.decision_policy,
        },
    )


def run_similarity_audit(payload: dict) -> dict:
    log_path = str(payload.get("provenance_log_path", "registry/provenance_log.jsonl"))
    job_id = str(payload.get("job_id") or "unknown")
    policy = _load_similarity_policy(payload)

    candidate_inputs = {
        "metadata": _load_candidate_render_metadata(payload),
        "fingerprint": _load_candidate_audio_fingerprint(payload),
        "embedding": _load_candidate_embedding(payload),
    }
    _ensure_release_similarity_inputs(payload, policy=policy, candidate_inputs=candidate_inputs)

    if all(value is None for value in candidate_inputs.values()):
        raise ValueError(
            "Similarity audit requires render metadata, audio fingerprint, and/or embedding input"
        )

    prior_entries = _read_provenance_entries(log_path)
    strategies = _build_strategies(policy)

    method_scores_by_entry: list[tuple[list[SimilarityMethodResult], dict[str, Any] | None]] = []

    for entry in prior_entries:
        prior_render_metadata, prior_audio_fingerprint, prior_embedding = _extract_prior_signature(entry)
        prior_inputs = {
            "metadata": prior_render_metadata,
            "fingerprint": prior_audio_fingerprint,
            "embedding": prior_embedding,
        }

        method_scores: list[SimilarityMethodResult] = []
        for strategy in strategies:
            score = strategy.score(candidate_inputs.get(strategy.method), prior_inputs.get(strategy.method))
            if score is None:
                continue
            method_scores.append(
                SimilarityMethodResult(
                    method=strategy.method,
                    version=strategy.version,
                    model_id=strategy.model_id,
                    score=score,
                    threshold=policy.block_threshold,
                    required_for_release_intent=strategy.method in policy.required_methods_release_intent,
                )
            )

        if not method_scores:
            continue

        method_scores_by_entry.append(
            (
                method_scores,
                {
                    "job_id": entry.get("job_id"),
                    "track_id": entry.get("track_id"),
                    "file": entry.get("file"),
                    "sha256": entry.get("sha256"),
                },
            )
        )

    decision, aggregate_similarity, method_results, most_similar_ref, decision_rationale = _evaluate_similarity_decision(
        method_scores_by_entry,
        policy,
    )

    confidence = max(0.0, min(1.0, aggregate_similarity))

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = _SIMILARITY_AUDIT_DIR / f"{job_id}_{timestamp}.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    audit_payload = {
        "job_id": job_id,
        "decision": decision,
        "max_similarity": round(aggregate_similarity, 6),
        "confidence": round(confidence, 6),
        "confidence_floor": policy.confidence_floor,
        "thresholds": {
            "revise": policy.revise_threshold,
            "block": policy.block_threshold,
        },
        "threshold_source": policy.threshold_source,
        "policy": {
            "version": policy.version,
            "decision_policy": policy.decision_policy,
        },
        "decision_rationale": decision_rationale,
        "method_results": [
            {
                "method": item.method,
                "method_version": item.version,
                "model_id": item.model_id,
                "score": round(item.score, 6),
                "required_for_release_intent": item.required_for_release_intent,
            }
            for item in method_results
        ],
        "most_similar_ref": most_similar_ref,
        "candidate": {
            "render_metadata": candidate_inputs["metadata"],
            "audio_fingerprint": candidate_inputs["fingerprint"],
            "embedding": candidate_inputs["embedding"],
        },
        "provenance_log_path": log_path,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    artifact_path.write_text(json.dumps(audit_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    return {
        "decision": decision,
        "max_similarity": aggregate_similarity,
        "confidence": confidence,
        "policy_version": policy.version,
        "audit_artifact_path": str(artifact_path),
        "audit_artifact": audit_payload,
    }


def run(input=None) -> dict:
    started_at = time.perf_counter()
    payload = input or {}
    output_files = payload.get("output_files")
    file_path = payload.get("file_path")

    if output_files is None:
        output_files = [file_path] if file_path else []

    job_id = str(payload.get("job_id") or "unknown")

    if not output_files:
        _record_stage(
            job_id=job_id,
            stage=_STAGE_RUN,
            started_at=started_at,
            result="failure:missing_output_files",
            fitness_score=0.0,
        )
        return {
            "ok": False,
            "error": "At least one output artifact is required",
            "stage_result_code": "failure:missing_output_files",
        }

    track_id = payload.get("track_id")

    if not payload.get("job_id") or not track_id:
        _record_stage(
            job_id=job_id,
            stage=_STAGE_RUN,
            started_at=started_at,
            result="failure:missing_required_ids",
            fitness_score=0.0,
        )
        return {
            "ok": False,
            "error": "job_id and track_id are required",
            "stage_result_code": "failure:missing_required_ids",
        }

    deny_reason_code = payload.get("deny_reason_code")
    if payload.get("deny_level3_action") or deny_reason_code:
        reason_code = str(deny_reason_code or "LEVEL3_POLICY_DENIED")
        context = {
            "policy_version": payload.get("policy_version", "1.0.0"),
            "job_id": payload["job_id"],
            "track_id": track_id,
            "provenance_id": payload.get("provenance_id") or payload["job_id"],
            "agent_log_path": payload.get("agent_log_path", "AGENT_LOG.md"),
        }
        try:
            hard_abort("level3.production_render_registry_write", reason_code, context)
        except HardAbortError as exc:
            _record_stage(
                job_id=payload["job_id"],
                stage=_STAGE_RUN,
                started_at=started_at,
                result=exc.failure["stage_result_code"],
                fitness_score=0.0,
            )
            return exc.failure

    _emit_uniqueness_audit_stage(payload, job_id=payload["job_id"])

    try:
        provenance_refs = list(payload.get("provenance_refs") or [])
        policy = _load_similarity_policy(payload)
        expected_version = payload.get("expected_similarity_policy_version")
        if expected_version and str(expected_version) != policy.version:
            raise ValueError(
                "Similarity policy version drift detected: "
                f"expected={expected_version} actual={policy.version}"
            )

        candidate_inputs = {
            "metadata": _load_candidate_render_metadata(payload),
            "fingerprint": _load_candidate_audio_fingerprint(payload),
            "embedding": _load_candidate_embedding(payload),
        }
        _ensure_release_similarity_inputs(payload, policy=policy, candidate_inputs=candidate_inputs)
        has_similarity_inputs = any(value is not None for value in candidate_inputs.values())
        if has_similarity_inputs:
            audit_result = run_similarity_audit(payload)
            provenance_refs.append(audit_result["audit_artifact_path"])
            provenance_targets = [*output_files, audit_result["audit_artifact_path"]]
        else:
            audit_result = {
                "decision": "pass",
                "max_similarity": 0.0,
                "confidence": 0.0,
                "policy_version": policy.version,
                "audit_artifact_path": None,
            }
            provenance_targets = list(output_files)

        entries = append_provenance_entries(
            provenance_targets,
            job_id=payload["job_id"],
            track_id=track_id,
            agent=payload.get("agent", _DEF_NAME),
            parent_artifact_hash=payload.get("parent_artifact_hash"),
            retry_attempt=int(payload.get("retry_attempt", payload.get("attempt", 0)) or 0),
            log_path=payload.get("provenance_log_path", "registry/provenance_log.jsonl"),
        )

        stage_result_code = "success"
        ok = True
        error = None
        if audit_result["decision"] == "revise":
            stage_result_code = "failure:similarity_revise_required"
            ok = False
            error = (
                "Similarity audit requires revision before continuation; "
                f"max_similarity={audit_result['max_similarity']:.4f}"
            )
        elif audit_result["decision"] == "block":
            stage_result_code = "failure:similarity_blocked"
            ok = False
            error = (
                "Similarity audit blocked pipeline completion; "
                f"max_similarity={audit_result['max_similarity']:.4f}"
            )

        result = {
            "ok": ok,
            "entries": entries,
            "similarity_audit": {
                "decision": audit_result["decision"],
                "max_similarity": audit_result["max_similarity"],
                "confidence": audit_result.get("confidence", 0.0),
                "policy_version": audit_result.get("policy_version", policy.version),
            },
            "provenance_refs": provenance_refs,
            "stage_result_code": stage_result_code,
        }
        if error:
            result["error"] = error

        _record_stage(
            job_id=payload["job_id"],
            stage=_STAGE_RUN,
            started_at=started_at,
            result=stage_result_code,
            fitness_score=score(result),
        )
        return result
    except Exception as exc:
        stage_result_code = "failure:similarity_audit_exception"
        _record_stage(
            job_id=payload["job_id"],
            stage=_STAGE_RUN,
            started_at=started_at,
            result=stage_result_code,
            fitness_score=0.0,
        )
        return {
            "ok": False,
            "error": f"Similarity audit/provenance append failed; blocking pipeline completion: {exc}",
            "output_files": output_files,
            "job_id": payload["job_id"],
            "track_id": track_id,
            "stage_result_code": stage_result_code,
        }


def mutate(src: str) -> str:
    return src


def score(output: dict) -> float:
    if output.get("ok") and output.get("entries"):
        return 1.0
    return 0.0
