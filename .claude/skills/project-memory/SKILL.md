---
name: project-memory
description: Routes durable lessons to per-project memory files and loads relevant lessons at task start. Maintains separate lesson namespaces for auto-co, margin-invest, and personal projects. Use when starting a new task (loads project's recent lessons into context), when a /assay run completes (appends new lessons), when Brandon explicitly states a preference or correction worth remembering, when a recurring pattern is observed across 3+ tasks, or when the user asks "remember this" or "log this". Detects current project via .claude/project-name file, git remote URL pattern matching, or working directory path. Falls back to personal namespace. Caps at 500 entries per project; archives oldest 100 into compressed file when over limit. Never deletes entries without compression. Always appends, never overwrites individual entries.
---

# Project Memory Skill

Routes durable lessons to per-project memory and loads them at task start. This skill is the policy layer over local lesson files. Storage is local markdown; this skill controls write rules and read rules.

## Storage Layout
$HOME/.claude/memory/projects/
├── auto-co/
│   ├── lessons.md          (active, capped at 500 entries)
│   └── archived-lessons.md (compressed older entries)
├── margin-invest/
│   ├── lessons.md
│   └── archived-lessons.md
└── personal/
├── lessons.md
└── archived-lessons.md

## Project Detection (Authoritative)

This skill is the canonical implementation of project detection. Other skills delegate here.

Detection order (stop at first match):

1. Check for `.claude/project-name` file. Search cwd, then walk up parent directories to $HOME. If found, read first line, strip whitespace. That is the project name.

2. Run `git remote -v 2>/dev/null` in cwd. Inspect remote URLs:
   - Contains `auto-co` (case-insensitive) → project is `auto-co`
   - Contains `margin-invest` (case-insensitive) → project is `margin-invest`

3. Check current working directory path:
   - Matches `*/auto-co/*` or `*/auto-co` → project is `auto-co`
   - Matches `*/margin-invest/*` or `*/margin-invest` → project is `margin-invest`

4. Fallback: project is `personal`.

If project name detected via step 1 is not one of [auto-co, margin-invest, personal], log a warning and treat as `personal`. Brandon adds new projects by creating a new directory under `$HOME/.claude/memory/projects/<new-name>/` and adding lessons.md.

## Entry Format

Each lesson is one line, pipe-delimited:
<ISO-timestamp> | <task-summary-one-line> | <lesson-1-to-3-sentences> | <tags-comma-separated>

Example:
2026-05-16T14:32:01Z | Refactored bond pricing module | Use Decimal for all financial arithmetic, never float. Floats accumulate rounding error in compounding calculations. | finance,arithmetic,decimal

Rules:
- ISO 8601 UTC timestamp.
- Task summary: one line, no pipes inside.
- Lesson: 1-3 sentences. State the lesson, not the task. Lessons generalize beyond the immediate task.
- Tags: lowercase, comma-separated, no spaces.

## Write Rules

The skill appends an entry when:

1. `/assay` completes successfully and the task taught a generalizable pattern.
2. Brandon explicitly says "remember this" or "log this lesson".
3. A judge from the judge-panel raises a concern that becomes a learned constraint.
4. The same correction is made 2+ times in a session (high-signal pattern).
5. A user-correctable mistake is made (e.g., wrong assumption stated, then corrected) — log the corrected understanding.

The skill does NOT log:
- One-off task outputs (use `episodic-memory` MCP for that).
- Brandon's personal preferences (those go to `operator-model`).
- Code itself (lessons are about patterns, not implementations).
- Things that are obvious from documentation.

## Read Rules

At task start, load the last 50 entries from the detected project's lessons.md into context.

If the task description mentions a specific topic, also load up to 20 additional entries matching the topic from `archived-lessons.md` (use ripgrep on tags and lesson text).

Maximum read context: 70 entries × ~3 lines each = ~210 lines. Approximately 4-6K tokens.

## Capacity Management

When `lessons.md` exceeds 500 entries:

1. Identify the oldest 100 entries.
2. Group them by tag.
3. For each tag with 3+ entries in the batch, write a single summary entry: `<earliest-timestamp> | ARCHIVED SUMMARY: <tag> (<count> entries) | <consolidated lesson> | <tag>,archived`.
4. Move the 100 raw entries to `archived-lessons.md` (append).
5. Replace them in `lessons.md` with the summary entries.

This runs at the end of `/assay` when entry count is checked, not on every read.

## The Rejection Ledger (`rejected.md`)

A lesson records what was learned. The ledger records **what was considered and
declined** — and without it, every recurring pass re-derives the same rejected
conclusion forever.

Two producers, one failure mode. The `survey` skill audits on a cadence: with no
ledger, a finding Brandon dismissed on Monday comes back next Monday, and the
Monday after, until he stops reading the queue. The `judge-panel` vet pass drops
by-design concerns: with no ledger, the same by-design call is re-litigated on
every diff that touches the same code.

```
$HOME/.claude/memory/projects/<ns>/rejected.md
```

One entry per line, pipe-delimited, same discipline as `lessons.md`:

```
<ISO-timestamp> | <source> | <finding or concern, one line> | <why it was declined> | <evidence ref>
```

- `source` is `survey`, `judge-vet`, `qa`, or `brandon`.
- The reason is mandatory and must be a reason, not a verdict. "Not worth
  doing" is not a reason; "standard proxy convention, every CLI honors it" is.
- `evidence ref` is the `file:line` the rejected claim pointed at, so a future
  pass can tell whether the code has changed underneath the rejection.

### Read rules

- `survey` recon reads the whole ledger before the audit and passes it into
  every subagent's delegation brief as decided tradeoffs. A finding matching a
  ledger entry is dropped during vetting, not reported.
- `judge-panel`'s vet pass reads it before classifying a concern as by-design.
- Both are additive to normal lesson loading, and the ledger is not counted
  against the 70-entry read cap — it is short by construction.

### Write rules

Append when a finding or concern is explicitly declined: Brandon rejects one
from the survey queue, the vet pass drops one as by-design, or he waves off a
judge concern at the gate. Never append a concern that was merely deprioritized
— deferred is not declined, and conflating them makes the ledger a place
findings go to disappear.

### Re-opening

A ledger entry is a decision, not a life sentence. A later pass may re-report a
rejected finding **only with new evidence**, and must say what changed — the
code moved, the reason no longer holds, the ADR it relied on went stale. Append
a new entry recording the reversal; never edit or delete the original. The
ledger is append-only for the same reason `lessons.md` is: the history of what
was declined and why is the thing being preserved.

## Cross-Project Lessons

A lesson can be relevant to multiple projects. If a lesson is tagged with `cross-project`, also append (with same content) to the `personal` project's lessons.md as the canonical cross-project home. Reference from project-specific files using `[cross-ref: personal/<timestamp>]` rather than duplicating.

## Federated Lessons (`/cross-learn` integration)

When `/cross-learn` promotes a lesson to a system-level artifact (skill, CLAUDE.md rule, operator-model entry, or hookify rule), it appends a `federated:<slug>` tag to the original entry's tag list — never modifies timestamp, task summary, lesson text, or other tags.

Read-rule consequence: entries carrying any `federated:*` tag are EXCLUDED from `/cross-learn`'s next clustering pass (they've already been promoted; re-clustering them creates noise). They remain fully visible to normal `load` and `search` modes — federation does not demote a lesson's local utility.

