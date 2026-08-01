---
name: assay-stats
description: Report whether /assay is actually earning its cost. Reads the run log written by /assay Step 14b and computes four metrics — stage fire rate, edit-after-review rate, per-judge acceptance, and first-pass approval — each with a kill threshold and an explicit sample size. Use when Brandon asks "is /assay working", "which judges are worth keeping", "is the judge panel doing anything", or before pruning the judge roster. Read-only; never modifies the log.
argument-hint: [--since=<YYYY-MM-DD>] [--json] [--log=<path>]
---

# /assay-stats — Is the pipeline earning its cost?

Instrumentation readout, not an experiment. Answers four questions from the
run log at `$HOME/.claude/memory/global/assay-runs.jsonl`.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/assay_stats.py" $ARGUMENTS
```

If `CLAUDE_PLUGIN_ROOT` is unset (symlink install straight from a clone),
resolve the script from the repo the `/assay` command symlink points at —
`readlink -f ~/.claude/commands/assay.md` gives the plugin root three levels
up.

Pass `--since=<YYYY-MM-DD>` to scope to a window, `--json` for the raw report,
`--log=<path>` to read a log other than the default.

## The four metrics

| Metric | Reads | Kill threshold | What a failure means |
|--------|-------|----------------|----------------------|
| **Stage fire rate** | `stages_fired` / `stages_eligible` | <70% | The stage is not running when it should. This is a skill-description problem, not a skill-quality problem — fix the trigger wording before judging the stage. |
| **Edit-after-review** | `diff_before_review` vs `diff_after_review` on judged runs | <20% | The judge panel produces findings that never change the shipped diff. The panel is theater; cut judges or cut the step. |
| **Judge acceptance** | per judge, `accepted` / `concerns` | <15% | That judge raises concerns Brandon consistently ignores. Cut it from the roster or drop it to a cheaper model. |
| **First-pass approval** | `brandon_verdict == approved_first_pass` | (north star, no kill line) | Read next to median rework turns. This is the number the whole pipeline exists to move. |

## Reading the output honestly

- **Every metric prints its own n.** Below the minimum sample size the script
  prints `insufficient data` instead of a rate. Do not read past that — a
  confident percentage computed from four runs gets believed and then
  misleads.
- **Judge acceptance clears its bar first.** It is counted in concerns, not
  runs: one HIGH-tier run contributes ~10 concern records. Expect a usable
  per-judge table long before first-pass approval means anything.
- **Stage fire rate is the first thing to check.** A stage that never fires
  makes every downstream metric about it meaningless.
- **A low edit-after-review rate is not automatically bad at TRIVIAL/LOW
  tier** — those runs are supposed to sail through. Scope with `--since`, or
  check the tier counts in the header, before cutting anything.

## What this command does NOT do

It does not compare /assay against not-using-/assay. Instrumentation shows
which stages are live; it cannot attribute quality. A paired A/B — same tasks,
with and without the pipeline, blind-graded by a subagent with order
randomized — is the only thing that answers "is it better", and it is worth
running only for stages this command shows are both firing and changing diffs.

## Failure modes

| Situation | Behavior |
|-----------|----------|
| Log file absent | Reports zero runs and says so. Not an error. |
| Malformed JSONL line | Skipped, counted, surfaced as a `!` warning. Never aborts the report. |
| No judge records yet | Judge table renders empty rather than dividing by zero. |
