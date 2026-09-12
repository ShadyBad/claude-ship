---
name: judge-panel
description: Multi-judge code review system invoked before any commit by /assay command. Reviews diffs at five risk tiers (TRIVIAL, LOW, MEDIUM, HIGH, CRITICAL) using a roster of 29 specialized judges across three tiers. Use when about to commit code changes, when /assay is invoked, when a diff needs review, or when Brandon explicitly requests "judge this" or "review this diff". Tier 1 judges focus on code quality and run as fresh-context subagents. Tier 2 judges focus on systemic risks (security, threat modeling, cost). Tier 3 judges apply business and product wisdom for strategic decisions. Risk tier determines which subset is invoked. Brandon can override with --judges, --no-judges, or --risk flags. Returns aggregate verdict of ship, revise, or block with structured concerns.
---

# Judge Panel: 29-Judge Code Review System

This skill is the core review mechanism invoked by `/assay` before any commit. It scales judge invocation to risk tier, parallelizes calls where possible, and runs every judge in a fresh context so no agent reviews its own reasoning.

## Relationship to other review-shaped skills

This is the sole review entry point for anything ship-bound — any `/assay` invocation, or an explicit "review this before I commit" request. Don't let another review skill fire independently on the same diff; that risks two conflicting verdicts on one change. Most of the apparent overlap here is narrower-scoped than it looks on the surface, not truly redundant:

- **Native `code-review` skill** — genuinely overlapping for ad hoc, non-ship review ("review this file" outside a commit flow). Fine standalone there; prefer judge-panel once a diff is ship-bound.
- **`ecc:security-review`** — a narrower auth/secrets/API-endpoint checklist, not a full diff review. Legitimately different lens from the Tier 2 security judge here; can run alongside, not instead of.
- **`ecc:security-scan`** — scans the Claude Code *configuration* (`.claude/`, CLAUDE.md, hooks, MCP servers) via AgentShield, not application code. Different subject entirely.
- **`ecc:quality-gate`** — a single-file formatter check driven by a PostToolUse hook, not a code review. Different subject entirely.
- **built-in `code-review` skill** — the engine several Tier 1 judges run on, not an independent competitor.

## Invocation Contract

The skill receives:
- `diff` — the unified diff to review
- `task_context` — exactly 2 sentences describing what the change accomplishes
- `risk_tier` — one of TRIVIAL, LOW, MEDIUM, HIGH, CRITICAL (from `/assay` classification)
- `project` — one of auto-co, margin-invest, personal
- Optional `judges_override` — comma-separated list to invoke instead of tier defaults
- Optional `no_judges` — boolean flag, skip entirely

The skill returns:
{
"aggregate_verdict": "ship" | "revise" | "block",
"blocking_concerns": [list],
"must_address_before_ship": [list],
"log_for_later": [list],
"judges_invoked": [list of judge names],
"tokens_used": <estimate>
}

## Judge Roster

### Tier 1 — Code Quality Judges (16)

Tier 1 judges focus on the diff itself. For MEDIUM and above, 3-5 are invoked. For HIGH and above, all relevant ones. Judges 1, 15, 16, and 14 run on the built-in `code-review` skill scoped to their rubric; the rest run as `general-purpose` subagents carrying their persona verbatim.

1. **Senior Staff Engineer** — code quality, maintainability, abstraction level, mental model alignment.
2. **Security Reviewer** — auth, secrets, injection, OWASP top 10. Runs on the built-in `security-review` skill.
3. **Performance Engineer** — latency, memory, query patterns, N+1, complexity.
4. **Test Architect** — coverage, edge cases, test isolation, flake-resistance.
5. **API Designer** — interface contracts, versioning, backward compatibility, RFC-style naming.
6. **Data Engineer** — schema, migrations, query plans, indexing, denormalization tradeoffs.
7. **DevOps Engineer** — deploy safety, rollback, observability, blast radius if it goes wrong.
8. **Accessibility Auditor** — WCAG 2.2 AA, keyboard nav, screen reader, contrast, focus order.
9. **Frontend Specialist** — component design, state, rerender cost, hydration.
10. **Backend Specialist** — service boundaries, error handling, idempotency, retries.
11. **Database Specialist** — transactions, isolation level, consistency guarantees, locking.
12. **Concurrency Reviewer** — race conditions, deadlocks, async correctness, ordering.
13. **Error Handler** — failure modes, retry logic, user-facing messages, fail-loud vs fail-quiet.
14. **Documentation Reviewer** — README, inline comments where needed, ADRs for non-obvious decisions.
15. **Naming Critic** — variables, functions, files, modules. Must match the project's `CONTEXT.md` glossary: a diff that coins a second name for an already-named concept is a finding, not a preference.
16. **Simplicity Judge** — would a junior engineer understand this in 30 seconds?

