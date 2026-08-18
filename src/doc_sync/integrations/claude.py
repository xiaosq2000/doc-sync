"""Claude Code Stop-hook protocol adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from doc_sync.errors import DocSyncError


class ClaudeInputError(DocSyncError, ValueError):
    """Raised when Claude Code supplies malformed hook input."""


@dataclass(frozen=True)
class ClaudeContext:
    """Fields needed from a Claude Code Stop-hook payload."""

    session_id: str
    cwd: Path


def parse_context(raw_input: str) -> ClaudeContext:
    """Parse the common fields supplied to a Claude Code command hook."""
    try:
        payload = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        raise ClaudeInputError(f"invalid Claude hook JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClaudeInputError("Claude hook input must be a JSON object")

    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    if not isinstance(session_id, str) or not session_id:
        raise ClaudeInputError("Claude hook input is missing `session_id`")
    if not isinstance(cwd, str) or not cwd:
        raise ClaudeInputError("Claude hook input is missing `cwd`")
    return ClaudeContext(session_id=session_id, cwd=Path(cwd))


def blocking_output(reason: str) -> dict[str, Any]:
    """Return Claude's structured Stop-hook blocking response."""
    return {"decision": "block", "reason": reason}
