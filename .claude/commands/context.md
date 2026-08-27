---
name: context
description: Maintain the project's ubiquitous language — a CONTEXT.md glossary of what this codebase's words mean, plus architecture decision records for choices a future reader would otherwise reverse by accident. Naming a mechanism once and reusing that name shortens every later prompt, keeps code naming consistent, and stops each session from re-deriving the same explanation. Entry point for the context-glossary skill. Modes: init, add, extract, adr, show, lint. Paths come from ~/.claude/assay.config.json (glossary.path, glossary.adr_path).
argument-hint: [init] | add "<term>" | extract [--session] | adr "<decision>" | show "<term>" | lint
---

# /context — Ubiquitous Language

Entry point for the `context-glossary` skill. Owns two artifacts that live in the repo, next to the code they describe:

- **`CONTEXT.md`** — the glossary. What this project's words mean. `/assay` Step 2 loads it on every run.
- **`docs/adr/NNNN-<slug>.md`** — decision records. Why a choice was made, and what lost.

Both paths are per-install; read them from `~/.claude/assay.config.json` via `scripts/assay_config.py`, never hardcoded.

## Invocation

```
/context                     # status: term count, ADR count, lint summary
/context init                # create the glossary + ADR directory
/context add "<term>"        # interview for one entry, append it
/context extract             # scan the working diff for unnamed concepts
/context extract --session   # scan this session's transcript instead
/context adr "<decision>"    # write an ADR from the decision under discussion
/context show "<term>"       # print one entry
/context lint                # report drift between the glossary and the code
```

## Why this exists

Vocabulary is compression. "The materialization cascade" costs four tokens; the paragraph it replaces costs sixty, and gets re-written slightly differently every session. Worse, without an agreed name the code accumulates three names for one concept and every reader pays for the ambiguity.

The glossary is also the cheapest context an agent can carry: small, stable, and read on every run.

## Behavior

Delegates to `context-glossary`. See that skill for the entry format, the ADR template, and the full pipeline. Summary:

1. **RESOLVE PATHS** — from config, against the repo root.
2. **LOAD** — parse existing `##` headings into the dedupe set. A near-match is a revision of that entry, never a second entry.
3. **GATHER CANDIDATES** — max 5 per run. From the named term, the working diff, the session transcript, or the decision in context.
4. **INTERVIEW** — one question at a time, each with a recommended answer. Is it real? What is it *not*? What carries the name in code?
5. **SHOW DIFF + WRITE** — exact markdown shown before anything is written. Per-entry `y` / edit / skip.

## Entry shape

Every entry states what the term **is**, what it **is not**, and what carries it **in code**. The exclusion is the useful half — a definition with no stated boundary is a synonym and will drift. A term nothing in the code greps for is a rename proposal, and gets flagged as one.

## When it fires on its own

- `/spec` grill loop coins a term → routed here at spec-write time, so the spec and the code use the same word from the start.
- `/assay` Step 12 LEARN → scans the shipped diff for unnamed concepts. Proposals only, never blocking.
- `/architecture` → a proposed deep module needs a name; the extraction proposal carries a draft entry for the new boundary.

## Constraints

- Never writes a term the code does not use without flagging it as a rename.
- Never rewrites an existing entry without showing the diff and getting approval.
- Never blocks a pipeline — every mode is advisory.
- `lint` is read-only. It reports orphaned, undefined, and colliding terms; it proposes nothing.
