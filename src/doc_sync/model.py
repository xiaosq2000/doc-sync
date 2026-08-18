"""Public domain models for doc-sync."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    """Result of evaluating changed paths against documentation rules."""

    PASS = "pass"  # noqa: S105
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class Rule:
    """A source-to-documentation review mapping."""

    id: str
    sources: tuple[str, ...]
    documents: tuple[str, ...]


@dataclass(frozen=True)
class Impact:
    """The effect of one triggered rule."""

    rule_id: str
    matched_sources: tuple[str, ...]
    review_targets: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "rule_id": self.rule_id,
            "matched_sources": list(self.matched_sources),
            "review_targets": list(self.review_targets),
        }


@dataclass(frozen=True)
class Evaluation:
    """Documentation impact for a set of changed paths."""

    impacts: tuple[Impact, ...] = ()

    @property
    def status(self) -> Status:
        """Return whether any impact still needs a documentation review."""
        return Status.REVIEW_REQUIRED if self.impacts else Status.PASS

    @property
    def review_targets(self) -> tuple[str, ...]:
        """Return all unique documentation review targets."""
        return tuple(
            sorted(
                {target for impact in self.impacts for target in impact.review_targets}
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-serializable representation."""
        return {
            "status": self.status.value,
            "review_targets": list(self.review_targets),
            "impacts": [impact.to_dict() for impact in self.impacts],
        }