### Tier 2 — Systemic Risk Judges (5)

Tier 2 judges are invoked for HIGH and CRITICAL changes. They assess risks beyond the diff itself.

17. **Karpathy** — surfaces silent assumptions, calls out overengineering, asks "would this be in the minimum code?" Pulls from `andrej-karpathy-skills` plugin context.
18. **Threat Modeler** — STRIDE analysis on auth/data flows. Runs on the built-in `security-review` skill with a systemic scope.
19. **Cost Accountant** — token cost (LLM API), infra cost (compute/storage), third-party API call budget. Estimates per-request and per-month.
20. **Regulatory Reviewer** — GDPR for EU data, SOC2 controls, financial reporting rules for margin-invest, vehicle data regulations for auto-co.
21. **Failure Mode Analyst** — what breaks when X dependency fails? Blast radius? Cascade risk? Recovery procedure?

### Tier 3 — Business and Product Judges (8)

Tier 3 judges are invoked only for CRITICAL changes affecting product strategy, pricing, or user-facing decisions. They speak in the voice of the operator they represent.

22. **Hormozi** — offer clarity, conversion, dollar-per-decision. "What is the value of the offer here in one sentence?"
23. **Naval** — leverage, permissionless, asymmetric upside. "Does this scale with my attention or independent of it?"
24. **Bezos** — customer obsession, two-pizza scope, reversible vs irreversible. "Is this a one-way door?"
25. **Buffett** — moat, margin of safety, simplicity. "Would I want to own this for 10 years?"
26. **Munger** — invert the problem, second-order effects. "What would make this fail catastrophically?"
27. **Thiel** — "What important truth do few people agree with you on?" Contrarian-but-correct test.
28. **Graham** — what would users actually use, do things that don't scale, ship the thing.
29. **Ive** — would Brandon be proud to ship this? Detail-craft level.

## Per-Judge Model Assignment

Each judge runs on a model matched to the reasoning depth its concern demands, not to the change's risk tier. This collapses panel cost without dropping a single judge: a naming nit on `haiku` costs a fraction of the same judge on `opus`, while correctness and systemic judgment still get the strongest model. The dispatching step passes each judge its assigned model.

Model names below are the **Agent tool's `model` aliases** (`opus`, `sonnet`, `haiku`), not versioned model IDs. The alias is what the dispatch parameter accepts, and it keeps resolving to the current release without an edit here — a pinned ID goes stale on the next model ship and is rejected by the dispatch parameter besides.

| Model | Judges | Why |
|-------|--------|-----|
| **opus** | 1 Senior Staff, 2 Security, 12 Concurrency, 13 Error Handler, 17 Karpathy, 18 Threat Modeler, 20 Regulatory, 21 Failure Mode, all Tier 3 (22–29) | Correctness, security, systemic risk, and strategic judgment — failure here is expensive or irreversible. |
| **sonnet** | 3 Performance, 4 Test Architect, 5 API Designer, 6 Data Engineer, 7 DevOps, 10 Backend, 11 Database, 19 Cost Accountant | Substantive review where sonnet's signal is close to opus at lower cost. |
| **haiku** | 8 Accessibility, 9 Frontend, 14 Documentation, 15 Naming Critic, 16 Simplicity | Nit-class / pattern-matching concerns; cheap model is sufficient. |

Override precedence: a judge's assigned model here wins over the tier default model from `/assay` Step 4. Pass the assigned model to the judge's subagent dispatch (see Judge Dispatch below). Hard floor: judges named in the Hard Constraints (Security, Karpathy on HIGH/CRITICAL) always run at their `opus` assignment — never downgraded.

## Concern-Detection Pre-Pass (diff-aware gating)

Before invoking the tier's judge set, run ONE cheap `haiku` pass over the diff to detect which concern categories are actually present. This avoids firing judges whose domain the diff never touches — same rigor where it's relevant, no over-coverage.

