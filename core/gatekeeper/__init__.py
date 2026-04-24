"""Gatekeeper validation primitives."""

from .ratification import RatificationValidationError, validate_ratification

__all__ = ["RatificationValidationError", "validate_ratification"]
