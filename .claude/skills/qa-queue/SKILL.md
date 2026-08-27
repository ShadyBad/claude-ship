---
name: qa-queue
description: Runs the hands-on quality pass that automation cannot do — pulling a shipped slice, actually using it, and turning what Brandon notices into new tickets rather than fixing it in a bloated context. Automated end-to-end coverage produces software that is technically correct and tasteless; the judgment about whether a thing feels right is the one input an agent cannot generate. Use when Brandon types /qa, when a ticket lands in needs-qa after commit, when he says "let me try it" or "this feels off", or when a batch from /implement finishes and the queue has entries. Reads qa.queue from ~/.claude/assay.config.json. Never fixes anything itself.
---

# qa-queue

Everything upstream of this skill checks whether the code is *correct*. Nothing
upstream checks whether it is *good*. Tests pass on interfaces nobody would want
to use, error messages nobody can act on, and flows that technically work while
feeling wrong at every step.

That judgment is Brandon's, and it only happens by using the thing. This skill's
job is to make that cheap and to make sure what he notices survives the session.

## The rule

**QA findings become tickets. They are never fixed in the QA session.**

The temptation is obvious: the bug is right there, the context is loaded, it is
a two-line change. But that context is the *end* of a long session — the far
side of the smart zone, holding a full pipeline's sediment — and it is the worst
place to make a judgment call. Worse, a fix applied here skips the TDD loop, the
judges, and done-gate entirely. It is the one path in the whole system that
lands unreviewed code.

So: write it down, file it, send the executor back to work.

## When to invoke

- Brandon types `/qa`.
- A `/implement` batch finishes and `needs-qa` is non-empty.
- Brandon says "let me try it", "this feels off", "that's not quite right".
- After any commit of user-facing behavior when `qa.queue` is `true`.

## Invocation contract

```
/qa                          # next needs-qa ticket, with run instructions
/qa <ticket-id>              # a specific ticket
/qa list                     # everything awaiting QA
/qa pass <ticket-id>         # accept: needs-qa -> done, unblocks dependents
/qa fail <ticket-id>         # findings become tickets; slice stays needs-qa
/qa note "<finding>"         # file one finding without a full session
```

## Pipeline

### Step 1: PULL

Take the oldest `needs-qa` ticket (or the named one). Read its Slice,
Acceptance, and Out of scope sections, plus the commit SHA.

### Step 2: BRIEF

Tell Brandon exactly how to exercise it. Not "test the feature" — the specific
commands, the URL, the input that reaches the new path:

```
Ticket 04 — Walk-forward runs on a worker pool
Commit  a1b2c3d on slice/walkforward-pool

Run it:
  uv run python -m mib.walkforward --folds 4 --start 2015 --end 2020

Watch for:
  - [ ] Four workers start and the run finishes                (acceptance 1)
  - [ ] Progress prints per fold, not per row                  (acceptance 2)
  - [ ] Ctrl-C stops cleanly rather than orphaning workers     (acceptance 3)

Deliberately out of scope: seed determinism (ticket 03), failure
propagation (ticket 05). Don't file those.
```

The Out of scope line matters — without it, half of QA is re-reporting work
that is already queued.

Use the `run` skill when the project has a launch path it already knows.

### Step 3: OBSERVE

Brandon uses it. Claude stays quiet unless asked. Do **not** narrate what should
happen — that primes him to see it, and the whole value of this step is an
unprimed reaction.

### Step 4: CAPTURE

For each thing he mentions, ask two questions and nothing more:

1. **"Blocking or polish?"** — Blocking means the slice is not actually done, or
   an assumption the remaining tickets rest on is wrong. Polish means it works
   and could be better.
2. **"Which ticket does this block?"** — only for blocking findings. Default
   recommendation: the tickets that depend on this slice. Never assume; a
   finding that blocks nothing is polish with strong feelings.

Then file it. Ticket `kind: qa`, tier from the finding's shape, seam named if
one is obvious and left empty with a note if not — a QA ticket without a seam is
allowed to reach `/spec revise` rather than being blocked at slicing.

Record findings verbatim first, categorize second. "The progress output is
noisy" is data; "improve progress output formatting" is a paraphrase that has
already lost the complaint.

### Step 5: VERDICT

- **No blocking findings** → `/qa pass`: ticket goes `needs-qa` → `done`,
  dependents unblock, polish tickets sit in `todo` at whatever priority Brandon
  gives them.
- **Blocking findings** → ticket stays `needs-qa`, new QA tickets are inserted
  as blockers of whatever they block, and the board is regenerated. Say plainly
  which downstream tickets just became unreachable.

Either way, print the next action: `/implement` for the new work, or `/qa` for
the next queued slice.

## Taste findings are first-class

A finding like "this works but the empty state is depressing" is not noise and
does not need a defect to justify it. File it as `kind: qa`, polish, with
Brandon's exact words in the body. An agent will never generate that ticket on
its own, which is precisely why it is worth capturing.

## Integration

- **`/implement`** — its batch ends by naming what is now awaiting QA.
- **`ticket-board`** — receives filed findings; `needs-qa` never unblocks
  dependents, which is what keeps work from stacking on unreviewed slices.
- **`project-memory`** — a finding category that recurs 3+ times across specs is
  a lesson, not a ticket. Surface it as one.
- **`operator-model`** — repeated taste findings of the same shape are a
  preference. Propose the entry; never write it silently.
- **`/postmortem`** — a blocking finding that invalidates a spec assumption is a
  postmortem, not just a ticket.

## Hard constraints

- NEVER fix a finding inside a QA session. File it.
- NEVER mark a ticket `done` when a blocking finding is open.
- NEVER paraphrase a finding before recording it verbatim.
- NEVER prime Brandon with what he should be seeing before he uses it.
- NEVER file a finding the ticket declared out of scope without asking first.
