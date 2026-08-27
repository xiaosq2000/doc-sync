from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from doc_sync.git import (
    GitError,
    changed_base_paths,
    changed_staged_paths,
    changed_worktree_paths,
    resolve_root,
)
from tests.support import commit_all, git

if TYPE_CHECKING:
    from pathlib import Path


def test_reports_staged_and_untracked_paths_before_the_first_commit(
    empty_repository: Path,
) -> None:
    (empty_repository / "staged.txt").write_text("new", encoding="utf-8")
    git(empty_repository, "add", "staged.txt")
    (empty_repository / "untracked.txt").write_text("new", encoding="utf-8")

    assert changed_worktree_paths(empty_repository) == ("staged.txt", "untracked.txt")


def test_reports_staged_unstaged_untracked_and_deleted_paths(
    empty_repository: Path,
) -> None:
    for name in ("staged.txt", "unstaged.txt", "deleted.txt"):
        (empty_repository / name).write_text("old", encoding="utf-8")
    commit_all(empty_repository)

    (empty_repository / "staged.txt").write_text("new", encoding="utf-8")
    git(empty_repository, "add", "staged.txt")
    (empty_repository / "unstaged.txt").write_text("new", encoding="utf-8")
    (empty_repository / "untracked.txt").write_text("new", encoding="utf-8")
    (empty_repository / "deleted.txt").unlink()

    assert changed_staged_paths(empty_repository) == ("staged.txt",)
    assert changed_worktree_paths(empty_repository) == (
        "deleted.txt",
        "staged.txt",
        "unstaged.txt",
        "untracked.txt",
    )


@pytest.mark.posix_only
def test_preserves_newline_in_file_name(empty_repository: Path) -> None:
    (empty_repository / "initial.txt").write_text("initial", encoding="utf-8")
    commit_all(empty_repository)
    unusual = "line\nbreak.txt"
    (empty_repository / unusual).write_text("content", encoding="utf-8")

    assert changed_worktree_paths(empty_repository) == (unusual,)


def test_reports_paths_from_merge_base(empty_repository: Path) -> None:
    (empty_repository / "one.txt").write_text("one", encoding="utf-8")
    commit_all(empty_repository)
    base = git(empty_repository, "rev-parse", "HEAD")
    (empty_repository / "two.txt").write_text("two", encoding="utf-8")
    commit_all(empty_repository, "second")

    assert changed_base_paths(empty_repository, base) == ("two.txt",)


def test_rejects_option_like_base(empty_repository: Path) -> None:
    (empty_repository / "initial.txt").write_text("initial", encoding="utf-8")
    commit_all(empty_repository)

    with pytest.raises(GitError):
        changed_base_paths(empty_repository, "--output=unexpected")


def test_git_failure_is_not_an_empty_change_set(root: Path) -> None:
    with pytest.raises(GitError):
        resolve_root(str(root))
