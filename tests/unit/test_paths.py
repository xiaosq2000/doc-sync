from __future__ import annotations

import pytest

from doc_sync.paths import match_path, normalize_path, relative_path_error


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        # Every pattern is anchored to the repository root.
        ("pyproject.toml", "pyproject.toml", True),
        ("pyproject.toml", "nested/pyproject.toml", False),
        ("*.py", "app.py", True),
        ("*.py", "src/app.py", False),
        ("src/", "src/app.py", True),
        ("src/", "src/pkg/app.py", True),
        ("src/", "other/src/app.py", False),
        ("src/app.py", "src/app.py", True),
        ("src/app.py", "nested/src/app.py", False),
        # `*` stays within one segment; `**` spans zero or more.
        ("src/*.py", "src/app.py", True),
        ("src/*.py", "src/pkg/app.py", False),
        ("src/**/*.py", "src/app.py", True),
        ("src/**/*.py", "src/pkg/app.py", True),
        # Matching at any depth is opt-in through an explicit `**/` prefix.
        ("**/*.py", "app.py", True),
        ("**/*.py", "src/pkg/app.py", True),
        ("**/app.py", "app.py", True),
        ("**/app.py", "nested/app.py", True),
        # A leading `!` or `#` is an ordinary character, not gitignore
        # negation or a comment.
        ("!literal.py", "!literal.py", True),
        ("#literal.py", "#literal.py", True),
        # A bare directory name behaves like the same name with a trailing
        # slash. `validate --check-paths` still steers configurations to the
        # explicit `src/` form, which is why this is only a fallback.
        ("src", "src/app.py", True),
        ("src", "src/pkg/app.py", True),
        # A trailing slash means a directory, so it never matches a file that
        # happens to carry the directory's name. Git reports changed files, so
        # this case only arises for a file literally named `src`.
        ("src/", "src", False),
    ],
)
def test_match_path(pattern: str, path: str, expected: bool) -> None:
    assert match_path(pattern, path) is expected


def test_normalizes_windows_separators() -> None:
    assert normalize_path(r"src\package\app.py") == "src/package/app.py"


@pytest.mark.parametrize(
    ("raw_path", "expected_fragment"),
    [
        ("../src", "`..`"),
        ("/src", "repository-relative"),
        ("./", "empty path"),
    ],
)
def test_rejects_unusable_path(raw_path: str, expected_fragment: str) -> None:
    error = relative_path_error("source", raw_path, normalize_path(raw_path))

    assert error is not None
    assert expected_fragment in error


def test_accepts_relative_path() -> None:
    assert relative_path_error("source", "src/app.py", "src/app.py") is None
