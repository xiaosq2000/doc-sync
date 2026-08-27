# Contributing

Thank you for helping improve doc-sync. Bug reports should include the command,
configuration, Git state, expected result, and actual result. Remove private
paths or repository contents before posting logs.

## Development setup

Doc-sync requires Python 3.11 or newer, Git, and [uv](https://docs.astral.sh/uv/).
Its only runtime dependency is `pathspec`.

```bash
uv sync --all-groups
```

That creates `.venv`, installs doc-sync in editable mode, and installs the
development tools pinned in `uv.lock`. Run the checks before opening a pull
request:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

Useful variations:

```bash
uv run pytest tests/unit/test_engine.py       # one file
uv run pytest -k "globstar"                   # one pattern
uv run pytest --cov --cov-report=term-missing # with coverage
```

`ruff` selects every rule and `ty` treats every rule as an error, so both are
version-pinned in `uv.lock`. Bump them deliberately with
`uv lock --upgrade-package ruff --upgrade-package ty` and fix whatever the new
release reports in the same commit.

Changes to configuration behavior, JSON output, exit codes, or agent adapters
must include contract tests and corresponding README updates.

## Architecture

Doc-sync is layered so each concern stays separate:

- **Engine** (`doc_sync.evaluate`) — pure function. Takes a list of rules and a
  list of changed paths, returns which documents need review. No Git calls, no
  file I/O, no side effects.
- **Configuration** — loads and validates `doc-sync.toml`.
- **Git** — discovers the repository, resolves changed paths against HEAD,
  staged index, merge bases, or explicit file lists.
- **Acknowledgement state** — tracks per-session review state under Git metadata
  so a reminder fires only once per relevant change.
- **CLI** — wires the layers together and formats output.
- **Agent adapters** — translate the domain status (`pass` / `review_required`)
  into each agent's protocol: structured `decision = "block"` JSON for Claude
  Code and Codex CLI Stop hooks, exit code 2 with structured output for OpenCode
  plugins.

Keep `evaluate()` independent of Git, file I/O, session state, and agent
protocols.

## Python API

The public engine is intentionally pure:

```python
from doc_sync import Rule, evaluate

result = evaluate(
    [Rule(id="api", sources=("src/",), documents=("docs/api.md",))],
    ["src/client.py"],
)
```

`evaluate()` performs no Git calls and reads or writes no files. Configuration,
Git discovery, acknowledgement state, CLI formatting, and agent protocols are
separate layers.
