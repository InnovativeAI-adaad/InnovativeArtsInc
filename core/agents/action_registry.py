"""Action registry and preflight validators for workflow action handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable

WF005_ANCHOR = "### 🎵 WF-005 · Music Catalog Update (InnovativeArts)"
AUTONOMY_MATRIX_ANCHOR = "## 1. Canonical Autonomy Matrix (Normative)"

ActionHandler = Callable[..., dict[str, object]]


class ActionRegistryError(RuntimeError):
    """Raised when action registry validation fails closed."""


@dataclass(frozen=True)
class ActionRegistryValidationReport:
    workflow_actions: set[str]
    documented_actions: set[str]
    registered_actions: set[str]
    undocumented_actions: tuple[str, ...]
    unimplemented_actions: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.undocumented_actions and not self.unimplemented_actions

    def diagnostics(self) -> str:
        lines = [
            "Action registry validation failed (fail-closed).",
            "- Source anchors:",
            f"  - WORKFLOWS.md: {WF005_ANCHOR}",
            f"  - AUTONOMY.md: {AUTONOMY_MATRIX_ANCHOR}",
        ]
        if self.undocumented_actions:
            lines.append(f"- Undocumented workflow actions: {', '.join(self.undocumented_actions)}")
        if self.unimplemented_actions:
            lines.append(f"- Unimplemented workflow actions: {', '.join(self.unimplemented_actions)}")
        return "\n".join(lines)


class ActionRegistry:
    """Maps canonical workflow action names to executable handlers."""

    def __init__(self, handlers: dict[str, ActionHandler], aliases: dict[str, str] | None = None) -> None:
        self._handlers = dict(handlers)
        self._aliases = dict(aliases or {})

    @property
    def handlers(self) -> dict[str, ActionHandler]:
        return dict(self._handlers)

    @property
    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    def resolve(self, action_name: str) -> ActionHandler:
        canonical = self._aliases.get(action_name, action_name)
        try:
            return self._handlers[canonical]
        except KeyError as exc:
            raise ActionRegistryError(f"No registered handler for action '{action_name}' (resolved: '{canonical}').") from exc

    def registered_action_names(self) -> set[str]:
        return set(self._handlers)

    def validate(self, workflow_actions: set[str], documented_actions: set[str]) -> ActionRegistryValidationReport:
        undocumented = tuple(sorted(action for action in workflow_actions if action not in documented_actions))
        unimplemented = tuple(sorted(action for action in workflow_actions if action not in self._handlers and action not in self._aliases))
        report = ActionRegistryValidationReport(
            workflow_actions=workflow_actions,
            documented_actions=documented_actions,
            registered_actions=self.registered_action_names(),
            undocumented_actions=undocumented,
            unimplemented_actions=unimplemented,
        )
        if not report.ok:
            raise ActionRegistryError(report.diagnostics())
        return report


def _stub_handler(action_name: str) -> ActionHandler:
    def _handler(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"ok": True, "action": action_name, "handler": f"stub:{action_name}"}

    return _handler


def parse_workflow_action_names(workflows_path: Path) -> set[str]:
    text = workflows_path.read_text(encoding="utf-8")
    if WF005_ANCHOR not in text:
        raise ActionRegistryError(f"Missing expected anchor in {workflows_path}: {WF005_ANCHOR}")

    actions: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"\s*\d+\.\s+([a-z0-9_]+)", line)
        if match:
            actions.add(match.group(1))
    return actions


def parse_canonical_action_names(autonomy_path: Path) -> set[str]:
    text = autonomy_path.read_text(encoding="utf-8")
    if AUTONOMY_MATRIX_ANCHOR not in text:
        raise ActionRegistryError(f"Missing expected anchor in {autonomy_path}: {AUTONOMY_MATRIX_ANCHOR}")

    actions: set[str] = set()
    in_matrix = False
    for line in text.splitlines():
        if line.strip() == AUTONOMY_MATRIX_ANCHOR:
            in_matrix = True
            continue
        if in_matrix and line.startswith("## "):
            break
        if in_matrix:
            match = re.match(r"\|\s*`([a-z0-9_]+)`\s*\|", line)
            if match:
                actions.add(match.group(1))
    return actions


def build_default_action_registry() -> ActionRegistry:
    # Canonical handlers (including WF-005 steps).
    names = {
        "read_repo",
        "review_code",
        "run_tests",
        "lint_code",
        "comment_on_pr",
        "merge_pr_dev_staging",
        "write_agent_log",
        "read_issue",
        "classify_issue",
        "assign_labels",
        "comment_on_issue",
        "close_issue",
        "explain_code",
        "generate_readme",
        "commit_files",
        "open_pr_draft",
        "draft_release",
        "send_email_owner",
        "verify_uniqueness_strategy",
        "generate_music",
        "generate_metadata",
        "catalog_music",
        "tag_audio",
        "create_issue",
        "read_agent_log",
        "list_branches",
        "search_github",
        "read_brief",
        "web_search_trends",
        "draft_press_release",
        "generate_social_drafts",
        "deploy_production",
    }
    handlers = {name: _stub_handler(name) for name in names}

    # Intentional compatibility aliases only.
    aliases = {
        "catalog_tracks": "catalog_music",
        "apply_audio_tags": "tag_audio",
    }
    return ActionRegistry(handlers=handlers, aliases=aliases)


def validate_action_registry_preflight(
    workflows_path: Path = Path("WORKFLOWS.md"),
    autonomy_path: Path = Path("AUTONOMY.md"),
    registry: ActionRegistry | None = None,
) -> ActionRegistryValidationReport:
    resolved_registry = registry or build_default_action_registry()
    workflow_actions = parse_workflow_action_names(workflows_path)
    documented_actions = parse_canonical_action_names(autonomy_path)
    return resolved_registry.validate(workflow_actions, documented_actions)
