from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from doc_sync import state
from doc_sync.cli import main
from doc_sync.git import GitError
from doc_sync.state import BaselineStore, default_state_directory
from tests.support import commit_all, git, write_config

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class HookRunner:
    root: Path
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]

    def __call__(self, event: str = "Stop", session: str = "one") -> str:
        payload: dict[str, object] = {
            "hook_event_name": event,
            "session_id": session,
            "cwd": str(self.root),
        }
        if event == "Stop":
            payload["stop_hook_active"] = False
        self.monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert main(["hook"]) == 0
        captured = self.capsys.readouterr()
        assert captured.err == ""
        return captured.out


@pytest.fixture
def hook(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> HookRunner:
    return HookRunner(repository, monkeypatch, capsys)


@pytest.mark.parametrize("staged", [False, True])
def test_existing_edits_do_not_prompt(hook: HookRunner, staged: bool) -> None:
    source = hook.root / "src/app.py"
    source.write_text("before the session", encoding="utf-8")
    (hook.root / "src/untracked.py").write_text("existing", encoding="utf-8")
    if staged:
        git(hook.root, "add", "src/app.py")
    assert hook("SessionStart") == ""
    assert source.read_text(encoding="utf-8") == "before the session"
    source.touch()
    assert hook() == ""

    source.write_text("session edit", encoding="utf-8")
    response = json.loads(hook())
    assert response["decision"] == "block"
    assert "src/app.py" in response["reason"]
    assert "src/untracked.py" not in response["reason"]
    assert hook() == ""


def test_missing_baseline_initializes_silently(hook: HookRunner) -> None:
    source = hook.root / "src/app.py"
    source.write_text("existing", encoding="utf-8")
    assert hook() == ""
    assert hook() == ""
    source.write_text("later edit", encoding="utf-8")
    assert json.loads(hook())["decision"] == "block"


def test_unrelated_edits_are_silent(hook: HookRunner) -> None:
    assert hook("SessionStart") == ""
    (hook.root / "notes.txt").write_text("notes", encoding="utf-8")
    assert hook() == ""


@pytest.mark.parametrize("document_before_session", [False, True])
def test_document_edits_use_the_session_baseline(
    hook: HookRunner, document_before_session: bool
) -> None:
    document = hook.root / "README.md"
    if document_before_session:
        document.write_text("old document edit", encoding="utf-8")
    assert hook("SessionStart") == ""
    (hook.root / "src/app.py").write_text("new source", encoding="utf-8")
    if not document_before_session:
        document.write_text("session documentation", encoding="utf-8")
    assert bool(hook()) is document_before_session


@pytest.mark.parametrize("change", ["add", "delete", "rename"])
def test_path_changes_are_reviewed(hook: HookRunner, change: str) -> None:
    assert hook("SessionStart") == ""
    source = hook.root / "src/app.py"
    if change == "add":
        (hook.root / "src/new.py").write_text("new", encoding="utf-8")
    elif change == "delete":
        source.unlink()
    else:
        source.rename(hook.root / "renamed.py")
    response = json.loads(hook())
    assert response["decision"] == "block"
    assert ("src/new.py" if change == "add" else "src/app.py") in response["reason"]


def test_reverting_clears_acknowledgement_but_keeps_baseline(hook: HookRunner) -> None:
    source = hook.root / "src/app.py"
    assert hook("SessionStart") == ""
    source.write_text("v2", encoding="utf-8")
    assert hook()
    assert hook() == ""
    source.write_text("v1", encoding="utf-8")
    assert hook() == ""
    source.write_text("v2", encoding="utf-8")
    assert hook()
    source.write_text("v3", encoding="utf-8")
    assert hook()


def test_committing_session_changes_does_not_hide_them(hook: HookRunner) -> None:
    assert hook("SessionStart") == ""
    (hook.root / "src/app.py").write_text("committed edit", encoding="utf-8")
    commit_all(hook.root, "session changes")
    assert json.loads(hook())["decision"] == "block"


def test_committing_existing_changes_does_not_prompt(hook: HookRunner) -> None:
    (hook.root / "src/app.py").write_text("existing edit", encoding="utf-8")
    assert hook("SessionStart") == ""
    commit_all(hook.root, "existing changes")
    assert hook() == ""


def test_sessions_have_independent_preserved_baselines(hook: HookRunner) -> None:
    assert hook("SessionStart", "one") == ""
    (hook.root / "src/app.py").write_text("v2", encoding="utf-8")
    assert hook("SessionStart", "two") == ""
    assert hook("Stop", "two") == ""
    # SessionStart also fires for resume and compaction, with the same ID.
    assert hook("SessionStart", "one") == ""
    assert hook("Stop", "one")
    assert hook("SessionStart", "one") == ""
    assert hook("Stop", "one") == ""


@pytest.mark.parametrize(
    "corrupt", ["{", '{"version": 99, "paths": {}}', '{"version": 1, "paths": []}']
)
def test_corrupt_baseline_is_replaced_silently(hook: HookRunner, corrupt: str) -> None:
    assert hook("SessionStart") == ""
    directory = default_state_directory(hook.root) / "baselines"
    next(directory.glob("*.json")).write_text(corrupt, encoding="utf-8")
    (hook.root / "src/app.py").write_text("v2", encoding="utf-8")
    assert hook() == ""
    (hook.root / "src/app.py").write_text("v3", encoding="utf-8")
    assert hook()


def test_new_configuration_uses_original_file_state(hook: HookRunner) -> None:
    (hook.root / "other.py").write_text("v1", encoding="utf-8")
    assert hook("SessionStart") == ""
    write_config(hook.root, sources=("other.py",))
    assert hook() == ""
    (hook.root / "other.py").write_text("v2", encoding="utf-8")
    assert "other.py" in json.loads(hook())["reason"]


def test_ignored_files_are_excluded(hook: HookRunner) -> None:
    (hook.root / ".gitignore").write_text("src/ignored.py\n", encoding="utf-8")
    assert hook("SessionStart") == ""
    (hook.root / "src/ignored.py").write_text("ignored", encoding="utf-8")
    assert hook() == ""


def test_hook_works_before_first_commit(
    uncommitted_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hook = HookRunner(uncommitted_repository, monkeypatch, capsys)
    assert hook("SessionStart") == ""
    assert hook() == ""
    (hook.root / "src/app.py").write_text("v2", encoding="utf-8")
    assert hook()


def test_linked_worktree_has_its_own_baseline(hook: HookRunner, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    git(hook.root, "worktree", "add", "-b", "linked", str(linked))
    other = HookRunner(linked, hook.monkeypatch, hook.capsys)
    assert hook("SessionStart") == ""
    (linked / "src/app.py").write_text("before linked session", encoding="utf-8")
    assert other("SessionStart") == ""
    assert other() == ""
    assert hook() == ""
    (linked / "src/app.py").write_text("linked session edit", encoding="utf-8")
    assert other()
    assert hook() == ""
    assert default_state_directory(linked) != default_state_directory(hook.root)


@pytest.mark.posix_only
def test_executable_mode_changes_prompt(hook: HookRunner) -> None:
    source = hook.root / "src/app.py"
    source.chmod(0o644)
    assert hook("SessionStart") == ""
    source.chmod(0o755)
    assert hook()


@pytest.mark.posix_only
def test_symlink_targets_are_compared_without_reading_them(hook: HookRunner) -> None:
    source = hook.root / "src/app.py"
    source.unlink()
    source.symlink_to("missing-target")
    assert hook("SessionStart") == ""
    assert hook() == ""
    source.unlink()
    source.symlink_to("another-missing-target")
    assert hook()


def test_active_stop_never_reads_git_or_state(hook: HookRunner) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("active Stop must return before accessing Git or state")

    hook.monkeypatch.setattr("doc_sync.cli.resolve_root", fail)
    hook.monkeypatch.setattr(BaselineStore, "load", fail)
    hook.monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "session_id": "one",
                    "cwd": str(hook.root),
                    "stop_hook_active": True,
                }
            )
        ),
    )
    assert main(["hook"]) == 0
    captured = hook.capsys.readouterr()
    assert captured.out == captured.err == ""


