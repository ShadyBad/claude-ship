#!/usr/bin/env bash
# finding-count.sh — count pending survey findings awaiting a decision.
#
# The survey stage writes one markdown file per finding under
#   ~/.claude/memory/projects/<namespace>/findings/<finding-id>.md
# with a `status:` line in its frontmatter. Only `pending` counts: promoted,
# spec'd, and rejected findings are settled and must not nag.
#
# Output: a single integer to stdout. Always exits 0 (never blocks anything).

PROJECTS_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/memory/projects"

if [ ! -d "$PROJECTS_DIR" ]; then
  echo 0
  exit 0
fi

count=0
for f in "$PROJECTS_DIR"/*/findings/*.md; do
  [ -f "$f" ] || continue
  case "$(basename "$f")" in _*) continue ;; esac
  if grep -qE '^status:[[:space:]]*pending[[:space:]]*$' "$f" 2>/dev/null; then
    count=$((count + 1))
  fi
done

echo "$count"
