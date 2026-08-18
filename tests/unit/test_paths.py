from __future__ import annotations

import unittest

from doc_sync.paths import match_path, normalize_path, relative_path_error


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

    def test_normalizes_windows_separators(self) -> None:
        assert normalize_path(r"src\package\app.py") == "src/package/app.py"

    def test_rejects_parent_reference(self) -> None:
        error = relative_path_error("source", "../src", "../src")

        assert error is not None
        assert "`..`" in error

    def test_accepts_relative_path(self) -> None:
        assert relative_path_error("source", "src/app.py", "src/app.py") is None
