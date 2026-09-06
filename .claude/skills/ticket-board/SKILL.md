---
name: ticket-board
description: Slices an approved spec into thin vertical tickets and maintains them as a DAG. A vertical slice crosses every layer the feature touches — storage, logic, interface — so it is independently testable and yields integrated feedback immediately; horizontal slices (all the schema first, then all the endpoints) hide integration failures until the last step. Each ticket declares what blocks it, which is what lets /implement pick safely and run independent slices in parallel on separate branches. Use when Brandon types /to-tickets, when an approved spec is bigger than one commit, when /assay finds a task needs more than one reviewable diff, or when QA findings need to re-enter the queue as blocking work. Backend and path come from ~/.claude/assay.config.json. Read/write on tickets; never edits code.
---

# ticket-board

A spec says where to go. Tickets say what to build first, and what cannot
start yet. This skill turns one into the other and then owns the board.

## The vertical slice rule

Agents left alone build horizontally: every schema change, then every service
method, then every endpoint, then the UI. It reads as organized and it is a
trap — nothing is integrated until the final layer lands, so the first real
feedback about whether the design works arrives when the whole feature is
already written.

**Every ticket must cross every layer its feature touches**, however thinly.
One row, one code path, one rendered element. A tracer bullet, fired all the
way through, so the integration is proven at the first commit and every
subsequent slice widens something that already works.

Test for a valid slice — all four:

1. **Demonstrable.** Someone can observe it working from outside the code.
   Not "the migration is applied" — "a lesson written today appears in
   `/assay-stats` output."
2. **Independently testable.** It names a seam from the spec, and a test can
   drive that seam without the other tickets existing.
3. **One reviewable diff.** If it cannot be reviewed in one sitting, it is two
   tickets.
4. **Shippable alone.** Merging only this ticket leaves the repo working, even
   if the feature is incomplete.

**Rejection criteria.** If a proposed ticket set contains a ticket whose title
is a layer name — "add the database schema", "build the API endpoints",
"wire up the UI" — the slicing is horizontal. Discard the set and re-slice by
user-observable behavior instead. Say that this is what happened; do not
silently fix it, because the same instinct will produce the same set next time.

The one exception: a genuine prerequisite that is not itself a feature slice
(adding a dependency, creating a config file, scaffolding a package). Mark it
`kind: groundwork` and keep it to one per spec. More than one is horizontal
slicing wearing a hat.

## Config

Read from `~/.claude/assay.config.json` via `scripts/assay_config.py`:

```
tickets.backend   repo-files (default) | memory-dir
tickets.path      docs/tickets   — relative to repo root; repo-files only
```

- **repo-files** — `<repo-root>/<tickets.path>/`. Versioned with the code the
  tickets describe; visible in review; survives a machine.
- **memory-dir** — `$HOME/.claude/memory/projects/<ns>/tickets/`. Keeps
  work-in-progress out of the repo. Namespace detected by the project-memory
  rules.

Never hardcode either. Resolve at every invocation — the operator may switch.

## Invocation contract

```
/to-tickets <spec-id>              # slice an approved spec into the board
/to-tickets <spec-id> --dry-run    # show the slice set, write nothing
/to-tickets board                  # render the DAG + what is unblocked now
/to-tickets next                   # the single highest-priority unblocked ticket
/to-tickets show <ticket-id>
/to-tickets add "<title>"          # one-off ticket, no spec
/to-tickets block <id> --by=<id>   # add an edge
/to-tickets status <id> <status>   # todo|in-progress|needs-qa|done|blocked
/to-tickets reconcile              # verify, refresh, unblock, retire the board
```

## Ticket format

One file per ticket: `<ticket-dir>/<ticket-id>.md`.

```markdown
---
ticket-id: parallelize-walkforward-2026-05-17-03
spec: parallelize-walkforward-2026-05-17
finding: perf-2026-05-16-02          # only when a survey finding produced it
title: Walk-forward runs on a worker pool for a single fold
status: todo
kind: slice | groundwork | qa | bug
tier: MEDIUM
blocked_by: [parallelize-walkforward-2026-05-17-01]
seam: run_walkforward() — engine/tests/test_walkforward.py
branch: slice/walkforward-pool
planned_at: a1b2c3d                  # short SHA this ticket was written against
created: 2026-05-17
---

## Slice

<One sentence: the user-observable behavior this makes true. Then the layers
it crosses, one line each, so the vertical claim is checkable.>

Crosses: config → pool executor → `run_walkforward()` → CLI output.

## Acceptance

- [ ] <Observable outcome, testable at the named seam>
- [ ] <Observable outcome>

## Out of scope

- <What a reader would reasonably assume is included and is not>
```

### Executor context (MEDIUM+ and every `--parallel` ticket)

