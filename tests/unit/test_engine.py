from __future__ import annotations

import unittest

from doc_sync.engine import evaluate
from doc_sync.model import Rule, Status
from doc_sync.render import build_review_message


class EvaluateTest(unittest.TestCase):
    rule = Rule(
        id="application",
        sources=("src/",),
        documents=("README.md", "docs/api.md"),
    )

    def test_requires_review_for_unchanged_documents(self) -> None:
        result = evaluate((self.rule,), ("src/app.py",))

        assert result.status is Status.REVIEW_REQUIRED
        assert result.review_targets == ("README.md", "docs/api.md")
        assert result.impacts[0].matched_sources == ("src/app.py",)

    def test_passes_when_all_documents_changed(self) -> None:
        result = evaluate((self.rule,), ("src/app.py", "README.md", "docs/api.md"))

        assert result.status is Status.PASS

    def test_message_names_rule_source_and_document(self) -> None:
        result = evaluate((self.rule,), ("src/app.py", "README.md"))

        message = build_review_message(result)

        assert "[application] src/app.py -> docs/api.md" in message
