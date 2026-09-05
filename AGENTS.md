# doc-sync

Doc-sync maps changed source paths to unchanged documents using TOML and Git.
Keep it deterministic, with no LLM calls or heuristics and `pathspec` as its only
runtime dependency. Do not add command variants, agent installers, or a public
Python API without a demonstrated use case.

## Development

Setup and check commands are in [CONTRIBUTING.md](CONTRIBUTING.md#development-setup).
Local tests use temporary fixtures and Git repositories. You may run checks and
fix failures caused by the requested change without asking for approval at each
step. Keep tool upgrades deliberate and fix new findings in the same change.

## Code boundaries

- Keep `evaluate()` free of Git, file access, hook input, and command output.
- Route all Git calls through `_run_git()` and human or JSON output through
  `cli.py`.
- Anchor source patterns to the repository root. Matching at any depth requires
  `**/`; leading `!` and `#` are literal characters.

## Hook invariants

The [README hook section](README.md#add-a-stop-hook) defines session behavior,
error handling, and setup.

- Return immediately when `stop_hook_active` is true, before accessing Git,
  configuration, or state.
- Keep session baselines separate from acknowledgements. Resume, compaction,
  and clearing acknowledgements must preserve the baseline.
- Store hook state under `git rev-parse --git-path doc-sync` so linked worktrees
  remain independent. The disable marker affects only hooks, never manual
  commands or their JSON status.

## Contract changes

Changes to configuration behavior, JSON output, exit codes, or hooks must include
contract tests and matching README updates. Mark tests that require POSIX
filesystem behavior with `@pytest.mark.posix_only` so they skip on Windows.
