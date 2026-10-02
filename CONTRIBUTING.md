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

Doc-sync has one job. It reports documents whose sources changed since their
last recorded review, using the `[documents]` table in `doc-sync.toml` and the
fingerprints in `doc-sync.lock`.

- `config.py` parses the configuration, expands document globs, sets, and
  `{dir}`, and validates document targets.
- `paths.py` normalizes paths and compiles anchored source patterns.
- `match.py` contains the pure matching and fingerprint functions.
- `lock.py` reads and writes `doc-sync.lock`.
- `git.py` discovers the repository, changed paths, and Git object ids.
- `hook.py` parses the shared Claude Code and Codex Stop protocol.
- `state.py` stores session fingerprints, reminder state, and the local disable
  marker.
- `cli.py` implements `check`, `stamp`, `hook`, `disable`, and `enable`.

Keep `match.py` and `Config.resolve()` free of Git, file access, hook input,
and command output.
Internal Python classes are implementation details and are not a public API.

## Contracts

Changes to configuration behavior, JSON output, exit codes, or the Stop hook
must include contract tests and matching README updates.

The stable exit codes are:

- `0` means the check passed or the hook completed.
- `1` means a manual command failed.
- `2` means one or more documents need review.
