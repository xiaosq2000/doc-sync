from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from doc_sync.integrations.install import (
    InstallError,
    _claude_command,
    _opencode_invocation,
    _source_launcher,
    install_hooks,
    uninstall_hooks,
)
from tests.support import initialize_repository


class InstallerTest(unittest.TestCase):
    def test_source_launcher_is_invoked_with_python3(self) -> None:
        # Agent hooks run in a non-interactive shell, where `python` is often
        # absent or only a login-shell alias; `python3` is the POSIX name.
        root = _source_launcher().parents[1]

        assert _claude_command(root).startswith('python3 "$CLAUDE_PROJECT_DIR/')
        assert "python3 ${worktree}/bin/doc-sync" in _opencode_invocation(root)

    def test_installs_updates_idempotently_and_uninstalls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)

            install_hooks(root, ("claude", "opencode"), dry_run=False, force=False)
            first_settings = (root / ".claude/settings.json").read_text()
            first_plugin = (root / ".opencode/plugins/doc-sync.ts").read_text()
            install_hooks(root, ("claude", "opencode"), dry_run=False, force=False)

            assert (root / "doc-sync.toml").exists()
            assert (root / ".claude/settings.json").read_text() == first_settings
            assert (root / ".opencode/plugins/doc-sync.ts").read_text() == first_plugin
            assert "doc-sync hook claude" in first_settings
            assert "managed-id: doc-sync.opencode.v1" in first_plugin

            uninstall_hooks(root, ("claude", "opencode"), dry_run=False)

            settings = json.loads((root / ".claude/settings.json").read_text())
            assert "hooks" not in settings
            assert not (root / ".opencode/plugins/doc-sync.ts").exists()
            assert (root / "doc-sync.toml").exists()

    def test_conflict_is_detected_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)
            plugin = root / ".opencode/plugins/doc-sync.ts"
            plugin.parent.mkdir(parents=True)
            plugin.write_text("unrelated", encoding="utf-8")

            with self.assertRaises(InstallError):
                install_hooks(root, ("claude", "opencode"), dry_run=False, force=False)

            assert not (root / ".claude/settings.json").exists()
            assert not (root / "doc-sync.toml").exists()

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
