from __future__ import annotations

import unittest

from doc_sync.engine import evaluate
from doc_sync.state import AcknowledgementStore
from tests.support import APPLICATION_RULE, temporary_repository


class AcknowledgementStoreTest(unittest.TestCase):
    def test_acknowledges_each_session_independently(self) -> None:
        with temporary_repository(commit=False) as root:
            config_path = root / "doc-sync.toml"
            result = evaluate(
                (APPLICATION_RULE,),
                ("src/app.py",),
            )
            store = AcknowledgementStore(root / "state")

            assert store.should_prompt(
                session_id="one",
                root=root,
                config_path=config_path,
                evaluation=result,
            )
            assert not store.should_prompt(
                session_id="one",
                root=root,
                config_path=config_path,
                evaluation=result,
            )
            assert store.should_prompt(
                session_id="two",
                root=root,
                config_path=config_path,
                evaluation=result,
            )

    def test_unrelated_file_does_not_change_state(self) -> None:
        with temporary_repository(commit=False) as root:
            config_path = root / "doc-sync.toml"
            result = evaluate(
                (APPLICATION_RULE,),
                ("src/app.py", "notes.txt"),
            )
            store = AcknowledgementStore(root / "state")
            assert store.should_prompt(
                session_id="one",
                root=root,
                config_path=config_path,
                evaluation=result,
            )

            (root / "notes.txt").write_text("unrelated", encoding="utf-8")

            assert not store.should_prompt(
                session_id="one",
                root=root,
                config_path=config_path,
                evaluation=result,
            )

    def test_changed_source_prompts_again(self) -> None:
        with temporary_repository(commit=False) as root:
            source = root / "src/app.py"
            config_path = root / "doc-sync.toml"
            result = evaluate(
                (APPLICATION_RULE,),
                ("src/app.py",),
            )
            store = AcknowledgementStore(root / "state")
            assert store.should_prompt(
                session_id="one",
                root=root,
                config_path=config_path,
                evaluation=result,
            )

            source.write_text("v2", encoding="utf-8")

            assert store.should_prompt(
                session_id="one",
                root=root,
                config_path=config_path,
                evaluation=result,
            )
