#!/usr/bin/env bash
# personalize.sh — rewrite the original author's strings to your own.
#
# Usage:
#   ./scripts/personalize.sh "<your-name>" "<project-1>" "<project-2>"
#
# Makes a .backup-<timestamp>/ copy before rewriting. Diff before committing.

set -euo pipefail

if [ $# -lt 1 ]; then
  cat <<'USAGE'
Usage: ./scripts/personalize.sh "<your-name>" ["<project-1>" "<project-2>"]

Replaces:
  Brandon        -> <your-name>
  auto-co        -> <project-1> (if supplied)
  margin-invest  -> <project-2> (if supplied)

Does NOT touch:
  - "personal" project namespace
  - Risk tier names (TRIVIAL/LOW/MEDIUM/HIGH/CRITICAL)
  - Pipeline step names and numbers
  - Skill IDs in YAML frontmatter
USAGE
  exit 1
fi

NAME="$1"
PROJ1="${2:-}"
PROJ2="${3:-}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$REPO_ROOT/.claude"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$REPO_ROOT/.backup-$STAMP"

if [ ! -d "$TARGET" ]; then
  echo "ERROR: expected $TARGET to exist. Run this from the repo root."
  exit 1
fi

echo "Backing up $TARGET -> $BACKUP"
cp -r "$TARGET" "$BACKUP"

# Detect sed flavor (BSD vs GNU)
if sed --version >/dev/null 2>&1; then
  SED_INPLACE=(-i)
else
  SED_INPLACE=(-i '')
fi

# Files to process: all .md under .claude/
mapfile -t FILES < <(find "$TARGET" -type f -name '*.md')

replace() {
  local from="$1" to="$2"
  if [ -z "$to" ]; then return; fi
  echo "  $from -> $to"
  for f in "${FILES[@]}"; do
    sed "${SED_INPLACE[@]}" "s/$from/$to/g" "$f"
  done
}

echo "Rewriting:"
replace "Brandon" "$NAME"
[ -n "$PROJ1" ] && replace "auto-co" "$PROJ1"
[ -n "$PROJ2" ] && replace "margin-invest" "$PROJ2"

# Runtime config: where tickets, the glossary, and the TDD floor live on THIS
# machine. Written once at install; personalize.sh never overwrites an existing
# one, so re-running it is safe.
CONFIG_PATH="$HOME/.claude/assay.config.json"
echo
if [ -f "$CONFIG_PATH" ]; then
  echo "Runtime config already present: $CONFIG_PATH (left untouched)"
else
  python3 "$REPO_ROOT/scripts/assay_config.py" --init
  echo "  edit it to change ticket backend, glossary path, or TDD floor"
fi

echo
echo "Done. Diff against backup:"
echo "  diff -ru \"$BACKUP\" \"$TARGET\""
echo
echo "If anything looks wrong, restore with:"
echo "  rm -rf \"$TARGET\" && mv \"$BACKUP\" \"$TARGET\""
