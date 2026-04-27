# ruff: noqa: D101, D102, S101
"""Tests for the portable doc-sync checker."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from doc_sync import check_changed_files, match_path


class MatchPathTest(unittest.TestCase):
    def test_exact_file(self) -> None:
        assert match_path("pyproject.toml", "pyproject.toml")
        assert not match_path("pyproject.toml", "nested/pyproject.toml")

    def test_directory_prefix(self) -> None:
        assert match_path("src/", "src/app.py")
        assert match_path("src/", "src/pkg/app.py")
        assert not match_path("src/", "other/src/app.py")

    def test_star_stays_within_one_segment(self) -> None:
        assert match_path("src/*.py", "src/app.py")
        assert not match_path("src/*.py", "src/pkg/app.py")

    def test_globstar_matches_zero_or_more_segments(self) -> None:
        assert match_path("src/**/*.py", "src/app.py")
        assert match_path("src/**/*.py", "src/pkg/app.py")
        assert match_path("**/*.py", "app.py")
        assert match_path("**/*.py", "src/pkg/app.py")


class CheckChangedFilesTest(unittest.TestCase):
    def test_blocks_once_for_same_missing_docs(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            config_path = root / "doc-sync.toml"
            state_path = root / ".doc-sync-state.json"
            config_path.write_text(
                """
version = 2

[[watch]]
paths = ["src/"]
docs = ["README.md"]
""".lstrip(),
                encoding="utf-8",
            )

            first = check_changed_files(
                config_path=config_path,
                state_path=state_path,
                changed_files=("src/app.py",),
            )
            second = check_changed_files(
                config_path=config_path,
                state_path=state_path,
                changed_files=("src/app.py",),
            )

            assert first.decision == "block"
            assert second.decision == "proceed"
            assert state_path.exists()

    def test_clears_state_when_docs_are_changed(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            config_path = root / "doc-sync.toml"
            state_path = root / ".doc-sync-state.json"
            config_path.write_text(
                """
version = 2

[[watch]]
paths = ["src/"]
docs = ["README.md"]
""".lstrip(),
                encoding="utf-8",
            )

            blocked = check_changed_files(
                config_path=config_path,
                state_path=state_path,
                changed_files=("src/app.py",),
            )
            cleared = check_changed_files(
                config_path=config_path,
                state_path=state_path,
                changed_files=("src/app.py", "README.md"),
            )

            assert blocked.decision == "block"
            assert cleared.decision == "proceed"
            assert not state_path.exists()

    def test_reblocks_when_content_fingerprint_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            config_path = root / "doc-sync.toml"
            state_path = root / ".doc-sync-state.json"
            config_path.write_text(
                """
version = 2

[[watch]]
paths = ["src/"]
docs = ["README.md"]
""".lstrip(),
                encoding="utf-8",
            )

            first = check_changed_files(
                config_path=config_path,
                state_path=state_path,
                changed_files=("src/app.py",),
                content_fingerprint="v1",
            )
            second = check_changed_files(
                config_path=config_path,
                state_path=state_path,
                changed_files=("src/app.py",),
                content_fingerprint="v1",
            )
            third = check_changed_files(
                config_path=config_path,
                state_path=state_path,
                changed_files=("src/app.py",),
                content_fingerprint="v2",
            )

            assert first.decision == "block"
            assert second.decision == "proceed"
            assert third.decision == "block"


if __name__ == "__main__":
    unittest.main()
