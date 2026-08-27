from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from doc_sync.engine import evaluate
from doc_sync.state import AcknowledgementStore, is_disabled, set_disabled
from tests.support import APPLICATION_RULE

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def store(uncommitted_repository: Path) -> AcknowledgementStore:
    return AcknowledgementStore(uncommitted_repository / "state")


def _prompted(store: AcknowledgementStore, root: Path, *changed: str) -> bool:
    return store.should_prompt(
        session_id="one",
        root=root,
        config_path=root / "doc-sync.toml",
        evaluation=evaluate((APPLICATION_RULE,), changed),
    )


def test_acknowledges_each_session_independently(
    uncommitted_repository: Path, store: AcknowledgementStore
) -> None:
    root = uncommitted_repository
    evaluation = evaluate((APPLICATION_RULE,), ("src/app.py",))
    arguments = {"root": root, "config_path": root / "doc-sync.toml"}

    assert store.should_prompt(session_id="one", evaluation=evaluation, **arguments)
    assert not store.should_prompt(session_id="one", evaluation=evaluation, **arguments)
    assert store.should_prompt(session_id="two", evaluation=evaluation, **arguments)


def test_unrelated_file_does_not_change_state(
    uncommitted_repository: Path, store: AcknowledgementStore
) -> None:
    root = uncommitted_repository
    assert _prompted(store, root, "src/app.py", "notes.txt")

    (root / "notes.txt").write_text("unrelated", encoding="utf-8")

    assert not _prompted(store, root, "src/app.py", "notes.txt")


def test_changed_source_prompts_again(
    uncommitted_repository: Path, store: AcknowledgementStore
) -> None:
    root = uncommitted_repository
    assert _prompted(store, root, "src/app.py")

    (root / "src/app.py").write_text("v2", encoding="utf-8")

    assert _prompted(store, root, "src/app.py")


def test_an_absent_state_directory_reads_as_enabled(root: Path) -> None:
    assert not is_disabled(root / "state")


def test_the_switch_round_trips(root: Path) -> None:
    directory = root / "state"

    assert set_disabled(directory, disabled=True)
    assert is_disabled(directory)

    assert set_disabled(directory, disabled=False)
    assert not is_disabled(directory)


def test_setting_the_current_state_reports_no_change(root: Path) -> None:
    directory = root / "state"

    assert not set_disabled(directory, disabled=False)
    assert set_disabled(directory, disabled=True)
    assert not set_disabled(directory, disabled=True)


def test_the_switch_is_independent_of_acknowledgement_state(
    uncommitted_repository: Path, store: AcknowledgementStore
) -> None:
    root = uncommitted_repository
    assert _prompted(store, root, "src/app.py")

    set_disabled(store.state_directory, disabled=True)
    set_disabled(store.state_directory, disabled=False)

    assert not _prompted(store, root, "src/app.py")
