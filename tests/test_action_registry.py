from __future__ import annotations

from pathlib import Path

import pytest

from core.agents.action_registry import (
    ActionRegistry,
    ActionRegistryError,
    build_default_action_registry,
    parse_workflow_action_names,
    validate_action_registry_preflight,
)


WF005_ACTIONS = {
    "read_repo",
    "generate_metadata",
    "verify_uniqueness_strategy",
    "generate_music",
    "catalog_music",
    "tag_audio",
    "create_issue",
    "write_agent_log",
}


def test_registry_maps_each_wf005_action_to_callable() -> None:
    registry = build_default_action_registry()

    for action in WF005_ACTIONS:
        handler = registry.resolve(action)
        result = handler()
        assert callable(handler)
        assert result["ok"] is True
        assert result["action"] == action


def test_intentional_compatibility_aliases_only() -> None:
    registry = build_default_action_registry()

    aliased = registry.resolve("catalog_tracks")
    canonical = registry.resolve("catalog_music")

    assert aliased is canonical
    with pytest.raises(ActionRegistryError, match="No registered handler"):
        registry.resolve("unknown_legacy_alias")


def test_preflight_fails_closed_with_explicit_diagnostics(tmp_path: Path) -> None:
    workflows = tmp_path / "WORKFLOWS.md"
    autonomy = tmp_path / "AUTONOMY.md"

    workflows.write_text(
        """
### 🎵 WF-005 · Music Catalog Update (InnovativeArts)
```yaml
steps:
  1. read_repo
  2. undocumented_action
  3. unimplemented_action
```
""",
        encoding="utf-8",
    )
    autonomy.write_text(
        """
## 1. Canonical Autonomy Matrix (Normative)
| Action Name | Tier | Approval Model | Notes |
|---|---:|---|---|
| `read_repo` | 🟢 1 | Autonomous | Read branches/files/history. |
| `unimplemented_action` | 🟡 2 | Log + notify owner | Exists in docs only. |

## 2. Runtime Policy Block (Machine-Readable)
""",
        encoding="utf-8",
    )

    registry = ActionRegistry(handlers={"read_repo": lambda: {"ok": True}})

    with pytest.raises(ActionRegistryError) as exc_info:
        validate_action_registry_preflight(workflows, autonomy, registry=registry)

    message = str(exc_info.value)
    assert "Undocumented workflow actions: undocumented_action" in message
    assert "Unimplemented workflow actions: undocumented_action, unimplemented_action" in message


def test_repo_preflight_passes_with_current_docs() -> None:
    actions = parse_workflow_action_names(Path("WORKFLOWS.md"))
    assert {"verify_uniqueness_strategy", "generate_music", "deploy_production"}.issubset(actions)

    report = validate_action_registry_preflight()
    assert report.ok is True
