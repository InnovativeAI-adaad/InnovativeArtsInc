"""Gatekeeper primitives for policy-level action controls."""

from core.gatekeeper.abort import HardAbortError, hard_abort

__all__ = ["HardAbortError", "hard_abort"]
