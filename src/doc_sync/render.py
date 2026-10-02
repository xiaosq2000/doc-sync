"""Render document review results for people and agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from doc_sync.match import Review

_REVIEW_GUIDANCE = (
    "Review each document and update it if the listed source changes altered "
    "durable facts."
)
CHECK_GUIDANCE = (
    f"{_REVIEW_GUIDANCE}\nThen record the review with `doc-sync stamp <document>`."
)
HOOK_GUIDANCE = (
    f"{_REVIEW_GUIDANCE}\n"
    "Then record the review with `doc-sync stamp <document>`, also when no update "
    "is needed."
)


def _heading(review: Review) -> str:
    if not review.stamped:
        return f"{review.document} (never stamped)"
    if review.since is not None:
        return f"{review.document} (changed since {review.since[:12]})"
    return review.document


def build_review_message(
    reviews: Iterable[Review], *, guidance: str = CHECK_GUIDANCE
) -> str:
    """Build a review request from pending documents."""
    lines = ["Documentation needs review.", ""]
    for review in reviews:
        lines.append(_heading(review))
        lines.extend(f"  {source}" for source in review.sources)
    lines.extend(["", guidance])
    return "\n".join(lines)
