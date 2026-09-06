#!/usr/bin/env bash
# composed-statusline.sh — wraps existing statusline command(s) and appends
# pending-work segments: skill proposals from ~/.claude/skills/_proposed/ and
# survey findings from ~/.claude/memory/projects/*/findings/.
#
# Runs the caveman statusline first (if present), then appends `📋 N` when the
# proposal count > 0 and `🔍 N` when the pending-finding count > 0. Silent
# appendix when both are 0.
#
# Configure ~/.claude/settings.json:
#   "statusLine": { "type": "command", "command": "bash <path>/composed-statusline.sh" }

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

# 1. Run caveman statusline if present (existing line content)
CAVEMAN_STATUSLINE="$CLAUDE_DIR/hooks/caveman-statusline.sh"
if [ -f "$CAVEMAN_STATUSLINE" ] && [ ! -L "$CAVEMAN_STATUSLINE" ]; then
  bash "$CAVEMAN_STATUSLINE"
fi

# 2. Append proposal segment when count > 0
count=$("$SCRIPT_DIR/proposal-count.sh" 2>/dev/null || echo 0)

if [ "$count" -gt 0 ]; then
  # Color 220 = yellow-orange. Bold for visibility.
  printf ' \033[1;38;5;220m📋 %d\033[0m' "$count"
fi

# 3. Append survey-finding segment when count > 0
findings=$("$SCRIPT_DIR/finding-count.sh" 2>/dev/null || echo 0)

if [ "$findings" -gt 0 ]; then
  # Color 45 = cyan. Distinct from the proposal segment at a glance.
  printf ' \033[1;38;5;45m🔍 %d\033[0m' "$findings"
fi
