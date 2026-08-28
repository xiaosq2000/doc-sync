from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from doc_sync.config import (
    ConfigError,
    Document,
    MissingConfigError,
    load_config,
    validate_repository_config,
)
from tests.support import write_config

if TYPE_CHECKING:
    from pathlib import Path


def test_loads_documents_in_stable_path_order(root: Path) -> None:
    path = root / "doc-sync.toml"
    path.write_text(
        '[documents]\n"z.md" = ["z/"]\n"a.md" = ["a/", "common.py"]\n',
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.documents == (
        Document(path="a.md", sources=("a/", "common.py")),
        Document(path="z.md", sources=("z/",)),
    )


def test_an_absent_file_has_a_distinct_error(root: Path) -> None:
    with pytest.raises(MissingConfigError, match="does not exist"):
        load_config(root / "doc-sync.toml")


def test_a_broken_file_is_not_reported_as_missing(root: Path) -> None:
    path = root / "doc-sync.toml"
    path.write_text("[documents\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="TOML parse error") as caught:
        load_config(path)

    assert not isinstance(caught.value, MissingConfigError)


@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        ("config_version = 1\n[documents]\n", "unknown key"),
        ("[documents]\n", "non-empty"),
        ('[documents]\n"README.md" = []\n', "non-empty array"),
        ('[documents]\n"docs/*.md" = ["src/"]\n', "exact file path"),
        ('[documents]\n"README.md" = ["../src"]\n', "`..`"),
        (
            '[documents]\n"README.md" = ["src/", "./src/"]\n',
            "duplicate source",
        ),
        (
            '[documents]\n"README.md" = ["src/"]\n"./README.md" = ["lib/"]\n',
            "duplicate document path",
        ),
    ],
    ids=[
        "unknown-root-key",
        "empty-documents",
        "empty-sources",
        "glob-document",
        "parent-source",
        "duplicate-source",
        "duplicate-document",
    ],
)
def test_rejects_invalid_config(
    root: Path, content: str, expected_message: str
) -> None:
    path = root / "doc-sync.toml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError, match=expected_message):
        load_config(path)


def test_repository_validation_requires_documents(repository: Path) -> None:
    path = write_config(repository, document="docs/missing.md")

    with pytest.raises(ConfigError, match=r"docs/missing\.md.*does not exist"):
        validate_repository_config(root=repository, config_path=path)


def test_repository_validation_allows_unmatched_source_patterns(
    repository: Path,
) -> None:
    path = write_config(repository, sources=("future/**/*.py",))

    config = validate_repository_config(root=repository, config_path=path)

    assert config.documents[0].sources == ("future/**/*.py",)
