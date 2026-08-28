"""Private acknowledgement and disable state for the Stop hook."""

from __future__ import annotations

import hashlib
import json
import stat
from typing import TYPE_CHECKING, Any

from doc_sync.fsutil import atomic_write
from doc_sync.git import git_metadata_path

if TYPE_CHECKING:
    from pathlib import Path

    from doc_sync.match import Review

STATE_VERSION = 1
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


def _session_path(state_directory: Path, session_id: str) -> Path:
    digest = hashlib.sha256(session_id.encode()).hexdigest()
    return state_directory / "sessions" / f"{digest}.json"


def _content_marker(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            return f"symlink:{path.readlink()}"
        if not stat.S_ISREG(mode):
            return "other"
        with path.open("rb") as source_file:
            digest = hashlib.file_digest(source_file, "sha256")
        return f"file:{digest.hexdigest()}"
    except FileNotFoundError:
        return "missing"
    except OSError as exc:
        return f"error:{exc.__class__.__name__}"


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
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


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
