"""TOML configuration loading and repository-aware validation."""

from __future__ import annotations

import re
import tomllib
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from doc_sync.errors import DocSyncError
from doc_sync.git import GitError, repository_file_paths
from doc_sync.model import Rule
from doc_sync.paths import (
    SourcePattern,
    has_glob,
    normalize_path,
    relative_path_error,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

CONFIG_FILENAME = "doc-sync.toml"
CONFIG_VERSION = 1
_ROOT_KEYS = {"config_version", "rules"}
_RULE_KEYS = {"id", "sources", "documents"}
_RULE_ID = re.compile(r"^[a-z][a-z0-9-]*$")
_LEGACY_ROOT_KEYS = {"version", "watch"}


class ConfigError(DocSyncError, ValueError):
    """Raised when the doc-sync configuration is invalid."""


@dataclass(frozen=True)
class Config:
    """Validated doc-sync configuration."""

    config_version: int
    rules: tuple[Rule, ...]


def _unknown_keys(location: str, value: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        rendered = ", ".join(f"`{key}`" for key in unknown)
        raise ConfigError(f"{location}: unknown key(s): {rendered}")


def _string_list(
    config_path: Path,
    rule_index: int,
    raw_rule: dict[str, Any],
    key: str,
) -> tuple[str, ...]:
    value = raw_rule.get(key)
    location = f"{config_path}: `[[rules]]` #{rule_index} `{key}`"
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{location} must be a non-empty array")

    normalized_paths: list[str] = []
    for item_index, item in enumerate(value, start=1):
        item_location = f"{location} item #{item_index}"
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"{item_location} must be a non-empty string")
        normalized = normalize_path(item, keep_trailing_slash=item.endswith("/"))
        if error := relative_path_error(item_location, item, normalized):
            raise ConfigError(error)
        normalized_paths.append(normalized)

    duplicates = sorted(
        path for path, count in Counter(normalized_paths).items() if count > 1
    )
    if duplicates:
        rendered = ", ".join(f"`{path}`" for path in duplicates)
        raise ConfigError(f"{location} contains duplicate path(s): {rendered}")
    return tuple(normalized_paths)


def _parse_rule(config_path: Path, index: int, raw_rule_value: object) -> Rule:
    location = f"{config_path}: `[[rules]]` #{index}"
    if not isinstance(raw_rule_value, dict):
        raise ConfigError(f"{location} must be a table")
    raw_rule = cast("dict[str, Any]", raw_rule_value)
    _unknown_keys(location, raw_rule, _RULE_KEYS)

    rule_id = raw_rule.get("id")
    if not isinstance(rule_id, str) or not _RULE_ID.fullmatch(rule_id):
        raise ConfigError(f"{location} `id` must match `{_RULE_ID.pattern}`")

    sources = _string_list(config_path, index, raw_rule, "sources")
    documents = _string_list(config_path, index, raw_rule, "documents")
    for document in documents:
        if document.endswith("/") or has_glob(document):
            raise ConfigError(
                f"{location} `documents` entry `{document}` must be an exact "
                "documentation file path"
            )
    return Rule(id=rule_id, sources=sources, documents=documents)


def load_config(config_path: Path) -> Config:
    """Load and fully validate a doc-sync TOML configuration."""
    if not config_path.is_file():
        raise ConfigError(f"{config_path}: configuration file does not exist")
    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path}: TOML parse error: {exc}") from exc

    version = raw_config.get("config_version")
    if version is None and _LEGACY_ROOT_KEYS & set(raw_config):
        raise ConfigError(
            f"{config_path}: this is a pre-{CONFIG_VERSION} `version`/`[[watch]]` "
            f"configuration; rewrite it as `config_version = {CONFIG_VERSION}` with "
            "`[[rules]]` blocks of `sources` and `documents`"
        )
    if isinstance(version, bool) or version != CONFIG_VERSION:
        raise ConfigError(
            f"{config_path}: expected `config_version = {CONFIG_VERSION}`"
        )
    _unknown_keys(str(config_path), raw_config, _ROOT_KEYS)

    raw_rules = raw_config.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ConfigError(f"{config_path}: expected at least one `[[rules]]` block")

    rules: list[Rule] = []
    seen_ids: set[str] = set()
    for index, raw_rule_value in enumerate(raw_rules, start=1):
        rule = _parse_rule(config_path, index, raw_rule_value)
        if rule.id in seen_ids:
            raise ConfigError(
                f"{config_path}: `[[rules]]` #{index} duplicates rule id `{rule.id}`"
            )
        seen_ids.add(rule.id)
        rules.append(rule)

    return Config(config_version=CONFIG_VERSION, rules=tuple(rules))


def _document_error(root: Path, location: str, value: str) -> str | None:
    if not (root / value).is_file():
        return f"{location} does not point to an existing file"
    return None


def _source_error(
    root: Path,
    tracked_paths: Callable[[], tuple[str, ...]],
    location: str,
    value: str,
) -> str | None:
    if value.endswith("/"):
        if has_glob(value.rstrip("/")):
            return f"{location} must not combine glob syntax with trailing `/`"
        if not (root / value.rstrip("/")).is_dir():
            return f"{location} does not point to an existing directory"
    elif has_glob(value):
        pattern = SourcePattern(value)
        if not any(pattern.matches(normalize_path(path)) for path in tracked_paths()):
            return f"{location} does not match any tracked or untracked file"
    elif not (root / value).is_file():
        return f"{location} does not point to an existing file"
    return None


def validate_repository_config(*, root: Path, config_path: Path) -> Config:
    """Validate configuration structure and paths against a Git checkout."""
    config = load_config(config_path)
    listed: tuple[str, ...] | None = None

    def tracked_paths() -> tuple[str, ...]:
        """List the repository once, and only if a glob source needs it."""
        nonlocal listed
        if listed is None:
            try:
                listed = repository_file_paths(root)
            except GitError as exc:
                raise ConfigError(str(exc)) from exc
        return listed

    errors: list[str] = []
    for rule in config.rules:
        for source in rule.sources:
            location = f"rule `{rule.id}` source `{source}`"
            if error := _source_error(root, tracked_paths, location, source):
                errors.append(error)
        for document in rule.documents:
            location = f"rule `{rule.id}` document `{document}`"
            if error := _document_error(root, location, document):
                errors.append(error)

    if errors:
        detail = "\n".join(f"  - {error}" for error in errors)
        raise ConfigError(f"{config_path}: invalid configured paths:\n{detail}")
    return config
