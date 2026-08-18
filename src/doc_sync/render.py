"""Human- and agent-facing rendering of an evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from doc_sync.model import Evaluation

REVIEW_GUIDANCE = (
    "Review each document above and update it when the source change affects "
    "durable facts."
)
SESSION_GUIDANCE = (
    f"{REVIEW_GUIDANCE}\n"
    "If no update is needed, the same session may proceed after this review reminder."
)


def build_review_message(
    evaluation: Evaluation, guidance: str = SESSION_GUIDANCE
) -> str:
    """Build the review request, closing with the caller's guidance."""
    lines = [
        "Documentation may need review.",
        "",
        "Changed sources triggered these doc-sync rules:",
    ]
    lines.extend(
        f"  [{impact.rule_id}] {source} -> {document}"
        for impact in evaluation.impacts
        for source in impact.matched_sources
        for document in impact.review_targets
    )
    lines.extend(["", guidance])
    return "\n".join(lines)
