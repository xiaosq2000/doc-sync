"""Strict Git-backed repository discovery."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from doc_sync.errors import DocSyncError


class GitError(DocSyncError, RuntimeError):
    """Raised when doc-sync cannot query repository state."""


def _run_git(root: Path, arguments: list[str]) -> bytes:
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(root), *arguments],  # noqa: S607
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise GitError(f"could not execute git: {exc}") from exc
    if result.returncode != 0:
        detail = os.fsdecode(result.stderr).strip() or "unknown git error"
        raise GitError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout


def _nul_paths(output: bytes) -> tuple[str, ...]:
    return tuple(os.fsdecode(raw_path) for raw_path in output.split(b"\0") if raw_path)


def resolve_root(raw_root: str | None = None) -> Path:
    """Resolve and validate the Git repository root."""
    candidate = Path(raw_root).resolve() if raw_root else Path.cwd().resolve()
    output = _run_git(candidate, ["rev-parse", "--show-toplevel"])
    return Path(os.fsdecode(output).strip()).resolve()


def changed_worktree_paths(root: Path) -> tuple[str, ...]:
    """Return staged, unstaged, and untracked non-ignored paths."""
    try:
        tracked = _nul_paths(_run_git(root, ["diff", "--name-only", "-z", "HEAD"]))
    except GitError:
        # Unborn HEAD: the index is the only thing there is to compare against.
        # Asking first would cost an extra `git` spawn on every agent hook fire.
        tracked = _nul_paths(_run_git(root, ["diff", "--cached", "--name-only", "-z"]))
    changed = {
        *tracked,
        *_nul_paths(
            _run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"])
        ),
    }
    return tuple(sorted(changed))


def worktree_paths(root: Path) -> tuple[str, ...]:
    """List tracked and non-ignored untracked paths, including deleted entries."""
    return tuple(
        sorted(
            set(
                _nul_paths(
                    _run_git(
                        root,
                        [
                            "ls-files",
                            "--cached",
                            "--others",
                            "--exclude-standard",
                            "-z",
                        ],
                    )
                )
            )
        )
    )


def changed_staged_paths(root: Path) -> tuple[str, ...]:
    """Return paths changed in the Git index."""
    return tuple(
        sorted(_nul_paths(_run_git(root, ["diff", "--cached", "--name-only", "-z"])))
    )


def changed_base_paths(root: Path, base: str) -> tuple[str, ...]:
    """Return committed paths changed from a merge base through HEAD."""
    base_commit = os.fsdecode(
        _run_git(
            root,
            ["rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"],
        )
    ).strip()
    return tuple(
        sorted(
            _nul_paths(
                _run_git(
                    root,
                    ["diff", "--name-only", "-z", f"{base_commit}...HEAD", "--"],
                )
            )
        )
    )


def git_metadata_path(root: Path, relative_path: str) -> Path:
    """Resolve a worktree-aware path inside Git metadata."""
    output = _run_git(root, ["rev-parse", "--git-path", relative_path])
    path = Path(os.fsdecode(output).strip())
    return path.resolve() if path.is_absolute() else (root / path).resolve()
