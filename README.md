# Docstale

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

A code change does not tell you which documents it made wrong. Docstale lists
every document whose source files changed since someone last reviewed it.

![An agent renames connect() to open() in src/client.py. README.md still says connect(), so the docstale Stop hook reports README.md with the changed source. A reviewer subagent finds the Usage section affected, the agent updates README.md, and docstale stamp records the review in docstale.lock.](docs/assets/agent-session.svg)

## How it works

- You list the source files that each document describes in `docstale.toml`.
- After you review a document, `docstale stamp` records its sources in
  `docstale.lock`.
- `docstale check` lists each document whose sources changed since its stamp.

Docstale compares Git object ids. It does not call an LLM or guess what a change
means. You commit the lock, so your agent, pre-commit, CI, and teammates all get
the same answer.

## Quick start

You need Python 3.11 or newer and Git.

1. Install docstale:

   ```bash
   uv tool install git+https://github.com/xiaosq2000/docstale.git
   ```

2. Create `docstale.toml` at the repository root. Each line maps a document to
   the files it describes:

   ```toml
   [documents]
   "README.md" = ["src/", "pyproject.toml"]
   "docs/api.md" = ["src/api/"]
   ```

3. Check that these documents are accurate today, then stamp them and commit the
   lock:

   ```bash
   docstale stamp --all
   git add docstale.toml docstale.lock
   ```

4. After you change code, run the check:

   ```bash
   docstale check
   ```

   Its output starts with each document to review and the sources that changed:

   ```text
   Documentation needs review.

   README.md (changed since 9c1b2e7d41f0)
     src/client.py
   ```

5. Read the document, fix it if needed, and stamp it. Stamp it even when nothing
   needed fixing:

   ```bash
   docstale stamp README.md
   ```

Editing a document does not count as a review. Only `docstale stamp` clears it.

## Remind your coding agent

Claude Code and Codex can run docstale when a session starts and when the agent
finishes a turn. If the agent changed sources of a document, docstale asks it to
review that document before it stops.

1. Add these hooks to `.claude/settings.json` or `.codex/hooks.json`. Keep the
   settings that are already in the file:

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

2. In Codex, open `/hooks` and trust the new entry.

3. Optional, for Claude Code: add the reviewer subagent. It runs on a small
   model, reads the diff and the document, and answers `unaffected`,
   `affected`, or `unsure`. It never edits or stamps files.

   ```bash
   mkdir -p .claude/agents
   curl -o .claude/agents/docstale-reviewer.md https://raw.githubusercontent.com/xiaosq2000/docstale/main/.claude/agents/docstale-reviewer.md
   ```

To pause the hook in one checkout, run `docstale disable`. Run `docstale enable`
to turn it back on.

## Block commits and pull requests

To block a commit while a document needs review, add the pre-commit hook:

```yaml
repos:
  - repo: https://github.com/xiaosq2000/docstale
    rev: <commit>
    hooks:
      - id: docstale
```

Stage `docstale.lock` with the rest of the commit.

To fail CI instead, add this step after the checkout:

```yaml
- uses: astral-sh/setup-uv@v6
- run: uvx --from git+https://github.com/xiaosq2000/docstale.git docstale check
```

`docstale check` exits `0` when no document needs review, `2` when one does, and
`1` when the configuration or Git fails.

## Learn more

| Topic | Page |
| --- | --- |
| Patterns, shared lists, globs, and `{dir}` | [Configure documents](docs/reference.md#configure-documents) |
| Fingerprints, merges, and JSON output | [Check and stamp documents](docs/reference.md#check-and-stamp-documents) |
| When the hook reminds the agent | [Agent hook](docs/reference.md#agent-hook) |
| What the reviewer subagent does | [Reviewer subagent](docs/reference.md#reviewer-subagent) |
| Pre-commit and CI details | [Pre-commit and CI](docs/reference.md#pre-commit-and-ci) |
| `pipx`, upgrades, moving from doc-sync, and removal | [Installation guide](docs/installation.md) |
| Development setup and architecture | [Contributing](CONTRIBUTING.md) |

## License

Docstale is released under the [MIT License](LICENSE).
