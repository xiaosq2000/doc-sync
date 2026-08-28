"""Load and validate doc-sync configuration."""

from __future__ import annotations

import tomllib
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from doc_sync.errors import DocSyncError
from doc_sync.paths import has_glob, normalize_path, relative_path_error

if TYPE_CHECKING:
    from pathlib import Path

CONFIG_FILENAME = "doc-sync.toml"
_ROOT_KEYS = {"documents"}


class ConfigError(DocSyncError, ValueError):
    """Raised when the doc-sync configuration is invalid."""


class MissingConfigError(ConfigError):
    """Raised when no doc-sync configuration exists."""


@dataclass(frozen=True)
class Document:
    """A document and the source patterns that may affect it."""

    path: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    """Validated doc-sync configuration."""

    documents: tuple[Document, ...]


def _unknown_keys(config_path: Path, value: dict[str, Any]) -> None:
    unknown = sorted(set(value) - _ROOT_KEYS)
    if unknown:
        rendered = ", ".join(f"`{key}`" for key in unknown)
        raise ConfigError(f"{config_path}: unknown key(s): {rendered}")


def _document_path(config_path: Path, raw_path: str) -> str:
    location = f"{config_path}: document `{raw_path}`"
    normalized = normalize_path(raw_path)
    if error := relative_path_error(location, raw_path, normalized):
        raise ConfigError(error)
    if raw_path.endswith("/") or has_glob(raw_path):
        raise ConfigError(f"{location} must be an exact file path")
    return normalized


def _sources(config_path: Path, document: str, raw_sources: object) -> tuple[str, ...]:
    location = f"{config_path}: document `{document}`"
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ConfigError(f"{location} must have a non-empty array of sources")

    sources: list[str] = []
    for index, raw_source in enumerate(raw_sources, start=1):
        source_location = f"{location} source #{index}"
        if not isinstance(raw_source, str) or not raw_source:
            raise ConfigError(f"{source_location} must be a non-empty string")
        normalized = normalize_path(
            raw_source, keep_trailing_slash=raw_source.endswith("/")
        )
        if error := relative_path_error(source_location, raw_source, normalized):
            raise ConfigError(error)
        sources.append(normalized)

    duplicates = sorted(
        source for source, count in Counter(sources).items() if count > 1
    )
    if duplicates:
        rendered = ", ".join(f"`{source}`" for source in duplicates)
        raise ConfigError(f"{location} contains duplicate source(s): {rendered}")
    return tuple(sources)


def load_config(config_path: Path) -> Config:
    """Load and validate a doc-sync TOML file."""
    if not config_path.is_file():
        raise MissingConfigError(f"{config_path}: configuration file does not exist")
    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path}: TOML parse error: {exc}") from exc

    _unknown_keys(config_path, raw_config)
    raw_documents_value = raw_config.get("documents")
    if not isinstance(raw_documents_value, dict) or not raw_documents_value:
        raise ConfigError(f"{config_path}: expected a non-empty `[documents]` table")
    raw_documents = cast("dict[str, object]", raw_documents_value)

    documents: list[Document] = []
    seen_paths: set[str] = set()
    for raw_path, raw_sources in raw_documents.items():
        path = _document_path(config_path, raw_path)
        if path in seen_paths:
            raise ConfigError(f"{config_path}: duplicate document path `{path}`")
        seen_paths.add(path)
        documents.append(
            Document(
                path=path,
                sources=_sources(config_path, path, raw_sources),
            )
        )
    return Config(tuple(sorted(documents, key=lambda document: document.path)))


def validate_repository_config(*, root: Path, config_path: Path) -> Config:
    """Validate configuration and require every document to exist."""
    config = load_config(config_path)
    missing = [
        document.path
        for document in config.documents
        if not (root / document.path).is_file()
    ]
    if missing:
        detail = "\n".join(f"  - `{path}` does not exist" for path in missing)
        raise ConfigError(f"{config_path}: invalid documents:\n{detail}")
    return config
