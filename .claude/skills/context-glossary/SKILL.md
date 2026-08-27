---
name: context-glossary
description: Maintains a project's ubiquitous language — a CONTEXT.md glossary of the terms this codebase uses for its own concepts, plus architecture decision records for the choices that are hard to explain twice. Naming a complex behavior once ("materialization cascade") and reusing that name keeps prompts short, keeps code naming consistent, and stops every future session from re-deriving the same explanation. Use when Brandon types /context, when a grilling session coins a term, when a shipped diff introduces a concept with no agreed name, when Claude finds itself explaining the same mechanism a second time, or when a decision gets made that a future reader would otherwise reverse by accident. Reads glossary.path and glossary.adr_path from ~/.claude/assay.config.json. Never rewrites an existing entry without showing the diff; never invents terms the code does not use.
---

# context-glossary

Vocabulary is compression. A term the whole project agrees on replaces a
paragraph of explanation in every prompt, every code review, and every future
session that touches the same area. Without one, each session re-derives the
same description in slightly different words, and the code ends up with three
names for one concept.

This skill owns two artifacts:

- **The glossary** — `CONTEXT.md` at the repo root (path from config). What
  the project's words mean. Loaded by `/assay` Step 2 on every run.
- **The ADRs** — `docs/adr/NNNN-<slug>.md` (path from config). Why a decision
  was made, so a future reader does not quietly reverse it.

## Config

Read paths from `~/.claude/assay.config.json` via `scripts/assay_config.py`:

```
glossary.path      default CONTEXT.md      the glossary file, relative to repo root
glossary.adr_path  default docs/adr        the ADR directory, relative to repo root
```

Both are per-install. Never hardcode either path.

## When to invoke

- Brandon types `/context` in any form.
- **During grilling** (`/spec`): the interview coins or clarifies a term.
  spec-builder hands candidate terms here rather than burying them in the spec.
- **After a ship** (`/assay` Step 12 LEARN): the diff introduced a concept the
  glossary does not name.
- **On repetition**: Claude explains the same mechanism for the second time in
  a session, or a lesson in `lessons.md` restates a definition. That is the
  signal a term is missing.
- **On a fork in the road**: a decision was made between real alternatives and
  the losing option is still plausible. That is an ADR, not a glossary entry.

## Invocation contract

```
/context                          # status: term count, ADR count, stale candidates
/context init                     # create CONTEXT.md + adr dir with a header
/context add "<term>"             # interview for one entry, append
/context extract                  # scan the working diff for unnamed concepts
/context extract --session        # scan this session's transcript instead
/context adr "<decision>"         # write an ADR from the decision in context
/context show "<term>"            # print one entry
/context lint                     # find drift between glossary and code
```

## Glossary entry format

One `##` section per term. Terse — a glossary that reads like prose stops
getting read.

```markdown
## Materialization cascade

**Is:** The chain that fires when a lesson is first written to disk — index
update, namespace fan-out, and statusline refresh, in that order.

**Is not:** A lesson being *loaded*. Loading is read-only and fires nothing.

**In code:** `materialize_lesson()` in `memory/cascade.py`; the `cascade_*`
event names.

**Coined:** 2026-08-26, spec `lesson-cascade-2026-08-26`.
```

Rules for an entry:

1. **Is / Is not are both required.** The boundary is the useful half. A term
   with no stated exclusion is a synonym, not a definition, and will drift.
2. **In code is required.** A glossary term that names nothing greppable is
   vocabulary theater. If nothing in the code carries the name, the entry is a
   rename proposal — say so explicitly and let Brandon accept or decline.
3. **Definitions are behavioral, not structural.** "The chain that fires
   when…" survives a refactor; "the three functions in cascade.py" does not.
4. **No entry for a term the codebase already makes obvious.** `retry`,
   `cache`, `handler` — skip. Earn the entry with genuine ambiguity.

## ADR format

