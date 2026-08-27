from __future__ import annotations

import json
import stat
from typing import TYPE_CHECKING

import pytest

from doc_sync.integrations.install import (
    InstallError,
    install_hooks,
    uninstall_hooks,
)

if TYPE_CHECKING:
    from pathlib import Path

TARGETS = ("claude", "codex", "opencode")


def _stop_commands(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return [
        handler["command"]
        for group in document["hooks"]["Stop"]
        for handler in group["hooks"]
    ]


def test_installs_updates_idempotently_and_uninstalls(empty_repository: Path) -> None:
    root = empty_repository
    install_hooks(root, TARGETS, dry_run=False, force=False)
    first_settings = (root / ".claude/settings.json").read_text(encoding="utf-8")
    first_hooks = (root / ".codex/hooks.json").read_text(encoding="utf-8")
    first_plugin = (root / ".opencode/plugins/doc-sync.ts").read_text(encoding="utf-8")

    install_hooks(root, TARGETS, dry_run=False, force=False)

    assert (root / "doc-sync.toml").exists()
    assert (root / ".claude/settings.json").read_text(
        encoding="utf-8"
    ) == first_settings
    assert (root / ".codex/hooks.json").read_text(encoding="utf-8") == first_hooks
    assert (root / ".opencode/plugins/doc-sync.ts").read_text(
        encoding="utf-8"
    ) == first_plugin
    assert "doc-sync hook claude" in first_settings
    assert "doc-sync hook codex" in first_hooks
    assert "managed-id: doc-sync.opencode.v1" in first_plugin

    uninstall_hooks(root, TARGETS, dry_run=False)

    settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
    assert "hooks" not in settings
    assert json.loads((root / ".codex/hooks.json").read_text(encoding="utf-8")) == {}
    assert not (root / ".opencode/plugins/doc-sync.ts").exists()
    assert (root / "doc-sync.toml").exists()


def test_replaces_wiring_written_by_a_source_checkout(empty_repository: Path) -> None:
    """A hook installed before the source launcher was dropped upgrades in place."""
    settings = empty_repository / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'python3 "$CLAUDE_PROJECT_DIR/bin/doc-sync" hook claude',
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    install_hooks(empty_repository, ("claude",), dry_run=False, force=False)

    assert _stop_commands(settings) == [
        'doc-sync hook claude --root "$CLAUDE_PROJECT_DIR"'
    ]


def test_codex_install_keeps_hooks_doc_sync_does_not_manage(
    empty_repository: Path,
) -> None:
    hooks_path = empty_repository / ".codex/hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "description": "project hooks",
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "shell",
                            "hooks": [{"type": "command", "command": "audit"}],
                        }
                    ],
                    "Stop": [{"hooks": [{"type": "command", "command": "notify"}]}],
                },
            }
        ),
        encoding="utf-8",
    )

    install_hooks(empty_repository, ("codex",), dry_run=False, force=False)
    installed = _stop_commands(hooks_path)
    assert "notify" in installed
    assert any("hook codex" in command for command in installed)

    uninstall_hooks(empty_repository, ("codex",), dry_run=False)
    remaining = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert remaining["description"] == "project hooks"
    assert remaining["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "audit"
    assert _stop_commands(hooks_path) == ["notify"]


def test_conflict_is_detected_before_any_write(empty_repository: Path) -> None:
    plugin = empty_repository / ".opencode/plugins/doc-sync.ts"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("unrelated", encoding="utf-8")

    with pytest.raises(InstallError):
        install_hooks(empty_repository, TARGETS, dry_run=False, force=False)

    assert not (empty_repository / ".claude/settings.json").exists()
    assert not (empty_repository / ".codex/hooks.json").exists()
    assert not (empty_repository / "doc-sync.toml").exists()


@pytest.mark.posix_only
def test_preserves_existing_settings_permissions(empty_repository: Path) -> None:
    settings = empty_repository / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}\n", encoding="utf-8")
    settings.chmod(0o640)

    install_hooks(empty_repository, ("claude",), dry_run=False, force=False)

    assert stat.S_IMODE(settings.stat().st_mode) == 0o640
