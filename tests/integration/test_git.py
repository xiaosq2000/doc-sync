from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from doc_sync.git import (
    GitError,
    changed_base_paths,
    changed_staged_paths,
    changed_worktree_paths,
    resolve_root,
)
from tests.support import commit_all, git, initialize_repository


class GitRepositoryTest(unittest.TestCase):
    def test_reports_staged_and_untracked_paths_before_the_first_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)
            (root / "staged.txt").write_text("new", encoding="utf-8")
            git(root, "add", "staged.txt")
            (root / "untracked.txt").write_text("new", encoding="utf-8")

            assert changed_worktree_paths(root) == ("staged.txt", "untracked.txt")

    def test_reports_staged_unstaged_untracked_and_deleted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)
            (root / "staged.txt").write_text("old", encoding="utf-8")
            (root / "unstaged.txt").write_text("old", encoding="utf-8")
            (root / "deleted.txt").write_text("old", encoding="utf-8")
            commit_all(root)

            (root / "staged.txt").write_text("new", encoding="utf-8")
            git(root, "add", "staged.txt")
            (root / "unstaged.txt").write_text("new", encoding="utf-8")
            (root / "untracked.txt").write_text("new", encoding="utf-8")
            (root / "deleted.txt").unlink()

            assert changed_staged_paths(root) == ("staged.txt",)
            assert changed_worktree_paths(root) == (
                "deleted.txt",
                "staged.txt",
                "unstaged.txt",
                "untracked.txt",
            )

    def test_preserves_newline_in_file_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)
            (root / "initial.txt").write_text("initial", encoding="utf-8")
            commit_all(root)
            unusual = "line\nbreak.txt"
            (root / unusual).write_text("content", encoding="utf-8")

            assert changed_worktree_paths(root) == (unusual,)

    def test_reports_paths_from_merge_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)
            (root / "one.txt").write_text("one", encoding="utf-8")
            commit_all(root)
            base = git(root, "rev-parse", "HEAD")
            (root / "two.txt").write_text("two", encoding="utf-8")
            commit_all(root, "second")

            assert changed_base_paths(root, base) == ("two.txt",)

    def test_rejects_option_like_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_repository(root)
            (root / "initial.txt").write_text("initial", encoding="utf-8")
            commit_all(root)

            with self.assertRaises(GitError):
                changed_base_paths(root, "--output=unexpected")

    def test_git_failure_is_not_an_empty_change_set(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaises(GitError),
        ):
            resolve_root(directory)
