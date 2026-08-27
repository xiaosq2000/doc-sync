"""Repository-relative path normalization and matching."""

from __future__ import annotations

from pathlib import PureWindowsPath

from pathspec.patterns.gitignore.basic import GitIgnoreBasicPattern


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


class SourcePattern:
    """A configured source pattern compiled once for repeated matching."""

    __slots__ = ("_pattern",)

    def __init__(self, pattern: str) -> None:
        """Compile one repository-relative source pattern."""
        is_directory = pattern.endswith("/")
        normalized = normalize_path(pattern, keep_trailing_slash=is_directory)
        self._pattern: GitIgnoreBasicPattern | None = None
        if not normalized:
            return
        # Every pattern is anchored to the repository root, which is what the
        # leading `/` means to gitignore. Matching at any depth is opt-in
        # through an explicit `**/` prefix, so `app.py` names the root file
        # while `**/app.py` names that file anywhere. Anchoring also makes a
        # leading `!` or `#` an ordinary character rather than gitignore
        # negation or a comment, neither of which doc-sync supports.
        compiled = GitIgnoreBasicPattern(f"/{normalized}")
        if compiled.include:
            self._pattern = compiled

    def matches(self, normalized_path: str) -> bool:
        """Return whether an already-normalized path matches this pattern."""
        if not normalized_path or self._pattern is None:
            return False
        return self._pattern.match_file(normalized_path) is not None


def match_path(pattern: str, path: str) -> bool:
    """Return whether a repository-relative path matches a source pattern."""
    return SourcePattern(pattern).matches(normalize_path(path))
