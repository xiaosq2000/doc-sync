from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

from doc_sync.cli import main

if TYPE_CHECKING:
    from pathlib import Path

BROKEN_CONFIG = """config_version = 1
[[rules
"""


def _stop_hook_payload(root: Path, session_id: str = "session-1") -> str:
    return json.dumps({"session_id": session_id, "cwd": str(root)})


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


# A repository holding no `doc-sync.toml` never opted in, so its hooks must add
# nothing at all to the agent's context.
@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_stop_adapters_stay_silent_without_a_configuration(
    empty_repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(_stop_hook_payload(empty_repository)))

    exit_code = main(["hook", agent, "--root", str(empty_repository)])

    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_opencode_adapter_stays_silent_without_a_configuration(
    empty_repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        ["hook", "opencode", "--root", str(empty_repository), "--session-id", "one"]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""


# A broken configuration is a real mistake, so it keeps blocking loudly.
def test_stop_hook_config_error_is_structured_blocking_json(
    empty_repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (empty_repository / "doc-sync.toml").write_text(BROKEN_CONFIG, encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO(_stop_hook_payload(empty_repository)))

    exit_code = main(["hook", "claude", "--root", str(empty_repository)])

    response = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert response["decision"] == "block"
    assert "TOML parse error" in response["reason"]


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_disabling_silences_the_stop_adapters(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
) -> None:
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    state = ["--root", str(repository), "--state-directory", str(repository / "state")]
    hook = ["hook", agent, *state]
    main(["disable", *state])
    capsys.readouterr()

    monkeypatch.setattr("sys.stdin", io.StringIO(_stop_hook_payload(repository)))
    disabled_exit = main(hook)
    disabled_output = capsys.readouterr().out

    main(["enable", *state])
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO(_stop_hook_payload(repository)))
    enabled_exit = main(hook)
    enabled_output = capsys.readouterr().out

    assert disabled_exit == 0
    assert disabled_output == ""
    assert enabled_exit == 0
    assert json.loads(enabled_output)["decision"] == "block"


def test_disabling_silences_the_opencode_adapter(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    state = ["--root", str(repository), "--state-directory", str(repository / "state")]
    main(["disable", *state])
    capsys.readouterr()

    exit_code = main(["hook", "opencode", *state, "--session-id", "one"])

    assert exit_code == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("arguments", "expected_output"),
    [([], ""), (["--format", "json"], '{"impacts": [], "review_targets": [], ')],
    ids=["human", "json"],
)
def test_disabling_passes_check_without_a_review(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    expected_output: str,
) -> None:
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    state = ["--root", str(repository), "--state-directory", str(repository / "state")]
    main(["disable", *state])
    capsys.readouterr()

    exit_code = main(["check", *state, *arguments])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert output.startswith(expected_output)
    if arguments:
        assert json.loads(output)["status"] == "disabled"


# `review` is the escape hatch from the switch, so it has to answer in the one
# situation `check` stays quiet. Neither command is given `--state-directory`, so
# both read the default: the contrast is the marker itself, not two separate
# states, and the silent `check` keeps the `review` assertions from passing
# vacuously against a marker written somewhere it never looks.
@pytest.mark.parametrize("arguments", [[], ["--format", "json"]], ids=["human", "json"])
def test_review_reports_documents_while_disabled(
    repository: Path, capsys: pytest.CaptureFixture[str], arguments: list[str]
) -> None:
    (repository / "src/app.py").write_text("v2", encoding="utf-8")
    root = ["--root", str(repository)]
    main(["disable", *root])
    capsys.readouterr()

    check_exit = main(["check", *root])
    check_output = capsys.readouterr().out

    review_exit = main(["review", *root, *arguments])
    review_output = capsys.readouterr().out

    assert check_exit == 0
    assert check_output == ""
    assert review_exit == 2
    assert "README.md" in review_output
    if arguments:
        # Never `"status": "disabled"` — the switch does not reach a hand-run check.
        assert json.loads(review_output)["status"] == "review_required"
    else:
        assert "Documentation may need review" in review_output


# A command the user ran by hand has to say something, or silence reads as a
# command that never ran. `check` stays silent, because nothing asked it to speak.
def test_review_confirms_when_nothing_needs_review(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = ["--root", str(repository)]

    review_exit = main(["review", *root])
    review_output = capsys.readouterr().out

    check_exit = main(["check", *root])
    check_output = capsys.readouterr().out

    assert review_exit == 0
    assert "no documents need review" in review_output
    assert check_exit == 0
    assert check_output == ""


def test_toggle_reports_the_state_and_whether_it_changed(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state = ["--root", str(repository), "--state-directory", str(repository / "state")]

    assert main(["status", *state]) == 0
    assert "is enabled" in capsys.readouterr().out

    assert main(["disable", *state]) == 0
    assert "doc-sync disabled for" in capsys.readouterr().out

    assert main(["disable", *state]) == 0
    assert "is already disabled" in capsys.readouterr().out

    assert main(["status", *state]) == 0
    assert "is disabled" in capsys.readouterr().out


# Only the agent adapters go quiet for a missing configuration; an explicit
# `check` still reports the problem.
def test_operational_error_uses_stderr_and_exit_one(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["check", "--root", str(root)])

    assert exit_code == 1
    assert "doc-sync error:" in capsys.readouterr().err
