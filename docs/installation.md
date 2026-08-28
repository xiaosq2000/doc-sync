# Installation

Doc-sync requires Python 3.11 or newer and Git.

## Install the command

Install with `uv`:

```bash
uv tool install git+https://github.com/xiaosq2000/doc-sync.git
doc-sync --help
```

Or install with `pipx`:

```bash
pipx install git+https://github.com/xiaosq2000/doc-sync.git
doc-sync --help
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
uv tool install --force git+https://github.com/xiaosq2000/doc-sync.git
pipx upgrade doc-sync
```

Doc-sync does not edit agent configuration. A command change therefore requires
you to update the Stop entry in `.claude/settings.json` or `.codex/hooks.json`.

## Remove doc-sync

First, remove the `doc-sync hook` entry from every agent configuration where
you added it. Then remove the command:

```bash
uv tool uninstall doc-sync
pipx uninstall doc-sync
```

The repository configuration remains at `doc-sync.toml`. Hook state remains
under `git rev-parse --git-path doc-sync`. Remove either path yourself if you no
longer need it.

## Troubleshooting

- If `doc-sync` is not found after a `uv` install, run `uv tool update-shell`
  and open a new shell.
- If it is not found after a `pipx` install, run `pipx ensurepath` and open a
  new shell.
- If doc-sync cannot find a repository, run it inside a Git worktree.
- If a Codex hook does not run, open `/hooks` and check its trust state.
