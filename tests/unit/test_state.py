from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from doc_sync.match import evaluate
from doc_sync.state import AcknowledgementStore, is_disabled, set_disabled
from tests.support import APPLICATION_DOCUMENT

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
        reviews=evaluate((APPLICATION_DOCUMENT,), changed),
    )


def test_acknowledges_each_session_independently(
    uncommitted_repository: Path, store: AcknowledgementStore
) -> None:
    root = uncommitted_repository
    reviews = evaluate((APPLICATION_DOCUMENT,), ("src/app.py",))
    arguments = {"root": root, "config_path": root / "doc-sync.toml"}

    assert store.should_prompt(session_id="one", reviews=reviews, **arguments)
    assert not store.should_prompt(session_id="one", reviews=reviews, **arguments)
    assert store.should_prompt(session_id="two", reviews=reviews, **arguments)


def test_changed_source_content_prompts_again(
    uncommitted_repository: Path, store: AcknowledgementStore
) -> None:
    root = uncommitted_repository
    assert _prompted(store, root, "src/app.py")

    (root / "src/app.py").write_text("v2", encoding="utf-8")

    assert _prompted(store, root, "src/app.py")


def test_the_hook_switch_round_trips(root: Path) -> None:
    directory = root / "state"

    assert set_disabled(directory, disabled=True)
    assert is_disabled(directory)
    assert not set_disabled(directory, disabled=True)
    assert set_disabled(directory, disabled=False)
    assert not is_disabled(directory)
