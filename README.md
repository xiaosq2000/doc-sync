# Doc-Sync

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Doc-sync finds documents that may need review after source files change. It
uses a repository configuration and Git. It does not call an LLM or guess what
the source change means.

## Install

Doc-sync requires Python 3.11 or newer and Git.

```bash
uv tool install git+https://github.com/xiaosq2000/doc-sync.git
```

You can also use `pipx`:

```bash
pipx install git+https://github.com/xiaosq2000/doc-sync.git
```

See the [installation guide](docs/installation.md) for source installs,
upgrades, and removal.

## Configure documents

Create `doc-sync.toml` at the repository root. Each key in `[documents]` is an
exact document path. Its value is a list of source patterns that may affect the
document.

```toml
[documents]
"README.md" = [
  "src/**",
  "pyproject.toml",
]

"docs/api.md" = [
  "src/api/**",
]
```

When a source pattern matches a changed file and the document is unchanged,
doc-sync asks for a review. A changed document needs no further review.

Source patterns are relative to the repository root and are case sensitive.

- `pyproject.toml` matches one root file.
- `src/` matches every file under the root `src` directory.
- `src/*.py` matches Python files directly inside `src`.
- `**/*.py` matches Python files at any depth.

Every pattern is anchored to the repository root. For example, `src/` does not
match `vendor/src/`. Use an explicit `**/` prefix when a pattern should match at
any depth.

Documents must be exact paths. Document globs are not accepted because every
result must name a concrete file.

## Check changes

Run a check against the working tree, staged files, or a merge base:

```bash
doc-sync check
doc-sync check --staged
doc-sync check --base origin/main
```

A manual check always prints a result. It exits `0` when no document needs
review, `2` when review is required, and `1` for configuration or Git errors.

Use `--json` for scripts:

```json
{
  "documents": [
    {
      "path": "README.md",
      "sources": ["src/client.py"]
    }
  ],
  "status": "review_required"
}
```

Validate the configuration and require every document to exist:

```bash
doc-sync validate
```

Source patterns do not have to match a file on the current branch. A shared
configuration can therefore refer to files that exist only on another branch.

## Add a Stop hook

Claude Code and Codex use the same `doc-sync hook` command. Add the following
Stop entry to `.claude/settings.json` or `.codex/hooks.json`, while preserving
any settings and hooks already in the file:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "doc-sync hook",
            "timeout": 30,
            "statusMessage": "Checking documentation impact..."
          }
        ]
      }
    ]
  }
}
```

Codex requires project hooks to be trusted. Open Codex in the repository and
use `/hooks` to review the entry.

The hook stays silent when no `doc-sync.toml` exists or no review is needed. A
broken configuration returns a continuation message so the agent can report or
fix it.

The agent protocol marks a continuation with `stop_hook_active`. Doc-sync lets
that continuation stop without running another check. It also remembers the
last review shown in each session, so unchanged source state does not produce a
reminder on every later turn. A change to a relevant source, document, or
configuration produces a new reminder.

Acknowledgement state lives under `git rev-parse --git-path doc-sync`. No state
file enters the working tree.

## Disable the Stop hook locally

Disable or enable only the automatic Stop hook for the current checkout:

```bash
doc-sync disable
doc-sync enable
```

Manual `check` and `validate` commands still run while the hook is disabled.
The switch is local to one checkout and is stored beside acknowledgement state
under Git metadata.

## Pre-commit

The repository publishes a `doc-sync-validate` pre-commit hook. It runs
`doc-sync validate` and does not receive changed filenames.

## License

Doc-sync is released under the [MIT License](LICENSE).
