from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

from doc_sync.cli import main

if TYPE_CHECKING:
    from pathlib import Path


def test_json_check_uses_stable_status_and_exit_code(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / "src/app.py").write_text("v2", encoding="utf-8")

    exit_code = main(["check", "--root", str(repository), "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "review_required"
    assert payload["review_targets"] == ["README.md"]


# Codex CLI implements Claude Code's Stop-hook wire format, so one contract
# covers both adapters.
@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_stop_adapters_block_with_json_on_exit_zero_once(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
) -> None:
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    payload = json.dumps({"session_id": "session-1", "cwd": str(repository)})
    arguments = [
        "hook",
        agent,
        "--root",
        str(repository),
        "--state-directory",
        str(repository / "state"),
    ]

    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    first_exit = main(arguments)
    first_output = capsys.readouterr().out

    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    second_exit = main(arguments)
    second_output = capsys.readouterr().out

    response = json.loads(first_output)
    assert first_exit == 0
    assert response["decision"] == "block"
    assert "Documentation may need review" in response["reason"]
    assert second_exit == 0
    assert second_output == ""


def test_codex_adapter_resolves_the_repository_from_the_payload_cwd(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Codex exposes no project-directory variable, so a session started in a
    # subdirectory has to reach the repository through `cwd` alone.
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    payload = json.dumps({"session_id": "session-1", "cwd": str(repository / "src")})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    exit_code = main(["hook", "codex", "--state-directory", str(repository / "state")])

    response = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert response["decision"] == "block"
    assert "README.md" in response["reason"]


def test_stop_hook_config_error_is_structured_blocking_json(
    empty_repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"session_id": "session-1", "cwd": str(empty_repository)})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    exit_code = main(["hook", "claude", "--root", str(empty_repository)])

    response = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert response["decision"] == "block"
    assert "configuration file does not exist" in response["reason"]


def test_operational_error_uses_stderr_and_exit_one(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["check", "--root", str(root)])

    assert exit_code == 1
    assert "doc-sync error:" in capsys.readouterr().err
