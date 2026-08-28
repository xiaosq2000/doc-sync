"""Shared fixtures for the doc-sync test suite."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from tests.support import commit_all, initialize_repository, write_config

if TYPE_CHECKING:
    from pathlib import Path


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip `posix_only` tests on Windows, which lacks the semantics they assert."""
    if sys.platform == "win32" and "posix_only" in item.keywords:
        pytest.skip("requires POSIX filesystem or permission semantics")


def _populate(root: Path) -> None:
    """Write the standard source, document, and configuration fixture."""
    (root / "src").mkdir()
    (root / "src/app.py").write_text("v1", encoding="utf-8")
    (root / "README.md").write_text("docs", encoding="utf-8")
    write_config(root)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An empty directory usable as a repository root."""
    return tmp_path


@pytest.fixture
def empty_repository(root: Path) -> Path:
    """An initialized Git repository holding no files."""
    initialize_repository(root)
    return root


@pytest.fixture
def repository(empty_repository: Path) -> Path:
    """A Git repository whose `APPLICATION_RULE` files are committed."""
    _populate(empty_repository)
    commit_all(empty_repository)
    return empty_repository


@pytest.fixture
def uncommitted_repository(empty_repository: Path) -> Path:
    """The same repository contents, left uncommitted in the worktree."""
    _populate(empty_repository)
    return empty_repository