```markdown
# NNNN — <decision, stated as the choice made>

- **Status:** accepted | superseded by NNNN | reversed
- **Date:** YYYY-MM-DD
- **Namespace:** <project namespace>

## Context
What forced a choice. The constraint, not the backstory.

## Decision
What we do now. Present tense, imperative.

## Alternatives rejected
Each real option, and the specific reason it lost. An ADR with no rejected
alternatives records a preference, not a decision — do not write it.

## Consequences
What this makes easy, and what it makes expensive. Both halves.
```

Number ADRs sequentially, zero-padded to four digits, from the highest existing
number in the directory. Never renumber; a superseded ADR keeps its number and
gains a `superseded by` status.

## Pipeline

### Step 1: RESOLVE PATHS

Read `glossary.path` and `glossary.adr_path` from config. Resolve against the
repo root (git top-level, or cwd if not a repo). If the glossary is missing and
the mode is not `init`, offer to create it and continue.

### Step 2: LOAD

Read the existing glossary. Parse `##` headings into a term list. This is the
dedupe set — a proposed term that is a near-match to an existing one is a
**revision** of that entry, never a second entry. Two entries for one concept
is worse than none, because now prompts have to pick.

### Step 3: GATHER CANDIDATES (mode-dependent)

- `add` — the term Brandon named.
- `extract` — read `git diff` (or the session transcript with `--session`).
  Look for: a multi-word phrase repeated 3+ times, a function or type name
  that needed a comment to explain what it is, and any concept the diff's own
  commit message had to spell out in more than one sentence.
- `adr` — the decision under discussion, plus the alternatives that were
  actually raised. If no alternative was raised, say so and stop.

Cap candidates at 5 per run. A 20-term dump is never reviewed; five are.

### Step 4: INTERVIEW

For each candidate, one question at a time, each with a recommended answer
Brandon can accept with `y`:

1. "Is this a real term, or incidental phrasing?" (drop / keep)
2. "What is it *not*?" — recommend the nearest concept it gets confused with.
3. "What carries this name in code today?" — recommend the greppable symbol.
4. If nothing carries it: "Rename `<current>` → `<term>`? That's a code change,
   not a doc change." Recommend declining unless the rename is small.

Never batch these. The point is alignment, and a batch gets one skim.

### Step 5: SHOW DIFF + WRITE

Show the exact markdown to be appended or replaced. Accept `y` / edit / skip
per entry. Only then write.

Entries append in alphabetical order by term. ADRs append as new files.

Existing entries are **never** silently rewritten. A revision shows the old
body and the new body side by side and requires explicit approval.

## Lint mode

`/context lint` reports drift, and proposes nothing on its own:

- **Orphaned** — glossary term whose "In code" symbol no longer greps. Either
  the code was renamed (update the entry) or the concept died (delete it).
- **Undefined** — a symbol appearing 5+ times across the codebase that reads
  like a domain concept and has no entry.
- **Colliding** — two entries whose Is/Is not overlap. Merge candidates.

Lint is read-only. Output a table; let Brandon pick what to act on.

## Integration

- **`/assay` Step 2 CONTEXT LOAD** — loads the glossary on every run, all
  tiers. It is small and it prevents renaming a concept the project already
  named. If the glossary exceeds ~150 lines, load headings plus the `Is:` line
  only; the full entry is read on demand.
- **`/spec` grill loop** — coined terms route here at spec-write time, so the
  spec and the code use the same word from the start.
- **`/assay` Step 12 LEARN** — after a successful ship, scan the diff for
  unnamed concepts (`extract` mode, non-blocking, proposals only).
- **`/architecture`** — a proposed deep module needs a name; the extraction
  proposal carries a glossary entry draft for the new boundary.
- **project-memory** — a lesson that restates a definition is a glossary entry
  trying to be born. Surface it.

## Hard constraints

- Never write a term the code does not use without flagging it as a rename.
- Never exceed 5 candidates per run.
- Never rewrite an existing entry without a shown diff and explicit approval.
- Never block a pipeline. Every mode is advisory; failure logs and continues.
- Never write the glossary outside the repo — it belongs to the code, and it
  is reviewed in the same pull request as the code that uses the words.
