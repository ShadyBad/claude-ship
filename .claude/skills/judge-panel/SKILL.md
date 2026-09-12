---
name: judge-panel
description: Multi-judge code review system invoked before any commit by /assay command. Reviews diffs at five risk tiers (TRIVIAL, LOW, MEDIUM, HIGH, CRITICAL) using a roster of 29 specialized judges across three tiers. Use when about to commit code changes, when /assay is invoked, when a diff needs review, or when Brandon explicitly requests "judge this" or "review this diff". Tier 1 judges focus on code quality and run as fresh-context subagents. Tier 2 judges focus on systemic risks (security, threat modeling, cost). Tier 3 judges apply business and product wisdom for strategic decisions. Risk tier determines which subset is invoked. Brandon can override with --judges, --no-judges, or --risk flags. Returns aggregate verdict of ship, revise, or block with structured concerns.
---

# Judge Panel: 29-Judge Code Review System

This skill is the core review mechanism invoked by `/assay` before any commit. It scales judge invocation to risk tier, parallelizes calls where possible, and runs every judge in a fresh context so no agent reviews its own reasoning.

## Relationship to other review-shaped skills

This is the sole review entry point for anything ship-bound — any `/assay` invocation, or an explicit "review this before I commit" request. Don't let another review skill fire independently on the same diff; that risks two conflicting verdicts on one change. Most of the apparent overlap here is narrower-scoped than it looks on the surface, not truly redundant:

- **built-in `code-review` skill** — genuinely overlapping for ad hoc, non-ship review ("review this file" outside a commit flow). Fine standalone there; prefer judge-panel once a diff is ship-bound. It is also the engine four Tier 1 judges invoke inside their own subagents, so in that role it is not a competitor at all.
- **built-in `security-review` skill** — likewise the engine behind judges 2 and 18 rather than a rival entry point.

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

Tier 1 judges focus on the diff itself. For MEDIUM and above, 3-5 are invoked. For HIGH and above, all relevant ones. Every one of them runs as a `general-purpose` subagent; see Judge Dispatch for which of them invoke a built-in review skill from inside that subagent.

1. **Senior Staff Engineer** — code quality, maintainability, abstraction level. Look for: a change that works but leaves the next reader with a wrong mental model; logic placed at the wrong layer; a fix that treats a symptom whose cause is one call up.
2. **Security Reviewer** — auth, secrets, injection, OWASP top 10. Invokes the built-in `security-review` skill inside its own subagent. Look for: input that reaches a sink without validation; a credential or token in the diff or in something the diff logs; an authorization check that runs after the effect it guards.
3. **Performance Engineer** — latency, memory, query patterns. Look for: a loop that issues I/O per iteration; an accidental O(n²) over a collection that grows with usage; work repeated per request that could be hoisted; a new allocation on a path called per item.
4. **Test Architect** — coverage, edge cases, isolation, flake-resistance. Look for: a test asserting what the implementation does rather than what the spec requires; empty, null, and boundary inputs with no case; shared mutable state or wall-clock time between tests; a test that would pass if the function body were deleted.
5. **API Designer** — interface contracts, versioning, compatibility. Look for: a changed signature, route, or payload shape with no story for existing callers; a required parameter added to a published interface; a name that describes the implementation rather than the contract.
6. **Data Engineer** — schema, migrations, query plans, indexing. Look for: a migration with no down path; a column added without a default on a populated table; a query whose predicate no index covers; a denormalization with no stated write-side owner.
7. **DevOps Engineer** — deploy safety, rollback, observability. Look for: a change that must land simultaneously with another to be correct; a failure that would be silent in production; no way to answer "is it working" after deploy; blast radius wider than the feature.
8. **Accessibility Auditor** — WCAG 2.2 AA. Look for: an interactive element unreachable by keyboard; state conveyed by color alone; a control with no accessible name; focus that vanishes or is trapped after an interaction.
9. **Frontend Specialist** — component design, state, render cost. Look for: state stored where two components must stay in sync manually; work done during render that belongs in an effect or a memo; a list rendered without stable keys; a hydration-sensitive value read during first paint.
10. **Backend Specialist** — service boundaries, error handling, idempotency. Look for: a handler that is not safe to retry; a partial write with no compensating path; an error swallowed into a default; a boundary crossed without a stated contract.
11. **Database Specialist** — transactions, isolation, consistency, locking. Look for: a read-then-write without the transaction to make it atomic; a lock held across a network call; an assumption of ordering the isolation level does not guarantee.
12. **Concurrency Reviewer** — races, deadlocks, async correctness. Look for: shared state mutated without synchronization; two locks acquirable in opposite orders; an await that leaves an invariant broken mid-flight; a fire-and-forget task whose failure nobody observes.
13. **Error Handler** — failure modes, retries, user-facing messages. Look for: a catch that hides the cause; a retry without backoff or a cap; a message that tells the user what broke but not what to do; fail-quiet where the correct behavior is fail-loud.
14. **Documentation Reviewer** — README, comments, ADRs. Look for: a statement elsewhere in the document that this change just made false; a non-obvious decision with no recorded reason; a comment restating the code instead of its motivation.
15. **Naming Critic** — variables, functions, files, modules. Must match the project's `CONTEXT.md` glossary: a diff that coins a second name for an already-named concept is a finding, not a preference. Look for: a name describing shape rather than role; two names for one concept; one name covering two.
16. **Simplicity Judge** — would a junior engineer understand this in 30 seconds? Look for: a branch reachable only by reading three other files; a clever expression where an obvious one fits; indirection that costs a hop and buys nothing.

