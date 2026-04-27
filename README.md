# Doc-Sync

Doc-sync is a small, portable session-end hook for AI-assisted repositories. It
checks changed files against a repo-local ownership map and injects a focused
documentation-review prompt only when mapped docs may need attention.

It is a hook, not an agent skill. The result is deterministic, cheap, and based
on git state instead of model discretion.

## Quick Start

Copy `tools/doc-sync/` into a repository, then install one or both integrations:

```bash
python3 tools/doc-sync/install.py --claude
python3 tools/doc-sync/install.py --opencode
python3 tools/doc-sync/install.py --all
```

Preview changes first with:

```bash
python3 tools/doc-sync/install.py --all --dry-run
```

The installer is conservative:

- It creates `doc-sync.toml` from `examples/doc-sync.toml` only when missing.
- It adds `.doc-sync-state.json` to `.gitignore` only when missing.
- It merges Claude Code `Stop` wiring without replacing existing hooks.
- It creates `.opencode/plugins/doc-sync.ts` when missing.
- It refuses to overwrite an unrelated OpenCode plugin unless `--force` is set.

## How It Works

1. Claude Code runs `hook.sh --event stop` from the `Stop` hook, or OpenCode
   runs `hook.sh --event session.idle` from its closest Stop-like event.
2. `hook.sh` ignores all other events unless you run it manually with `--check`.
3. `doc_sync.py` reads changed files from git and compares them with
   `doc-sync.toml`.
4. If a watched source changed without its owner docs changing, the hook returns
   structured JSON with `decision = block`, `prompt`, and `reason` fields.
5. The same changed-file content and source/doc state blocks once. Retrying the
   same Stop-like event passes if no doc update is needed.

## Manual Check

Run the hook manually with:

```bash
tools/doc-sync/hook.sh --check
```

Useful lower-level form:

```bash
python3 tools/doc-sync/doc_sync.py --root . --config doc-sync.toml
```

## Config

Project-specific mappings live outside this package, usually at repo root as
`doc-sync.toml`.

```toml
version = 2

[[watch]]
paths = [
  "src/",
  "pyproject.toml",
]
docs = [
  "README.md",
  "docs/architecture.md",
]
```

Path rules are repo-relative:

- `path/to/file.toml` matches one exact file.
- `path/to/dir/` matches every descendant recursively.
- `*.toml` matches within one path segment.
- `**/*.py` uses real globstar semantics and matches top-level and nested files.

When any `paths` entry matches a changed file, every listed `docs` path must
also be changed, otherwise the hook asks the agent to review those docs.

## State

The checker writes `.doc-sync-state.json` at the repo root by default. The file
is only used to avoid re-blocking the same reviewed condition. Editing the same
source path again changes the content fingerprint and can block again.

The state file is removed once there are no changed files or all required docs
are changed.

## Claude Code

The installer updates `.claude/settings.json`. The minimal hook is:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/tools/doc-sync/hook.sh\" --event stop",
            "timeout": 30,
            "statusMessage": "Checking documentation sync..."
          }
        ]
      }
    ]
  }
}
```

A copyable example lives at `integrations/claude-settings.example.json`.

## OpenCode

OpenCode does not expose Claude Code's exact `Stop` event. Use `session.idle` as
the closest session-end review point and pass `--event session.idle`.

The installer creates `.opencode/plugins/doc-sync.ts`. A copyable example lives
at `integrations/opencode-plugin.example.ts`.

## Files

- `doc_sync.py` is the reusable checker.
- `hook.sh` is the Stop/session-idle event gate.
- `install.py` installs Claude Code and OpenCode integrations.
- `schema.json` describes the config shape.
- `examples/doc-sync.toml` is a copyable starting point.
- `integrations/` contains manual integration examples.

## Sharing

To publish or reuse this tool elsewhere, copy only `tools/doc-sync/`. Keep the
target repository's `doc-sync.toml` outside the package so mappings remain
project-owned.
