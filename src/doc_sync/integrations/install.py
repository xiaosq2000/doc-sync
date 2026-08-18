"""Conservative installation of agent integrations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from doc_sync.config import CONFIG_FILENAME
from doc_sync.errors import DocSyncError
from doc_sync.fsutil import atomic_write

if TYPE_CHECKING:
    from collections.abc import Sequence

CLAUDE_SETTINGS = Path(".claude/settings.json")
OPENCODE_PLUGIN = Path(".opencode/plugins/doc-sync.ts")
OPENCODE_MARKER = "managed-id: doc-sync.opencode.v1"
# Wiring written by doc-sync 0.0.x, recognized only so upgrades can replace it.
_LEGACY_HOOK_SCRIPT = "tools/doc-sync/hook.sh"
HOOK_TIMEOUT = 30
HOOK_STATUS_MESSAGE = "Checking documentation impact..."
# Agent hooks run in a non-interactive shell, where `python` is frequently
# absent or only a login-shell alias. `python3` is the name POSIX installs.
SOURCE_INTERPRETER = "python3"
_SAFE_RELATIVE_LAUNCHER = re.compile(r"^[A-Za-z0-9_./-]+$")


class InstallError(DocSyncError, RuntimeError):
    """Raised when an integration cannot be changed safely."""


@dataclass(frozen=True)
class PlannedWrite:
    """One file update prepared before installation mutates the repository."""

    path: Path
    content: str


def _resource_text(name: str) -> str:
    return files("doc_sync.resources").joinpath(name).read_text(encoding="utf-8")


def _source_launcher() -> Path:
    return Path(__file__).resolve().parents[3] / "bin" / "doc-sync"


def _relative_source_launcher(root: Path) -> str | None:
    launcher = _source_launcher()
    try:
        relative = launcher.relative_to(root).as_posix()
    except ValueError:
        return None
    return relative if _SAFE_RELATIVE_LAUNCHER.fullmatch(relative) else None


def _claude_command(root: Path) -> str:
    relative = _relative_source_launcher(root)
    if relative is None:
        return 'doc-sync hook claude --root "$CLAUDE_PROJECT_DIR"'
    return (
        f'{SOURCE_INTERPRETER} "$CLAUDE_PROJECT_DIR/{relative}" hook claude '
        '--root "$CLAUDE_PROJECT_DIR"'
    )


def _opencode_invocation(root: Path) -> str:
    relative = _relative_source_launcher(root)
    if relative is None:
        invocation = (
            "        await shell`doc-sync hook opencode --root ${worktree} "
            "--session-id ${sessionID}`"
        )
    else:
        invocation = (
            f"        await shell`{SOURCE_INTERPRETER} ${{worktree}}/{relative} "
            "hook opencode --root ${worktree} --session-id ${sessionID}`"
        )
    return (
        f"      const result =\n{invocation}\n          .quiet()\n          .nothrow();"
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise InstallError(f"{path} must contain a JSON object")
    return cast("dict[str, Any]", value)


def _managed_claude_command(value: object) -> bool:
    """Recognize any Claude hook command doc-sync has written, at any layout."""
    if not isinstance(value, str):
        return False
    if "hook claude" in value and "doc-sync" in value:
        return True
    return _LEGACY_HOOK_SCRIPT in value


def _prepare_claude_install(root: Path) -> PlannedWrite | None:
    path = root / CLAUDE_SETTINGS
    settings = _load_json_object(path)
    hooks_value = settings.setdefault("hooks", {})
    if not isinstance(hooks_value, dict):
        raise InstallError(f"{path}: `hooks` must be an object")
    hooks = cast("dict[str, Any]", hooks_value)
    stop_value = hooks.setdefault("Stop", [])
    if not isinstance(stop_value, list):
        raise InstallError(f"{path}: `hooks.Stop` must be an array")

    handler_payload = {
        "type": "command",
        "command": _claude_command(root),
        "timeout": HOOK_TIMEOUT,
        "statusMessage": HOOK_STATUS_MESSAGE,
    }
    found = False
    for group in stop_value:
        if not isinstance(group, dict):
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            continue
        for handler in handlers:
            if isinstance(handler, dict) and _managed_claude_command(
                handler.get("command")
            ):
                handler.update(handler_payload)
                found = True
    if not found:
        stop_value.append({"hooks": [dict(handler_payload)]})

    content = json.dumps(settings, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return None
    return PlannedWrite(path, content)


def _prepare_claude_uninstall(root: Path) -> PlannedWrite | None:
    path = root / CLAUDE_SETTINGS
    if not path.exists():
        return None
    settings = _load_json_object(path)
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return None
    stop_value = hooks.get("Stop")
    if not isinstance(stop_value, list):
        return None

    changed = False
    retained_groups: list[Any] = []
    for group in stop_value:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            retained_groups.append(group)
            continue
        handlers = group["hooks"]
        retained_handlers = [
            handler
            for handler in handlers
            if not (
                isinstance(handler, dict)
                and _managed_claude_command(handler.get("command"))
            )
        ]
        changed |= len(retained_handlers) != len(handlers)
        if retained_handlers:
            updated_group = dict(group)
            updated_group["hooks"] = retained_handlers
            retained_groups.append(updated_group)

    if not changed:
        return None
    if retained_groups:
        hooks["Stop"] = retained_groups
    else:
        hooks.pop("Stop", None)
    if not hooks:
        settings.pop("hooks", None)
    return PlannedWrite(path, json.dumps(settings, indent=2) + "\n")


def _prepare_opencode_install(root: Path, *, force: bool) -> PlannedWrite | None:
    path = root / OPENCODE_PLUGIN
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        managed = OPENCODE_MARKER in existing or _LEGACY_HOOK_SCRIPT in existing
        if not managed and not force:
            raise InstallError(
                f"{path} is not managed by doc-sync; pass `--force` to replace it"
            )
    content = _resource_text("opencode-plugin.ts").replace(
        "      // __DOC_SYNC_INVOCATION__", _opencode_invocation(root)
    )
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return None
    return PlannedWrite(path, content)


def _prepare_opencode_uninstall(root: Path) -> Path | None:
    path = root / OPENCODE_PLUGIN
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    if OPENCODE_MARKER not in content and _LEGACY_HOOK_SCRIPT not in content:
        raise InstallError(f"{path} is not managed by doc-sync; refusing to remove it")
    return path


def _apply(
    writes: Sequence[PlannedWrite],
    removals: Sequence[Path] = (),
    *,
    dry_run: bool,
) -> None:
    for planned in writes:
        print(f"would write {planned.path}" if dry_run else f"wrote {planned.path}")
        if not dry_run:
            atomic_write(planned.path, planned.content)
    for path in removals:
        print(f"would remove {path}" if dry_run else f"removed {path}")
        if not dry_run:
            path.unlink()


def initialize_config(root: Path, *, dry_run: bool) -> bool:
    """Create the example configuration when the repository has none."""
    path = root / CONFIG_FILENAME
    if path.exists():
        return False
    _apply([PlannedWrite(path, _resource_text("example.toml"))], dry_run=dry_run)
    return True


def install_hooks(
    root: Path,
    targets: tuple[str, ...],
    *,
    dry_run: bool,
    force: bool,
) -> None:
    """Install selected integrations after all changes have been validated."""
    writes: list[PlannedWrite] = []
    if "claude" in targets and (planned := _prepare_claude_install(root)):
        writes.append(planned)
    if "opencode" in targets and (
        planned := _prepare_opencode_install(root, force=force)
    ):
        writes.append(planned)

    initialize_config(root, dry_run=dry_run)
    _apply(writes, dry_run=dry_run)
    if not writes:
        print("all selected doc-sync hooks are already current")


def uninstall_hooks(root: Path, targets: tuple[str, ...], *, dry_run: bool) -> None:
    """Remove selected managed integrations while retaining configuration."""
    writes: list[PlannedWrite] = []
    removals: list[Path] = []
    if "claude" in targets and (planned := _prepare_claude_uninstall(root)):
        writes.append(planned)
    if "opencode" in targets and (removal := _prepare_opencode_uninstall(root)):
        removals.append(removal)

    _apply(writes, removals, dry_run=dry_run)
    if not writes and not removals:
        print("no selected doc-sync hooks were installed")
