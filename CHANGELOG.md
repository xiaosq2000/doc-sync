# Changelog

All notable changes to doc-sync will be recorded here. The project follows
[Semantic Versioning](https://semver.org/) once its first public version is
released.

## Unreleased

### Added

- `doc-sync review` runs the check by hand. It takes the same change-selection
  and output flags as `doc-sync check`, but it ignores the per-checkout switch
  and always answers, printing `doc-sync: no documents need review` when there is
  nothing to report. This makes `doc-sync disable` a choice about the automatic
  reminder rather than about doc-sync as a whole: switch the hook off so it stops
  spending an agent's context every turn, then ask for a check when you want one.
  Inside an agent it is a single short command — `!doc-sync review` in Claude
  Code — so a long session can pull the result in without re-enabling the hook.
  Unlike `check`, it never reports `"status": "disabled"`.

### Changed

- Agent hooks now stay silent in a repository holding no `doc-sync.toml`. Such a
  repository never opted in, so reporting a missing configuration on every turn
  only spent the agent's context. A malformed or otherwise invalid
  configuration still blocks with an explanation, and `doc-sync check` still
  exits `1` for either. Anyone who relied on the old blocking message as a
  reminder to run `doc-sync init` will no longer see it.
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

- Add `doc-sync disable`, `doc-sync enable`, and `doc-sync status` to switch the
  tool off for one checkout. The switch is a marker file beside the
  acknowledgement state under `git rev-parse --git-path doc-sync`, so it is
  never committed, never enters the worktree, and never reaches a fresh CI
  clone. While disabled, `check` and every agent adapter exit `0` and print
  nothing; `validate`, `init`, and `hook install`/`uninstall` are unaffected.
  `doc-sync check --format json` reports `"status": "disabled"`.
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
