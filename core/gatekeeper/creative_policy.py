"""Policy validation helpers for creative control-plane constraints."""

from __future__ import annotations

from typing import Any


class ConstraintPolicyError(ValueError):
    """Raised when creative constraints fail policy checks."""


def validate_creative_constraints(
    constraints: dict[str, Any],
    *,
    runtime_policy: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(constraints, dict):
        raise ConstraintPolicyError("constraints must be a JSON object")

    required_fields = {
        "genre_blend",
        "mood_arc",
        "lyrical_boundaries",
        "tempo_window",
        "key_window",
    }
    missing = sorted(field for field in required_fields if field not in constraints)
    if missing:
        raise ConstraintPolicyError(f"missing required constraint fields: {', '.join(missing)}")

    genre_blend = constraints["genre_blend"]
    if not isinstance(genre_blend, list) or not genre_blend:
        raise ConstraintPolicyError("genre_blend must be a non-empty list")
    normalized_genres = [str(genre).strip().lower() for genre in genre_blend if str(genre).strip()]
    if len(normalized_genres) != len(genre_blend):
        raise ConstraintPolicyError("genre_blend contains empty values")
    if len(normalized_genres) > int(runtime_policy["genre_blend"]["max_components"]):
        raise ConstraintPolicyError("genre_blend exceeds max_components policy")

    mood_arc = constraints["mood_arc"]
    if not isinstance(mood_arc, list) or not mood_arc:
        raise ConstraintPolicyError("mood_arc must be a non-empty list")
    allowed_moods = set(runtime_policy["mood_arc"]["allowed"])
    normalized_mood_arc = [str(mood).strip().lower() for mood in mood_arc]
    if any(mood not in allowed_moods for mood in normalized_mood_arc):
        raise ConstraintPolicyError("mood_arc contains values outside policy allowlist")

    lyrical = constraints["lyrical_boundaries"]
    if not isinstance(lyrical, dict):
        raise ConstraintPolicyError("lyrical_boundaries must be an object")
    max_explicitness = float(lyrical.get("max_explicitness", -1))
    if not 0 <= max_explicitness <= float(runtime_policy["lyrical_boundaries"]["max_explicitness"]):
        raise ConstraintPolicyError("max_explicitness exceeds policy")
    blocked_terms = [str(term).strip().lower() for term in lyrical.get("blocked_terms", [])]
    if not isinstance(lyrical.get("blocked_terms", []), list):
        raise ConstraintPolicyError("blocked_terms must be a list")

    tempo_window = constraints["tempo_window"]
    if not isinstance(tempo_window, dict):
        raise ConstraintPolicyError("tempo_window must be an object")
    min_bpm = int(tempo_window.get("min_bpm", -1))
    max_bpm = int(tempo_window.get("max_bpm", -1))
    policy_tempo = runtime_policy["tempo_window"]
    if min_bpm > max_bpm:
        raise ConstraintPolicyError("tempo_window min_bpm must be <= max_bpm")
    if min_bpm < int(policy_tempo["min_allowed"]) or max_bpm > int(policy_tempo["max_allowed"]):
        raise ConstraintPolicyError("tempo_window values are outside policy range")

    key_window = constraints["key_window"]
    if not isinstance(key_window, dict):
        raise ConstraintPolicyError("key_window must be an object")
    allowed_keys = set(runtime_policy["key_window"]["allowed_keys"])
    requested_keys = [str(key).strip() for key in key_window.get("keys", [])]
    if not requested_keys:
        raise ConstraintPolicyError("key_window.keys must be non-empty")
    if any(key not in allowed_keys for key in requested_keys):
        raise ConstraintPolicyError("key_window includes unsupported key")

    return {
        "genre_blend": normalized_genres,
        "mood_arc": normalized_mood_arc,
        "lyrical_boundaries": {
            "max_explicitness": max_explicitness,
            "blocked_terms": blocked_terms,
            "theme_allowlist": [str(v).strip().lower() for v in lyrical.get("theme_allowlist", [])],
        },
        "tempo_window": {"min_bpm": min_bpm, "max_bpm": max_bpm},
        "key_window": {
            "keys": requested_keys,
            "mode": str(key_window.get("mode", "major")).strip().lower(),
        },
    }


def enforce_policy_safe_constraints(strategy_payload: dict[str, Any], *, runtime_policy: dict[str, Any]) -> None:
    banned_genre_combos = {
        tuple(sorted(combo))
        for combo in runtime_policy.get("genre_blend", {}).get("banned_combinations", [])
        if isinstance(combo, list)
    }
    genre_combo = tuple(sorted(strategy_payload["constraints"]["genre_blend"]))
    if genre_combo in banned_genre_combos:
        raise ConstraintPolicyError("genre blend is policy-blocked")

    blocked_terms = set(runtime_policy.get("lyrical_boundaries", {}).get("blocked_terms", []))
    requested_terms = set(strategy_payload["constraints"]["lyrical_boundaries"].get("blocked_terms", []))
    if not blocked_terms.issubset(requested_terms):
        raise ConstraintPolicyError("lyrical boundaries must include all mandatory blocked terms")


def map_override_to_tier(override_level: str, *, runtime_policy: dict[str, Any]) -> dict[str, Any]:
    mapping = runtime_policy.get("override_tiers", {})
    resolved = mapping.get(override_level)
    if not resolved:
        raise ConstraintPolicyError(f"unsupported override level: {override_level}")
    return {
        "override_level": override_level,
        "tier": int(resolved["tier"]),
        "approval_model": resolved["approval_model"],
        "autonomy_actions": list(resolved.get("autonomy_actions", [])),
    }
