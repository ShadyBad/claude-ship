---
name: implement
description: Batch executor for the ticket board. Walks the DAG, picks unblocked tickets, and runs a full /assay on each with the TDD loop and judge panel — then stops at done-gate and queues the finished diff for Brandon rather than committing it. Gets the throughput of an unattended night shift without handing over commit authority, which the completion contract reserves for a human. Use when the board has unblocked tickets and Brandon wants several slices worked through in one sitting, or when he says "work the board", "keep going", or "do the next few tickets".
argument-hint: [<ticket-id>] [--count=<n>] [--all-unblocked] [--parallel] [--dry-run] [--stop-on-fail]
---

# /implement — Work the Board

Reads the ticket DAG, runs `/assay` on unblocked tickets back to back, and parks each finished diff in a commit queue for you.

```
/spec  →  /to-tickets  →  /implement  →  /qa
```

## Invocation

```
/implement                      # the next unblocked ticket, one only
/implement <ticket-id>          # a specific ticket (must be unblocked)
/implement --count=3            # up to 3 tickets, sequentially
/implement --all-unblocked      # every currently unblocked ticket
/implement --parallel           # independent tickets on separate branches
/implement --dry-run            # show the pick order and stop
/implement --stop-on-fail       # halt the batch on the first failure
```

## The bargain

The playbook this pattern comes from runs agents unattended overnight in a container and lets them commit. That collides head-on with the completion contract: Brandon sees a commit overview and approves before anything lands. Rather than pick one, `/implement` splits the difference at the only point that matters.

Everything up to and including done-gate runs unattended and back to back — plan, TDD cycles, judges, revision loops, the full nine checks. **The run then stops at Check 8 and queues the diff.** Commit authority never moves.

What you get: N tickets' worth of reviewed, tested, judge-cleared work waiting when you come back, instead of one. What you keep: every commit still passes under your eyes.

## Per-ticket run

For each picked ticket, run the standard `/assay <ticket-id>` pipeline:

1. Ticket supplies the task, the tier, the seam, and the acceptance criteria (done-gate Check 1).
2. Mark the ticket `in-progress` before starting, so a crashed batch is diagnosable.
3. Create the ticket's `branch` if it does not exist. Never work two tickets on one branch — the queued diffs have to be separable.
4. Run the TDD loop per behavior, at the tier's floor.
5. Judge panel at the tier, then revise cycles as normal.
6. done-gate Checks 1-7 and 9.
7. **Stop.** Write the queue entry. Do not invoke commit-protocol.

## The commit queue

Each finished ticket writes to `$HOME/.claude/memory/sessions/<date>-<session-id>/commit-queue/<ticket-id>.md`:

- Branch, ticket id, tier.
- Proposed commit message.
- Diff stat and the file list.
- Judge verdict with the concerns that were accepted.
- The TDD proofs — red reason and green result per behavior.
- Anything the run had to assume.

Then, at the end of the batch:

```
Batch complete — 3 queued, 1 halted.

  ✓ slice/walkforward-pool     04  MEDIUM  +142 −18   judges: ship
  ✓ slice/worker-seeds         03  MEDIUM  +67  −4    judges: ship (1 concern accepted)
  ✓ slice/fold-config          02  LOW     +31  −9    judges: ship
  ✗ slice/worker-failure       05  HIGH    halted at Check 9 — false red on
                                            test_worker_failure_propagates

Review and commit:  /implement review
```

`/implement review` walks the queue one entry at a time through commit-protocol, which is where Check 8 finally happens.

## Pick order

From `ticket-board next`: unblocked, `todo`, highest tier first, then lowest id. Highest tier first is deliberate — a HIGH slice that fails is cheaper to discover before three MEDIUM slices are built on top of it.

A ticket unblocks only when every id in its `blocked_by` is `done`. A queued-but-uncommitted ticket is **not** `done`. So a batch cannot build on work you have not approved yet, which is what keeps the queue reviewable in any order.

That also caps a batch at the DAG's current parallel width. If `--count=5` and only two tickets are unblocked, you get two and are told why.

## Parallel mode

`--parallel` runs independent tickets as concurrent subagents on separate branches, one worktree each. Only tickets with no path between them in the DAG are eligible. Bounded by the risk tier's max-subagent ceiling from `/assay` Step 4.

Off by default. Serial is easier to interrupt, easier to read, and the wall-clock win only shows up on a genuinely wide board.

## Failure handling

A ticket that halts (judges block, done-gate fails, revise cycles exhausted) marks the ticket `blocked`, fires `/postmortem` in auto mode, and — by default — **the batch continues to the next ticket**. One bad slice should not idle the other four.

`--stop-on-fail` inverts that for when a failure suggests the whole slice set is wrong.

Nothing is left half-done: a halted ticket's branch is preserved with its work in place, and the queue entry records where it stopped.

## Constraints

- Never commits. Not with `--all-unblocked`, not with `--force`, not ever. `/implement review` → commit-protocol → your approval is the only path to a commit.
- Never picks a blocked ticket, even when named explicitly. It tells you what is blocking it.
- Never works two tickets on one branch.
- Never marks a ticket `done`. That happens at commit time, and only then.
