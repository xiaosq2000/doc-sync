# Doc-Sync

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![No Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#)

**Keep documentation honest as AI agents change your code.**

AI coding agents move fast — a single session can touch dozens of files across a
monorepo. Documentation drifts silently. By the time a human notices, the docs
describe a codebase that no longer exists.

Doc-sync is a deterministic guard that maps source files to the documents that
describe them. When a matched source changes and its document doesn't, doc-sync
blocks the agent and asks for a review — before the session ends, not weeks
later.

- **Deterministic.** No LLM calls, no heuristics — a TOML file maps sources to
  documents and the engine evaluates changed paths against it.
- **Zero dependencies.** Pure Python, nothing to install beyond the standard
  library.
- **Agent-native.** First-class hooks for Claude Code, Codex CLI, and OpenCode.
  One command wires each integration.
- **Git-aware.** Compares against HEAD, staged changes, merge bases, or explicit
  file lists. Acknowledgement state lives in Git metadata — no dotfiles in your
  working tree.

## Quick start

```bash
doc-sync init                    # create doc-sync.toml with starter rules
doc-sync validate --check-paths  # verify paths exist in the repo
doc-sync check                   # run the check
doc-sync hook install claude     # wire a Stop hook for Claude Code
```

## Install

Requires Python 3.11+ and Git.

```bash
# uv (recommended)
uv tool install git+https://github.com/xiaosq2000/doc-sync.git

# pipx
pipx install git+https://github.com/xiaosq2000/doc-sync.git
```

In a [pixi](https://pixi.sh) workspace, add doc-sync as a PyPI dependency in
`pixi.toml`:

```toml
[pypi-dependencies]
doc-sync = { git = "https://github.com/xiaosq2000/doc-sync.git" }
```

Or run once without installing:

```bash
uvx --from git+https://github.com/xiaosq2000/doc-sync.git doc-sync --help
```

See the [installation guide](docs/installation.md) for virtual-environment
setup, source checkouts, upgrades, uninstallation, and troubleshooting.

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

Documents are exact file paths — doc-sync intentionally does not accept document
globs because its output should identify concrete review targets.

## Validation

Structural validation catches malformed TOML, unknown fields, unsupported
versions, duplicate IDs, and unsafe paths:

```bash
doc-sync validate
```

Add `--check-paths` to also verify that every path and directory exists and every
glob matches at least one tracked file:

```bash
doc-sync validate --check-paths
```

A `doc-sync-validate` pre-commit hook and a JSON Schema at
`schemas/doc-sync.schema.json` are included in the repository.

## Selecting changes

By default, `doc-sync check` compares the working tree, index, and untracked
non-ignored files against `HEAD`:

```bash
doc-sync check
doc-sync check --staged
doc-sync check --base origin/main
doc-sync check --paths-from changed-files.txt
git diff --name-only -z HEAD^ | tr '\0' '\n' | doc-sync check --paths-from -
```

Use `--format json` for machine-readable output. Exit code `0` means no review
is needed; `2` means documents should be reviewed; `1` signals a configuration
or operational error.

## Agent hooks

Wire an integration without editing agent config files yourself:

```bash
doc-sync hook install claude
doc-sync hook install codex
doc-sync hook install opencode
doc-sync hook install all --dry-run
```

Each integration is placed where the agent expects it: a `Stop` entry in
`.claude/settings.json`, a `Stop` entry in `.codex/hooks.json`, or a generated
`.opencode/plugins/doc-sync.ts`. Existing hooks are preserved; doc-sync only
manages its own entries.

Remove managed wiring with:

```bash
doc-sync hook uninstall claude   # or codex, opencode, all
```

### Codex trust

Codex requires two extra steps before a hook runs: the repository must be a
trusted Codex project (offered on first launch), and the hook itself must be
reviewed from `/hooks` inside Codex. Doc-sync will not write trust records on
your behalf.

### Acknowledgement state

A review reminder fires once per agent session and relevant source/document
state. State lives under `git rev-parse --git-path doc-sync` — nothing is added
to the repository or `.gitignore`. Changing a matched source, document, rule, or
configuration triggers a new reminder; unrelated dirty files do not.

## License

Doc-sync is released under the [MIT License](LICENSE).