The sections above are enough for a ticket Brandon runs himself in a session
that already has the repo loaded. They are **not** enough for a subagent in a
fresh worktree, which is what `/implement --parallel` dispatches: it has no
session context, sees only committed files, and has no way to ask a question.
That executor is the weakest plausible reader of this file, and a ticket that
assumes context it does not have produces a diff that misses.

So add these four sections whenever the tier is MEDIUM or above, **or** the
ticket may be run under `--parallel` at any tier:

```markdown
## Current state

- `engine/walkforward.py` — the sequential loop, lines 40–72.

<A short excerpt of the code as it exists today, with `file:line` markers, so
the executor can confirm it is looking at the right thing.>

Conventions this must match: <the pattern, plus one exemplar file to copy —
"error handling follows the Result pattern, see `engine/result.py` and its use
in `engine/scoring.py:40-60`">.

Vocabulary: <the glossary terms from `glossary.path` this work must use in
names and comments, quoted — the executor has not read that file>.

## Commands

| Purpose | Command | Expected |
|---|---|---|
| Tests | `uv run pytest engine/tests/test_walkforward.py` | exit 0 |
| Lint | `uv run ruff check .` | exit 0 |
| Types | `uv run mypy` | exit 0 |

(Read from the repo during slicing, never guessed. A guessed command produces
a ticket that fails its own acceptance.)

## Drift check

`git diff --stat <planned_at>..HEAD -- <in-scope paths>`

If any in-scope file changed since `planned_at`, compare the Current state
excerpt against the live code before starting. A mismatch is a STOP condition.

## STOP conditions

Stop and report rather than improvising if:

- The code does not match the Current state excerpt.
- A verification fails twice after one reasonable fix attempt.
- The work appears to require touching something in Out of scope.
- <the specific assumption this slice rests on> turns out to be false.
```

STOP conditions must be specific to this slice's actual risks. Boilerplate
copied between tickets is not a STOP condition; it is decoration, and an
executor learns to ignore it.

The tier gate is a cost decision. A LOW ticket does not need a novel, and
writing one taxes every slice to protect the few that need it. But `--parallel`
overrides the tier: zero-context execution is the condition that makes the
extra sections load-bearing, not the size of the change.

Ticket ids are `<spec-id>-NN`, two-digit, assigned in dependency order so the
numbering itself hints at sequence. One-off tickets (`add`) use
`<kebab-slug>-<YYYY-MM-DD>`.

`seam` is copied from the spec's Testing seams table. A slice with no seam
cannot start a TDD loop, so slicing **fails** rather than emitting one: say
which behavior has no seam and send Brandon back to `/spec revise`.

## Pipeline

### Step 1: LOAD SPEC

Resolve `<spec-id>` through spec-builder's rules. Refuse `draft` — "Run
`/spec approve <spec-id>` first." Warn on `shipped`.

Read Success criteria, Implementation choices, Testing seams, Non-goals. Those
four are the slicing inputs; Problem and Hypothesis are context only.

### Step 2: PROPOSE SLICES

Draft 3-8 slices. Fewer than 3 and the spec did not need slicing — say so and
suggest `/assay <spec-id>` directly. More than 8 and the spec is two specs —
say that too, and name the seam where it splits.

Order by **thinnest end-to-end path first**. The first ticket should be the
smallest thing that proves the whole stack connects, even if it handles one
hardcoded case. Everything after widens it.

Run each slice against the four-part test above. Run the whole set against the
rejection criteria. Re-slice on failure, once, then surface to Brandon.

### Step 3: BUILD THE DAG

Set `blocked_by` from real dependencies only: ticket B is blocked by A if B
cannot be *tested* without A. Not "would be tidier after A" — that is
sequencing preference, and it serializes work that could run in parallel.

Validate before writing:

- **Acyclic.** Walk the graph; a cycle is a slicing error, not an edge to
  delete. Re-slice the cycle members.
- **No dangling refs.** Every id in `blocked_by` exists.
- **A root exists.** At least one ticket with empty `blocked_by`, or nothing
  can ever start.
- **Width is real.** If every ticket blocks the next, the set is a list, not a
  DAG. Say so — it may be correct, but it forfeits all parallelism, and that
  is worth one line of explanation.

### Step 4: SHOW

Render the set before writing anything:

```
Slices for <spec-id>  (5 tickets, max parallel width 3)

  01  Thinnest path: one fold through the pool          [unblocked]
  02  Fold count from config                            [blocked by 01]
  03  Deterministic seeds across workers                [blocked by 01]
  04  Progress output per worker                        [blocked by 01]
  05  Failure of one worker fails the run cleanly       [blocked by 02, 03]

Parallelizable now: 01
After 01: 02, 03, 04 can run on separate branches.
```

