# Doc-Sync

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

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
- **Lightweight.** Pure Python with a single dependency, `pathspec`, for
  gitignore-style pattern matching.
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
doc-sync disable                 # switch it off here; `enable` switches it back
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

Every pattern is anchored to the repository root, so `pyproject.toml` names the
root file and `src/` never matches a nested `vendor/src/`. Matching at any depth
is opt-in through an explicit `**/` prefix: `app.py` is the root file, while
`**/app.py` is that file anywhere in the repository.

Documents are exact file paths — doc-sync intentionally does not accept document
globs because its output should identify concrete review targets.

A repository holding no `doc-sync.toml` has not opted in, so its agent hooks stay
silent rather than reporting the absence on every turn. Run `doc-sync init` to
opt in. An invalid configuration is a different matter and still blocks with an
explanation.

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
is needed — or that doc-sync is switched off here; `2` means documents should be
reviewed; `1` signals a configuration or operational error.

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

### Switching doc-sync off

To quiet doc-sync for a while without touching your agent configuration:

```bash
doc-sync disable
doc-sync status    # doc-sync is disabled for /path/to/repo
doc-sync enable
```

While disabled, `doc-sync check` and every agent hook exit `0` and print nothing
at all — a disabled checkout costs an agent zero context on every turn.
`doc-sync check --format json` reports `"status": "disabled"` for scripts that
need to tell the two apart. `validate`, `init`, and `hook install`/`uninstall`
ignore the switch, so you can still lint your configuration and manage wiring
while it is off.

The switch is a marker file beside the acknowledgement state, under
`git rev-parse --git-path doc-sync`. It is local to one checkout: nothing is
committed, nothing enters your working tree, and a fresh clone — including the
one your CI makes — is always enabled. Like the acknowledgement state, it is
scoped to a single worktree, so a linked worktree carries its own switch.

To remove the integration outright rather than quiet it, use
`doc-sync hook uninstall`.

## License

Doc-sync is released under the [MIT License](LICENSE).