The `search` mode accepts an optional `exclude_federated: true` flag for cross-learn's use. Default is false.

## Invocation Contract

The skill accepts:
- `mode` — one of `load`, `append`, `search`, `archive_check`.
- For `load`: returns last N entries (default 50) plus topic-matched archives.
- For `append`: writes a new entry. Inputs: task_summary, lesson, tags (auto-includes project name as tag).
- For `search`: returns matching entries. Input: query string. Uses ripgrep against active and archived files.
- For `archive_check`: runs capacity management if needed. No return value.

## Integration with Other Skills

- `session-recall` calls this skill's `search` mode in parallel with episodic-memory queries.
- `operator-model` reads this skill's archive to detect cross-project patterns (same lesson logged 3+ times across projects → candidate for operator-model update).
- `skill-curator` reads invocation stats to identify lessons that should become skills.
- `claude-md-management` plugin's session-learnings capture should route through this skill for project-scoped lessons.

## Plugin Compatibility

Required: none. This skill works with pure filesystem.
Enhanced by: `claude-md-management` (for session-learning capture), `episodic-memory` (for adjacent retrieval), ripgrep (for fast search).

## Hard Constraints

- NEVER delete an entry, in `lessons.md` or in `rejected.md`. Archives
  compress, they do not destroy.
- NEVER write a rejection without a reason. An entry reading "not worth doing"
  is unusable to the pass that reads it next, and the finding will simply come
  back.
- NEVER treat a deferred finding as a rejected one. Deferred work waits;
  rejected work is decided.
- NEVER write a lesson without a tag. Untagged lessons are unsearchable and degrade the system.
- NEVER write a lesson longer than 3 sentences. If it needs more, it is two lessons.
- NEVER load more than 70 entries at task start. Token budget matters.
- ALWAYS validate the project name is one of the known three before writing. Default to personal if unsure and log a warning.
