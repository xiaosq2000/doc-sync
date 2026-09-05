from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from doc_sync.match import evaluate
from doc_sync.state import (
    AcknowledgementStore,
    BaselineStore,
    is_disabled,
    set_disabled,
)
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


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"version": True, "paths": {}},
        {"version": 1, "paths": {"../outside": "missing"}},
        {"version": 1, "paths": {"/outside": "missing"}},
        {"version": 1, "paths": {".git/config": "missing"}},
        {"version": 1, "paths": {"src/app.py": None}},
        {"version": 1, "paths": {"src/app.py": "invalid fingerprint"}},
    ],
)
def test_baseline_rejects_invalid_state(
    uncommitted_repository: Path, value: object
) -> None:
    directory = uncommitted_repository / "state"
    store = BaselineStore(directory)
    store.capture(session_id="one", root=uncommitted_repository)
    path = next((directory / "baselines").glob("*.json"))
    path.write_text(json.dumps(value), encoding="utf-8")
    assert store.load("one") is None


def test_baseline_contains_fingerprints_and_uses_safe_session_names(
    uncommitted_repository: Path,
) -> None:
    directory = uncommitted_repository / "state"
    store = BaselineStore(directory)
    session_id = "../outside/session"
    source = uncommitted_repository / "src/app.py"
    source.write_text("private source text", encoding="utf-8")
    store.capture(session_id=session_id, root=uncommitted_repository)
    baseline = store.load(session_id)
    assert baseline is not None
    assert baseline["src/app.py"].startswith("file:")
    path = next((directory / "baselines").glob("*.json"))
    assert len(path.stem) == 64
    assert "private source text" not in path.read_text(encoding="utf-8")
