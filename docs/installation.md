# Installation

Doc-sync requires Python 3.11 or newer and Git. Its only Python runtime
dependency is `pathspec`, which every install method below resolves for you.

The [README](../README.md#install) covers the recommended one-line installs
(`uv`, `pipx`, `pixi`). This guide covers source checkouts, virtual
environments, upgrades, uninstallation, and troubleshooting.

## Install from a source checkout

Clone the repository and run one of these commands from the directory containing
`pyproject.toml`:

Using `uv`:

```bash
uv tool install .
doc-sync --help
```

Using `pipx`:

```bash
pipx install .
doc-sync --help
```

If neither tool is available, install into a dedicated virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install .
doc-sync --help
```

On PowerShell, activate that environment with `.venv\Scripts\Activate.ps1`
instead.

To run doc-sync from a checkout without installing it:

```bash
uv run doc-sync --help
```

For package development, see [CONTRIBUTING.md](../CONTRIBUTING.md); `uv sync
--all-groups` sets up an editable install alongside the test and lint tools.

## Upgrade

Update the source checkout, return to the directory containing
`pyproject.toml`, and reinstall with the same tool:

```bash
uv tool install --force .
pipx install --force .
```

For a virtual environment, use `python -m pip install --upgrade .`.

Upgrading does not rewrite agent wiring. Re-run `doc-sync hook install all` if a
release changes the generated hook command; the installer updates existing
doc-sync wiring in place rather than appending a second entry.

Re-running it is required after upgrading from a version that wired hooks
through `bin/doc-sync`. Those commands looked like
`python3 "$CLAUDE_PROJECT_DIR/bin/doc-sync" hook claude`; the launcher no longer
exists, and every integration now invokes the installed `doc-sync` command.

## Uninstall

Doc-sync writes to three places: the agent wiring it manages, the repository's
own `doc-sync.toml`, and per-session state under Git metadata. Remove the wiring
first, while the command is still installed.

To quiet doc-sync in one repository without uninstalling anything, run
`doc-sync disable` there instead; see
[Switching doc-sync off](../README.md#switching-doc-sync-off).

### 1. Remove the managed agent wiring

Run this inside every repository that has an integration installed:

```bash
doc-sync hook uninstall all --dry-run
doc-sync hook uninstall all
```

`--dry-run` prints the planned changes without touching anything. Name a single
integration — `claude`, `codex`, or `opencode` — to remove just that one, and
pass `--root /path/to/repository` to act on a repository you are not inside.

Only wiring doc-sync manages is removed: the `Stop` entries it added to
`.claude/settings.json` and `.codex/hooks.json`, and the generated
`.opencode/plugins/doc-sync.ts`. Your own hooks and settings in those files are
left exactly as they were. An OpenCode plugin that doc-sync did not generate is
refused rather than deleted:

```text
doc-sync error: <path> is not managed by doc-sync; refusing to remove it
```

Delete such a file yourself once you have confirmed it is no longer wanted.
Running with nothing installed reports `no selected doc-sync hooks were
installed` and exits `0`, so the command is safe to repeat.

### 2. Remove the repository's own files

Uninstalling hooks deliberately keeps your configuration, so remove it
explicitly along with the accumulated session state:

```bash
rm "$(git rev-parse --show-toplevel)/doc-sync.toml"
rm -rf "$(git rev-parse --git-path doc-sync)"
```

Both forms resolve from anywhere inside the repository. The state path is also
worktree-aware — `.git/doc-sync` in a primary worktree and
`.git/worktrees/<name>/doc-sync` in a linked one — so repeat the second command
in each worktree that ran an agent hook. Removing that directory also clears the
`disabled` marker written by `doc-sync disable`. Neither path is tracked, so
nothing needs to be committed.

If `.claude/settings.json`, `.codex/hooks.json`, or `.opencode/` existed only
for doc-sync, they may now be empty and can be removed as well. Codex keeps its
own trust record for a hook it has seen; clear that from `/hooks` inside Codex.
If you wired the `doc-sync-validate` pre-commit hook, drop its entry from
`.pre-commit-config.yaml`; `pre-commit gc` then clears its cached environment.

### 3. Remove the tool

```bash
uv tool uninstall doc-sync
pipx uninstall doc-sync
```

For a virtual environment, run `python -m pip uninstall doc-sync` or delete the
environment directory.

## Troubleshooting

- If the command is not found after a `uv` installation, run
  `uv tool update-shell` and open a new shell.
- If the command is not found after a `pipx` installation, run
  `pipx ensurepath` and open a new shell.
- If doc-sync cannot locate a repository, run it inside a Git worktree or pass
  `--root /path/to/repository` to the command.
- If an installed Codex hook never fires, check `/hooks` inside Codex. An entry
  that is missing means the repository is not a trusted Codex project; an entry
  listed as `untrusted` or `modified` needs review there.
- Exit code `2` from `doc-sync check` means documentation review is required;
  it is not an operational failure. Exit code `1` reports configuration or Git
  errors.
