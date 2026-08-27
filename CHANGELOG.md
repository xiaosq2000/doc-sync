# Changelog

All notable changes to doc-sync will be recorded here. The project follows
[Semantic Versioning](https://semver.org/) once its first public version is
released.

## Unreleased

### Changed

- **Breaking.** Removed the `bin/doc-sync` source launcher, along with the hook
  commands that invoked it through `python3`. Every integration now invokes the
  installed `doc-sync` command. Run `doc-sync hook install all` once after
  upgrading to rewrite existing wiring in place.
- Replaced the hand-rolled source-pattern matcher with `pathspec`, the first
  runtime dependency. It is pure Python with no transitive dependencies.
  Matching semantics are unchanged: every pattern stays anchored to the
  repository root, and matching at any depth stays opt-in through an explicit
  `**/` prefix. Existing configurations need no edits. Two edge cases are
  refined: a source given as a bare directory name now behaves like the same
  name with a trailing slash, where it previously matched nothing usable, and a
  trailing-slash pattern no longer matches a file carrying the directory's own
  name.

### Development

- Manage the project with `uv`. `uv sync --all-groups` replaces the manual
  virtual-environment setup, and `uv.lock` pins `ruff` and `ty` so a release of
  either cannot turn an unrelated CI run red.
- Replace `unittest` with `pytest`: fixtures in `tests/conftest.py`,
  parametrized matching and configuration cases, a `posix_only` marker in place
  of `skipIf`, and coverage reporting through `pytest-cov`.
- Run CI on `uv` across the same twelve interpreter and platform cells.

### Added

- Extract a pure source-to-documentation impact engine.
- Add strict, named `config_version = 1` rules.
- Add worktree, staged, merge-base, and explicit path inputs.
- Add per-session acknowledgement state under Git metadata.
- Add Claude Code, Codex CLI, and OpenCode adapters with managed install and
  uninstall.
- Wire Codex CLI through a `Stop` entry in `.codex/hooks.json`. Codex speaks
  Claude Code's Stop-hook wire format, so both adapters share one protocol
  module; because Codex exposes no project-directory variable, its adapter
  resolves the repository from the payload `cwd`.
- Add a Python package and console entry point.
- License the project under MIT and document manual source installation,
  upgrade, and uninstallation.
