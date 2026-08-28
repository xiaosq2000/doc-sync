from __future__ import annotations

from doc_sync.config import Document
from doc_sync.match import Review, evaluate
from doc_sync.render import build_review_message


def test_returns_each_unchanged_document_with_its_changed_sources() -> None:
    documents = (
        Document("README.md", ("src/", "pyproject.toml")),
        Document("docs/api.md", ("src/api/",)),
    )

    reviews = evaluate(
        documents,
        ("src/app.py", "src/api/client.py", "pyproject.toml", "README.md"),
    )

    assert reviews == (Review("docs/api.md", ("src/api/client.py",)),)


def test_one_source_can_require_several_documents() -> None:
    documents = (
        Document("README.md", ("src/",)),
        Document("docs/api.md", ("src/",)),
    )

    reviews = evaluate(documents, ("src/app.py",))

    assert tuple(review.document for review in reviews) == (
        "README.md",
        "docs/api.md",
    )


def test_message_names_documents_and_sources() -> None:
    message = build_review_message((Review("README.md", ("src/app.py",)),))

    assert "README.md\n  src/app.py" in message