### Tier 2 — Systemic Risk Judges (5)

Tier 2 judges are invoked for HIGH and CRITICAL changes. They assess risks beyond the diff itself.

17. **Karpathy** — surfaces silent assumptions and calls out overengineering. Rubric, applied in order: (a) name every assumption the diff makes but never states; (b) find the abstraction introduced for one caller; (c) find "flexibility" nobody requested — a parameter, hook, or config key with exactly one value in the tree; (d) ask what this looks like as the minimum code that satisfies the spec, and what was added past that line. Sourced from the Operating Principles in `~/.claude/CLAUDE.md`, not from a plugin.
18. **Threat Modeler** — STRIDE analysis on auth/data flows. Invokes the built-in `security-review` skill inside its own subagent, with a systemic scope.
19. **Cost Accountant** — token, infra, and third-party call budget. Produce a per-request and per-month figure, name the driver that dominates it, and state what happens to that figure at 10x volume.
20. **Regulatory Reviewer** — GDPR for EU data, SOC2 controls, financial reporting rules for margin-invest, vehicle data regulations for auto-co. Look for: personal data acquiring a new purpose or a longer life; an audit trail the change breaks; a number that reaches a report without a traceable source.
21. **Failure Mode Analyst** — name each dependency this change adds, then for each: what breaks when it fails, who notices, how long recovery takes, and whether the failure cascades or stays local. A dependency whose failure has no stated recovery is the finding.

### Tier 3 — Business and Product Judges (8)

Tier 3 judges are invoked only for CRITICAL changes affecting product strategy, pricing, or user-facing decisions.

**Each is a question, not an impersonation.** The named operator is cited as the
source of the lens, but the rubric is what the subagent applies. A prompt that
says only "be Bezos" returns generic strategy prose wearing a famous name,
which is worse than no judge: it is unfalsifiable, and the name lends borrowed
authority to whatever the model would have said anyway. Judge the question.

22. **Offer Clarity** (Hormozi lens) — state the value of what this ships in one sentence a buyer would repeat. If that sentence needs a preamble, the offer is unclear. Name what the user gives up and what they get, and whether the change moves either.
23. **Leverage** (Naval lens) — does the shipped thing scale with Brandon's attention or independent of it? Name the per-use human step, if any. A change that adds recurring manual work is negative leverage however good it is otherwise.
24. **Reversibility** (Bezos lens) — is this a one-way door? Name the specific thing that becomes expensive to undo: a stored format, a published interface, a user expectation. If it is reversible, say so plainly and stop arguing for caution.
25. **Durability** (Buffett lens) — would this still be the right call in ten years, or does it depend on a condition that is currently true by accident? Name the assumption with the shortest shelf life.
26. **Inversion** (Munger lens) — assume this has failed catastrophically six months out. Write the one-paragraph cause. Then say whether the diff makes that cause more or less likely. Second-order effects only; first-order defects belong to Tier 1.
27. **Contrarian Test** (Thiel lens) — what does this change assume that most people building the same thing would disagree with? If the answer is "nothing", the work is consensus and its edge must come from execution, which is a different claim — say which one is being made.
28. **Usage Reality** (Graham lens) — who uses this in the next week, and for what? Name them. If the honest answer is nobody yet, say so; that may be fine, but it must be a decision rather than an oversight.
29. **Craft** (Ive lens) — the detail test. Find the part that was finished versus the part that was merely completed, and name one thing a careful owner would be embarrassed to ship as-is.

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