def test_session_start_failure_uses_stderr(hook: HookRunner) -> None:
    def fail(_root: str) -> None:
        raise GitError("unavailable repository")

    hook.monkeypatch.setattr("doc_sync.cli.resolve_root", fail)
    hook.monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "session_id": "one",
                    "cwd": str(hook.root),
                    "hook_event_name": "SessionStart",
                }
            )
        ),
    )
    assert main(["hook"]) == 0
    captured = hook.capsys.readouterr()
    assert captured.out == ""
    assert "unavailable repository" in captured.err


@pytest.mark.parametrize("event", ["SessionStart", "Stop"])
def test_disabled_hook_does_not_create_a_baseline(hook: HookRunner, event: str) -> None:
    directory = default_state_directory(hook.root)
    state.set_disabled(directory, disabled=True)
    assert hook(event) == ""
    assert not (directory / "baselines").exists()


@pytest.mark.parametrize("event", ["SessionStart", "Stop"])
def test_missing_config_does_not_create_a_baseline(
    hook: HookRunner, event: str
) -> None:
    (hook.root / "doc-sync.toml").unlink()
    assert hook(event) == ""
    assert not (default_state_directory(hook.root) / "baselines").exists()


def test_stop_does_not_hash_unrelated_files(hook: HookRunner) -> None:
    unrelated = hook.root / "unrelated.txt"
    unrelated.write_text("unrelated contents", encoding="utf-8")
    assert hook("SessionStart") == ""
    original = state._content_marker  # noqa: SLF001 - instrument actual file reads

    def fingerprint(path: Path) -> str:
        assert path != unrelated
        return original(path)

    hook.monkeypatch.setattr(state, "_content_marker", fingerprint)
    unrelated.write_text("changed but irrelevant", encoding="utf-8")
    assert hook() == ""


def test_stop_reports_file_read_failure(hook: HookRunner) -> None:
    assert hook("SessionStart") == ""

    def fail(_path: Path) -> str:
        raise PermissionError("source is unreadable")

    hook.monkeypatch.setattr(state, "_content_marker", fail)
    response = json.loads(hook())
    assert response["decision"] == "block"
    assert "source is unreadable" in response["reason"]


@pytest.mark.posix_only
@pytest.mark.parametrize("name", ["line\nbreak.py", "a:b.py", "back\\slash.py"])
def test_baseline_preserves_git_file_names(hook: HookRunner, name: str) -> None:
    source = hook.root / "src" / name
    source.write_text("v1", encoding="utf-8")
    assert hook("SessionStart") == ""
    assert hook() == ""
    source.write_text("v2", encoding="utf-8")
    assert json.loads(hook())["decision"] == "block"
