"""Shared temporary-repository helpers."""

from __future__ import annotations

import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from doc_sync.model import Rule

if TYPE_CHECKING:
    from collections.abc import Iterator

# The rule every fixture repository is built around. `write_config` renders its
# TOML from this object so the config and the expected Rule cannot drift apart.
APPLICATION_RULE = Rule(id="application", sources=("src/",), documents=("README.md",))


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def initialize_repository(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "config", "user.email", "doc-sync@example.invalid")
    git(root, "config", "user.name", "Doc Sync Tests")


def commit_all(root: Path, message: str = "initial") -> None:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


def render_config(rule: Rule) -> str:
    sources = ", ".join(f'"{source}"' for source in rule.sources)
    documents = ", ".join(f'"{document}"' for document in rule.documents)
    return (
        "config_version = 1\n"
        "\n"
        "[[rules]]\n"
        f'id = "{rule.id}"\n'
        f"sources = [{sources}]\n"
        f"documents = [{documents}]\n"
    )


def write_config(root: Path, *, document: str = "README.md") -> Path:
    path = root / "doc-sync.toml"
    rule = replace(APPLICATION_RULE, documents=(document,))
    path.write_text(render_config(rule), encoding="utf-8")
    return path


@contextmanager
def temporary_root() -> Iterator[Path]:
    """Yield an empty temporary directory as a repository root."""
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)


@contextmanager
def temporary_repository(*, commit: bool = True) -> Iterator[Path]:
    """Yield a Git repository holding the source, document, and config of APPLICATION_RULE."""
    with temporary_root() as root:
        initialize_repository(root)
        (root / "src").mkdir()
        (root / "src/app.py").write_text("v1", encoding="utf-8")
        (root / "README.md").write_text("docs", encoding="utf-8")
        write_config(root)
        if commit:
            commit_all(root)
        yield root