Before invoking the tier's judge set, run ONE cheap `haiku` pass over the diff to detect which concern categories are actually present. It runs as its own subagent, for the same reason the judges do: this pass decides whether the Security judge fires at all, and a lead that gated its own security coverage would be marking its own homework one level up. This avoids firing judges whose domain the diff never touches — same rigor where it's relevant, no over-coverage.

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

**Gating floor (never bypassed).** Two rules, and the first applies at every tier:

- **Any tier:** if the diff carries `auth`, `secrets`, `user-input`, `pii`, or `financial`, then 2 Security fires — even when the tier template does not list it. The Hard Constraint says never skip Security for those changes *regardless of tier*, and a MEDIUM template like `Modified business logic → 1, 3, 4, 13, 16` would otherwise intersect Security straight out of an auth-touching review.
- **HIGH/CRITICAL:** 2 Security, 17 Karpathy, and 21 Failure Mode Analyst fire regardless of detected tags.

The pre-pass can ADD judges but can NEVER drop these. This preserves the Hard Constraints below. For Tier 1 and Tier 2, the pre-pass output is the *intersection* with the tier template, then *union* with this floor. Tier 3 bypasses the intersection entirely per the scope rule above.

If the pre-pass itself fails, times out, or returns nothing parseable, **treat
every tag as present**. Dispatch the full tier template UNION the complete
gating floor — including the any-tier Security rule — and treat 2 Security as
mandatory under Aggregation rule 0 for that run.

Falling back to the tier template alone would be the opposite of failing safe:
the template carries no tags, so every tag-conditional guarantee above
evaporates at exactly the moment the detector broke. A missing tag set is not
evidence of a missing concern.

## Risk Tier → Judge Invocation Map

### TRIVIAL
No judges. `/assay` skips the panel entirely. Return immediate `ship` verdict.

Exception, and it is absolute: if the diff touches `auth`, `secrets`,
`user-input`, `pii`, or `financial`, 2 Security fires anyway and Aggregation
rule 0 applies. A change is not trivial because it is small; it is trivial
because nothing depends on getting it right, and security-relevant code never
qualifies.

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
  - Pricing/offer change → 22 Offer Clarity
  - Architectural one-way door → 24 Reversibility + 26 Inversion
  - Long-term platform decision → 25 Durability + 27 Contrarian Test
  - Automation or leverage change → 23 Leverage
  - User-facing product launch → 22 Offer Clarity, 28 Usage Reality, 29 Craft
  - Always include 26 Inversion on any CRITICAL change — the pre-mortem is not optional

## Override Flags

Brandon can override the tier-based selection via `/assay`:

- `/assay --no-judges "<task>"` — skip the panel entirely. Used for trivial fixes Brandon already verified. Does NOT skip 2 Security on a diff touching `auth`, `secrets`, `user-input`, `pii`, or `financial` — that judge is not overridable at any tier. The pre-pass still runs: the any-tier Security floor is tag-conditional, so suppressing tag detection would suppress the exception it triggers.
- `/assay --judges=karpathy,security "<task>"` — invoke only the named judges. Match by name (case-insensitive, partial match allowed). The pre-pass still runs, because Aggregation rule 0's mandatory set is tag-conditional and an explicit list does not suppress 2 Security on a security-tagged diff.
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
4. A judge that errors, returns nothing, or returns unparseable output is recorded `verdict: "unreachable"` and the panel continues without it. There is no wall-clock timeout: the dispatch mechanism exposes no timeout parameter, and a number stated here would be enforced by nobody. Quorum is the real guard — `/assay` Step 8 surfaces to Brandon when fewer than half the expected judges report.

When invoking multiple judges, parallelize the calls: issue every judge's Agent dispatch in a single message so they run concurrently. Judge Dispatch below is the single description of the mechanism.

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

0. **Mandatory judges must actually report.** The mandatory set for a run is:
   2 Security whenever the diff carries `auth`, `secrets`, `user-input`, `pii`,
   or `financial` at any tier; 17 Karpathy and 21 Failure Mode Analyst on
   HIGH/CRITICAL; 18 Threat Modeler on HIGH/CRITICAL carrying `auth`,
   `secrets`, `user-input`, or `pii` (not `financial` — that is judge 20's
   concern, and this list must match the tag row and the Hard Constraint
   exactly). Before aggregating, check each mandatory judge for an
   `approve`, `block`, or `nit` verdict. Anything else — `unreachable`, or no
   entry at all because the judge was never dispatched — forces one
   re-dispatch. If it still has no verdict, the aggregate is `block`. It is
   never `ship`. **A judge that never ran and a judge that was skipped are the
   same event**, and the Hard Constraints forbid the second, so they forbid the
   first.
