"""Shared repository helpers."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from doc_sync.config import Document

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


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


def add_submodule(root: Path, library: Path) -> Path:
    """Commit a submodule at `vendor/lib` whose clone can make commits."""
    initialize_repository(library)
    (library / "lib.txt").write_text("one", encoding="utf-8")
    commit_all(library)
    git(
        root,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        library.as_uri(),
        "vendor/lib",
    )
    commit_all(root)
    submodule = root / "vendor/lib"
    initialize_repository(submodule)
    return submodule


def render_config(documents: Iterable[Document]) -> str:
    lines = ["[documents]"]
    for document in documents:
        sources = ", ".join(json.dumps(source) for source in document.sources)
        lines.append(f"{json.dumps(document.path)} = [{sources}]")
    return "\n".join(lines) + "\n"


def write_config(
    root: Path, *, document: str = "README.md", sources: tuple[str, ...] = ("src/",)
) -> Path:
    path = root / "doc-sync.toml"
    path.write_text(
        render_config((Document(path=document, sources=sources),)), encoding="utf-8"
    )
    return path
