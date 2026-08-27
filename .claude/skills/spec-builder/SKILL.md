---
name: spec-builder
description: Transforms a fuzzy goal into a crisp, /assay-consumable spec via a relentless grilling session — one question at a time, each with a recommended answer, until Brandon's mental model and Claude's agree. Wires divergent framing, the grill loop, and operator-model (Brandon's constraint bias) into a single interview that produces a 1-page spec at $HOME/.claude/memory/projects/<ns>/specs/<spec-id>.md with status draft|approved|shipped. Use when Brandon types /spec, when a /assay task arrives without measurable success criteria, when Brandon says "I want to build X but I'm not sure what", or when an idea has been kicking around long enough to deserve a written hypothesis. Output feeds /to-tickets for vertical slicing. Coordinates with project-memory (loads relevant prior lessons), session-recall (surfaces prior similar specs), context-glossary (terms coined during the grill), and judge-panel (risk-tier classification for downstream /assay). Pinned. Never silently overwrites an existing spec — collisions get a numeric suffix.
---

# spec-builder

The missing step between fuzzy goal and `/assay`. Most bad ships come from shipping the wrong thing well. This skill forces the scoping moment.

## When to invoke

- Brandon types `/spec "<fuzzy goal>"` directly.
- Brandon types `/assay "<task>"` and the task description has no measurable success criteria (no numbers, no observable outcome, no test plan possible).
- Brandon says variations of: "I want to build X", "I should probably tackle Y", "what should I do about Z", "I have an idea for...".
- An auto-co or margin-invest task has been mentioned 3+ times across sessions without a spec being written.

## Invocation contract

```
/spec "<fuzzy goal>"                    # full interrogation
/spec "<fuzzy goal>" --quick            # skip framing, go straight to the grill
/spec "<fuzzy goal>" --deep             # raise the grill floor to 12 questions
/spec "<fuzzy goal>" --namespace=<ns>   # override detection
/spec "<fuzzy goal>" --risk=<tier>      # pre-set risk classification
/spec list                              # show all specs in current namespace
/spec list --status=draft               # filter
/spec show <spec-id>                    # print spec contents
/spec approve <spec-id>                 # flip status draft -> approved
/spec revise <spec-id>                  # reopen for edits, flip status back to draft
```

## Pipeline

### Step 1: PARSE

Extract from invocation:
- Fuzzy goal string.
- Flags (`--quick`, `--namespace`, `--risk`).
- Mode (`list`, `show`, `approve`, `revise`, or default new-spec).

If mode is `list`, `show`, `approve`, or `revise`: jump to the corresponding section below. Otherwise continue.

### Step 2: DETECT NAMESPACE

Use the project detection rules from `~/.claude/CLAUDE.md`:
1. `.claude/project-name` file (walk up to $HOME).
2. `git remote -v` pattern match (`auto-co`, `margin-invest`).
3. cwd path match (`/auto-co/`, `/margin-invest/`, `/margin_invest/`, `/margin-invest-backtest/`).
4. Fallback: `personal`.

`margin_invest/` and `margin-invest-backtest/` both map to namespace `margin-invest` (per project CLAUDE.md).

If `--namespace=` flag is set, override and log.

### Step 3: LOAD CONTEXT

In parallel:
1. **operator-model** — load Brandon's preferences. Pull the relevant section based on the goal's category (technical / business / process). Pull all "Things Brandon Hates" entries unconditionally.
2. **project-memory** — load last 50 lessons from `$HOME/.claude/memory/projects/<ns>/lessons.md`. Surface 3-5 most relevant to the fuzzy goal.
3. **session-recall** — search for prior specs with overlapping keywords. If a prior spec exists for a similar goal, surface its `spec-id` and status before continuing.

If session-recall finds a prior spec with status `draft` or `approved` on the same topic: stop and ask Brandon "Looks like spec `<spec-id>` covers similar ground (status: `<status>`). Revise it, or write a new one?" Default action: revise existing.

### Step 4: FRAME (skipped if --quick)

Before grilling the plan, check we are solving the right problem. Produce 3-5
alternative **framings** of the goal — not solutions, framings. "What problem
are we actually solving?"

Each framing is one sentence plus the thing it would make true. Bias them with
the operator-model constraints and the 3-5 lessons surfaced in Step 3, so no
framing violates something Brandon already rejected.

```
Three ways I can read this goal:
  [A] <framing> — succeeds when <observable>
  [B] <framing> — succeeds when <observable>
  [C] <framing> — succeeds when <observable>
Pick one, or describe a fourth.
```

Brandon picks one (or types a new framing). The picked framing replaces the
original fuzzy goal as the spec subject, and becomes the thing the grill
attacks.

### Step 5: GRILL

The heart of the skill. **Interview Brandon relentlessly, one question at a
time.** Not a form. Not a batch of seven questions — a batch gets one skim and
produces a spec that agrees with itself and nothing else.

The purpose is not to fill in sections. It is to **align two mental models**
before a line of code exists. A grilled spec exposes the edge cases neither
Brandon nor Claude had considered — whether a feature is retroactive, what
happens to existing rows, which of two plausible readings of "done" is meant.
Those are exactly the questions that, unasked, become a rewrite in Step 9.

**Loop protocol.** Repeat until the exit condition:

1. Ask exactly **one** question.
2. Attach a **recommended answer** and the reason for it. Brandon accepts with
   `y`, overrides with prose, or defers with `skip`. A question with no
   recommendation makes Brandon do the work — the recommendation is what makes
   a 30-question grill cost 5 minutes instead of an hour.
3. Record the answer. If the answer contradicts an earlier one, say so
   immediately and resolve it before moving on. Silent contradictions are how a
   spec ends up unbuildable.
4. Pick the next question from the highest-uncertainty area remaining, not from
   a fixed list. Follow the answer that surprised you.

**Question budget.** Minimum 8 questions, target 12-20, `--deep` raises the
floor to 12. Below 8, the spec is a transcription of what Brandon already said
and the grill did nothing.

**Exit condition** — all three must hold:

- Every section of the spec template can be filled without guessing.
- Claude can state the change's edge cases back to Brandon and Brandon agrees.
- The last three questions produced no new information.

Then state: "I think I have it. Here's what I heard —" and summarize in 5
bullets before writing anything. Brandon corrects the summary; that correction
is worth more than the previous ten answers.

**Question sources.** Push hardest on the areas that are cheapest to get wrong
now and most expensive later:

| Area | The question behind the questions |
|------|-----------------------------------|
| Retroactivity | Does this apply to data that already exists, or only new data? |
| Boundaries | What is the smallest version that is still worth shipping? |
| Failure | What should happen when this breaks at 3am? |
| Migration | What happens to the thing this replaces? |
| Observability | How will you know it worked, from outside the code? |
| Concurrency | What if two of these run at once? |
| Reversal | If this is wrong, how do we undo it? |
| Numbers | Every threshold, limit, timeout, and level — pin them now. |
| Vocabulary | What do we call this thing? (routes to context-glossary) |
| Seams | Where exactly does a test grab hold of this? |

The last two are new outputs, not just spec inputs:

- **Vocabulary** — any term coined or clarified during the grill is handed to
  `context-glossary` at write time, so the spec, the tickets, and the code all
  use the same word from the first commit.
- **Seams** — the answers become the spec's Testing Seams section, which is
  what makes the downstream `/tdd` loop able to write a failing test at all.

**Do not skip the grill to be polite.** Brandon typing a long initial goal is
not a substitute; a detailed wrong assumption is more expensive than a vague
one, because it looks finished.

### Step 6: SYNTHESIZE

Generate the spec markdown using the template in the "Spec Template" section below. Auto-fill:
- `spec-id`: `<kebab-slug>-<YYYY-MM-DD>` where slug is kebab-cased from the title, max 4 words. If a spec with this id exists in the namespace, append `-2`, `-3`, etc.
- `created`: today's date.
- `namespace`: from Step 2.
- `status`: `draft`.
- `risk-tier`: classify using the rules from `~/.claude/CLAUDE.md` Risk Tiers section. If `--risk=` flag set, override.

Title is generated from the picked framing in Step 4, max 8 words.

### Step 7: SHOW + APPROVE

Show the full spec to Brandon. Ask:

```
Spec written: <spec-id>
Path: $HOME/.claude/memory/projects/<ns>/specs/<spec-id>.md
Status: draft

Options:
  approve — flip status to approved, ready for /assay
  draft   — save as draft, return to it later
  revise  — re-open interrogation on a specific section
  abort   — discard, do not save
```

Default response: `draft`. Brandon must explicitly type `approve` to flip status. This is the gate that protects `/assay` from running unapproved specs.

### Step 8: WRITE

Create directory if missing: `$HOME/.claude/memory/projects/<ns>/specs/`.

Write the spec to `$HOME/.claude/memory/projects/<ns>/specs/<spec-id>.md`.

If status is `approved`: also append a one-line entry to `$HOME/.claude/memory/projects/<ns>/specs/_index.md`:
```
| <spec-id> | <title> | <risk-tier> | approved | <created> | unset |
```

Index columns: spec-id, title, risk-tier, status, created, shipped-at.

### Step 9: PRINT NEXT ACTION

```
Spec <spec-id> saved with status=<status>.

<if approved:>
Next: /assay <spec-id>

<if draft:>
Next: /spec approve <spec-id>   # when ready to ship
       /spec revise <spec-id>   # to keep editing
```

## Spec Template

```markdown
---
spec-id: <slug>-<YYYY-MM-DD>
title: <short title, max 8 words>
namespace: auto-co | margin-invest | personal
created: <YYYY-MM-DD>
status: draft
risk-tier: trivial | low | medium | high | critical
shipped-at:
shipped-commit:
---

# <title>

## Problem

<1-3 sentences. What hurts? Who feels it? Why now?>

## Hypothesis

<1 paragraph. Proposed fix and why it will work.>

## Success criteria

- <Measurable bullet 1 — must include a number, test name, or observable outcome>
- <Measurable bullet 2>
- <Measurable bullet 3>

## Non-goals

- <Explicit out-of-scope 1>
- <Explicit out-of-scope 2>
- <Explicit out-of-scope 3>

## Constraints

- <From operator-model — e.g. no premature optimization>
- <From project — e.g. margin_invest is frozen, don't touch>
- <From session — e.g. <2 hours of work>

## Implementation choices

<Every decision the grill pinned down. Schemas, thresholds, levels, timeouts,
enum values, defaults, retention windows. One line each, stated as a fact:
"Retry backoff is 3 attempts at 1s/4s/16s." No prose, no rationale — the
rationale that mattered became an ADR.>

- <choice 1>
- <choice 2>

## Testing seams

<Where and how this gets verified — the seam a test grabs hold of. This is
what /tdd writes its first failing test against, so it must name a real
boundary, not an intention. "Tested by unit tests" is not a seam.>

| Behavior | Seam | Kind |
|----------|------|------|
| <what must be true> | <function, endpoint, CLI, or fixture the test drives> | unit / integration / e2e / manual |

## Risks / Ways this could be wrong

- <Adversarial bullet 1>
- <Adversarial bullet 2>
- <Adversarial bullet 3>

## Plan sketch

- <Step / file / approach 1>
- <Step / file / approach 2>
- <Step / file / approach 3>

## Approval

- [ ] Brandon reviewed and approved
```

## Modes

### list

Show all specs in current namespace as a table:

```
| spec-id | title | tier | status | created | shipped-at |
```

Source: `$HOME/.claude/memory/projects/<ns>/specs/_index.md` if present, otherwise scan the directory and reconstruct.

`--status=<status>` filters. `--namespace=all` shows across all namespaces.

### show <spec-id>

Resolve spec-id in current namespace. If not found, search across all namespaces and surface the match. Print the full spec contents.

### approve <spec-id>

Flip status from `draft` to `approved`. Refuse if status is `shipped` (already done — write a new spec for follow-up work).

Update the `_index.md` row.

### revise <spec-id>

Flip status from any to `draft`. Re-enter interrogation, focused on the sections Brandon names. Save as same spec-id (not a new one) — preserves history.

If status was `shipped`: warn — "This spec already shipped. Revising creates a new draft on the same spec-id. Ship history will be preserved in the frontmatter."

## Coordination with /assay

`/assay` Step 1 PARSE checks if the first arg matches a spec-id pattern (`<slug>-\d{4}-\d{2}-\d{2}(-\d+)?`). If yes:

1. Resolve in current namespace's specs/ directory.
2. If found, load the spec.
3. If status is `draft`: refuse. "Run `/spec approve <spec-id>` first."
4. If status is `shipped`: warn. Allow with `--force`. Otherwise abort.
5. If status is `approved`: snapshot the spec into the session state directory. Lock it for the duration of this /assay run.

`/assay` Step 11 COMMIT, on successful commit: update spec frontmatter `status: shipped`, `shipped-at: <date>`, `shipped-commit: <SHA>`. Update `_index.md` row.

This is what makes a spec a contract, not just a doc.

## Failure modes

| Failure | Default behavior |
|---------|------------------|
| Brandon answers `skip` repeatedly | After 3 consecutive skips, stop the grill and say what cannot be filled in without those answers. Do not guess. |
| Grill exits under 8 questions | Refuse to write. Say which sections are still guesses. |
| Contradictory answers | Surface immediately, resolve before continuing. Never write a spec containing both. |
| operator-model file missing | Continue without constraint bias. Log warning. |
| Namespace directory creation fails | Surface error. Do not write spec. |
| Spec-id collision (same slug, same day) | Append `-2`, `-3`, etc. until unique. |
| Brandon types `abort` at Step 7 | Discard. Nothing written. |
| Brandon revises a `shipped` spec | Preserve `shipped-at` and `shipped-commit`. New draft is on the same id. |

## Hard constraints

- NEVER write a spec with `status: approved` without Brandon explicitly typing `approve`.
- NEVER overwrite a `shipped` spec. Revising creates a new draft on the same id; ship history is preserved.
- NEVER skip the Risks section. Inherited from margin-invest-backtest convention — every spec must end with an adversarial section.
- NEVER infer success criteria. If Brandon refuses to give a measurable outcome, abort the spec with "Without measurable success criteria, /assay cannot verify done. Walk away or come back with a number."
- NEVER write a spec whose Testing seams section says how it will be tested rather than where. A seam names a boundary a test can drive.
- NEVER batch grill questions. One at a time, each with a recommendation, or the alignment does not happen.
- ALWAYS load operator-model before the grill. Brandon's constraints bias the questions.
- ALWAYS append to `_index.md` so `/spec list` and `/assay`'s spec-id resolution stay cheap.

## Dependencies

- `operator-model` skill — Step 3 constraint loading, and the bias behind every recommended answer.
- `project-memory` skill — Step 3 lesson loading.
- `session-recall` skill — Step 3 prior-spec search.
- `context-glossary` skill — receives terms coined during the grill (Step 5), at write time.

The grill and the framing step run inline. They previously delegated to
`superpowers:brainstorming` and `ecc:prp-prd`; both plugins are uninstalled and
the delegation is gone, not degraded — a batch-of-seven interrogation was the
wrong shape anyway.

Downstream: an approved spec is consumed by `/to-tickets` (vertical slicing) or
directly by `/assay <spec-id>`. Other skills (judge-panel, done-gate,
commit-protocol, notion-bridge) interact with this skill only through those.
