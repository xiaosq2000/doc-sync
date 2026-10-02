# Doc-Sync

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Doc-sync finds documents that may need review after source files change. It
uses a repository configuration, a committed record of reviews, and Git. It
does not call an LLM or guess what the source change means.

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

Create `doc-sync.toml` at the repository root. Each key in `[documents]` names
a document, and its value lists the source patterns that may affect it.

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

`doc-sync check` reports a document when the files its sources match have
changed since its last review was stamped. The [Stop hook](#add-a-stop-hook)
reports a document when a source changed during the session and the document
did not.

### Source patterns

Source patterns are relative to the repository root and are case sensitive.

- `pyproject.toml` matches one root file.
- `src/` matches every file under the root `src` directory.
- `src/*.py` matches Python files directly inside `src`.
- `**/*.py` matches Python files at any depth.

Every pattern is anchored to the repository root. For example, `src/` does not
match `vendor/src/`. Use an explicit `**/` prefix when a pattern should match at
any depth.

A directory pattern without glob characters, such as `vendor/lib/`, also
matches a submodule or symlink at that path. A submodule counts as changed when
its commit changes, not when files inside it are edited.

### Shared source lists

A `[sets]` table names a source list once so that several documents can include
it. A source written as `@name` inserts the set with that name.

```toml
[sets]
build = ["pixi.toml", "pyproject.toml"]

[documents]
"README.md" = ["@build", "src/"]
"docs/development.md" = ["@build", "scripts/"]
```

Set names use lowercase letters, digits, `-`, and `_`. A set cannot include
another set. Write `./@name` for a root path that starts with `@`.

### Document globs and directory templates

A key that contains `*`, `?`, or `[` is a glob. It names every matching file
that Git tracks, plus untracked files that Git does not ignore. Files created
later are included automatically, and each result is still a concrete document.
A source that starts with `{dir}` is relative to the directory of each document.

```toml
[documents]
"packages/*/README.md" = ["{dir}/"]
"packages/*/docs/architecture.md" = ["{dir}/../src/"]
```

Each package README watches its own package, and each architecture document
watches the `src` directory beside its `docs` directory. A template cannot climb
above the repository root.

When several keys name the same document, the document watches the sources of
all of them. An exact key can therefore add sources to a document that a glob
already covers.

## Check and stamp documents

`doc-sync.lock` records a fingerprint of each document's sources at its last
review. Commit it together with the documents and sources it describes.

```bash
doc-sync check
doc-sync stamp README.md
doc-sync stamp --all
```

`check` compares each document's current fingerprint with the lock. A document
needs review when its sources have changed since it was stamped, or when it was
never stamped. The command always prints a result. It exits `0` when no document
needs review, `2` when review is required, and `1` for configuration or Git
errors.

After you review a document, and update it if needed, record the review with
`doc-sync stamp` and the document's repository-relative path. Editing a document
does not record a review. `stamp --all` stamps every document, which is how a
repository starts using the lock. Every stamp also drops entries for documents
that are no longer configured.

A fingerprint covers the Git object id of every file that the document's sources
match, except the document itself. It is the same on every clone and platform,
so a pre-commit hook, CI, and other people all get the same answer. Reverting a
source change makes the document current again.

Entries are separated by blank lines, so stamps of different documents merge
cleanly. When a merge leaves an entry in conflict, `check` reports that document
and `stamp` rewrites the file.

Use `--json` for scripts:

```json
{
  "documents": [
    {
      "path": "README.md",
      "since": "9c1b2e7d41f0a3c2b5e8d6f4a1c0b9e8d7f6a5c4",
      "sources": ["src/client.py"],
      "stamped": true
    }
  ],
  "status": "review_required"
}
```

`since` is the commit that recorded the current stamp. For a stamp that is not
committed yet, it is the commit at `HEAD`. `sources` lists the matched files that
changed since that commit. A document that was never stamped has `stamped` set
to `false`, `since` set to `null`, and no sources.

Validate the configuration:

```bash
doc-sync validate
```

Validation fails when an exact document does not exist or a glob key matches no
document. Sources that match no file and sets that no document uses produce
warnings on stderr, and the command still exits `0`. A shared configuration can
therefore refer to files that exist only on another branch.

## Add a Stop hook

Claude Code and Codex use the same `doc-sync hook` command. Add the following
SessionStart and Stop entries to `.claude/settings.json` or `.codex/hooks.json`,
while preserving any settings and hooks already in the file:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "doc-sync hook",
            "timeout": 30
          }
        ]
      }
    ],
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
broken configuration returns a continuation message at Stop so the agent can
report or fix it. SessionStart failures are reported on stderr without blocking
the session.

SessionStart saves a baseline of tracked and non-ignored untracked files. Stop
checks for changes since that baseline, so pre-existing edits do not trigger a
reminder when the agent only reads files or answers questions. A document edited
before the session does not suppress review of source changes made during the
session. The baseline is preserved when the same session resumes or compacts.

Changes made by you or other tools in the same checkout during the session also
count. Committing session edits does not hide them from the hook. Staging or
committing existing edits alone does not trigger a reminder. Restoring a file to
its starting state removes it from the session's changes.

If a baseline is missing, corrupt, or from an unsupported version, the hook
saves the current state and stays silent. Existing installations should add the
SessionStart entry and start a new session to detect edits in the first
response. With only Stop configured, the first Stop establishes the baseline,
and only later edits can trigger a reminder.

The agent protocol marks a continuation with `stop_hook_active`. Doc-sync lets
that continuation stop without running another check. It also remembers the
last review shown in each session, so unchanged source state does not produce a
reminder on every later turn. A change to a relevant source, document, or
configuration produces a new reminder.

Baselines and acknowledgements live separately under
`git rev-parse --git-path doc-sync`. Baselines contain file fingerprints, not
file contents. Clearing an acknowledgement preserves the baseline. No state
file enters the working tree, and linked worktrees have separate state.

## Disable the Stop hook locally

Disable or enable only the automatic Stop hook for the current checkout:

```bash
doc-sync disable
doc-sync enable
```

Manual `check`, `stamp`, and `validate` commands still run while the hook is
disabled.
The switch is local to one checkout and is stored beside acknowledgement state
under Git metadata.

## Pre-commit

The repository publishes two pre-commit hooks. Neither receives changed
filenames.

| Hook | Command | Use |
| --- | --- | --- |
| `doc-sync-validate` | `doc-sync validate` | Catch configuration errors |
| `doc-sync-check` | `doc-sync check` | Block commits while documents need review |

Pre-commit sets unstaged changes aside while hooks run, so stage
`doc-sync.lock` with the rest of the commit. It also hides the warnings of a
passing hook unless the hook sets `verbose: true`.

## License

Doc-sync is released under the [MIT License](LICENSE).
