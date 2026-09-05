"""The session hook protocol shared by Claude Code and Codex."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from doc_sync.errors import DocSyncError


class HookInputError(DocSyncError, ValueError):
    """Raised when an agent supplies malformed hook input."""


@dataclass(frozen=True)
class HookContext:
    """Fields needed from a SessionStart or Stop hook payload."""

    session_id: str
    cwd: Path
    stop_hook_active: bool
    hook_event_name: str


def parse_context(raw_input: str) -> HookContext:
    """Parse shared fields and validate event-specific input."""
    try:
        payload = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        raise HookInputError(f"invalid hook JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HookInputError("hook input must be a JSON object")

    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    event = payload.get("hook_event_name", "Stop")
    if event not in ("SessionStart", "Stop"):
        raise HookInputError("hook input has an unsupported `hook_event_name`")
    stop_hook_active = payload.get("stop_hook_active") if event == "Stop" else False
    if not isinstance(session_id, str) or not session_id:
        raise HookInputError("hook input is missing `session_id`")
    if not isinstance(cwd, str) or not cwd:
        raise HookInputError("hook input is missing `cwd`")
    if not isinstance(stop_hook_active, bool):
        raise HookInputError("hook input is missing `stop_hook_active`")
    return HookContext(
        session_id=session_id,
        cwd=Path(cwd),
        stop_hook_active=stop_hook_active,
        hook_event_name=event,
    )


def blocking_output(reason: str) -> dict[str, Any]:
    """Return the response that asks the agent to continue."""
    return {"decision": "block", "reason": reason}
