---
name: architecture-scan
description: Scans a repository for shallow, highly-coupled file clusters and proposes extracting them into deep modules — narrow interfaces hiding substantial implementation. Agents are unusually sensitive to this: a sprawl of tiny files that export everything forces an agent to hold a large fragile dependency graph in context, which is exactly how context gets exhausted and bugs get written. Use when Brandon types /architecture, when a /assay run keeps touching the same six files for unrelated reasons, when a subagent reports it could not scope a change without reading half the repo, or every few days as entropy control. Proposal-only — never refactors on its own.
---

# architecture-scan

An agent's effective intelligence in a codebase is bounded by how much of that
codebase it has to hold at once to make a safe change. Two repos with identical
functionality can differ by an order of magnitude on that measure.

**Deep module** — a simple, narrow interface hiding substantial implementation.
An agent reads the interface, gets the whole contract, and changes the inside
freely. Cheap to work in.

**Shallow module** — a thin file that exports everything it has, whose real
behavior lives in how it is called. An agent must read every caller to know
whether a change is safe. Twenty of these are worse than one large file,
because the dependency graph is now the thing you must understand, and it is
invisible.

This skill finds the shallow clusters and proposes boundaries. It never
performs the extraction.

## Signals

Scan for, in rough order of how much they cost an agent:

1. **Bidirectional coupling.** A imports B and B imports A, directly or through
   a cycle. Nothing can be understood alone. Strongest signal there is.
2. **Fan-out per unit of behavior.** A file whose change requires touching 5+
   others. Measure from git history — files that co-change in the same commit
   more than ~60% of the time are one module wearing several filenames.
3. **Interface-to-implementation ratio.** A module exporting 12 symbols with 40
   lines of logic is a namespace, not a module. Invert it.
4. **Leaked internals.** Callers reaching for a type, constant, or helper that
   exists only to serve the module's own implementation. Each one is a piece of
   interface nobody designed.
5. **Pass-through layers.** A function that only calls one other function and
   renames the arguments. Depth without benefit.
6. **Context cost.** Files that repeatedly appear together in `/assay` runs
   about unrelated tasks. Sourced from the run log — this is the most direct
   evidence available, since it measures what work actually required.

## Invocation contract

```
/architecture                       # full scan, ranked proposals
/architecture <path>                # scan one subtree
/architecture --signal=<name>       # one signal only
/architecture --since=<ref>          # co-change analysis from a git ref
/architecture propose <cluster-id>  # expand one cluster into a full proposal
/architecture tickets <cluster-id>  # emit the proposal as groundwork tickets
```

## Pipeline

### Step 1: SCOPE

Default to the source tree, excluding tests, vendored code, generated files,
and anything gitignored. Respect the repo's own layout — a uv workspace's
members are scanned separately, since a boundary between members is intentional
and not a finding.

### Step 2: MEASURE

Build the import graph and the co-change matrix. Prefer `Explore` for the graph
on an unfamiliar tree. Co-change comes from `git log --name-only` over the last
~200 commits or `--since`.

Report the measurements before the interpretation. A cluster is a claim about
code, and the numbers are what make it checkable.

### Step 3: CLUSTER

Group files that move together. A cluster is a candidate module. Rank by
`(files in cluster) × (external callers) × (co-change rate)` — the product,
because a tight cluster nobody calls is not urgent and a widely-called single
file is not a cluster.

Cap at the top 5. An architecture report with 20 findings is read once and
acted on never.

### Step 4: PROPOSE

Per cluster, state:

- **The boundary.** What the new module's interface is — every exported symbol,
  in full. If the proposed interface has more than ~5 entry points, the boundary
  is wrong; say so rather than proposing it.
- **What moves inside.** The files or functions that become implementation.
- **What breaks.** Every caller that must change, counted, with the mechanical
  ones separated from the ones needing judgment.
- **The name.** Drafted as a `context-glossary` entry, because a boundary
  without an agreed name gets re-explained in every future session.
- **What this makes worse.** Mandatory. Extraction always costs something —
  indirection, a migration, a new place for state to hide. A proposal with no
  stated cost has not been thought through.

### Step 5: HAND OFF

Nothing here refactors. Output is one of:

- A report Brandon reads and closes.
- `/architecture tickets <cluster-id>` — the proposal becomes `kind: groundwork`
  tickets on the board, each an independently shippable step. A big-bang
  extraction is not a slice; break it into: introduce the interface alongside
  the old code, migrate callers in batches, delete the old path.
- An ADR via `/context adr` when the boundary reflects a real decision between
  alternatives.

## What not to flag

- **A large file that is already a deep module.** Length is not the signal.
  A 900-line file with three exports and no leaked internals is working
  correctly; splitting it into nine files makes things worse.
- **Test files.** Tests are supposed to depend on many things.
- **Deliberate seams.** A boundary the spec's Implementation choices or an
  existing ADR named on purpose is not a finding. Check before flagging.
- **Anything in a frozen project.** Per the repo's own CLAUDE.md, decommissioned
  trees are read-only portfolio pieces. Scan them if asked; propose nothing.

## Cadence

Every few days, or when a `/assay` run reports it could not scope a change
without reading half the repo. That report is the highest-signal trigger
available, because it is a measurement of the actual cost rather than a
prediction of it.

Software entropy is monotonic. The work is not to reach a good architecture
once; it is to lose ground more slowly than agents add code.

## Integration

- **`ticket-board`** — receives `kind: groundwork` tickets from proposals.
- **`context-glossary`** — every proposed boundary carries a draft entry.
- **`judge-panel`** — judge 17 (Karpathy) sees one diff; this skill sees the
  repo. They answer different questions and neither substitutes.
- **`project-memory`** — a cluster that keeps reappearing after being declined
  is a lesson about the codebase, worth recording.

## Hard constraints

- NEVER refactor. Proposals only, always.
- NEVER propose more than 5 clusters per run.
- NEVER propose a boundary with more than ~5 entry points — that is a namespace.
- NEVER omit the "what this makes worse" section.
- NEVER flag a boundary that an ADR or a spec's Implementation choices
  deliberately established.
- NEVER propose changes in a project marked frozen.
