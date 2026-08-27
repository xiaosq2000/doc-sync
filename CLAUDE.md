# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and development

The project is managed with [uv](https://docs.astral.sh/uv/). This creates `.venv`, installs doc-sync in editable mode, and installs the development tools pinned in `uv.lock`:

```bash
uv sync --all-groups
```

## Commands

```bash
# Run all tests
uv run pytest

# Run a single test file, test case, or pattern
uv run pytest tests/unit/test_engine.py
uv run pytest tests/unit/test_engine.py::test_passes_when_all_documents_changed
uv run pytest -k "globstar"

# Run with coverage
uv run pytest --cov --cov-report=term-missing

# Lint and format
uv run ruff check .
uv run ruff format --check .

# Type check
uv run ty check
```

## Lint configuration

Ruff selects ALL rules with specific ignores configured in `pyproject.toml`. Tests have relaxed rules (no docstrings, assertions allowed, subprocess permitted, boolean positionals for `parametrize`). The `ty` type checker is set to treat all rules as errors.

Because both tools are configured at maximum strictness, a new release of either turns unrelated CI runs red. Both are version-pinned in `uv.lock` and bounded in `pyproject.toml`; upgrade them deliberately with `uv lock --upgrade-package ruff --upgrade-package ty` and fix the fallout in the same commit.

## Architecture

Doc-sync is a Python tool that maps changed source files to documentation review targets using a TOML configuration. It has no LLM calls or heuristics. Its only runtime dependency is `pathspec`; keep it that way unless there is a strong reason, because doc-sync runs as an agent Stop hook on every turn and is installed into other people's repositories via `uvx` and pre-commit.

### Layered design

Each layer has a strict boundary — `evaluate()` is pure and must never touch Git, file I/O, or agent protocols:

- **Model** (`model.py`) — frozen dataclasses: `Rule`, `Impact`, `Evaluation`, `Status`. All other layers depend on these.
- **Paths** (`paths.py`) — path normalization and `SourcePattern` matching, backed by `pathspec`'s `GitIgnoreBasicPattern`. Every pattern is compiled with a leading `/`, which anchors it to the repository root; matching at any depth is opt-in via an explicit `**/` prefix. This reproduces the semantics of the hand-rolled matcher it replaced, so configurations did not have to change. Anchoring also makes a leading `!` or `#` an ordinary character rather than gitignore negation or a comment. Do not drop the anchoring without treating it as a breaking config change.
- **Engine** (`engine.py`) — `evaluate(rules, changed_paths) -> Evaluation`. Pure function, no side effects. This is the public API.
- **Config** (`config.py`) — loads and validates `doc-sync.toml`. Structural validation via `load_config()`, repository-aware validation via `validate_repository_config()` (checks that paths/globs resolve).
- **Git** (`git.py`) — discovers repo root, resolves changed paths (worktree, staged, merge-base, or explicit file lists). All Git calls go through `_run_git()` which shells out to `git`.
- **State** (`state.py`) — per-session acknowledgement tracking under Git metadata (`git rev-parse --git-path doc-sync`). Uses content-hashing so the same reminder fires only once per distinct source/document/config state.
- **Render** (`render.py`) — builds human/agent-facing review messages from an `Evaluation`.
- **CLI** (`cli.py`) — wires layers together via argparse subcommands: `check`, `validate`, `init`, `hook`. `main()` unpacks the parsed `Namespace` into the selected handler's keyword parameters, so every argparse `dest` must match a parameter name on its handler and handlers never receive a `Namespace`.
- **Integrations** (`integrations/`) — agent-specific adapters:
  - `stop_hook.py` — shared Stop-hook protocol for Claude Code and Codex CLI (JSON stdin/stdout with `decision: "block"`).
  - `install.py` — conservative install/uninstall of hooks into `.claude/settings.json`, `.codex/hooks.json`, and `.opencode/plugins/doc-sync.ts`. Manages only its own entries; preserves everything else.

### Exit codes

- `0` — pass (no review needed), or hook ran successfully
- `1` — configuration or operational error
- `2` — documents need review

### Testing

Tests use `pytest`. Fixtures live in `tests/conftest.py`, all built on `tmp_path`:

- `root` — an empty directory, no Git.
- `empty_repository` — an initialized Git repo holding no files.
- `repository` — the `APPLICATION_RULE` source, document, and config, committed.
- `uncommitted_repository` — the same contents left dirty in the worktree.

`tests/support.py` holds the plain helpers: `git()`, `initialize_repository()`, `commit_all()`, `render_config()`, `write_config()`, and `APPLICATION_RULE`.

Mark a test `@pytest.mark.posix_only` when it needs POSIX filesystem or permission semantics; `pytest_runtest_setup` in `conftest.py` skips those on Windows. Integration tests in `tests/integration/` shell out to Git and exercise the CLI and installer; unit tests in `tests/unit/` test pure logic.

### Key constraint

Changes to configuration behavior, JSON output, exit codes, or agent adapters must include contract tests and corresponding README updates (per CONTRIBUTING.md).
