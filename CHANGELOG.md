# Changelog

All notable changes to doc-sync will be recorded here. The project will follow
Semantic Versioning after its first stable release.

## Unreleased

### Changed

- Replaced named rules with a `[documents]` table that maps each exact document
  path to its source patterns. Removed `config_version`, rule IDs, and rules
  that group several documents. The old configuration format is not accepted.
- Reduced the command surface to `check`, `validate`, `hook`, `disable`, and
  `enable`. Manual checks always answer and ignore the hook switch. Removed
  `review`, `status`, `init`, custom roots, custom configuration paths, custom
  state directories, explicit path files, and hook installation commands.
- Replaced agent specific hook commands with one shared `doc-sync hook` command
  for Claude Code and Codex. The hook now honors `stop_hook_active` before it
  reads Git or configuration state.
- Removed the OpenCode adapter and all code that edited agent configuration
  files. Agent setup now uses documented JSON entries.
- Replaced the public Python model and evaluation API with internal document and
  review records. JSON output now contains `status` and `documents`.
- Validation now requires configured documents to exist. Source patterns may be
  unmatched on the current branch.
