"""Command-line interface for doc-sync."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from doc_sync.config import (
    CONFIG_FILENAME,
    load_config,
    validate_repository_config,
)
from doc_sync.engine import evaluate
from doc_sync.errors import DocSyncError
from doc_sync.git import (
    changed_base_paths,
    changed_staged_paths,
    changed_worktree_paths,
    resolve_root,
)
from doc_sync.integrations.stop_hook import blocking_output, parse_context
from doc_sync.model import Evaluation, Status
from doc_sync.render import REVIEW_GUIDANCE, build_review_message
from doc_sync.state import AcknowledgementStore, default_state_directory

EXIT_ERROR = 1
EXIT_REVIEW_REQUIRED = 2


def _path_from_root(root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else root / path


def _changed_paths(args: argparse.Namespace, root: Path) -> tuple[str, ...]:
    if args.paths_from:
        if args.paths_from == "-":
            content = sys.stdin.read()
        else:
            content = Path(args.paths_from).read_text(encoding="utf-8")
        return tuple(path for path in content.splitlines() if path)
    if args.staged:
        return changed_staged_paths(root)
    if args.base:
        return changed_base_paths(root, args.base)
    return changed_worktree_paths(root)


def _json_output(value: object) -> None:
    json.dump(value, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def _run_check(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    config = load_config(_path_from_root(root, args.config))
    result = evaluate(config.rules, _changed_paths(args, root))
    payload = result.to_dict()
    if result.status is Status.REVIEW_REQUIRED:
        payload["message"] = build_review_message(result, REVIEW_GUIDANCE)

    if args.format == "json":
        _json_output(payload)
    elif result.status is Status.REVIEW_REQUIRED:
        print(payload["message"])
    return EXIT_REVIEW_REQUIRED if result.status is Status.REVIEW_REQUIRED else 0


def _run_validate(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    config_path = _path_from_root(root, args.config)
    if args.check_paths:
        validate_repository_config(root=root, config_path=config_path)
    else:
        load_config(config_path)
    print(f"valid {config_path}")
    return 0


def _run_init(args: argparse.Namespace) -> int:
    from doc_sync.integrations.install import initialize_config  # noqa: PLC0415

    root = resolve_root(args.root)
    created = initialize_config(root, dry_run=args.dry_run)
    if not created:
        print(f"kept existing {root / CONFIG_FILENAME}")
    return 0


def _state_store(root: Path, raw_state_directory: str | None) -> AcknowledgementStore:
    directory = (
        _path_from_root(root, raw_state_directory)
        if raw_state_directory
        else default_state_directory(root)
    )
    return AcknowledgementStore(directory)


def _hook_evaluation(
    args: argparse.Namespace, *, root: Path, session_id: str
) -> Evaluation | None:
    """Evaluate the worktree, returning it only when this session must be prompted."""
    config_path = _path_from_root(root, args.config)
    config = load_config(config_path)
    result = evaluate(config.rules, changed_worktree_paths(root))
    store = _state_store(root, args.state_directory)
    if result.status is Status.PASS:
        store.clear(session_id)
        return None
    if not store.should_prompt(
        session_id=session_id,
        root=root,
        config_path=config_path,
        evaluation=result,
    ):
        return None
    return result


def _run_stop_hook(args: argparse.Namespace) -> int:
    """Run the Stop-hook protocol Claude Code and Codex CLI both speak."""
    try:
        context = parse_context(sys.stdin.read(), agent=args.agent)
        project_directory = (
            os.environ.get(args.project_directory_variable)
            if args.project_directory_variable
            else None
        )
        raw_root = args.root or project_directory or str(context.cwd)
        result = _hook_evaluation(
            args, root=resolve_root(raw_root), session_id=context.session_id
        )
        if result is not None:
            _json_output(blocking_output(build_review_message(result)))
    except (DocSyncError, OSError) as exc:
        _json_output(blocking_output(f"doc-sync could not complete its check: {exc}"))
    return 0


def _run_opencode_hook(args: argparse.Namespace) -> int:
    result = _hook_evaluation(
        args, root=resolve_root(args.root), session_id=args.session_id
    )
    if result is None:
        return 0
    _json_output({**result.to_dict(), "message": build_review_message(result)})
    return EXIT_REVIEW_REQUIRED


INTEGRATIONS = ("claude", "codex", "opencode")


def _targets(raw_target: str) -> tuple[str, ...]:
    return INTEGRATIONS if raw_target == "all" else (raw_target,)


def _run_hook_install(args: argparse.Namespace) -> int:
    from doc_sync.integrations.install import install_hooks  # noqa: PLC0415

    root = resolve_root(args.root)
    install_hooks(
        root,
        _targets(args.target),
        dry_run=args.dry_run,
        force=args.force,
    )
    return 0


def _run_hook_uninstall(args: argparse.Namespace) -> int:
    from doc_sync.integrations.install import uninstall_hooks  # noqa: PLC0415

    root = resolve_root(args.root)
    uninstall_hooks(root, _targets(args.target), dry_run=args.dry_run)
    return 0


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", help="A path inside the target Git repository.")


def _add_repository_arguments(parser: argparse.ArgumentParser) -> None:
    _add_root_argument(parser)
    parser.add_argument(
        "--config",
        default=CONFIG_FILENAME,
        help=f"Configuration path relative to the repository (default: {CONFIG_FILENAME}).",
    )


def _add_stop_hook_arguments(
    parser: argparse.ArgumentParser,
    *,
    agent: str,
    project_directory_variable: str | None,
) -> None:
    _add_repository_arguments(parser)
    parser.add_argument("--state-directory")
    parser.set_defaults(
        handler=_run_stop_hook,
        agent=agent,
        project_directory_variable=project_directory_variable,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc-sync",
        description="Map changed source files to documentation review targets.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Evaluate changed paths.")
    _add_repository_arguments(check)
    source = check.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true", help="Check staged paths.")
    source.add_argument("--base", help="Check committed paths changed since this ref.")
    source.add_argument(
        "--paths-from", metavar="FILE", help="Read changed paths from FILE or `-`."
    )
    check.add_argument("--format", choices=("human", "json"), default="human")
    check.set_defaults(handler=_run_check)

    validate = subparsers.add_parser("validate", help="Validate configuration.")
    _add_repository_arguments(validate)
    validate.add_argument(
        "--check-paths",
        action="store_true",
        help="Also require every configured path to resolve in this checkout.",
    )
    validate.set_defaults(handler=_run_validate)

    initialize = subparsers.add_parser("init", help="Create an example config.")
    _add_root_argument(initialize)
    initialize.add_argument("--dry-run", action="store_true")
    initialize.set_defaults(handler=_run_init)

    hook = subparsers.add_parser("hook", help="Run or manage agent hooks.")
    hook_subparsers = hook.add_subparsers(dest="hook_command", required=True)

    claude = hook_subparsers.add_parser("claude", help="Run the Claude Stop adapter.")
    _add_stop_hook_arguments(
        claude, agent="Claude Code", project_directory_variable="CLAUDE_PROJECT_DIR"
    )

    codex = hook_subparsers.add_parser("codex", help="Run the Codex Stop adapter.")
    # Codex exposes no project-directory variable, so the payload `cwd` is the
    # only hint about which repository the session is working in.
    _add_stop_hook_arguments(codex, agent="Codex", project_directory_variable=None)

    opencode = hook_subparsers.add_parser(
        "opencode", help="Run the OpenCode session.idle adapter."
    )
    _add_repository_arguments(opencode)
    opencode.add_argument("--session-id", required=True)
    opencode.add_argument("--state-directory")
    opencode.set_defaults(handler=_run_opencode_hook)

    install = hook_subparsers.add_parser("install", help="Install agent hooks.")
    install.add_argument("target", choices=(*INTEGRATIONS, "all"))
    _add_root_argument(install)
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--force", action="store_true")
    install.set_defaults(handler=_run_hook_install)

    uninstall = hook_subparsers.add_parser("uninstall", help="Remove agent hooks.")
    uninstall.add_argument("target", choices=(*INTEGRATIONS, "all"))
    _add_root_argument(uninstall)
    uninstall.add_argument("--dry-run", action="store_true")
    uninstall.set_defaults(handler=_run_hook_uninstall)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the doc-sync CLI and return its stable exit code."""
    args = _build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (DocSyncError, OSError) as exc:
        print(f"doc-sync error: {exc}", file=sys.stderr)
        return EXIT_ERROR