1. If any judge returns `verdict: "block"` → aggregate verdict is `block`. Surface all blocking concerns.
2. If 2+ judges return the same `concern` (semantic match, not exact string) → promote to `must_address_before_ship`.
3. If a single judge returns a `nit` not echoed by others → put in `log_for_later`.
4. If every dispatched judge returned `approve` → aggregate verdict is `ship`. A judge that returned `unreachable` has not approved, so this rule does not apply while any judge is still unreachable.
5. Mixed approve/nit with no blocks → aggregate verdict is `revise`. Brandon decides whether to address each item now or log.
6. Any non-mandatory judge left `unreachable` after one re-dispatch downgrades a `ship` to `revise`, and is named in the output. Silence is not consent; Brandon decides whether to proceed without that lens.

Output format to Brandon:
JUDGE PANEL RESULT (risk tier: <tier>)
Verdict: SHIP | REVISE | BLOCK
Judges invoked: <list>
Unreachable judges: <list | none>
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
All dispatched judges approved; no mandatory judge unreachable. Ready to commit.
Tokens used: <count>

## Judge Dispatch

Every judge runs as its own subagent with a fresh context, carrying only the
diff, a two-sentence task summary, and its own rubric from the roster below.
Fresh context is the point: an implementing agent reviewing its own work in the
same session is reading its own reasoning back, and will confirm it.

**Every judge, without exception, is dispatched with the Agent tool as a
`general-purpose` subagent.** Judges whose rubric matches a built-in review
engine invoke that skill *from inside their own subagent*, which keeps the
engine's value without moving the judge into the lead's context.

| Judge | Runs as |
|-------|---------|
| Senior Staff Engineer, Simplicity, Naming Critic, Documentation | `general-purpose` subagent instructed to invoke the built-in `code-review` skill, scoped to that judge's rubric |
| Security Reviewer, Threat Modeler | `general-purpose` subagent instructed to invoke the built-in `security-review` skill |
| Everyone else | `general-purpose` subagent carrying the judge's persona and rubric verbatim |

The distinction is not pedantry. The `Skill` tool loads instructions into the
**calling** context, so a judge routed through it is the lead re-reading the
diff it just wrote — the exact thing the fresh-context constraint forbids. The
judges most exposed by that route are Security and Threat Modeler, which may
never be skipped. A subagent that invokes the same skill gets the same rubric and a
context that has never seen the implementation reasoning.

Pass each judge its assigned model from the Per-Judge Model Assignment table via
the dispatch `model` parameter.

A persona-carrying subagent is not cheap, so keep the diff-aware gating tight
to compensate.

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

- TRIVIAL: 0 tokens, or one pre-pass + judge 2 on a security-tagged diff
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
- NEVER skip the Security Reviewer for changes touching auth, secrets, user data, or financial calculation, regardless of tier or override. This binds every path that would otherwise return a verdict without it: a TRIVIAL classification, `--no-judges`, a tier template that omits judge 2, and a pre-pass that failed before it could raise a tag.
- NEVER skip Karpathy (judge 17) on HIGH or CRITICAL — overengineering check is non-negotiable.
- NEVER skip the Failure Mode Analyst (judge 21) on HIGH or CRITICAL.
- NEVER skip the Threat Modeler (judge 18) on a HIGH or CRITICAL change carrying `auth`, `secrets`, `user-input`, or `pii`.
- NEVER let a concern reach Brandon, the revise loop, or the aggregate verdict
  without the vet pass re-opening its cited location. An unvetted concern is a
  claim, not a finding.
- NEVER vet a concern by asking another agent. The lead re-reads the code
  itself; delegating the check reintroduces the inference it exists to catch.
- NEVER drop a concern silently. Every drop is counted into the judge's
  `dropped` field, because a judge that is mostly noise can only be cut with
  evidence.
- ALWAYS produce a verdict, even when some judges are unreachable, and ALWAYS
  name every unreachable judge in the output block. A failure Brandon cannot
  see is a failure that will be repeated.
- NEVER return `ship` while a mandatory judge is unreachable. See Aggregation
  rule 0 — one re-dispatch, then `block`.
