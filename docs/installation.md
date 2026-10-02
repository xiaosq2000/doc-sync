# Installation

Docstale requires Python 3.11 or newer and Git.

## Install the command

Install with `uv`:

```bash
uv tool install git+https://github.com/xiaosq2000/docstale.git
docstale --help
```

Or install with `pipx`:

```bash
pipx install git+https://github.com/xiaosq2000/docstale.git
docstale --help
```

For a source checkout, run one of the following commands from the directory
that contains `pyproject.toml`:

```bash
uv tool install .
pipx install .
```

For project development, use `uv sync --all-groups` instead. It creates an
editable install and installs the test, lint, and type checking tools.

## Upgrade

Upgrade the installed command with the same tool:

```bash
uv tool install --force git+https://github.com/xiaosq2000/docstale.git
pipx upgrade docstale
```

Docstale does not edit agent configuration. A command change therefore requires
you to update the Stop entry in `.claude/settings.json` or `.codex/hooks.json`.

## Move from doc-sync

Docstale is the new name of doc-sync, and it reads only its own files. To move a
repository:

1. Run `git mv doc-sync.toml docstale.toml`. Rename `doc-sync.lock` to
   `docstale.lock` the same way if it exists.
2. Replace `doc-sync hook` with `docstale hook` in `.claude/settings.json` and
   `.codex/hooks.json`.
3. Replace `doc-sync validate` with `docstale check`, and replace the
   `doc-sync-validate` or `doc-sync-check` pre-commit hook with `docstale`.
4. Uninstall doc-sync, install docstale, and run `docstale stamp --all` if the
   repository has no lock yet.

Docstale ignores hook state under `git rev-parse --git-path doc-sync`, so you can
delete that directory.

## Remove docstale

First, remove the `docstale hook` entry from every agent configuration where
you added it. Then remove the command:

```bash
uv tool uninstall docstale
pipx uninstall docstale
```

The repository files `docstale.toml` and `docstale.lock` remain in place. Hook
state remains under `git rev-parse --git-path docstale`. Remove these paths
yourself if you no longer need them.

## Troubleshooting

- If `docstale` is not found after a `uv` install, run `uv tool update-shell`
  and open a new shell.
- If it is not found after a `pipx` install, run `pipx ensurepath` and open a
  new shell.
- If docstale cannot find a repository, run it inside a Git worktree.
- If a Codex hook does not run, open `/hooks` and check its trust state.
