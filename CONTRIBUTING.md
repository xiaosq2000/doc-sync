# Contributing

Bug reports should include the command, configuration, Git state, expected
result, and actual result. Remove private paths and repository content from
logs before posting them.

## Development setup

Doc-sync requires Python 3.11 or newer, Git, and
[uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
```

Run all checks before opening a pull request:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

Ruff selects every rule, and ty treats every rule as an error. Both tools are
pinned in `uv.lock` and bounded in `pyproject.toml`. Upgrade them deliberately
and fix new findings in the same change.

## Architecture

Doc-sync has one job. It maps changed source paths to unchanged documents from
the `[documents]` table in `doc-sync.toml`.

- `config.py` parses the configuration and validates document targets.
- `paths.py` normalizes paths and compiles anchored source patterns.
- `match.py` contains the pure matching function.
- `git.py` discovers the repository and changed paths.
- `hook.py` parses the shared Claude Code and Codex Stop protocol.
- `state.py` stores private hook acknowledgements and the local disable marker.
- `cli.py` implements `check`, `validate`, `hook`, `disable`, and `enable`.

Keep `evaluate()` free of Git, file access, hook input, and command output.
Internal Python classes are implementation details and are not a public API.

## Contracts

Changes to configuration behavior, JSON output, exit codes, or the Stop hook
must include contract tests and matching README updates.

The stable exit codes are:

- `0` means the check passed or the hook completed.
- `1` means a manual command failed.
- `2` means one or more documents need review.