**Scope: Tier 1 and Tier 2 only.** Tier 3 judges are selected by the CRITICAL change-type map below and are never intersected with detected tags. A content scanner reading a diff can see that a query changed; it cannot see that the change is a one-way door, or that it alters what the product charges for. Those are properties of the decision, not of the text, so gating Tier 3 on tags would silently delete the entire business panel from every CRITICAL review — which is the one tier that exists to have it.

The pre-pass returns a tag set drawn from:
`auth` · `secrets` · `user-input` · `concurrency` · `async` · `query` · `schema` · `migration` · `ui` · `accessibility` · `api-contract` · `external-api` · `error-handling` · `naming` · `docs` · `perf-hot-path` · `financial` · `pii`

`api-contract` fires on a changed **public function signature, endpoint route or payload shape, exported module interface, CLI flag, or serialized schema contract** — something a caller outside this diff depends on. It is the inverse of `external-api`: that tag means the diff *consumes* someone else's interface, this one means it *publishes* its own.

Map tags → judges (a judge fires only if at least one of its tags is present AND it is in the tier template):

| Tag(s) | Activates judge(s) |
|--------|--------------------|
| auth, secrets, user-input, pii | 2 Security, 18 Threat Modeler |
| concurrency, async | 12 Concurrency, 10 Backend |
| query, schema, migration | 6 Data Engineer, 11 Database |
| ui, accessibility | 8 Accessibility, 9 Frontend |
| api-contract | 5 API Designer |
| external-api | 19 Cost Accountant, 7 DevOps |
| error-handling | 13 Error Handler |
| naming, docs | 14 Documentation, 15 Naming Critic |
| perf-hot-path | 3 Performance |
| financial, pii | 20 Regulatory Reviewer |

Always-on regardless of tags (the structural reviewers): 1 Senior Staff, 4 Test Architect, 16 Simplicity.

**Gating floor (never bypassed):** for HIGH/CRITICAL, 2 Security, 17 Karpathy, and 21 Failure Mode Analyst fire regardless of detected tags — the pre-pass can ADD judges but can NEVER drop these. This preserves the Hard Constraints below. For Tier 1 and Tier 2, the pre-pass output is the *intersection* with the tier template, then *union* with this floor. Tier 3 bypasses the intersection entirely per the scope rule above.

If the pre-pass itself fails or times out, fall back to the full tier template (fail toward more coverage, not less).

## Risk Tier → Judge Invocation Map

### TRIVIAL
No judges. `/assay` skips the panel entirely. Return immediate `ship` verdict.

### LOW
1-2 Tier 1 judges, picked by change type:
- Test-only change → judge 4 (Test Architect)
- Rename only → judges 15 (Naming Critic) + 16 (Simplicity)
- Single-file refactor, no logic change → judges 1 (Senior Staff) + 16 (Simplicity)
- Comment/doc only → judge 14 (Documentation) only
- Dependency bump → judge 2 (Security) only

### MEDIUM
3-5 Tier 1 judges, picked by change surface area:
- New function added → 1, 4, 13, 15, 16
- Modified business logic → 1, 3, 4, 13, 16
- New endpoint → 1, 2, 4, 5, 13
- UI component change → 1, 8, 9, 16
- Schema change (non-breaking) → 1, 6, 11

### HIGH
ALL relevant Tier 1 + at least 2 Tier 2:
- All Tier 1 judges whose domain the diff touches
- Always include: 17 (Karpathy), 21 (Failure Mode Analyst)
- Add 18 (Threat Modeler) if auth/data flow
- Add 19 (Cost Accountant) if introduces new external API calls
- Add 20 (Regulatory Reviewer) if touches user data or financial calculation

### CRITICAL
Full Tier 1 + full Tier 2 + relevant Tier 3:
- All Tier 1 + all Tier 2
- Tier 3 selection by change type:
  - Pricing/offer change → 22 (Hormozi)
  - Architectural one-way door → 24 (Bezos) + 26 (Munger)
  - Long-term platform decision → 25 (Buffett) + 27 (Thiel)
  - Automation or leverage change → 23 (Naval) — does the shipped thing scale with Brandon's attention or independent of it?
  - User-facing product launch → 22, 28, 29
  - Always include 26 (Munger) for invert-the-problem on any CRITICAL change

## Override Flags

Brandon can override the tier-based selection via `/assay`:

