#!/usr/bin/env python3
"""CI preflight check: detect drift between workflow docs and action registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.agents.action_registry import ActionRegistryError, validate_action_registry_preflight


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows", default="WORKFLOWS.md", help="Path to WORKFLOWS.md")
    parser.add_argument("--autonomy", default="AUTONOMY.md", help="Path to AUTONOMY.md")
    args = parser.parse_args()

    try:
        report = validate_action_registry_preflight(
            workflows_path=Path(args.workflows),
            autonomy_path=Path(args.autonomy),
        )
    except ActionRegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        "Action registry preflight passed: "
        f"{len(report.workflow_actions)} workflow actions, "
        f"{len(report.documented_actions)} documented actions, "
        f"{len(report.registered_actions)} registered handlers."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
