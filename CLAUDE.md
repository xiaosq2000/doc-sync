# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and development

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install --editable .
python -m pip install ruff ty
```

## Commands

```bash
# Run all tests
python -m unittest discover -s tests -v

# Run a single test file or test case
python -m unittest tests.unit.test_engine -v
python -m unittest tests.unit.test_engine.TestEvaluate.test_matched_source -v

# Lint and format
ruff check .
ruff format --check .

# Type check
ty check
```

## Lint configuration

Ruff selects ALL rules with specific ignores configured in `pyproject.toml`. Tests have relaxed rules (no docstrings, assertions allowed, subprocess permitted). The `ty` type checker is set to treat all rules as errors.

## Architecture

Doc-sync is a zero-dependency Python tool that maps changed source files to documentation review targets using a TOML configuration. It has no LLM calls or heuristics.

### Layered design

Each layer has a strict boundary — `evaluate()` is pure and must never touch Git, file I/O, or agent protocols:

- **Model** (`model.py`) — frozen dataclasses: `Rule`, `Impact`, `Evaluation`, `Status`. All other layers depend on these.
- **Paths** (`paths.py`) — path normalization and `SourcePattern` matching (directory prefix, literal, glob/globstar via memoized segment matching).
- **Engine** (`engine.py`) — `evaluate(rules, changed_paths) -> Evaluation`. Pure function, no side effects. This is the public API.
- **Config** (`config.py`) — loads and validates `doc-sync.toml`. Structural validation via `load_config()`, repository-aware validation via `validate_repository_config()` (checks that paths/globs resolve).
- **Git** (`git.py`) — discovers repo root, resolves changed paths (worktree, staged, merge-base, or explicit file lists). All Git calls go through `_run_git()` which shells out to `git`.
- **State** (`state.py`) — per-session acknowledgement tracking under Git metadata (`git rev-parse --git-path doc-sync`). Uses content-hashing so the same reminder fires only once per distinct source/document/config state.
- **Render** (`render.py`) — builds human/agent-facing review messages from an `Evaluation`.
- **CLI** (`cli.py`) — wires layers together via argparse subcommands: `check`, `validate`, `init`, `hook`.
- **Integrations** (`integrations/`) — agent-specific adapters:
  - `stop_hook.py` — shared Stop-hook protocol for Claude Code and Codex CLI (JSON stdin/stdout with `decision: "block"`).
  - `install.py` — conservative install/uninstall of hooks into `.claude/settings.json`, `.codex/hooks.json`, and `.opencode/plugins/doc-sync.ts`. Manages only its own entries; preserves everything else.

### Exit codes

- `0` — pass (no review needed), or hook ran successfully
- `1` — configuration or operational error
- `2` — documents need review

### Testing

Tests use `unittest` (no pytest). The `tests/support.py` module provides `temporary_repository()` (context manager yielding a temp Git repo with a committed source, document, and config) and helpers like `git()`, `commit_all()`, `render_config()`. Integration tests in `tests/integration/` shell out to Git and exercise the CLI and installer; unit tests in `tests/unit/` test pure logic.

### Key constraint

Changes to configuration behavior, JSON output, exit codes, or agent adapters must include contract tests and corresponding README updates (per CONTRIBUTING.md).
