#!/usr/bin/env python3
# ruff: noqa: T201
"""Install the portable doc-sync hook into a repository."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

STATE_FILENAME = ".doc-sync-state.json"
CONFIG_FILENAME = "doc-sync.toml"
DEFAULT_TIMEOUT = 30


class InstallError(RuntimeError):
    """Raised when doc-sync cannot be installed safely."""


def _run_git(root: Path, args: list[str]) -> list[str]:
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(root), *args],  # noqa: S607
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _resolve_root(raw_root: str | None) -> Path:
    if raw_root:
        return Path(raw_root).resolve()

    git_root = _run_git(Path.cwd(), ["rev-parse", "--show-toplevel"])
    if git_root:
        return Path(git_root[0]).resolve()
    return Path.cwd().resolve()


def _tool_dir() -> Path:
    return Path(__file__).resolve().parent


def _hook_command(root: Path, event: str) -> str:
    hook_path = _tool_dir() / "hook.sh"
    try:
        relative_hook = hook_path.relative_to(root)
    except ValueError:
        return f'bash "{hook_path}" --event {event}'
    return f'bash "$CLAUDE_PROJECT_DIR/{relative_hook.as_posix()}" --event {event}'


def _opencode_hook_path(root: Path) -> str:
    hook_path = _tool_dir() / "hook.sh"
    try:
        relative_hook = hook_path.relative_to(root)
    except ValueError:
        return str(hook_path)
    return f"${{worktree}}/{relative_hook.as_posix()}"


def _write_text(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"would write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def _copy_example_config(root: Path, *, dry_run: bool) -> None:
    config_path = root / CONFIG_FILENAME
    if config_path.exists():
        print(f"kept existing {config_path}")
        return

    example_path = _tool_dir() / "examples" / CONFIG_FILENAME
    content = example_path.read_text(encoding="utf-8")
    _write_text(config_path, content, dry_run=dry_run)


def _ensure_gitignore(root: Path, *, dry_run: bool) -> None:
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
    else:
        content = ""

    lines = content.splitlines()
    if STATE_FILENAME in lines:
        print(f"kept existing {gitignore_path} entry for {STATE_FILENAME}")
        return

    suffix = "" if not content or content.endswith("\n") else "\n"
    updated = f"{content}{suffix}\n# doc-sync hook state\n{STATE_FILENAME}\n"
    _write_text(gitignore_path, updated, dry_run=dry_run)


def _load_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        raw_value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw_value, dict):
        raise InstallError(f"{path} must contain a JSON object")
    return cast("dict[str, object]", raw_value)


def _json_contains_hook(value: object) -> bool:
    if isinstance(value, str):
        return "tools/doc-sync/hook.sh" in value
    if isinstance(value, list):
        return any(_json_contains_hook(item) for item in value)
    if isinstance(value, dict):
        return any(_json_contains_hook(item) for item in value.values())
    return False


def _install_claude(root: Path, *, dry_run: bool) -> None:
    settings_path = root / ".claude" / "settings.json"
    settings = _load_json_object(settings_path)
    if _json_contains_hook(settings):
        print(f"kept existing Claude doc-sync hook in {settings_path}")
        return

    hooks_value = settings.get("hooks")
    if hooks_value is None:
        hooks: dict[str, object] = {}
        settings["hooks"] = hooks
    elif isinstance(hooks_value, dict):
        hooks = cast("dict[str, object]", hooks_value)
    else:
        raise InstallError(f"{settings_path}: `hooks` must be an object")

    stop_hooks_value = hooks.get("Stop")
    if stop_hooks_value is None:
        stop_hooks: list[object] = []
        hooks["Stop"] = stop_hooks
    elif isinstance(stop_hooks_value, list):
        stop_hooks = cast("list[object]", stop_hooks_value)
    else:
        raise InstallError(f"{settings_path}: `hooks.Stop` must be an array")

    stop_hooks.append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": _hook_command(root, "stop"),
                    "timeout": DEFAULT_TIMEOUT,
                    "statusMessage": "Checking documentation sync...",
                },
            ],
        },
    )
    _write_text(
        settings_path,
        json.dumps(settings, indent=2, sort_keys=False) + "\n",
        dry_run=dry_run,
    )


def _opencode_plugin_content(root: Path) -> str:
    hook_path = _opencode_hook_path(root)
    return f"""type StructuredHookOutput = {{
  decision?: string;
  prompt?: string;
  reason?: string;
}};

function getHookErrorMessage(
  stdout: string,
  stderr: string,
  exitCode: number,
): string {{
  if (stdout) {{
    try {{
      const parsed = JSON.parse(stdout) as StructuredHookOutput;
      if (parsed.decision === "block") {{
        return parsed.reason ?? parsed.prompt ?? stdout;
      }}
    }} catch {{
      return stdout;
    }}

    return stdout;
  }}

  if (stderr) {{
    return stderr;
  }}

  return `doc-sync hook failed with exit code ${{exitCode}}`;
}}

export const DocSyncHook = async ({{
  $,
  worktree,
}}: {{
  $: any;
  worktree: string;
}}) => {{
  return {{
    event: async ({{ event }}: {{ event: {{ type: string }} }}) => {{
      if (event.type !== "session.idle") return;

      const shell = $.cwd(worktree).env({{ CLAUDE_PROJECT_DIR: worktree }});
      const result = await shell`bash {hook_path} --event session.idle`
        .quiet()
        .nothrow();

      if (result.exitCode !== 0) {{
        throw new Error(
          getHookErrorMessage(
            result.text().trim(),
            result.stderr.toString().trim(),
            result.exitCode,
          ),
        );
      }}
    }},
  }};
}};
"""


def _install_opencode(root: Path, *, dry_run: bool, force: bool) -> None:
    plugin_path = root / ".opencode" / "plugins" / "doc-sync.ts"
    if plugin_path.exists():
        content = plugin_path.read_text(encoding="utf-8")
        if "tools/doc-sync/hook.sh" in content:
            print(f"kept existing OpenCode doc-sync plugin in {plugin_path}")
            return
        if not force:
            raise InstallError(
                f"{plugin_path} already exists and does not look like doc-sync; use --force to overwrite",
            )

    _write_text(plugin_path, _opencode_plugin_content(root), dry_run=dry_run)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install the portable doc-sync Stop/session-idle hook.",
    )
    parser.add_argument("--root", help="Repository root. Defaults to git root or cwd.")
    parser.add_argument(
        "--claude", action="store_true", help="Install Claude Code Stop hook."
    )
    parser.add_argument(
        "--opencode", action="store_true", help="Install OpenCode session.idle plugin."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Install both Claude Code and OpenCode wiring.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite a conflicting OpenCode doc-sync plugin.",
    )
    return parser.parse_args()


def main() -> None:
    """Install doc-sync wiring."""
    args = _parse_args()
    install_claude = bool(args.claude or args.all)
    install_opencode = bool(args.opencode or args.all)
    if not install_claude and not install_opencode:
        print(
            "select at least one target: --claude, --opencode, or --all",
            file=sys.stderr,
        )
        sys.exit(1)

    root = _resolve_root(args.root)
    try:
        _copy_example_config(root, dry_run=args.dry_run)
        _ensure_gitignore(root, dry_run=args.dry_run)
        if install_claude:
            _install_claude(root, dry_run=args.dry_run)
        if install_opencode:
            _install_opencode(root, dry_run=args.dry_run, force=args.force)
    except InstallError as exc:
        print(f"doc-sync install failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
