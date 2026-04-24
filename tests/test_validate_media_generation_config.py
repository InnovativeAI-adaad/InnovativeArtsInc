from __future__ import annotations

import pytest

from pipelines.validate_media_outputs import _validate_generation_config


def test_validate_generation_config_accepts_canonical_shape_with_planning_fields() -> None:
    _validate_generation_config(
        {
            "model_version": "gen-2026.04",
            "prompt_template_version": "p2",
            "random_seed": 123,
            "creativity_profile": "balanced",
            "style_constraints": ["clean", "cinematic"],
            "style_dna_fingerprint": "v2:abcd",
            "style_dna_fingerprint_version": "v2",
            "planning_strategy_id": "strategy-alpha",
        }
    )


def test_validate_generation_config_rejects_missing_planning_fields_for_canonical() -> None:
    with pytest.raises(ValueError, match="canonical or legacy shape"):
        _validate_generation_config(
            {
                "model_version": "gen-2026.04",
                "prompt_template_version": "p2",
                "random_seed": 123,
                "creativity_profile": "balanced",
                "style_constraints": ["clean", "cinematic"],
                "style_dna_fingerprint": "v2:abcd",
            }
        )
