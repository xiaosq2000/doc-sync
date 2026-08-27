"""Per-session acknowledgement state for agent hooks."""

from __future__ import annotations

import hashlib
import json
import stat
from typing import TYPE_CHECKING, Any

from doc_sync.fsutil import atomic_write
from doc_sync.git import git_metadata_path

if TYPE_CHECKING:
    from pathlib import Path

    from doc_sync.model import Evaluation

STATE_VERSION = 1
DISABLED_MARKER = "disabled"
_DISABLED_NOTE = (
    "doc-sync is switched off for this checkout.\n"
    "Remove this file, or run `doc-sync enable`, to switch it back on.\n"
)


def default_state_directory(root: Path) -> Path:
    """Return the worktree-aware Git metadata directory for state."""
    return git_metadata_path(root, "doc-sync")


def is_disabled(state_directory: Path) -> bool:
    """Report whether doc-sync is switched off for this checkout."""
    return (state_directory / DISABLED_MARKER).exists()


def set_disabled(state_directory: Path, *, disabled: bool) -> bool:
    """Switch doc-sync off or on, returning true when the state changed."""
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


def state_key(*, root: Path, config_path: Path, evaluation: Evaluation) -> str:
    """Fingerprint only the configuration and paths relevant to an evaluation."""
    relevant_paths = sorted(
        {
            path
            for impact in evaluation.impacts
            for path in (*impact.matched_sources, *impact.review_targets)
        }
    )
    payload = {
        "config": _content_marker(config_path),
        "evaluation": evaluation.to_dict(),
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


def _write_state(path: Path, key: str) -> None:
    payload = json.dumps(
        {"version": STATE_VERSION, "state_key": key}, indent=2, sort_keys=True
    )
    atomic_write(path, payload + "\n")


class AcknowledgementStore:
    """Persist prompt acknowledgement independently for each agent session."""

    def __init__(self, state_directory: Path) -> None:
        """Create a store rooted at a worktree-specific state directory."""
        self.state_directory = state_directory

    def should_prompt(
        self,
        *,
        session_id: str,
        root: Path,
        config_path: Path,
        evaluation: Evaluation,
    ) -> bool:
        """Return true once for each distinct session evaluation state."""
        path = _session_path(self.state_directory, session_id)
        key = state_key(root=root, config_path=config_path, evaluation=evaluation)
        previous = _read_state(path)
        if (
            previous
            and previous.get("version") == STATE_VERSION
            and previous.get("state_key") == key
        ):
            return False
        _write_state(path, key)
        return True

    def clear(self, session_id: str) -> None:
        """Clear acknowledgement state for one session."""
        _session_path(self.state_directory, session_id).unlink(missing_ok=True)
