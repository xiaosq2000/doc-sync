from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

from doc_sync.cli import main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

BROKEN_CONFIG = "[documents\n"


def _hook_payload(
    root: Path,
    *,
    session_id: str = "session-1",
    active: bool = False,
    event: str = "Stop",
) -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "cwd": str(root),
            "stop_hook_active": active,
            "hook_event_name": event,
        }
    )


def _start_session(
    root: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(_hook_payload(root, event="SessionStart"))
    )
    assert main(["hook"]) == 0
    assert capsys.readouterr().out == ""


def test_json_check_has_a_small_stable_contract(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    monkeypatch.chdir(repository)

    exit_code = main(["check", "--json"])

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "review_required",
        "documents": [{"path": "README.md", "sources": ["src/app.py"]}],
    }


def test_check_always_confirms_a_pass(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repository)

    exit_code = main(["check"])

    assert exit_code == 0
    assert "no documents need review" in capsys.readouterr().out


def test_hook_blocks_once_for_the_same_session_state(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _start_session(repository, capsys, monkeypatch)
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    payload = _hook_payload(repository)

    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    first_exit = main(["hook"])
    first_output = capsys.readouterr().out

    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    second_exit = main(["hook"])
    second_output = capsys.readouterr().out

    assert first_exit == 0
    assert json.loads(first_output)["decision"] == "block"
    assert "README.md" in json.loads(first_output)["reason"]
    assert second_exit == 0
    assert second_output == ""


def test_active_stop_hook_never_blocks_again(
    empty_repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (empty_repository / "doc-sync.toml").write_text(BROKEN_CONFIG, encoding="utf-8")
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(_hook_payload(empty_repository, active=True))
    )

    exit_code = main(["hook"])

    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_hook_resolves_a_repository_from_a_nested_payload_cwd(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _start_session(repository, capsys, monkeypatch)
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO(_hook_payload(repository / "src")))

    exit_code = main(["hook"])

    assert exit_code == 0
    assert "README.md" in json.loads(capsys.readouterr().out)["reason"]


def test_hook_is_silent_without_a_configuration(
    empty_repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(_hook_payload(empty_repository)))

    exit_code = main(["hook"])

    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_hook_reports_a_broken_configuration_as_blocking_json(
    empty_repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (empty_repository / "doc-sync.toml").write_text(BROKEN_CONFIG, encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO(_hook_payload(empty_repository)))

    exit_code = main(["hook"])

    response = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert response["decision"] == "block"
    assert "TOML parse error" in response["reason"]


def test_disabling_affects_the_hook_but_not_manual_checks(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    monkeypatch.chdir(repository)

    assert main(["disable"]) == 0
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO(_hook_payload(repository)))
    assert main(["hook"]) == 0
    assert capsys.readouterr().out == ""

    assert main(["check"]) == 2
    assert "README.md" in capsys.readouterr().out


def test_validate_checks_document_targets(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repository)

    exit_code = main(["validate"])

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("valid ")


def test_manual_error_uses_stderr_and_exit_one(
    empty_repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(empty_repository)

    exit_code = main(["check"])

    assert exit_code == 1
    assert "doc-sync error:" in capsys.readouterr().err
