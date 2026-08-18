"""Pure documentation-impact evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from doc_sync.model import Evaluation, Impact
from doc_sync.paths import SourcePattern, normalize_path

if TYPE_CHECKING:
    from collections.abc import Iterable

    from doc_sync.model import Rule


def evaluate(rules: Iterable[Rule], changed_paths: Iterable[str]) -> Evaluation:
    """Evaluate changed paths without reading or writing external state."""
    changed = tuple(
        sorted({normalize_path(path) for path in changed_paths if path.strip()})
    )
    if not changed:
        return Evaluation()
    changed_set = set(changed)
    impacts: list[Impact] = []

    for rule in rules:
        patterns = [SourcePattern(source) for source in rule.sources]
        matched_sources = tuple(
            path
            for path in changed
            if any(pattern.matches(path) for pattern in patterns)
        )
        if not matched_sources:
            continue
        review_targets = tuple(
            document for document in rule.documents if document not in changed_set
        )
        if review_targets:
            impacts.append(
                Impact(
                    rule_id=rule.id,
                    matched_sources=matched_sources,
                    review_targets=review_targets,
                )
            )

    return Evaluation(tuple(impacts))
