from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from doc_sync.config import (
    ConfigError,
    MissingConfigError,
    load_config,
    validate_repository_config,
)
from tests.support import write_config

if TYPE_CHECKING:
    from pathlib import Path

UNKNOWN_RULE_KEY = """config_version = 1
[[rules]]
id = "application"
sources = ["src/"]
document = ["README.md"]
"""

LEGACY_LAYOUT = """version = 1
[[watch]]
sources = ["src/"]
"""

GLOB_DOCUMENT = """config_version = 1
[[rules]]
id = "application"
sources = ["src/"]
documents = ["docs/*.md"]
"""


def test_loads_named_rules(root: Path) -> None:
    config = load_config(write_config(root))

    assert config.config_version == 1
    assert config.rules[0].id == "application"


# Agent adapters branch on this subclass to stay silent for a repository that
# never opted in, so an absent file must not be conflated with a broken one.
def test_an_absent_file_raises_the_missing_config_subclass(root: Path) -> None:
    with pytest.raises(MissingConfigError, match="does not exist"):
        load_config(root / "doc-sync.toml")


def test_a_broken_file_is_not_reported_as_missing(root: Path) -> None:
    path = root / "doc-sync.toml"
    path.write_text("config_version = 1\n[[rules\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="TOML parse error") as caught:
        load_config(path)

    assert not isinstance(caught.value, MissingConfigError)


@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        (UNKNOWN_RULE_KEY, "`document`"),
        (LEGACY_LAYOUT, "pre-1 `version`/`\\[\\[watch\\]\\]` configuration"),
        (GLOB_DOCUMENT, "must be an exact"),
    ],
    ids=["unknown-rule-key", "legacy-layout", "glob-document"],
)
def test_rejects_invalid_config(
    root: Path, content: str, expected_message: str
) -> None:
    path = root / "doc-sync.toml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError, match=expected_message):
        load_config(path)


@pytest.mark.parametrize(
    ("original", "replacement", "expected_message"),
    [
        (
            "config_version = 1\n",
            "config_version = 1\nunknown = true\n",
            "unknown key",
        ),
        ('sources = ["src/"]', 'sources = ["src/", "./src/"]', "duplicate path"),
        ('id = "application"', 'id = "Application"', "`id` must match"),
    ],
    ids=["unknown-root-key", "duplicate-source", "uppercase-id"],
)
def test_rejects_invalid_edit(
    root: Path, original: str, replacement: str, expected_message: str
) -> None:
    path = write_config(root)
    path.write_text(
        path.read_text(encoding="utf-8").replace(original, replacement),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected_message):
        load_config(path)


def test_repository_validation_checks_paths(repository: Path) -> None:
    config = validate_repository_config(
        root=repository, config_path=repository / "doc-sync.toml"
    )

    assert config.rules[0].sources == ("src/",)


def test_repository_validation_reports_missing_paths(repository: Path) -> None:
    path = repository / "doc-sync.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'sources = ["src/"]', 'sources = ["absent/"]'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="does not point to an existing directory"):
        validate_repository_config(root=repository, config_path=path)