- `/assay --no-judges "<task>"` — skip the panel entirely. Used for trivial fixes Brandon already verified.
- `/assay --judges=karpathy,security "<task>"` — invoke only the named judges. Match by name (case-insensitive, partial match allowed).
- `/assay --judges=tier1 "<task>"` — invoke all of Tier 1.
- `/assay --judges=+hormozi "<task>"` — add judges to the tier defaults (the `+` prefix).
- `/assay --judges=-naming "<task>"` — exclude judges from tier defaults (the `-` prefix).
- `/assay --risk=high "<task>"` — force a specific risk tier regardless of automatic classification.

## Per-Judge Invocation Protocol

Each judge call must:

1. Receive ONLY:
   - The unified diff (compressed by caveman if available)
   - The 2-sentence task context
   - The judge's name and role
   - The risk tier
2. NOT receive: full session transcript, project lessons, other judges' output.
3. Return a structured response:
{
"judge": "<judge name>",
"verdict": "approve" | "block" | "nit",
"concerns": [up to 3 items],
"concrete_suggestion": "<one specific change>" | null
}
4. Time out after 30 seconds. If a judge times out, record `verdict: "timeout"` and continue.

When invoking multiple judges, parallelize the calls. Use Claude Code's subagent dispatch (via `superpowers` plugin's subagent-driven-development) to run them concurrently.

## Vet Pass (mandatory, between dispatch and aggregation)

Pipeline stage **VET**, recorded as `judge-vet` in the run record. It sits
inside Step 8 between judge dispatch and aggregation, and it is eligible on
every run where the panel fires.

**Judges over-report.** Twenty-nine fresh-context reviewers, each incentivized
to find something, produce concerns faster than they produce signal. This
skill's own output contract already admits it: the run record enforces
`accepted <= concerns` per judge *because* raised and acted-on are different
numbers. Without a vetting step, that gap is measuring noise, and the revise
loop spends Brandon's attention on it.

So before any concern reaches aggregation, Brandon, or the revise loop, the
lead re-opens every cited location in the diff and confirms it. Three failure
classes, all common:

- **By-design reported as defect.** The concern describes deliberate behavior
   — a convention, a tradeoff recorded in an ADR under `glossary.adr_path`, a
   choice pinned in the spec's Implementation choices, or an entry already in
   `rejected.md`. Drop it. The exception is drift: if the code no longer
   matches what the ADR says, the drift is a real finding and outranks the
   original concern.
- **Mis-attributed evidence.** A real concern pinned to the wrong file, the
   wrong line, or a line the diff did not touch. Correct it, or drop it if the
   cited code does not exist. Never pass a citation through unopened — a judge
   reviewing a diff in fresh context cites what it inferred, and inference is a
   lead, not a fact.
- **Cross-judge duplicates.** The same concern from three judges is one
   concern with three votes, not three concerns. Merge, keep the strongest
   evidence, and record the vote count — it is what promotes a concern to
   `must_address_before_ship` under Aggregation rule 2.

The vet pass runs on the lead, not a subagent. It is a re-read of code already
in context, and handing it to a fresh agent would reintroduce the same
inference problem it exists to catch.

**Record the drops.** Each judge's entry in the run record carries `dropped`
alongside `concerns` and `accepted`. `concerns` is the post-vet count, so a
judge's real noise level is `dropped / (dropped + concerns)`. A judge whose
drop rate stays high is not reviewing — it is generating work for the vetter,
and `/assay-stats` will say so with a sample size behind it.

**Cost.** The vet pass adds a serial re-read to every run where judges fire.
That is real, and it is only worth paying if the false-positive rate is
material. It is instrumented precisely so that question gets answered with data
rather than defended with argument.

Skip conditions: none at HIGH/CRITICAL. At LOW/MEDIUM the pass may be limited
to concerns carrying a `file:line` citation — a concern with no citation cannot
be vetted, and goes to `log_for_later` rather than `must_address_before_ship`.

## Aggregation Rules

After the vet pass, aggregate what survived it. Every count below is a
post-vet count:

1. If any judge returns `verdict: "block"` → aggregate verdict is `block`. Surface all blocking concerns.
2. If 2+ judges return the same `concern` (semantic match, not exact string) → promote to `must_address_before_ship`.
3. If a single judge returns a `nit` not echoed by others → put in `log_for_later`.
4. If all judges return `approve` → aggregate verdict is `ship`.
5. Mixed approve/nit with no blocks → aggregate verdict is `revise`. Brandon decides whether to address each item now or log.

Output format to Brandon:
JUDGE PANEL RESULT (risk tier: <tier>)
Verdict: SHIP | REVISE | BLOCK
Judges invoked: <list>
[if BLOCK]
Blocking concerns:

