"""Pure matching of changed source paths to documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from doc_sync.paths import SourcePattern, normalize_path

if TYPE_CHECKING:
    from collections.abc import Iterable

    from doc_sync.config import Document


@dataclass(frozen=True)
class Review:
    """One document and the changed sources that caused its review."""

    document: str
    sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""
        return {"path": self.document, "sources": list(self.sources)}


def evaluate(
    documents: Iterable[Document], changed_paths: Iterable[str]
) -> tuple[Review, ...]:
    """Return unchanged documents whose configured sources changed."""
    changed = tuple(sorted({normalize_path(path) for path in changed_paths if path}))
    changed_set = set(changed)
    reviews: list[Review] = []

    for document in documents:
        patterns = tuple(SourcePattern(source) for source in document.sources)
        matched = tuple(
            path
            for path in changed
            if any(pattern.matches(path) for pattern in patterns)
        )
        if matched and document.path not in changed_set:
            reviews.append(Review(document=document.path, sources=matched))

    return tuple(reviews)
