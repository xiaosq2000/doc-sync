#!/usr/bin/env python3
"""Portable doc-sync checker for session-end agent hooks."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PureWindowsPath
from typing import Any

STATE_FILENAME = ".doc-sync-state.json"
CONFIG_FILENAME = "doc-sync.toml"
EXIT_BLOCK = 2


@dataclass(frozen=True)
class Watch:
    """A set of paths that requires docs to be reviewed when changed."""

    paths: tuple[str, ...]
    docs: tuple[str, ...]


@dataclass(frozen=True)
class CheckResult:
    """Structured doc-sync decision."""

    decision: str
    reason: str = ""
    missing_docs: tuple[str, ...] = ()
    triggered_rules: tuple[dict[str, Any], ...] = ()

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "decision": self.decision,
            "prompt": self.reason,
            "reason": self.reason,
            "missing_docs": list(self.missing_docs),
            "triggered_rules": list(self.triggered_rules),
        }


class ConfigError(ValueError):
    """Raised when the doc-sync config is invalid."""


def _normalize_path(path: str, *, keep_trailing_slash: bool = False) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if keep_trailing_slash:
        return normalized
    return normalized.rstrip("/")


def _has_glob(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def _match_segments(
    pattern_segments: tuple[str, ...], path_segments: tuple[str, ...]
) -> bool:
    memo: dict[tuple[int, int], bool] = {}

    def match(pattern_index: int, path_index: int) -> bool:
        key = (pattern_index, path_index)
        if key in memo:
            return memo[key]
        if pattern_index == len(pattern_segments):
            result = path_index == len(path_segments)
        elif pattern_segments[pattern_index] == "**":
            result = any(
                match(pattern_index + 1, next_path_index)
                for next_path_index in range(path_index, len(path_segments) + 1)
            )
        elif path_index >= len(path_segments):
            result = False
        else:
            result = fnmatchcase(
                path_segments[path_index],
                pattern_segments[pattern_index],
            ) and match(pattern_index + 1, path_index + 1)
        memo[key] = result
        return result

    return match(0, 0)


def match_path(pattern: str, path: str) -> bool:
    """Return whether a repo-relative path matches a doc-sync pattern."""
    is_directory_pattern = pattern.endswith("/")
    normalized_pattern = _normalize_path(
        pattern, keep_trailing_slash=is_directory_pattern
    )
    normalized_path = _normalize_path(path)

    if not normalized_pattern or not normalized_path:
        return False

    if is_directory_pattern:
        directory = normalized_pattern.rstrip("/")
        return normalized_path == directory or normalized_path.startswith(
            f"{directory}/"
        )

    if not _has_glob(normalized_pattern):
        return normalized_path == normalized_pattern

    return _match_segments(
        tuple(normalized_pattern.split("/")),
        tuple(normalized_path.split("/")),
    )


def _load_config(config_path: Path) -> tuple[Watch, ...] | None:
    if not config_path.exists():
        return None

    try:
        with config_path.open("rb") as config_file:
            config = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path}: TOML parse error: {exc}") from exc

    version = config.get("version")
    if version != 2:
        raise ConfigError(f"{config_path}: expected `version = 2`")

    raw_watches = config.get("watch")
    if not isinstance(raw_watches, list) or not raw_watches:
        raise ConfigError(f"{config_path}: expected at least one `[[watch]]` block")

    watches: list[Watch] = []
    for index, raw_watch in enumerate(raw_watches, start=1):
        if not isinstance(raw_watch, dict):
            raise ConfigError(f"{config_path}: `[[watch]]` #{index} must be a table")
        paths = _validate_string_list(config_path, index, raw_watch, "paths")
        docs = _validate_string_list(config_path, index, raw_watch, "docs")
        watches.append(Watch(paths=tuple(paths), docs=tuple(docs)))
    return tuple(watches)


def _validate_string_list(
    config_path: Path,
    watch_index: int,
    raw_watch: dict[str, Any],
    key: str,
) -> list[str]:
    value = raw_watch.get(key)
    if not isinstance(value, list) or not value:
        raise ConfigError(
            f"{config_path}: `[[watch]]` #{watch_index} must define a non-empty `{key}` list",
        )

    strings: list[str] = []
    for item_index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(
                f"{config_path}: `[[watch]]` #{watch_index} `{key}` item #{item_index} must be a non-empty string",
            )
        normalized = _normalize_path(item, keep_trailing_slash=item.endswith("/"))
        location = (
            f"{config_path}: `[[watch]]` #{watch_index} `{key}` item #{item_index}"
        )
        _validate_relative_config_path(location, item, normalized)
        strings.append(normalized)
    return strings


def _validate_relative_config_path(
    location: str,
    raw_item: str,
    normalized: str,
) -> None:
    if (
        raw_item.startswith("/")
        or normalized.startswith("/")
        or PureWindowsPath(raw_item).is_absolute()
    ):
        raise ConfigError(f"{location} must be repo-relative")

    normalized_without_slash = normalized.rstrip("/")
    if not normalized_without_slash:
        raise ConfigError(f"{location} must not normalize to an empty path")

    if any(segment in {".", ".."} for segment in normalized_without_slash.split("/")):
        raise ConfigError(f"{location} must not contain `.` or `..` segments")


def lint_config_paths(*, root: Path, config_path: Path) -> None:
    """Validate that every configured doc-sync path resolves in the repository."""
    watches = _load_config(config_path)
    if watches is None:
        raise ConfigError(f"{config_path}: config file does not exist")

    root = root.resolve()
    repo_file_paths = _repo_file_paths(root)
    errors: list[str] = []
    for watch_index, watch in enumerate(watches, start=1):
        for item_index, pattern in enumerate(watch.paths, start=1):
            location = (
                f"`[[watch]]` #{watch_index} `paths` item #{item_index} `{pattern}`"
            )
            error = _lint_path_entry(
                root,
                repo_file_paths,
                location,
                "paths",
                pattern,
            )
            if error:
                errors.append(error)
        for item_index, doc in enumerate(watch.docs, start=1):
            location = f"`[[watch]]` #{watch_index} `docs` item #{item_index} `{doc}`"
            error = _lint_path_entry(
                root,
                repo_file_paths,
                location,
                "docs",
                doc,
            )
            if error:
                errors.append(error)

    if errors:
        detail = "\n".join(f"  - {error}" for error in errors)
        raise ConfigError(f"{config_path}: invalid configured paths:\n{detail}")


def _repo_file_paths(root: Path) -> tuple[str, ...]:
    git_paths = _run_git(
        root, ["ls-files", "--cached", "--others", "--exclude-standard"]
    )
    if git_paths:
        normalized_paths = {_normalize_path(path) for path in git_paths}
        return tuple(
            sorted(path for path in normalized_paths if (root / path).is_file()),
        )

    return tuple(
        sorted(
            _normalize_path(str(path.relative_to(root)))
            for path in root.rglob("*")
            if path.is_file()
        ),
    )


def _lint_path_entry(
    root: Path,
    repo_file_paths: tuple[str, ...],
    location: str,
    key: str,
    value: str,
) -> str | None:
    error: str | None = None
    if key == "docs":
        if value.endswith("/") or _has_glob(value):
            error = f"{location} must be an exact documentation file path"
        elif not (root / value).is_file():
            error = f"{location} does not point to an existing file"
    elif value.endswith("/"):
        if _has_glob(value.rstrip("/")):
            error = f"{location} must not combine glob syntax with trailing `/` directory matching"
        elif not (root / value.rstrip("/")).is_dir():
            error = f"{location} does not point to an existing directory"
    elif _has_glob(value):
        if not any(match_path(value, path) for path in repo_file_paths):
            error = f"{location} glob does not match any tracked or untracked file"
    elif not (root / value).is_file():
        error = f"{location} does not point to an existing file"
    return error


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


def _changed_files(root: Path) -> tuple[str, ...]:
    changed = {
        _normalize_path(path)
        for path in [
            *_run_git(root, ["diff", "--name-only", "HEAD"]),
            *_run_git(root, ["ls-files", "--others", "--exclude-standard"]),
        ]
        if path.strip()
    }
    return tuple(sorted(changed))


def _content_fingerprint(root: Path, changed_files: tuple[str, ...]) -> str:
    items: list[dict[str, str]] = []
    for path in changed_files:
        file_path = root / path
        try:
            if file_path.is_symlink():
                marker = f"symlink:{file_path.readlink()}"
            elif file_path.is_file():
                marker = f"file:{hashlib.sha256(file_path.read_bytes()).hexdigest()}"
            elif file_path.exists():
                marker = "other"
            else:
                marker = "missing"
        except OSError as exc:
            marker = f"error:{exc.__class__.__name__}"
        items.append({"path": path, "content": marker})
    encoded = json.dumps(items, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _evaluate(
    watches: tuple[Watch, ...], changed_files: tuple[str, ...]
) -> CheckResult:
    changed_set = set(changed_files)
    triggered: list[dict[str, Any]] = []
    all_missing: set[str] = set()

    for watch in watches:
        matched_files = tuple(
            sorted(
                {
                    path
                    for path in changed_files
                    if any(match_path(pattern, path) for pattern in watch.paths)
                },
            ),
        )
        if not matched_files:
            continue

        missing_docs = tuple(doc for doc in watch.docs if doc not in changed_set)
        if missing_docs:
            triggered.append(
                {
                    "watch_paths": list(watch.paths),
                    "matched_files": list(matched_files),
                    "missing_docs": list(missing_docs),
                },
            )
            all_missing.update(missing_docs)

    if not all_missing:
        return CheckResult(decision="proceed")

    missing_docs = tuple(sorted(all_missing))
    return CheckResult(
        decision="block",
        reason=_build_reason(triggered),
        missing_docs=missing_docs,
        triggered_rules=tuple(triggered),
    )


def _build_reason(triggered: list[dict[str, Any]]) -> str:
    lines = [
        "Documentation may need updating.",
        "",
        "Changed files triggered these doc-sync watches:",
    ]
    lines.extend(
        f"  {matched_file} -> {doc}"
        for rule in triggered
        for matched_file in rule["matched_files"]
        for doc in rule["missing_docs"]
    )
    lines.extend(
        [
            "",
            "Review each doc listed above. Update it if the source changes affect durable facts.",
            "If no update is needed, you may proceed; this exact doc-sync state will not block again.",
        ],
    )
    return "\n".join(lines)


def _state_key(result: CheckResult, content_fingerprint: str) -> str:
    payload = {
        "content_fingerprint": content_fingerprint,
        "missing_docs": list(result.missing_docs),
        "triggered_rules": list(result.triggered_rules),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_state(state_path: Path) -> dict[str, Any] | None:
    try:
        raw_state = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw_state, dict):
        return None
    return raw_state


def _write_state(state_path: Path, state_key: str, result: CheckResult) -> None:
    payload = {
        "version": 1,
        "state_key": state_key,
        "missing_docs": list(result.missing_docs),
        "triggered_rules": list(result.triggered_rules),
    }
    state_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _clear_state(state_path: Path) -> None:
    state_path.unlink(missing_ok=True)


def check_changed_files(
    *,
    config_path: Path,
    state_path: Path,
    changed_files: tuple[str, ...],
    content_fingerprint: str = "",
) -> CheckResult:
    """Check changed files and update doc-sync state."""
    normalized_changed = tuple(
        sorted({_normalize_path(path) for path in changed_files if path})
    )
    if not normalized_changed:
        _clear_state(state_path)
        return CheckResult(decision="proceed")

    watches = _load_config(config_path)
    if watches is None:
        _clear_state(state_path)
        return CheckResult(decision="proceed")

    result = _evaluate(watches, normalized_changed)
    if result.decision != "block":
        _clear_state(state_path)
        return result

    current_key = _state_key(result, content_fingerprint)
    previous_state = _read_state(state_path)
    if previous_state and previous_state.get("state_key") == current_key:
        return CheckResult(decision="proceed")

    _write_state(state_path, current_key, result)
    return result


def _resolve_root(raw_root: str | None) -> Path:
    if raw_root:
        return Path(raw_root).resolve()

    git_root = _run_git(Path.cwd(), ["rev-parse", "--show-toplevel"])
    if git_root:
        return Path(git_root[0]).resolve()
    return Path.cwd().resolve()


def _resolve_path(root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return root / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check source/doc sync for changed files."
    )
    parser.add_argument("--root", help="Repository root. Defaults to git root or cwd.")
    parser.add_argument(
        "--config",
        default=CONFIG_FILENAME,
        help=f"Config path. Defaults to {CONFIG_FILENAME} at the repo root.",
    )
    parser.add_argument(
        "--state",
        default=STATE_FILENAME,
        help=f"State path. Defaults to {STATE_FILENAME} at the repo root.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read changed file paths from stdin instead of git.",
    )
    parser.add_argument(
        "--lint-config",
        action="store_true",
        help="Validate that configured paths exist, then exit.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the doc-sync checker CLI."""
    args = _parse_args()
    root = _resolve_root(args.root)
    config_path = _resolve_path(root, args.config)
    state_path = _resolve_path(root, args.state)

    if args.lint_config:
        try:
            lint_config_paths(root=root, config_path=config_path)
        except ConfigError as exc:
            sys.stderr.write(f"doc-sync config error: {exc}\n")
            sys.exit(1)
        sys.exit(0)

    changed_files = (
        tuple(line.strip() for line in sys.stdin.read().splitlines() if line.strip())
        if args.stdin
        else _changed_files(root)
    )
    content_fingerprint = _content_fingerprint(root, changed_files)

    try:
        result = check_changed_files(
            config_path=config_path,
            state_path=state_path,
            changed_files=changed_files,
            content_fingerprint=content_fingerprint,
        )
    except ConfigError as exc:
        json.dump(
            {
                "decision": "block",
                "prompt": f"doc-sync config error: {exc}",
                "reason": f"doc-sync config error: {exc}",
            },
            sys.stdout,
        )
        sys.exit(EXIT_BLOCK)

    if result.decision == "block":
        json.dump(result.to_json(), sys.stdout)
        sys.exit(EXIT_BLOCK)

    sys.exit(0)


if __name__ == "__main__":
    main()
