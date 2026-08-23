# Contributing

Thank you for helping improve doc-sync. Bug reports should include the command,
configuration, Git state, expected result, and actual result. Remove private
paths or repository contents before posting logs.

## Development setup

Doc-sync requires Python 3.11 or newer and has no runtime dependencies.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --editable .
python -m pip install ruff ty
```

Run the checks before opening a pull request:

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
ty check
```

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
