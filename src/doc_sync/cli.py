"""Command line interface for doc-sync."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from doc_sync.config import (
    CONFIG_FILENAME,
    Document,
    MissingConfigError,
    load_config,
    validate_repository_config,
)
from doc_sync.errors import DocSyncError
from doc_sync.git import (
    changed_worktree_paths,
    head_commit,
    last_change_commit,
    object_ids,
    resolve_root,
    worktree_paths,
)
from doc_sync.hook import HookContext, blocking_output, parse_context
from doc_sync.lock import LOCK_FILENAME, entry_line, read_lock, write_lock
from doc_sync.match import Review, fingerprint, matched_paths, stale_documents
from doc_sync.paths import normalize_path
from doc_sync.render import HOOK_GUIDANCE, build_review_message
from doc_sync.state import (
    AcknowledgementStore,
    BaselineStore,
    default_state_directory,
    is_disabled,
    set_disabled,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

EXIT_ERROR = 1
EXIT_REVIEW_REQUIRED = 2
_NO_REVIEW_MESSAGE = "doc-sync: no documents need review"
_DISPATCH_KEYS = frozenset({"command", "handler"})


def _describe(
    root: Path, documents: Iterable[Document], lock: Mapping[str, str]
) -> tuple[Review, ...]:
    """Describe stale documents with the sources changed since their stamps."""
    changed: dict[str | None, tuple[str, ...]] = {}
    reviews: list[Review] = []
    for document in documents:
        recorded = lock.get(document.path)
        if recorded is None:
            reviews.append(Review(document=document.path, sources=(), stamped=False))
            continue
        # A stamp that is not committed yet was made after HEAD.
        since = last_change_commit(
            root, LOCK_FILENAME, entry_line(document.path, recorded)
        ) or head_commit(root)
        if since not in changed:
            changed[since] = changed_worktree_paths(root, since)
        reviews.append(
            Review(
                document=document.path,
                sources=matched_paths(document, changed[since]),
                since=since,
            )
        )
    return tuple(reviews)


def _payload(reviews: tuple[Review, ...]) -> dict[str, object]:
    return {
        "status": "review_required" if reviews else "pass",
        "documents": [review.to_dict() for review in reviews],
    }


def _write_json(value: object) -> None:
    json.dump(value, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def _run_check(*, json_output: bool) -> int:
    root = resolve_root()
    config = load_config(root / CONFIG_FILENAME)
    ids = object_ids(root)
    lock = read_lock(root / LOCK_FILENAME)
    reviews = _describe(root, stale_documents(config.resolve(ids), ids, lock), lock)
    if json_output:
        _write_json(_payload(reviews))
    elif reviews:
        print(build_review_message(reviews))
    else:
        print(_NO_REVIEW_MESSAGE)
    return EXIT_REVIEW_REQUIRED if reviews else 0


def _run_stamp(*, documents: list[str], all_documents: bool) -> int:
    if bool(documents) == all_documents:
        raise DocSyncError("name the documents to stamp, or pass --all alone")
    root = resolve_root()
    config = load_config(root / CONFIG_FILENAME)
    ids = object_ids(root)
    resolved = {document.path: document for document in config.resolve(ids)}
    targets = (
        list(resolved)
        if all_documents
        else [normalize_path(path) for path in documents]
    )
    unknown = [path for path in targets if path not in resolved]
    if unknown:
        rendered = ", ".join(f"`{path}`" for path in unknown)
        raise DocSyncError(f"not a configured document: {rendered}")

    lock_path = root / LOCK_FILENAME
    # Entries for documents that are no longer configured are dropped.
    lock = {
        path: recorded
        for path, recorded in read_lock(lock_path).items()
        if path in resolved
    }
    for path in targets:
        lock[path] = fingerprint(resolved[path], ids)
    write_lock(lock_path, lock)
    for path in targets:
        print(f"stamped {path}")
    return 0


def _run_validate() -> int:
    root = resolve_root()
    path = root / CONFIG_FILENAME
    for warning in validate_repository_config(
        root=root, config_path=path, paths=worktree_paths(root)
    ):
        print(f"doc-sync warning: {warning}", file=sys.stderr)
    print(f"valid {path}")
    return 0


def _hook_reviews(*, root: Path, context: HookContext) -> tuple[Review, ...] | None:
    state_directory = default_state_directory(root)
    if is_disabled(state_directory):
        return None

    config = load_config(root / CONFIG_FILENAME)
    session_id = context.session_id
    acknowledgements = AcknowledgementStore(state_directory)
    baselines = BaselineStore(state_directory)
    baseline = baselines.load(session_id)
    # SessionStart also fires on resume and compaction, which keep the baseline.
    if baseline is not None and context.hook_event_name == "SessionStart":
        return None

    ids = object_ids(root)
    documents = config.resolve(ids)
    current = {document.path: fingerprint(document, ids) for document in documents}
    if baseline is None:
        baselines.capture(session_id=session_id, fingerprints=current)
        acknowledgements.clear(session_id)
        return None

    # Report documents that went stale during this session. Staleness from
    # before the session is left to `doc-sync check`.
    lock = read_lock(root / LOCK_FILENAME)
    candidates = {
        path: value
        for path, value in current.items()
        if value not in {lock.get(path), baseline.get(path)}
    }
    unreported = set(
        acknowledgements.unreported(session_id=session_id, candidates=candidates)
    )
    if not unreported:
        return None
    return _describe(
        root, (document for document in documents if document.path in unreported), lock
    )


def _run_hook() -> int:
    context = None
    try:
        context = parse_context(sys.stdin.read())
        if context.stop_hook_active:
            return 0
        reviews = _hook_reviews(root=resolve_root(str(context.cwd)), context=context)
        if reviews:
            reason = build_review_message(reviews, guidance=HOOK_GUIDANCE)
            _write_json(blocking_output(reason))
    except MissingConfigError:
        return 0
    except (DocSyncError, OSError) as exc:
        reason = f"doc-sync could not complete its check: {exc}"
        if context is not None and context.hook_event_name == "SessionStart":
            print(reason, file=sys.stderr)
        else:
            _write_json(blocking_output(reason))
    return 0


def _run_toggle(*, disabled: bool) -> int:
    root = resolve_root()
    state = "disabled" if disabled else "enabled"
    changed = set_disabled(default_state_directory(root), disabled=disabled)
    qualifier = "" if changed else "already "
    print(f"doc-sync hook is {qualifier}{state} for {root}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc-sync",
        description="Find documents that may need review after source changes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="List documents that need review.")
    check.add_argument("--json", dest="json_output", action="store_true")
    check.set_defaults(handler=_run_check)

    stamp = subparsers.add_parser("stamp", help="Record that documents were reviewed.")
    stamp.add_argument(
        "documents", nargs="*", metavar="document", help="A repository-relative path."
    )
    stamp.add_argument(
        "--all", dest="all_documents", action="store_true", help="Stamp every document."
    )
    stamp.set_defaults(handler=_run_stamp)

    validate = subparsers.add_parser("validate", help="Validate doc-sync.toml.")
    validate.set_defaults(handler=_run_validate)

    hook = subparsers.add_parser("hook", help="Run the shared session hook adapter.")
    hook.set_defaults(handler=_run_hook)

    disable = subparsers.add_parser("disable", help="Disable the Stop hook here.")
    disable.set_defaults(handler=_run_toggle, disabled=True)

    enable = subparsers.add_parser("enable", help="Enable the Stop hook here.")
    enable.set_defaults(handler=_run_toggle, disabled=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run doc-sync and return its exit code."""
    args = _build_parser().parse_args(argv)
    options = {
        key: value for key, value in vars(args).items() if key not in _DISPATCH_KEYS
    }
    try:
        return int(args.handler(**options))
    except (DocSyncError, OSError) as exc:
        print(f"doc-sync error: {exc}", file=sys.stderr)
        return EXIT_ERROR
