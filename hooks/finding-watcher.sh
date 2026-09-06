#!/usr/bin/env bash
# finding-watcher.sh — SessionStart hook: surface pending survey findings.
#
# The survey stage is automatic — it fires from inside /assay and from a
# post-ship cadence check. That is exactly why it needs a surfacing mechanism:
# a background pass whose output nobody sees is a background pass that has
# stopped working, and it looks identical to one that found nothing.
#
# Output contract: stdout is injected into the SessionStart context.
# stderr is logged to /tmp/finding-watcher.err. Exit 0 always.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECTS_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/memory/projects"

count=$("$SCRIPT_DIR/finding-count.sh" 2>/dev/null || echo 0)

# Silent when zero — no banner on a clean board.
if [ "$count" -eq 0 ]; then
  exit 0
fi

field() {
  # field <file> <key> — first value of a flat frontmatter key, or empty.
  sed -n "s/^$2:[[:space:]]*//p" "$1" 2>/dev/null | head -1
}

{
  echo "🔍 $count pending survey finding(s) awaiting a decision."
  echo
  echo "Pending:"

  for f in "$PROJECTS_DIR"/*/findings/*.md; do
    [ -f "$f" ] || continue
    case "$(basename "$f")" in _*) continue ;; esac
    grep -qE '^status:[[:space:]]*pending[[:space:]]*$' "$f" 2>/dev/null || continue

    ns=$(basename "$(dirname "$(dirname "$f")")")
    id=$(field "$f" "finding-id")
    [ -n "$id" ] || id=$(basename "$f" .md)
    title=$(field "$f" "title" | head -c 90)
    cat=$(field "$f" "category")
    conf=$(field "$f" "confidence")

    echo "  - [$ns] $id ($cat, $conf): $title"
  done

  echo
  echo "Review with \`/survey queue\`. Promote with \`/survey promote <finding-id>\`,"
  echo "spec it with \`/spec <finding-id>\`, or drop it with \`/survey reject <finding-id> \"<reason>\"\`."
} 2>/tmp/finding-watcher.err

exit 0
