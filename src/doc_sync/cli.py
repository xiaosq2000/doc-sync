"""Command line interface for doc-sync."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from doc_sync.config import (
    CONFIG_FILENAME,
    MissingConfigError,
    load_config,
    validate_repository_config,
)
from doc_sync.errors import DocSyncError
from doc_sync.git import (
    changed_base_paths,
    changed_staged_paths,
    changed_worktree_paths,
    resolve_root,
)
from doc_sync.hook import HookContext, blocking_output, parse_context
from doc_sync.match import Review, evaluate
from doc_sync.render import HOOK_GUIDANCE, build_review_message
from doc_sync.state import (
    AcknowledgementStore,
    BaselineStore,
    default_state_directory,
    is_disabled,
    session_changed_paths,
    set_disabled,
)

if TYPE_CHECKING:
    from pathlib import Path

EXIT_ERROR = 1
EXIT_REVIEW_REQUIRED = 2
_NO_REVIEW_MESSAGE = "doc-sync: no documents need review"
_DISPATCH_KEYS = frozenset({"command", "handler"})


def _changed_paths(root: Path, *, staged: bool, base: str | None) -> tuple[str, ...]:
    if staged:
        return changed_staged_paths(root)
    if base:
        return changed_base_paths(root, base)
    return changed_worktree_paths(root)


def _payload(reviews: tuple[Review, ...]) -> dict[str, object]:
    return {
        "status": "review_required" if reviews else "pass",
        "documents": [review.to_dict() for review in reviews],
    }


def _write_json(value: object) -> None:
    json.dump(value, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def _run_check(*, staged: bool, base: str | None, json_output: bool) -> int:
    root = resolve_root()
    config = load_config(root / CONFIG_FILENAME)
    reviews = evaluate(config.documents, _changed_paths(root, staged=staged, base=base))
    if json_output:
        _write_json(_payload(reviews))
    elif reviews:
        print(build_review_message(reviews))
    else:
        print(_NO_REVIEW_MESSAGE)
    return EXIT_REVIEW_REQUIRED if reviews else 0


def _run_validate() -> int:
    root = resolve_root()
    path = root / CONFIG_FILENAME
    validate_repository_config(root=root, config_path=path)
    print(f"valid {path}")
    return 0


def _hook_reviews(*, root: Path, context: HookContext) -> tuple[Review, ...] | None:
    state_directory = default_state_directory(root)
    if is_disabled(state_directory):
        return None

    config_path = root / CONFIG_FILENAME
    config = load_config(config_path)
    session_id = context.session_id
    store = AcknowledgementStore(state_directory)
    baselines = BaselineStore(state_directory)
    baseline = baselines.load(session_id)
    if baseline is None:
        baselines.capture(session_id=session_id, root=root)
        store.clear(session_id)
        return None
    if context.hook_event_name == "SessionStart":
        return None
    reviews = evaluate(
        config.documents,
        session_changed_paths(root=root, baseline=baseline, documents=config.documents),
    )
    if not reviews:
        store.clear(session_id)
        return None
    if not store.should_prompt(
        session_id=session_id,
        root=root,
        config_path=config_path,
        reviews=reviews,
    ):
        return None
    return reviews


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

    check = subparsers.add_parser("check", help="Check changed source files.")
    source = check.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true", help="Check staged files.")
    source.add_argument("--base", help="Check committed files changed from this ref.")
    check.add_argument("--json", dest="json_output", action="store_true")
    check.set_defaults(handler=_run_check)

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
