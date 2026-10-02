# Docstale

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Docstale reports documents that may be out of date. You map each document to
the source files it describes and stamp the document after you review it.
Docstale then reports every document whose sources changed after its stamp. It
uses a TOML file, a committed lockfile, and Git. It does not call an LLM or
guess what a change means.

## How it works

| Piece | Role |
| --- | --- |
| `docstale.toml` | Maps each document to the source patterns it depends on |
| `docstale.lock` | Records a fingerprint of each document's sources at its last review |
| `docstale check` | Reports documents whose sources changed since their stamp |
| `docstale stamp` | Records that you reviewed a document |
| `docstale hook` | Reminds Claude Code or Codex about documents that went stale during a session |

You commit the lock, so an agent, a pre-commit hook, CI, and other people all
get the same answer from the same files.

## Install

Docstale requires Python 3.11 or newer and Git.

```bash
uv tool install git+https://github.com/xiaosq2000/docstale.git
```

You can also run `pipx install git+https://github.com/xiaosq2000/docstale.git`.
The [installation guide](docs/installation.md) covers source installs, upgrades,
moving from doc-sync, and removal.

## Quick start

1. Create `docstale.toml` at the repository root:

   ```toml
   [documents]
   "README.md" = ["src/", "pyproject.toml"]
   "docs/api.md" = ["src/api/"]
   ```

2. Make sure each document is accurate, then stamp them all and commit the lock:

   ```bash
   docstale stamp --all
   git add docstale.toml docstale.lock
   ```

3. After later changes, run `docstale check`. Review each document it lists,
   update the document if needed, and run `docstale stamp <document>`.

4. Optionally add the [agent hook](#add-the-agent-hook), the
   [reviewer subagent](#review-with-a-subagent), and a
   [pre-commit or CI gate](#gate-commits-and-pull-requests).

## Configure documents

Each key in `[documents]` names a document, and its value lists the source
patterns that may affect it.

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

```bash
docstale check
docstale stamp README.md
docstale stamp --all
```

`check` compares each document's current fingerprint with the lock. A document
needs review when its sources have changed since it was stamped, or when it was
never stamped. The command always prints a result. It exits `0` when no document
needs review, `2` when review is required, and `1` for configuration or Git
errors.

`check` also validates the configuration. It fails when an exact document does
not exist or a glob key matches no document. Sources that match no file and sets
that no document uses produce warnings on stderr without changing the exit
code, so a shared configuration can refer to files that exist only on another
branch.

After you review a document, and update it if needed, record the review with
`docstale stamp` and the document's repository-relative path. Editing a document
does not record a review. `stamp --all` stamps every document, which is how a
repository starts using the lock. Every stamp also drops entries for documents
that are no longer configured.

A fingerprint covers the Git object id of every file that the document's sources
match, except the document itself. It is the same on every clone and platform.
Reverting a source change makes the document current again.

Entries in `docstale.lock` are separated by blank lines, so stamps of different
documents merge cleanly. When a merge leaves an entry in conflict, `check`
reports that document and `stamp` rewrites the file.

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

## Add the agent hook

Claude Code and Codex use the same `docstale hook` command. Add the following
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
            "command": "docstale hook",
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
            "command": "docstale hook",
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

The hook stays silent when no `docstale.toml` exists or no review is needed. A
broken configuration returns a continuation message at Stop so the agent can
report or fix it. SessionStart failures are reported on stderr without blocking
the session.

SessionStart saves a baseline with the fingerprint of every document. At Stop,
the hook asks for a review of each document whose fingerprint differs from both
the lock and the baseline. A document that already needed review when the
session started is left to `docstale check`, so a session that only reads files
or answers questions gets no reminder. The reminder lists every source that
changed since the document was stamped, and stamping the document clears it.
The baseline is preserved when the same session resumes or compacts.

Changes made by you or other tools in the same checkout during the session also
count, and so does a configuration change that alters a document's matched
files. Committing session edits does not hide them from the hook. Staging or
committing existing edits alone does not trigger a reminder. Restoring the
sources to their starting state removes the document from the reminder.

If a baseline is missing, corrupt, or from an unsupported version, the hook
saves the current fingerprints and stays silent. With only Stop configured, the
first Stop establishes the baseline, and only later edits can trigger a
reminder.

The agent protocol marks a continuation with `stop_hook_active`. Docstale lets
that continuation stop without running another check. It also remembers the
fingerprint at which it last reported each document in a session, so a document
is reported again only after its sources change again.

Baselines and acknowledgements live separately under
`git rev-parse --git-path docstale`. They contain document fingerprints, not
file contents. Clearing an acknowledgement preserves the baseline. No state file
enters the working tree, and linked worktrees have separate state.

To switch the hook off or on for the current checkout only, run
`docstale disable` or `docstale enable`. Manual `check` and `stamp` commands
still run while the hook is disabled. The switch is stored beside the hook state
under Git metadata.

## Review with a subagent

The hook reminder suggests a `docstale-reviewer` subagent when the agent has
one. The subagent reads the source diff and the document and reports whether
the document needs an update. It does not edit files or stamp documents, so the
main agent stays responsible for both. Without the subagent, the main agent
reviews each document itself.

For Claude Code, save the following as `.claude/agents/docstale-reviewer.md`:

```markdown
---
name: docstale-reviewer
description: Decides whether source changes require an update to one document that docstale reported. Use once for each reported document.
tools: Read, Grep, Glob, Bash
model: haiku
---

You review one document that docstale reported. You receive the document path,
the commit in its heading, and its changed sources. A document that was never
stamped has no commit to compare with, so answer `unsure` for it.

1. Run `git diff <commit> -- <sources>`. Read any listed source that the diff
   does not show, such as a new file.
2. Read the document.
3. Decide whether the changes make any statement in the document wrong or
   incomplete.

Answer with one verdict on the first line, followed by at most three lines:

- `unaffected` when nothing in the document needs to change.
- `affected`, followed by each section that is now wrong and why.
- `unsure`, followed by what you could not decide.

Do not edit files and do not run `docstale stamp`.
```

The main agent stamps `unaffected` documents, updates and then stamps
`affected` ones, and asks you about `unsure` ones. A small model keeps each
review cheap, and every stamp stays visible in the `docstale.lock` diff.

## Gate commits and pull requests

The repository publishes a `docstale` pre-commit hook. It runs `docstale check`,
which blocks a commit while a document needs review or the configuration is
invalid. It does not receive changed filenames.

```yaml
repos:
  - repo: https://github.com/xiaosq2000/docstale
    rev: <commit>
    hooks:
      - id: docstale
```

Pre-commit sets unstaged changes aside while hooks run, so stage
`docstale.lock` with the rest of the commit. It also hides the warnings of a
passing hook unless the hook sets `verbose: true`.

In CI, run the same check after checking out the repository:

```yaml
- uses: astral-sh/setup-uv@v6
- run: uvx --from git+https://github.com/xiaosq2000/docstale.git docstale check
```

A shallow checkout gives the right result. The report lists changed sources
only when the history includes the commit that recorded each stamp, so use
`fetch-depth: 0` if you want that list.

## License

Docstale is released under the [MIT License](LICENSE).
