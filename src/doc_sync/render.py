"""Render document review results for people and agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from doc_sync.match import Review

CHECK_GUIDANCE = (
    "Review each document and update it if the listed source changes altered "
    "durable facts."
)
HOOK_GUIDANCE = (
    f"{CHECK_GUIDANCE}\n"
    "If no update is needed, stop again without changing the document."
)


def build_review_message(
    reviews: Iterable[Review], *, guidance: str = CHECK_GUIDANCE
) -> str:
    """Build a review request from pending documents."""
    lines = ["Documentation needs review.", ""]
    for review in reviews:
        lines.append(review.document)
        lines.extend(f"  {source}" for source in review.sources)
    lines.extend(["", guidance])
    return "\n".join(lines)
