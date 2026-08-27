---
name: architecture
description: Scan the repo for shallow, highly-coupled file clusters and propose extracting them into deep modules — narrow interfaces hiding substantial implementation. Agents are unusually sensitive to this: a sprawl of tiny files that export everything forces an agent to hold a large fragile dependency graph in context, which is how context gets exhausted and bugs get written. Entry point for the architecture-scan skill. Proposal-only; it never refactors. Run every few days as entropy control.
argument-hint: [<path>] [--signal=<name>] [--since=<ref>] | propose <cluster-id> | tickets <cluster-id>
---

# /architecture — Deep Modules

Entry point for the `architecture-scan` skill. Maintenance, not delivery — it runs on its own cadence, outside the ship loop.

## Invocation

```
/architecture                       # full scan, ranked proposals
/architecture <path>                # scan one subtree
/architecture --signal=<name>       # one signal only
/architecture --since=<ref>         # co-change analysis from a git ref
/architecture propose <cluster-id>  # expand one cluster into a full proposal
/architecture tickets <cluster-id>  # emit the proposal as groundwork tickets
```

## Why it matters more for agents than for people

An agent's effective intelligence in a codebase is bounded by how much of that codebase it must hold at once to make a safe change. A human can carry a fuzzy mental model across weeks; an agent re-derives everything from what fits in the window.

**Deep module** — narrow interface, substantial hidden implementation. Read the interface, get the contract, change the inside freely.

**Shallow module** — a thin file exporting everything, whose real behavior lives in how it is called. Every caller must be read before any change is safe. Twenty of these cost more than one large file, because now the dependency graph is the thing you have to understand and it is invisible.

## What it looks for

Ranked by how much each costs an agent: bidirectional coupling and import cycles; files that co-change in the same commit more than ~60% of the time; modules exporting twelve symbols over forty lines of logic; internals leaking into callers; pass-through layers; and files that keep appearing together in unrelated `/assay` runs — the last being the most direct evidence, since it measures work that actually happened rather than predicting it.

## What it will not flag

A large file that is already deep. Length is not the signal — a 900-line file with three exports and no leaked internals is working correctly, and splitting it into nine files makes everything worse. Also skipped: tests, boundaries an ADR or a spec deliberately established, and anything in a frozen project.

## Every proposal states

The exact interface (more than ~5 entry points means the boundary is wrong, and it says so instead of proposing it), what moves inside, every caller that breaks with mechanical changes separated from judgment calls, a drafted glossary name for the new boundary, and — mandatory — **what this makes worse**. Extraction always costs indirection, a migration, or a new place for state to hide. A proposal with no stated cost has not been thought through.

## Output

A report, or `tickets <cluster-id>` to put it on the board as `kind: groundwork` slices. A big-bang extraction is not a slice: it decomposes into introduce-the-interface, migrate-callers-in-batches, delete-the-old-path.

Capped at 5 clusters. A report with 20 findings is read once and acted on never.

## Cadence

Every few days, or the moment an `/assay` run reports it could not scope a change without reading half the repo.

Software entropy is monotonic. The work is not reaching a good architecture once — it is losing ground more slowly than agents add code.
