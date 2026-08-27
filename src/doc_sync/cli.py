"""Command-line interface for doc-sync."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from doc_sync.config import (
    CONFIG_FILENAME,
    MissingConfigError,
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
from doc_sync.state import (
    AcknowledgementStore,
    default_state_directory,
    is_disabled,
    set_disabled,
)

EXIT_ERROR = 1
EXIT_REVIEW_REQUIRED = 2
# Same key set as `Evaluation.to_dict()`, so a disabled checkout does not change
# the shape a `--format json` consumer has to parse.
_DISABLED_PAYLOAD = {"status": "disabled", "review_targets": [], "impacts": []}
# Parser bookkeeping that names a handler rather than one of its parameters.
_DISPATCH_KEYS = frozenset({"command", "handler", "hook_command"})


def _path_from_root(root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else root / path


def _changed_paths(
    root: Path, *, staged: bool, base: str | None, paths_from: str | None
) -> tuple[str, ...]:
    if paths_from:
        if paths_from == "-":
            content = sys.stdin.read()
        else:
            content = Path(paths_from).read_text(encoding="utf-8")
        paths: list[str] = [path for path in content.splitlines() if path]
        return tuple(paths)
    if staged:
        return changed_staged_paths(root)
    if base:
        return changed_base_paths(root, base)
    return changed_worktree_paths(root)


def _json_output(value: object) -> None:
    json.dump(value, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def _state_directory(root: Path, raw_state_directory: str | None) -> Path:
    return (
        _path_from_root(root, raw_state_directory)
        if raw_state_directory
        else default_state_directory(root)
    )


def _run_check(
    *,
    root: str | None,
    config_path: str,
    state_directory: str | None,
    staged: bool,
    base: str | None,
    paths_from: str | None,
    output_format: str,
) -> int:
    repository = resolve_root(root)
    # Check the switch before the configuration: a disabled checkout stays quiet
    # even when its `doc-sync.toml` is missing or broken.
    if is_disabled(_state_directory(repository, state_directory)):
        if output_format == "json":
            _json_output(_DISABLED_PAYLOAD)
        return 0
    config = load_config(_path_from_root(repository, config_path))
    result = evaluate(
        config.rules,
        _changed_paths(repository, staged=staged, base=base, paths_from=paths_from),
    )
    payload = result.to_dict()
    if result.status is Status.REVIEW_REQUIRED:
        payload["message"] = build_review_message(result, REVIEW_GUIDANCE)

    if output_format == "json":
        _json_output(payload)
    elif result.status is Status.REVIEW_REQUIRED:
        print(payload["message"])
    return EXIT_REVIEW_REQUIRED if result.status is Status.REVIEW_REQUIRED else 0


def _run_validate(*, root: str | None, config_path: str, check_paths: bool) -> int:
    repository = resolve_root(root)
    resolved = _path_from_root(repository, config_path)
    if check_paths:
        validate_repository_config(root=repository, config_path=resolved)
    else:
        load_config(resolved)
    print(f"valid {resolved}")
    return 0


def _run_init(*, root: str | None, dry_run: bool) -> int:
    from doc_sync.integrations.install import initialize_config  # noqa: PLC0415

    repository = resolve_root(root)
    if not initialize_config(repository, dry_run=dry_run):
        print(f"kept existing {repository / CONFIG_FILENAME}")
    return 0


def _hook_evaluation(
    *, root: Path, config_path: str, state_directory: str | None, session_id: str
) -> Evaluation | None:
    """Evaluate the worktree, returning it only when this session must be prompted."""
    directory = _state_directory(root, state_directory)
    if is_disabled(directory):
        return None
    resolved = _path_from_root(root, config_path)
    config = load_config(resolved)
    result = evaluate(config.rules, changed_worktree_paths(root))
    store = AcknowledgementStore(directory)
    if result.status is Status.PASS:
        store.clear(session_id)
        return None
    if not store.should_prompt(
        session_id=session_id,
        root=root,
        config_path=resolved,
        evaluation=result,
    ):
        return None
    return result


def _run_stop_hook(
    *,
    root: str | None,
    config_path: str,
    state_directory: str | None,
    agent: str,
    project_directory_variable: str | None,
) -> int:
    """Run the Stop-hook protocol Claude Code and Codex CLI both speak."""
    try:
        context = parse_context(sys.stdin.read(), agent=agent)
        project_directory = (
            os.environ.get(project_directory_variable)
            if project_directory_variable
            else None
        )
        raw_root = root or project_directory or str(context.cwd)
        result = _hook_evaluation(
            root=resolve_root(raw_root),
            config_path=config_path,
            state_directory=state_directory,
            session_id=context.session_id,
        )
        if result is not None:
            _json_output(blocking_output(build_review_message(result)))
    except MissingConfigError:
        # A repository holding no configuration never opted in, so saying so on
        # every turn would only spend the agent's context.
        return 0
    except (DocSyncError, OSError) as exc:
        _json_output(blocking_output(f"doc-sync could not complete its check: {exc}"))
    return 0


def _run_opencode_hook(
    *,
    root: str | None,
    config_path: str,
    state_directory: str | None,
    session_id: str,
) -> int:
    try:
        result = _hook_evaluation(
            root=resolve_root(root),
            config_path=config_path,
            state_directory=state_directory,
            session_id=session_id,
        )
    except MissingConfigError:
        return 0
    if result is None:
        return 0
    _json_output({**result.to_dict(), "message": build_review_message(result)})
    return EXIT_REVIEW_REQUIRED


def _run_toggle(
    *, root: str | None, state_directory: str | None, disabled: bool
) -> int:
    repository = resolve_root(root)
    state = "disabled" if disabled else "enabled"
    if set_disabled(_state_directory(repository, state_directory), disabled=disabled):
        print(f"doc-sync {state} for {repository}")
    else:
        print(f"doc-sync is already {state} for {repository}")
    return 0


def _run_status(*, root: str | None, state_directory: str | None) -> int:
    repository = resolve_root(root)
    disabled = is_disabled(_state_directory(repository, state_directory))
    print(f"doc-sync is {'disabled' if disabled else 'enabled'} for {repository}")
    return 0


INTEGRATIONS = ("claude", "codex", "opencode")


def _targets(raw_target: str) -> tuple[str, ...]:
    return INTEGRATIONS if raw_target == "all" else (raw_target,)


def _run_hook_install(
    *, target: str, root: str | None, dry_run: bool, force: bool
) -> int:
    from doc_sync.integrations.install import install_hooks  # noqa: PLC0415

    install_hooks(
        resolve_root(root),
        _targets(target),
        dry_run=dry_run,
        force=force,
    )
    return 0


def _run_hook_uninstall(*, target: str, root: str | None, dry_run: bool) -> int:
    from doc_sync.integrations.install import uninstall_hooks  # noqa: PLC0415

    uninstall_hooks(resolve_root(root), _targets(target), dry_run=dry_run)
    return 0


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", help="A path inside the target Git repository.")


def _add_repository_arguments(parser: argparse.ArgumentParser) -> None:
    _add_root_argument(parser)
    parser.add_argument(
        "--config",
        dest="config_path",
        default=CONFIG_FILENAME,
        help=f"Configuration path relative to the repository (default: {CONFIG_FILENAME}).",
    )


def _add_state_directory_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-directory")


def _add_stop_hook_arguments(
    parser: argparse.ArgumentParser,
    *,
    agent: str,
    project_directory_variable: str | None,
) -> None:
    _add_repository_arguments(parser)
    _add_state_directory_argument(parser)
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
    _add_state_directory_argument(check)
    source = check.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true", help="Check staged paths.")
    source.add_argument("--base", help="Check committed paths changed since this ref.")
    source.add_argument(
        "--paths-from", metavar="FILE", help="Read changed paths from FILE or `-`."
    )
    check.add_argument(
        "--format",
        dest="output_format",
        choices=("human", "json"),
        default="human",
    )
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

    disable = subparsers.add_parser(
        "disable", help="Switch doc-sync off for this checkout."
    )
    _add_root_argument(disable)
    _add_state_directory_argument(disable)
    disable.set_defaults(handler=_run_toggle, disabled=True)

    enable = subparsers.add_parser(
        "enable", help="Switch doc-sync back on for this checkout."
    )
    _add_root_argument(enable)
    _add_state_directory_argument(enable)
    enable.set_defaults(handler=_run_toggle, disabled=False)

    status = subparsers.add_parser("status", help="Report whether doc-sync is on.")
    _add_root_argument(status)
    _add_state_directory_argument(status)
    status.set_defaults(handler=_run_status)

    _add_hook_commands(subparsers.add_parser("hook", help="Run or manage agent hooks."))
    return parser


def _add_hook_commands(hook: argparse.ArgumentParser) -> None:
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
    _add_state_directory_argument(opencode)
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


def main(argv: list[str] | None = None) -> int:
    """Run the doc-sync CLI and return its stable exit code."""
    args = _build_parser().parse_args(argv)
    # Every remaining destination is named after a handler parameter, so the
    # parsed namespace unpacks straight into the selected handler's signature.
    options = {
        key: value for key, value in vars(args).items() if key not in _DISPATCH_KEYS
    }
    try:
        return int(args.handler(**options))
    except (DocSyncError, OSError) as exc:
        print(f"doc-sync error: {exc}", file=sys.stderr)
        return EXIT_ERROR
