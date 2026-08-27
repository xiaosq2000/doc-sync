from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from doc_sync.engine import evaluate
from doc_sync.state import AcknowledgementStore
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
