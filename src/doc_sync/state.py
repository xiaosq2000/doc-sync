"""Private session baselines, acknowledgements, and hook disable state."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import PurePath
from typing import TYPE_CHECKING, Any

from doc_sync.fsutil import atomic_write
from doc_sync.git import git_metadata_path, worktree_paths
from doc_sync.paths import SourcePattern, normalize_path

if TYPE_CHECKING:
    from pathlib import Path

    from doc_sync.config import Document
    from doc_sync.match import Review

STATE_VERSION = 1
BASELINE_VERSION = 1
_FINGERPRINT = re.compile(r"(?:file:[01]:[0-9a-f]{64}|symlink:[\s\S]*|missing|other)")
DISABLED_MARKER = "disabled"
_DISABLED_NOTE = (
    "doc-sync is disabled for this checkout.\n"
    "Run `doc-sync enable` to enable its Stop hook.\n"
)


def default_state_directory(root: Path) -> Path:
    """Return the worktree-specific Git metadata directory for hook state."""
    return git_metadata_path(root, "doc-sync")


def is_disabled(state_directory: Path) -> bool:
    """Return whether the Stop hook is disabled for this checkout."""
    return (state_directory / DISABLED_MARKER).exists()


def set_disabled(state_directory: Path, *, disabled: bool) -> bool:
    """Set the Stop hook state and report whether it changed."""
    marker = state_directory / DISABLED_MARKER
    if disabled == marker.exists():
        return False
    if disabled:
        atomic_write(marker, _DISABLED_NOTE)
    else:
        marker.unlink(missing_ok=True)
    return True


def _session_path(
    state_directory: Path, session_id: str, *, category: str = "sessions"
) -> Path:
    digest = hashlib.sha256(session_id.encode()).hexdigest()
    return state_directory / category / f"{digest}.json"


def _content_marker(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            return f"symlink:{path.readlink()}"
        if not stat.S_ISREG(mode):
            return "other"
        with path.open("rb") as source_file:
            digest = hashlib.file_digest(source_file, "sha256")
        executable = int(bool(mode & stat.S_IXUSR))
        return f"file:{executable}:{digest.hexdigest()}"
    except (FileNotFoundError, NotADirectoryError):
        return "missing"


def _state_key(*, root: Path, config_path: Path, reviews: tuple[Review, ...]) -> str:
    relevant_paths = sorted(
        {path for review in reviews for path in (review.document, *review.sources)}
    )
    payload = {
        "config": _content_marker(config_path),
        "reviews": [review.to_dict() for review in reviews],
        "paths": [
            {"path": path, "content": _content_marker(root / path)}
            for path in relevant_paths
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_state(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def _valid_baseline_path(path: str) -> bool:
    # Baselines are private data, but reject corrupt paths before reading files.
    relative = PurePath(path)
    return bool(relative.parts) and not (
        relative.anchor
        or "\0" in path
        or any(part in {"..", ".git"} for part in relative.parts)
    )


class BaselineStore:
    """Save the initial file state independently of reminder acknowledgements."""

    def __init__(self, state_directory: Path) -> None:
        """Create a store in worktree-specific Git metadata."""
        self.state_directory = state_directory

    def _path(self, session_id: str) -> Path:
        return _session_path(self.state_directory, session_id, category="baselines")

    def load(self, session_id: str) -> dict[str, str] | None:
        """Load a supported baseline, or return None for missing or corrupt data."""
        value = _read_state(self._path(session_id))
        if (
            not value
            or type(value.get("version")) is not int
            or value["version"] != BASELINE_VERSION
        ):
            return None
        paths = value.get("paths")
        if not isinstance(paths, dict):
            return None
        fingerprints: dict[str, str] = {}
        for path, marker in paths.items():
            if (
                not isinstance(path, str)
                or not _valid_baseline_path(path)
                or not isinstance(marker, str)
                or _FINGERPRINT.fullmatch(marker) is None
            ):
                return None
            fingerprints[path] = marker
        return fingerprints

    def capture(self, *, session_id: str, root: Path) -> None:
        """Atomically save fingerprints without storing any file contents."""
        paths = {path: _content_marker(root / path) for path in worktree_paths(root)}
        content = json.dumps(
            {"version": BASELINE_VERSION, "paths": paths}, sort_keys=True
        )
        atomic_write(self._path(session_id), content + "\n")


def session_changed_paths(
    *, root: Path, baseline: dict[str, str], documents: tuple[Document, ...]
) -> tuple[str, ...]:
    """Compare relevant file contents with their state at session start."""
    targets = {document.path for document in documents}
    patterns = tuple(
        SourcePattern(source) for document in documents for source in document.sources
    )
    candidates = baseline.keys() | set(worktree_paths(root))
    changed: list[str] = []
    for path in sorted(candidates):
        normalized = normalize_path(path)
        if normalized not in targets and not any(
            pattern.matches(normalized) for pattern in patterns
        ):
            continue
        if _content_marker(root / path) != baseline.get(path, "missing"):
            changed.append(path)
    return tuple(changed)


class AcknowledgementStore:
    """Remember the last review state shown in each agent session."""

    def __init__(self, state_directory: Path) -> None:
        """Create a store in a worktree-specific state directory."""
        self.state_directory = state_directory

    def should_prompt(
        self,
        *,
        session_id: str,
        root: Path,
        config_path: Path,
        reviews: tuple[Review, ...],
    ) -> bool:
        """Return true once for each distinct relevant content state."""
        path = _session_path(self.state_directory, session_id)
        key = _state_key(root=root, config_path=config_path, reviews=reviews)
        previous = _read_state(path)
        if (
            previous
            and previous.get("version") == STATE_VERSION
            and previous.get("state_key") == key
        ):
            return False
        content = json.dumps(
            {"version": STATE_VERSION, "state_key": key}, indent=2, sort_keys=True
        )
        atomic_write(path, content + "\n")
        return True

    def clear(self, session_id: str) -> None:
        """Clear acknowledgement state for one session."""
        _session_path(self.state_directory, session_id).unlink(missing_ok=True)
