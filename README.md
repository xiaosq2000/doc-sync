# Doc-Sync

Doc-sync maps changed source files to documentation that should be reviewed. It
is a deterministic Git-based guard for agent-assisted repositories: it does not
generate documentation, inspect prose quality, or claim that two files are
semantically synchronized.

The same rule engine supports manual checks, pre-commit validation, Claude Code
`Stop` hooks, and OpenCode `session.idle` plugins.

> Doc-sync is intentionally not published to PyPI yet. Install it manually from
> a source checkout using the [installation guide](docs/installation.md).

## Requirements

- Python 3.11 or newer
- Git
- No Python runtime dependencies

## Installation

Use an isolated application environment when possible. The
[installation guide](docs/installation.md) covers `uv`, `pipx`, virtual
environments, running without installation, upgrades,
[uninstallation](docs/installation.md#uninstall), and PATH troubleshooting.

## Quick start

From an installed package:

```bash
doc-sync init
doc-sync validate --check-paths
doc-sync check
doc-sync hook install claude
doc-sync hook install opencode
```

From a source checkout, replace `doc-sync` with `python3 bin/doc-sync`.

`doc-sync check` returns `0` when no review is required, `2` when documents
should be reviewed, and `1` for configuration or operational errors.

## Configuration

Project-specific mappings live at the repository root in `doc-sync.toml`:

```toml
config_version = 1

[[rules]]
id = "public-api"
sources = [
  "src/",
  "pyproject.toml",
]
documents = [
  "README.md",
  "docs/api.md",
]
```

Each rule needs a stable, unique lowercase `id`. When any `sources` pattern
matches a changed path, every unchanged `documents` entry becomes a review
target.

Source patterns are repository-relative and case-sensitive:

- `path/to/file.toml` matches one exact file.
- `path/to/dir/` matches that directory recursively.
- `src/*.py` keeps `*` within one path segment.
- `**/*.py` uses globstar semantics and matches top-level and nested files.

Documents are exact file paths. Doc-sync intentionally does not accept document
globs because its output should identify concrete review targets.

## Validation

Structural validation rejects malformed TOML, unknown fields, unsupported
versions, duplicate rule identifiers, duplicate normalized paths, unsafe
relative paths, and document entries that use glob or directory syntax:

```bash
doc-sync validate
```

Repository-aware validation additionally requires exact paths and directories to
exist and every source glob to match at least one tracked or untracked
non-ignored file:

```bash
doc-sync validate --check-paths
```

The repository ships a `doc-sync-validate` pre-commit hook and a JSON Schema at
`schemas/doc-sync.schema.json`.

## Selecting changes

The default compares the working tree, index, and untracked non-ignored files
with `HEAD`:

```bash
doc-sync check
```

Other inputs are explicit:

```bash
doc-sync check --staged
doc-sync check --base origin/main
doc-sync check --paths-from changed-files.txt
git diff --name-only -z HEAD^ | tr '\0' '\n' | doc-sync check --paths-from -
```

Use `--format json` for machine-readable output. The domain status is `pass` or
`review_required`; agent adapters translate that status into their own protocol.

## Agent hooks

Install integrations without changing an existing config:

```bash
doc-sync hook install claude
doc-sync hook install opencode
doc-sync hook install all --dry-run
```

The installer validates every requested integration before writing, updates
older doc-sync wiring in place, and refuses to replace an unrelated OpenCode
plugin unless `--force` is supplied. Remove only managed wiring with:

```bash
doc-sync hook uninstall claude
doc-sync hook uninstall opencode
```

This removes managed wiring only and keeps `doc-sync.toml`. See
[Uninstall](docs/installation.md#uninstall) for removing the configuration and
session state as well.

The Claude adapter returns structured `decision = "block"` JSON with exit code
`0`, as required by Claude Code's Stop-hook protocol. The OpenCode adapter uses
exit code `2` and structured output consumed by the generated plugin.

### Acknowledgement state

A review reminder blocks once per agent session and relevant source/document
state. State lives under the worktree-aware Git metadata path returned by
`git rev-parse --git-path doc-sync`; it does not add files to the repository or
require a `.gitignore` entry.

Changing a matched source, affected document, rule, or configuration causes a
new reminder. Unrelated dirty files do not.

## Python API

The public engine is pure:

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

## Development

Run the source tests and checks through the enclosing workspace's Pixi tasks:

```bash
pixi run -e style ruff check tools/doc-sync
pixi run -e style ruff format --check tools/doc-sync
pixi run -e style python -m unittest discover -s tools/doc-sync/tests -v
```

The project still needs a standalone GitHub repository and repository URLs.
PyPI publishing is intentionally disabled; tagged builds create artifacts for
manual installation only.

## License

Doc-sync is released under the [MIT License](LICENSE).
