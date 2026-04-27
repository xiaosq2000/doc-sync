#!/usr/bin/env bash
# Portable doc-sync session-end hook.

set -euo pipefail

TOOL_DIR="$(cd -P "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-}"
CONFIG=""
STATE=""
EVENT="${DOC_SYNC_EVENT:-}"
CHECK=0

while [[ $# -gt 0 ]]; do
	case "$1" in
	--check)
		CHECK=1
		shift
		;;
	--config)
		CONFIG="$2"
		shift 2
		;;
	--event)
		EVENT="$2"
		shift 2
		;;
	--root)
		PROJECT_ROOT="$2"
		shift 2
		;;
	--state)
		STATE="$2"
		shift 2
		;;
	*)
		printf 'doc-sync: unknown argument: %s\n' "$1" >&2
		exit 1
		;;
	esac
done

case "$EVENT" in
stop | Stop | claude.stop | session.idle | opencode.session.idle) ;;
"")
	if [[ "$CHECK" -ne 1 ]]; then
		exit 0
	fi
	;;
*)
	exit 0
	;;
esac

if [[ -z "$PROJECT_ROOT" ]]; then
	PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

if [[ -z "$CONFIG" ]]; then
	CONFIG="$PROJECT_ROOT/doc-sync.toml"
fi

if [[ -z "$STATE" ]]; then
	STATE="$PROJECT_ROOT/.doc-sync-state.json"
fi

exec python3 "$TOOL_DIR/doc_sync.py" --root "$PROJECT_ROOT" --config "$CONFIG" --state "$STATE"
