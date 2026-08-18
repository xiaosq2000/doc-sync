"""Repository-relative path normalization and matching."""

from __future__ import annotations

import re
from fnmatch import translate
from pathlib import PureWindowsPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def normalize_path(path: str, *, keep_trailing_slash: bool = False) -> str:
    """Normalize a repository-relative path to slash-separated form."""
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if keep_trailing_slash:
        return normalized
    return normalized.rstrip("/")


def has_glob(pattern: str) -> bool:
    """Return whether a pattern contains supported glob syntax."""
    return any(character in pattern for character in "*?[")


def relative_path_error(location: str, raw_path: str, normalized: str) -> str | None:
    """Return why a configured path is not repository-relative, or None if it is."""
    if (
        raw_path.startswith("/")
        or normalized.startswith("/")
        or PureWindowsPath(raw_path).is_absolute()
    ):
        return f"{location} must be repository-relative"

    without_slash = normalized.rstrip("/")
    if not without_slash:
        return f"{location} must not normalize to an empty path"
    if any(segment in {".", ".."} for segment in without_slash.split("/")):
        return f"{location} must not contain `.` or `..` segments"
    return None


def _match_segments(
    pattern_segments: Sequence[re.Pattern[str] | None], path_segments: Sequence[str]
) -> bool:
    memo: dict[tuple[int, int], bool] = {}

    def match(pattern_index: int, path_index: int) -> bool:
        key = (pattern_index, path_index)
        if key in memo:
            return memo[key]
        segment = (
            pattern_segments[pattern_index]
            if pattern_index < len(pattern_segments)
            else None
        )
        if pattern_index == len(pattern_segments):
            result = path_index == len(path_segments)
        elif segment is None:
            result = any(
                match(pattern_index + 1, next_path_index)
                for next_path_index in range(path_index, len(path_segments) + 1)
            )
        elif path_index >= len(path_segments):
            result = False
        else:
            result = segment.match(path_segments[path_index]) is not None and match(
                pattern_index + 1, path_index + 1
            )
        memo[key] = result
        return result

    return match(0, 0)


class SourcePattern:
    """A configured source pattern compiled once for repeated matching."""

    __slots__ = ("_directory", "_literal", "_segments")

    def __init__(self, pattern: str) -> None:
        """Compile one repository-relative source pattern."""
        is_directory = pattern.endswith("/")
        normalized = normalize_path(pattern, keep_trailing_slash=is_directory)
        self._directory: str | None = None
        self._literal: str | None = None
        self._segments: tuple[re.Pattern[str] | None, ...] | None = None
        if not normalized:
            return
        if is_directory:
            self._directory = normalized.rstrip("/")
        elif has_glob(normalized):
            self._segments = tuple(
                None if segment == "**" else re.compile(translate(segment))
                for segment in normalized.split("/")
            )
        else:
            self._literal = normalized

    def matches(self, normalized_path: str) -> bool:
        """Return whether an already-normalized path matches this pattern."""
        if not normalized_path:
            return False
        if self._directory is not None:
            return normalized_path == self._directory or normalized_path.startswith(
                f"{self._directory}/"
            )
        if self._literal is not None:
            return normalized_path == self._literal
        if self._segments is None:
            return False
        return _match_segments(self._segments, normalized_path.split("/"))


def match_path(pattern: str, path: str) -> bool:
    """Return whether a repository-relative path matches a source pattern."""
    return SourcePattern(pattern).matches(normalize_path(path))
