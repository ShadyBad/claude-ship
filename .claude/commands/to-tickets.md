---
name: to-tickets
description: Slice an approved spec into thin vertical tickets and maintain them as a DAG. A vertical slice crosses every layer its feature touches, so integration is proven at the first commit instead of the last; horizontal slicing (all the schema, then all the endpoints) hides failure until everything is written. Each ticket declares what blocks it, which is what lets /implement pick safely and run independent slices in parallel on separate branches. Entry point for the ticket-board skill. Modes: slice a spec, board, next, show, add, block, status, reconcile. Backend and path come from ~/.claude/assay.config.json.
argument-hint: <spec-id> [--dry-run] | board | next | show <ticket-id> | add "<title>" | block <id> --by=<id> | status <id> <status> | reconcile
---

# /to-tickets — Vertical Slices as a DAG

Entry point for the `ticket-board` skill. Sits between `/spec` and `/implement`.

```
/spec  →  /to-tickets  →  /implement  →  /qa
```

## Invocation

```
/to-tickets <spec-id>              # slice an approved spec onto the board
/to-tickets <spec-id> --dry-run    # show the slice set, write nothing
/to-tickets board                  # the DAG, grouped by status, with parallel width
/to-tickets next                   # the one ticket /implement would pick
/to-tickets show <ticket-id>
/to-tickets add "<title>"          # one-off ticket, no spec
/to-tickets block <id> --by=<id>   # add a dependency edge
/to-tickets status <id> <status>   # todo | in-progress | needs-qa | done | blocked
/to-tickets reconcile              # verify, refresh, unblock, retire the board
```

## Reconcile

A board with no reconcile pass rots, and it rots invisibly — every row still
looks live. Tickets written three weeks ago describe code that has moved.
`blocked` tickets sit behind obstacles nobody revisited. `todo` tickets
describe work an unrelated slice already did in passing.

`reconcile` spot-checks `done` against HEAD, flags stale `needs-qa` and crashed
`in-progress`, investigates `blocked` and either re-slices around the obstacle
or retires it, and drift-checks every `todo` against its `planned_at` SHA —
re-verifying the work is still needed before refreshing anything.

A ticket carrying a `finding` id closes the loop back to `/survey`: retired
work is written to the rejection ledger with a reason, so the next cadence
survey does not re-derive it.

It changes ticket files and the ledger. It never touches code and never
commits.

## The rule this exists to enforce

Left alone, an agent builds layer by layer: every schema change, then every service method, then every endpoint. It looks organized. It means the first honest feedback about whether the design works arrives after the entire feature is written.

Every ticket here crosses every layer it touches, however thinly — one row, one code path, one rendered element. A tracer bullet fired all the way through. The first ticket is the smallest thing that proves the stack connects; every later ticket widens something that already works.

A ticket qualifies only if it is demonstrable from outside the code, testable at a named seam without the other tickets existing, reviewable in one diff, and shippable alone.

If a proposed set contains a ticket whose title is a layer name, the slicing was horizontal — the set is discarded and re-sliced by observable behavior, and you are told that happened.

## Blocking edges

`blocked_by` means **cannot be tested without**. Not "would be tidier after." Sequencing preference disguised as a dependency serializes work that could have run in parallel on three branches.

The DAG is validated before anything is written: acyclic, no dangling ids, at least one root. If every ticket blocks the next, you get told the set is a list and forfeits all parallelism — it may still be right, but it should be a choice.

A ticket unblocks when every id in `blocked_by` is `done`. `needs-qa` is not `done`; work does not stack on a slice you have not laid hands on yet.

## Seams are load-bearing

Each ticket carries a `seam` copied from the spec's Testing seams table — the boundary a test drives. A slice with no seam cannot start a TDD loop, so slicing fails rather than emitting one, and names the behavior that needs a seam. Fix it with `/spec revise`.

## Output

```
Slices for parallelize-walkforward-2026-05-17  (5 tickets, max parallel width 3)

  01  Thinnest path: one fold through the pool          [unblocked]
  02  Fold count from config                            [blocked by 01]
  03  Deterministic seeds across workers                [blocked by 01]
  04  Progress output per worker                        [blocked by 01]
  05  Failure of one worker fails the run cleanly       [blocked by 02, 03]

Parallelizable now: 01
After 01: 02, 03, 04 can run on separate branches.
```

Nothing is written until you accept the set.

## Where tickets live

`tickets.backend` in `~/.claude/assay.config.json`:

- `repo-files` (default) — `<repo>/docs/tickets/`, versioned with the code they describe.
- `memory-dir` — `~/.claude/memory/projects/<ns>/tickets/`, out of the repo.

`_board.md` is regenerated from the ticket files, never hand-edited, so an edited ticket cannot desync the board.

## Constraints

- Fewer than 3 slices means the spec did not need slicing — use `/assay <spec-id>`.
- More than 8 means it is two specs, and you are told where it splits.
- Tickets are never marked `done` here. Only `/assay`'s commit step does that, and only once a commit exists.
