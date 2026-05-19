---
name: plugin-packager
description: Extracts a set of local `~/.claude/commands/*.md` + `~/.claude/skills/<name>/` files into a standalone Claude Code plugin repository, then optionally swaps the local files for symlinks into the repo so `git pull` propagates updates. Use when Brandon says "package this as a plugin", "turn these skills into a repo I can share", "extract X command and its skills into something installable", or after a /ship run produces a coherent set of skills + commands that should be versioned, shared, or installed on another machine. Generates `.claude-plugin/plugin.json`, README, INSTALL (three install paths), CONFIG (personalization guide), MIT LICENSE, .gitignore, and a `personalize.sh` script that rewrites operator-specific strings (name, project namespaces) without touching pinned IDs or pipeline step references. Backs up originals before swapping local files for symlinks. Hard refuses to package or rewrite files that are not Brandon-owned (no plugin-shipped skill extraction).
---

# plugin-packager

Pattern observed: Brandon repeatedly extracts custom skills + commands into shareable Claude Code plugin repos so he can (a) reference them in a stable location, (b) push to GitHub for sharing, and (c) symlink them back into `~/.claude/` so `git pull` updates the live skills.

This skill captures the seven-step flow so it can be invoked deliberately without rediscovering the steps each time.

## When to invoke

- Brandon says "package this as a plugin", "make this shareable", "extract these into a repo I can share with others".
- A /ship run produces a coherent set of N skills + M commands that hang together (e.g. `/ship` + its 11 supporting skills, or `/spec` + spec-builder + project-memory).
- Brandon wants to version a subset of `~/.claude/` content outside the home directory.
- Brandon explicitly invokes `/plugin-package <name>` (slash command TBD).

## Inputs

```
scope:        <list of command names + skill directory names to package>
repo-name:    <kebab-case name, default derived from primary command>
destination:  <absolute path, default ~/repos/<repo-name>>
swap:         <bool, default true — replace originals with symlinks into repo after backup>
push:         <bool, default false — only push to GitHub on explicit yes>
```

## Pipeline

1. **Inventory + validate.** Confirm every named command and skill exists at `~/.claude/commands/<name>.md` and `~/.claude/skills/<name>/SKILL.md`. Refuse if any file is a plugin-shipped path (e.g. lives under `~/.claude/plugins/marketplaces/`).
2. **Skeleton.** Create `<destination>/.claude-plugin/`, `<destination>/.claude/commands/`, `<destination>/.claude/skills/`, `<destination>/scripts/`.
3. **Copy files.** Copy each command + skill directory into the destination preserving structure.
4. **Manifest.** Write `<destination>/.claude-plugin/plugin.json` with name, description (synthesized from the primary command), version `0.1.0`, MIT license, author (from operator-model), keywords, and `commands` + `skills` paths.
5. **Docs.** Write README.md (what + design + install + license), INSTALL.md (three install paths: plugin loader, direct drop, symlink), CONFIG.md (personalization guide, what NOT to rename), LICENSE (MIT), .gitignore.
6. **Personalize script.** Write `<destination>/scripts/personalize.sh` — BSD/GNU sed-compatible, takes `<name> <project-1> <project-2>`, backs up `.claude/` to `.backup-<timestamp>/`, then rewrites `Brandon` → `<name>` and project namespace strings → `<project-N>`. Never touches risk tier names, pipeline step numbers, skill YAML IDs, or the pinned-skills list.
7. **Local swap (if `swap=true`).** Backup current `~/.claude/commands/<name>.md` and `~/.claude/skills/<name>/` for every scoped item to `~/.claude/backups/pre-<repo-name>-<timestamp>/`. Verify backup is bit-identical to repo copy via `diff -rq`. If diff is non-empty, halt — abort the swap. If empty, remove originals and replace with symlinks pointing into the destination repo.
8. **Git + GitHub (if approved).** `git init`, initial commit using conventional-commit format, then `gh repo create <user>/<repo-name> --public --source=. --push` on explicit Brandon yes only.

## Hard constraints

- NEVER extract or rewrite a plugin-shipped skill. Only Brandon-owned files under `~/.claude/commands/` and `~/.claude/skills/<name>/`.
- NEVER swap local files for symlinks without first writing a backup and verifying bit-identical match via `diff -rq`. Halt on any drift.
- NEVER push to GitHub without explicit yes. Repo creation is irreversible-ish.
- NEVER overwrite an existing destination directory. If `<destination>` exists, refuse with the path and ask Brandon to pick another.
- NEVER rewrite risk tier names, pipeline step numbers, pinned-skills list, or YAML skill IDs in the personalize script — these are load-bearing across files.
- ALWAYS use `cp -i` or check existence before copying when paths could collide.
- ALWAYS preserve file modes (the personalize.sh script needs +x).
- ALWAYS surface the final tree + file count + size to Brandon before commit step.

## Coordination

- **commit-protocol** — use for the initial commit (engineer-in-the-loop flow).
- **operator-model** — read for author name + GitHub username when writing plugin.json + LICENSE copyright.
- **done-gate** — bypass tests/lint checks (markdown only); Check 8 (Brandon approval) still applies.
- **judge-panel** — LOW tier (doc-only packaging); skip judges with `--no-judges` flag unless `swap=true` triggers MEDIUM.

## Failure modes

| Failure | Behavior |
|---------|----------|
| Named skill/command does not exist | Refuse with list of missing paths. |
| Destination exists | Refuse with destination path. Suggest alternate. |
| Backup diff non-empty before swap | Halt swap. Surface diff to Brandon. |
| `gh` not authenticated when push requested | Surface `gh auth login` instruction. Skip push. Keep local commit. |
| Pre-commit hook rejects initial commit | Surface hook output. Offer auto-fix per commit-protocol. |
