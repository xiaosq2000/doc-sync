"""Stop-hook protocol shared by the Claude Code and Codex CLI adapters.

Codex CLI implements Claude Code's Stop-hook wire format: the same
`session_id`/`cwd` payload on stdin, and the same `decision = "block"`
response at exit code `0`. Only the agent named in diagnostics differs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from doc_sync.errors import DocSyncError


class StopHookInputError(DocSyncError, ValueError):
    """Raised when an agent supplies malformed Stop-hook input."""


@dataclass(frozen=True)
class StopHookContext:
    """Fields needed from an agent's Stop-hook payload."""

    session_id: str
    cwd: Path


def parse_context(raw_input: str, *, agent: str) -> StopHookContext:
    """Parse the common fields supplied to an agent's Stop-hook command."""
    try:
        payload = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        raise StopHookInputError(f"invalid {agent} hook JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise StopHookInputError(f"{agent} hook input must be a JSON object")

    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    if not isinstance(session_id, str) or not session_id:
        raise StopHookInputError(f"{agent} hook input is missing `session_id`")
    if not isinstance(cwd, str) or not cwd:
        raise StopHookInputError(f"{agent} hook input is missing `cwd`")
    return StopHookContext(session_id=session_id, cwd=Path(cwd))


def blocking_output(reason: str) -> dict[str, Any]:
    """Return the structured blocking response both agents accept."""
    return {"decision": "block", "reason": reason}