Accept `write` / revise / abort. `--dry-run` stops here always.

### Step 5: WRITE

Write one file per ticket through the configured backend, plus `_board.md`:

```
| ticket | title | status | tier | blocked_by | branch |
```

`_board.md` is derived state — regenerate it from the ticket files rather than
editing it in place, so a hand-edited ticket cannot desync the board.

## Board queries

**`board`** — render the DAG grouped by status, and state the current parallel
width. Mark anything `blocked_by` a `done` ticket as newly unblocked.

**`next`** — the single ticket `/implement` would pick: unblocked, `todo`,
highest tier first (a HIGH slice failing early is cheaper than after three
MEDIUM slices land on top of it), then lowest id. Ties broken by id, so the
choice is reproducible.

A ticket is **unblocked** when every id in `blocked_by` has status `done`.
`needs-qa` is not `done` — a slice awaiting hands-on review does not unblock
work built on top of it. That is the whole point of the QA queue.

## Reconcile

A board with no reconcile pass rots. Tickets written three weeks ago describe
code that has moved; `blocked` tickets sit behind obstacles nobody revisited;
`todo` tickets describe findings that got fixed in passing by an unrelated
slice. None of that is visible from the board itself — every row still looks
live — so the board quietly becomes a to-do list nobody trusts, and the DAG
that `/implement` walks stops meaning anything.

`reconcile` processes what happened since the last pass. Read every ticket
file, then by status:

- **`done`** — spot-check the cheap acceptance criteria against current HEAD.
  Mark verified. Never delete the file; it is the record of what shipped.
- **`needs-qa`** — check whether `/qa` has run. Stale beyond a week, flag it:
  a slice nobody has laid hands on is blocking everything built on top of it,
  and that is the QA queue working as designed only if someone eventually
  arrives.
- **`in-progress`** — almost always a crashed batch. Check whether the branch
  exists and what is on it, then flag to Brandon. Never silently reset it.
- **`blocked`** — read the reason and investigate the obstacle in the code.
  Either re-slice around it (a new ticket id when the approach changed
  fundamentally, an in-place rewrite when it did not) or retire it to the
  rejection ledger with one line of rationale.
- **`todo`** — run the drift check against `planned_at`. If in-scope files
  moved, **re-verify the work is still needed** before refreshing anything: a
  finding fixed in passing is retired to the rejection ledger, not rewritten.
  If it is still needed, refresh the Current state excerpt and stamp a new
  `planned_at`.

A ticket carrying a `finding` id closes the loop back to `survey`: when it
lands, mark the finding `promoted` and done; when it is retired, write the
finding to `rejected.md` with the reason, so the next cadence survey does not
re-derive it.

Finish with a short report — what verified, what refreshed, what retired, and
what is executable right now. Then stop. Reconcile changes ticket files and the
ledger; it never changes code and never commits.

## Integration

- **`/spec`** — an approved spec is this skill's input. Testing seams are
  load-bearing: no seam, no ticket.
- **`/implement`** — picks unblocked tickets and runs `/assay <ticket-id>` on
  each. Never picks a ticket this skill has not validated.
- **`/assay <ticket-id>`** — a third invocation form. The ticket supplies the
  task, the tier, the seam, and the acceptance criteria that become done-gate
  Check 1.
- **`/qa`** — findings become new tickets with `kind: qa`, which **block** the
  spec's remaining tickets when they invalidate an assumption, and stand alone
  when they are polish. Ask which; do not assume.
- **`/architecture`** — extraction proposals become `kind: groundwork` tickets.
- **`/survey`** — vetted findings become `kind: bug` or `kind: groundwork`
  tickets carrying a `finding` id and the survey's verified commands. A
  finding with no seam never arrives here; it goes to `/spec` instead.

## Hard constraints

- NEVER accept a horizontal slice set. Re-slice and say that you did.
- NEVER write a ticket with no seam.
- NEVER add a `blocked_by` edge for sequencing preference. Only testability.
- NEVER edit `_board.md` by hand; regenerate it from the ticket files.
- NEVER mark a ticket `done` from this skill. Only `/assay`'s commit step
  does that, and only after a real commit exists.
- NEVER write outside the configured backend path.
- NEVER write a MEDIUM+ or `--parallel`-eligible ticket without Current state,
  Commands, a drift check, and STOP conditions. A zero-context executor cannot
  ask, and improvises instead.
- NEVER copy an excerpt from a survey finding or a subagent report without
  opening the file. Cited line numbers are leads; a wrong excerpt becomes a
  ticket that fails its own drift check.
- NEVER guess a verification command. Read it from the repo or leave the ticket
  unwritten.
- NEVER let `reconcile` edit code, commit, or reset a stuck ticket silently.