<judge>: <concern>
<judge>: <concern>

[if REVISE]
Address before ship:

<concern> (raised by <judges>)

Log for later:


<concern>


[if SHIP]
All judges approved. Ready to commit.
Tokens used: <count>

## Judge Dispatch

Every judge runs as its own subagent with a fresh context, carrying only the
diff, a two-sentence task summary, and its own rubric from the roster below.
Fresh context is the point: an implementing agent reviewing its own work in the
same session is reading its own reasoning back, and will confirm it.

Dispatch via the Agent tool (`general-purpose`), or via the built-in
`code-review` and `security-review` skills where a judge's rubric matches what
those already do:

| Judge | Runs as |
|-------|---------|
| Senior Staff Engineer, Simplicity, Naming Critic, Documentation | built-in `code-review` skill, scoped to that judge's rubric |
| Security Reviewer, Threat Modeler | built-in `security-review` skill |
| Everyone else | `general-purpose` subagent carrying the judge's persona and rubric verbatim |

This previously delegated to `pr-review-toolkit` and `ecc` reviewer agents.
Those plugins are uninstalled and the delegation is removed, not degraded —
which costs more tokens per judge than the old path, so keep the diff-aware
gating tight to compensate.

## Two Axes

Every judge answers on two axes, and a pass on one is not a pass:

- **Standards** — does this meet the codebase's bar? Naming, error handling,
  test quality, security posture.
- **Spec** — does it do what the ticket or spec said, and nothing the Non-goals
  excluded? A judge that never reads the acceptance criteria cannot
   catch the most expensive failure, which is well-built code that solves a
   slightly different problem.

Judges receive the spec's Success criteria and the ticket's Acceptance bullets
alongside the diff. A finding on the spec axis outranks any standards nit.

## Token Budget Guidelines

Approximate token cost per invocation:

- TRIVIAL: 0 tokens (skipped)
- LOW: 2-4K tokens (1-2 judges, parallel)
- MEDIUM: 8-15K tokens (3-5 judges, parallel)
- HIGH: 25-40K tokens (8-12 judges, parallel)
- CRITICAL: 50-80K tokens (16-25 judges, parallel)

If a CRITICAL change is anticipated to exceed 100K tokens, surface this to Brandon before invoking and offer to split the review into batches.

## Project-Specific Tuning

The skill consults `$HOME/.claude/memory/projects/<project>/lessons.md` before invoking judges. If past lessons indicate Brandon has consistently dismissed a particular concern category (e.g., "Brandon has rejected 5 accessibility nits on auto-co internal tools"), reduce that judge's weight or skip them for that project at LOW/MEDIUM tier. Always still invoke at HIGH/CRITICAL.

## Self-Update Hook

When Brandon overrides a judge verdict ("ship anyway") or repeatedly dismisses a concern type, append a lesson to the project's lessons.md via the `project-memory` skill. Format:

`<ISO-timestamp> | judge-panel feedback | Brandon dismissed <judge>:<concern-type> on <change-type>; reduce weight for this combination | judge-tuning,<project>`

After 3 such dismissals of the same combination, the `operator-model` skill should be notified to update Brandon's preference profile.

## Hard Constraints

- NEVER auto-bypass the panel for HIGH or CRITICAL changes, even if Brandon's history suggests he would approve.
- NEVER reveal one judge's output to another judge (each must reason independently).
- NEVER let the agent that wrote the diff also judge it. A fresh context per judge is the mechanism, not a nicety.
- NEVER return `ship` on a standards-clean diff that misses the spec. The spec axis is not optional.
- NEVER skip the Security Reviewer for changes touching auth, secrets, user data, or financial calculation, regardless of tier or override.
- NEVER skip Karpathy (judge 17) on HIGH or CRITICAL — overengineering check is non-negotiable.
- NEVER let a concern reach Brandon, the revise loop, or the aggregate verdict
  without the vet pass re-opening its cited location. An unvetted concern is a
  claim, not a finding.
- NEVER vet a concern by asking another agent. The lead re-reads the code
  itself; delegating the check reintroduces the inference it exists to catch.
- NEVER drop a concern silently. Every drop is counted into the judge's
  `dropped` field, because a judge that is mostly noise can only be cut with
  evidence.
- ALWAYS produce a verdict, even if some judges time out. Note timeouts in the output.
