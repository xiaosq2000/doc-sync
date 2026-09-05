# CLAUDE.md

This file gives coding agents the repository instructions they need when they
work on doc-sync.

## Build and development

The project uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync --all-groups
```

## Commands

```bash
uv run pytest
uv run pytest tests/unit/test_match.py
uv run pytest -k "globstar"
uv run pytest --cov --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

Ruff selects all rules, and ty treats all rules as errors. Both tools are pinned
in `uv.lock` and bounded in `pyproject.toml`. Upgrade them deliberately and fix
the resulting findings in the same commit.

## Product boundary

Doc-sync maps changed source paths to unchanged documents through a TOML
configuration. It has no LLM calls or heuristics. Its only runtime dependency
is `pathspec`.

The supported commands are `check`, `validate`, `hook`, `disable`, and `enable`.
Do not add command variants, agent installers, or a public Python API without a
demonstrated use case.

## Architecture

- `config.py` loads `[documents]`, rejects unknown or unsafe input, and checks
  that document targets exist during `validate`.
- `paths.py` anchors every source pattern to the repository root. Matching at
  any depth requires an explicit `**/` prefix. A leading `!` or `#` is an
  ordinary character.
- `match.py` implements pure matching. `evaluate()` must not access Git, files,
  hook input, or command output.
- `git.py` discovers the repository, lists worktree paths, and reads worktree,
  staged, or merge base changes. All Git calls go through `_run_git()`.
- `hook.py` parses the SessionStart and Stop protocols shared by Claude Code
  and Codex.
- `state.py` stores per session baselines, acknowledgements, and the local
  disable marker under `git rev-parse --git-path doc-sync`. It compares relevant
  file fingerprints against the session baseline.
- `cli.py` connects the modules and owns all human and JSON output.

## Hook rules

The Stop hook must return immediately when `stop_hook_active` is true. The
protocol field prevents continuation loops. The acknowledgement store serves a
different purpose and suppresses the same reminder across later turns in one
session.

SessionStart captures a baseline once per session and checkout. Resume and
compaction preserve it. Stop compares sources and documents against that
baseline, including changes committed during the session. A missing, corrupt,
or unsupported baseline is initialized silently. Clearing acknowledgements must
not clear the baseline. SessionStart operational errors go to stderr and exit
`0`, without Stop-specific blocking JSON.

A missing `doc-sync.toml` is silent only in `hook`. A malformed configuration
returns blocking JSON at Stop. Manual `check` and `validate` commands report
either error on stderr and exit `1`.

The disable marker affects only `hook`. Manual commands always run. Do not add a
disabled status to manual JSON output.

## Exit codes

- `0` means a manual check passed, or the hook completed.
- `1` means a manual command failed.
- `2` means documents need review.

## Testing

Fixtures in `tests/conftest.py` use `tmp_path`. Integration tests shell out to
Git and exercise command contracts. Unit tests cover configuration, matching,
paths, and state.

Mark tests that require POSIX filesystem behavior with
`@pytest.mark.posix_only`. The test setup skips them on Windows.

Changes to configuration behavior, JSON output, exit codes, or the Stop hook
must include contract tests and matching README updates.
