# Changelog

All notable changes to doc-sync will be recorded here. The project follows
[Semantic Versioning](https://semver.org/) once its first public version is
released.

## Unreleased

- Extract a pure source-to-documentation impact engine.
- Add strict, named `config_version = 1` rules.
- Add worktree, staged, merge-base, and explicit path inputs.
- Add per-session acknowledgement state under Git metadata.
- Add Claude Code and OpenCode adapters with managed install and uninstall,
  invoking the source launcher with `python3` so hooks work in the bare
  non-interactive shell agents run them from.
- Add a zero-runtime-dependency Python package and console entry point.
- License the project under MIT and document manual source installation,
  upgrade, and uninstallation.
