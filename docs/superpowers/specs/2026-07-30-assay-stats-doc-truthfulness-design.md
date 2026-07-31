# /assay-stats doc truthfulness — design

**Date:** 2026-07-30
**Risk tier:** TRIVIAL (doc-only, single file)
**Status:** approved

## Problem

`/assay-stats` documentation makes two false statements about the tool.

1. `.claude/commands/assay-stats.md:48` tells the reader to "read the tier
   breakdown before cutting anything." No per-tier breakdown exists.
   `scripts/assay_stats.py` emits only a run-count-by-tier line in the header
   (`tiers: {'HIGH': 6}`) — a census of runs, not a per-tier split of any
   metric. A reader following the instruction looks for output that is not
   there.
2. The same file's frontmatter says the run log is "written by /assay Step 14."
   The emitter is Step 14b. Step 14 is REPORT; 14b is RUN RECORD.

Both are defects introduced when the instrumentation shipped
(`4eaed73`). Neither affects behavior — they mislead the operator reading the
docs to decide whether to cut a judge.

## Decision

Fix the documentation to describe what the tool does. Do not build the missing
feature.

- Line 48: "read the tier breakdown" → "check the tier counts in the header".
- Frontmatter: "Step 14" → "Step 14b".

No code changes. No new tests.

## Why not build the per-tier split

The obvious reading of defect (1) is "the tool is missing a feature." Sample
size says otherwise.

Per-tier edit-after-review divides an already-tiny sample across up to five
buckets. `MIN_N_EDIT` is 5, so a bucket renders a verdict only after five
judged runs *at that tier*. Lifetime `/assay` invocations are approximately 4
(`~/.claude/memory/global/skill-stats.json`), and the run log itself is empty —
instrumentation shipped the same day as this spec. Every bucket would print
`insufficient data` for roughly the next year of usage at current run volume.

That is code whose only output is a promise to report later. It also inverts
the rule the module already states in its own docstring: "A confident number
computed from four runs is worse than no number, because it gets believed."

Revisit when the run log holds enough judged runs at a single tier to clear
`MIN_N_EDIT` — check with `/assay-stats` before reopening this.

## Alternatives rejected

**Build the split with the standard insufficient-data guard.** ~25 lines plus
three tests. Makes the doc true and is correctly cautious. Rejected on timing,
not on design: it adds a section that says nothing measurable for a year, and
the doc can be made true today for free.

**Build the split with no minimum-n guard.** Renders raw per-tier rates
immediately. Rejected outright — reporting "HIGH: 100.0% ok" off a single run
manufactures exactly the false confidence the guards exist to prevent, and
contradicts the module's stated design rule.

## Success criteria

1. No sentence in `assay-stats.md` describes output `assay_stats.py` does not
   produce.
2. The frontmatter names the correct emitting step (14b).
3. `uv run pytest` and `uv run ruff check .` and `uv run ruff format --check .`
   all pass.
4. `scripts/assay_stats.py` is unmodified — confirms the fix stayed doc-only.

## Testing

Existing coverage suffices. `tests/test_commands.py` asserts every command file
is non-empty, has frontmatter, and that `name` matches the file stem — all still
hold after a description edit. No behavior changes, so no new tests. Adding a
test that greps prose for a phrase would couple the suite to wording and break
on the next honest rewrite.

## Ways this could be wrong

- **The reader wanted the feature, not the doc fix.** If per-tier analysis is
  what actually gets used when pruning judges, this defers real value to avoid
  a temporarily-empty section. Mitigated by the revisit trigger above.
- **"Tier counts in the header" may still over-promise.** The header reports how
  many runs occurred at each tier — enough to notice a rate is dominated by
  TRIVIAL runs, not enough to decompose the rate itself. The replacement wording
  claims only the former.
- **Deferring on n could become permanent.** If `/assay` usage never rises, the
  split never gets built and the header stays the only tier signal. That is the
  correct outcome at that run volume, but it should be a decision, not drift.
