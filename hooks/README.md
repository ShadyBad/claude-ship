# hooks/

Hook scripts that surface pending work so it doesn't rot unseen: skill proposals from `~/.claude/skills/_proposed/`, and survey findings from `~/.claude/memory/projects/*/findings/`.

## Why

Two skills in this system propose and never execute, by hard constraint. `skill-curator` proposes skills, consolidations, and fixes. `survey` audits the repo on a cadence and writes findings.

Both fail the same way without a surfacing mechanism: the output sits untouched until you remember to go looking. That is worse for `survey` than for the curator, because the survey fires automatically — a background pass whose findings nobody reads is indistinguishable from a background pass that has stopped running.

## What's in here

| Script | Hook type | What it does |
|--------|-----------|--------------|
| `proposal-count.sh` | helper | Counts subdirs of `_proposed/` that contain a `SKILL.md`. Emits a single integer. Used by the other two. |
| `proposal-watcher.sh` | SessionStart | When count > 0, emits a banner naming each pending proposal with a truncated description. Silent when zero. |
| `composed-statusline.sh` | statusLine | Wraps the existing statusline command (caveman if present) and appends `📋 N` for proposals and `🔍 N` for findings when either count > 0. Silent when both are zero. |
| `finding-count.sh` | helper | Counts survey findings under `memory/projects/*/findings/` whose frontmatter says `status: pending`. Emits a single integer. |
| `finding-watcher.sh` | SessionStart | When count > 0, lists each pending finding with its namespace, category, confidence, and title. Silent when zero. |

All five:
- Skip subdirs without `SKILL.md` (the meta dirs like `_archives/`, `_consolidations/`, `_fixes/`).
- Skip proposals whose `_proposal_metadata.md` contains `# Status: promoted` or `# Status: rejected` (audit-trail entries don't count as pending).
- Skip findings whose status is anything but `pending` — promoted, spec'd, and rejected findings are settled and must not nag.
- Exit 0 in all cases. Never block a session or statusline render.

## Install

If you're using the `assay` plugin install paths from the root README, the scripts already live at `~/.claude/hooks/<name>.sh` as symlinks (or copies) into the repo. To wire them into Claude Code, append the two settings.json entries below.

### Add to `~/.claude/settings.json`

**SessionStart hook** — append a second entry to the `hooks.SessionStart` array (keeps any existing SessionStart hooks intact):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"/Users/<you>/.claude/hooks/proposal-watcher.sh\"",
            "timeout": 5,
            "statusMessage": "Checking pending skill proposals..."
          },
          {
            "type": "command",
            "command": "bash \"/Users/<you>/.claude/hooks/finding-watcher.sh\"",
            "timeout": 5,
            "statusMessage": "Checking pending survey findings..."
          }
        ]
      }
    ]
  }
}
```

**statusLine** — flip the existing command to the composed wrapper:

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash \"/Users/<you>/.claude/hooks/composed-statusline.sh\""
  }
}
```

The composed script first runs `~/.claude/hooks/caveman-statusline.sh` if present (preserving the caveman badge), then appends the proposal and finding segments when needed. If you don't have caveman installed, the script silently skips that call and just emits the segments.

## Behavior

| Pending count | SessionStart output | statusLine append |
|---------------|---------------------|-------------------|
| 0 proposals | nothing | nothing |
| ≥ 1 proposal | banner + per-proposal list | `📋 N` in yellow-bold |
| 0 findings | nothing | nothing |
| ≥ 1 finding | banner + per-finding list | `🔍 N` in cyan-bold |

All of them resolve their root from `${CLAUDE_CONFIG_DIR:-$HOME/.claude}` — `skills/_proposed/` for proposals, `memory/projects/*/findings/` for findings — so a custom config directory is respected.

## Rollback

Restore the saved settings.json backup made when you installed:

```bash
cp ~/.claude/settings.json.pre-assay-hooks-<timestamp> ~/.claude/settings.json
rm ~/.claude/hooks/{proposal-count,proposal-watcher,finding-count,finding-watcher,composed-statusline}.sh
```

## Performance

- `proposal-count.sh`, `finding-count.sh`, and `composed-statusline.sh` are called on every keystroke for the statusline. All shell-only. `finding-count.sh` greps one line per finding file across a handful of namespace directories; at realistic queue sizes (the survey caps its own output for exactly this reason) it completes in single-digit milliseconds alongside the others.
- The two watchers run once at session start. Wall-clock impact: negligible.

## Hardening

`proposal-watcher.sh` writes stderr to `/tmp/proposal-watcher.err` and `finding-watcher.sh` to `/tmp/finding-watcher.err`, so a malformed SKILL.md or finding file never propagates a noisy banner into the session-start context. Every script exits 0 unconditionally — none of them can block a session or a statusline render, even on a parse error.
