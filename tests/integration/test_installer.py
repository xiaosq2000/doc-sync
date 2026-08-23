from __future__ import annotations

import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from doc_sync.integrations.install import (
    InstallError,
    _claude_command,
    _codex_command,
    _opencode_invocation,
    _source_launcher,
    install_hooks,
    uninstall_hooks,
)
from tests.support import initialize_repository


def _stop_commands(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return [
        handler["command"]
        for group in document["hooks"]["Stop"]
        for handler in group["hooks"]
    ]


class InstallerTest(unittest.TestCase):
    def test_source_launcher_is_invoked_with_python3(self) -> None:
        # Agent hooks run in a non-interactive shell, where `python` is often
        # absent or only a login-shell alias; `python3` is the POSIX name.
        root = _source_launcher().parents[1]

        assert _claude_command(root).startswith('python3 "$CLAUDE_PROJECT_DIR/')
        assert "python3 ${worktree}/bin/doc-sync" in _opencode_invocation(root)
        # Codex has no project-directory variable to expand, so the launcher is
        # located from the worktree Git reports.
        assert _codex_command(root).startswith(
            'python3 "$(git rev-parse --show-toplevel)/'
        )

    def test_installs_updates_idempotently_and_uninstalls(self) -> None:
        targets = ("claude", "codex", "opencode")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)

            install_hooks(root, targets, dry_run=False, force=False)
            first_settings = (root / ".claude/settings.json").read_text()
            first_hooks = (root / ".codex/hooks.json").read_text()
            first_plugin = (root / ".opencode/plugins/doc-sync.ts").read_text()
            install_hooks(root, targets, dry_run=False, force=False)

            assert (root / "doc-sync.toml").exists()
            assert (root / ".claude/settings.json").read_text() == first_settings
            assert (root / ".codex/hooks.json").read_text() == first_hooks
            assert (root / ".opencode/plugins/doc-sync.ts").read_text() == first_plugin
            assert "doc-sync hook claude" in first_settings
            assert "doc-sync hook codex" in first_hooks
            assert "managed-id: doc-sync.opencode.v1" in first_plugin

            uninstall_hooks(root, targets, dry_run=False)

            settings = json.loads((root / ".claude/settings.json").read_text())
            assert "hooks" not in settings
            assert json.loads((root / ".codex/hooks.json").read_text()) == {}
            assert not (root / ".opencode/plugins/doc-sync.ts").exists()
            assert (root / "doc-sync.toml").exists()

    def test_codex_install_keeps_hooks_doc_sync_does_not_manage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)
            hooks_path = root / ".codex/hooks.json"
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
                            "Stop": [
                                {"hooks": [{"type": "command", "command": "notify"}]}
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            install_hooks(root, ("codex",), dry_run=False, force=False)
            installed = _stop_commands(hooks_path)
            assert "notify" in installed
            assert any("hook codex" in command for command in installed)

            uninstall_hooks(root, ("codex",), dry_run=False)
            remaining = json.loads(hooks_path.read_text())
            assert remaining["description"] == "project hooks"
            assert remaining["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "audit"
            assert _stop_commands(hooks_path) == ["notify"]

    def test_conflict_is_detected_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)
            plugin = root / ".opencode/plugins/doc-sync.ts"
            plugin.parent.mkdir(parents=True)
            plugin.write_text("unrelated", encoding="utf-8")

            with self.assertRaises(InstallError):
                install_hooks(
                    root, ("claude", "codex", "opencode"), dry_run=False, force=False
                )

            assert not (root / ".claude/settings.json").exists()
            assert not (root / ".codex/hooks.json").exists()
            assert not (root / "doc-sync.toml").exists()

    @unittest.skipIf(sys.platform == "win32", "Windows lacks POSIX permission bits")
    def test_preserves_existing_settings_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)
            settings = root / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text("{}\n", encoding="utf-8")
            settings.chmod(0o640)

            install_hooks(root, ("claude",), dry_run=False, force=False)

            assert stat.S_IMODE(settings.stat().st_mode) == 0o640
