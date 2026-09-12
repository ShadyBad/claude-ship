---
name: assay
description: Master orchestrator. Runs the full 14-step pipeline from task parse through commit and learn. Coordinates all custom skills (spec-builder, ticket-board, tdd-loop, context-glossary, judge-panel, project-memory, session-recall, operator-model, skill-curator, notion-bridge, mcp-router, done-gate, commit-protocol) and the ticket board built by /to-tickets. Use whenever Brandon wants to make a meaningful change to a project — code, docs, configuration, or strategy artifacts. Three invocation forms: /assay "<task description>" for direct execution, /assay <spec-id> to consume an approved spec produced by /spec, or /assay <ticket-id> to execute one vertical slice from the board built by /to-tickets. Supports flags for risk classification, judge control, MCP control, check skipping, and commit behavior. Saves state on interrupt for /assay resume.
argument-hint: <spec-id> | <ticket-id> | "<task description>" [--judges] [--no-judges] [--risk=<tier>] [--mcps=<list>] [--skip-tests] [--skip-lint] [--skip-types] [--no-tdd] [--force] [--commit-message=<msg>] [--amend] [--no-push] [--auto-push] [--deploy] [--no-deploy] [--dry-run]
---

# /assay — Master Orchestrator

Runs the 14-step pipeline. Every step delegates to a skill. This file is the conductor, not the orchestra.

## Cache Discipline (operating principle, all steps)

The sequential steps can ride a warm prompt cache (Anthropic cache TTL ~5 min) only if the context prefix stays stable. Claude Code auto-caches the system + tool prefix; /assay cannot set cache breakpoints directly, so the lever is **stop mutating context mid-run**:

- Load CONTEXT (Step 2) exactly once into the context bundle. Do not re-invoke context-mutating skills (project-memory, session-recall, operator-model) later in the pipeline.
- Read each memory file once; work from the in-context bundle thereafter, never re-read the same file.
- Keep skill-load order fixed across a run — don't reorder or interleave loads between steps.
- Prefer the Artifact Reference Protocol (Step 7) over re-injecting large bodies, which churns the suffix and forces cache misses on every subsequent step.

This is guidance, not a hard mechanism — its ROI is lower than model tiering (Step 4) or diff-aware judge gating (Step 8). Stated here so a context-churning pattern is greppable when observed.

## Flag Parsing (Step 0)

Parse the invocation arguments before starting the pipeline. The first argument is the task description. Remaining flags adjust pipeline behavior.

| Flag | Effect |
|------|--------|
| `--judges` | Force judge-panel invocation even at TRIVIAL tier. |
| `--no-judges` | Skip judge-panel. Only valid for TRIVIAL/LOW tiers. HIGH/CRITICAL still enforces judges. |
| `--risk=<tier>` | Override automatic risk classification. Values: trivial, low, medium, high, critical. |
| `--mcps=<list>` | Override mcp-router's category-based loading. Comma-separated MCP names. Prefixes: `+` to add to category default, `-` to exclude. |
| `--no-mcps` | Load no MCPs (rare; pure local work). |
| `--skip-tests` | Bypass done-gate Checks 2 and 3. Requires note explaining why. |
| `--skip-lint` | Bypass done-gate Check 5. |
| `--skip-types` | Bypass done-gate Check 6. |
| `--no-tdd` | Bypass the Step 7 red-green loop and done-gate Check 9. Logged to the run record so the bypass rate stays measurable. |
| `--no-survey` | Skip the Step 8.5 branch survey and the Step 13 cadence survey for this run. Logged. |
| `--survey` | Force the Step 8.5 branch survey even when `survey.in_pipeline` is false or the tier is TRIVIAL. |
| `--no-spec` | Skip the Step 1 spec escalation gate. Run a MEDIUM+ task with no measurable outcome or named seam. Logged to the run record. |
| `--force` | Bypass all done-gate checks except Check 8 (Brandon approval). Logged to force-bypass-log. Emergency use only. |
| `--commit-message="<msg>"` | Use exact message in commit-protocol. Skip generation. |
| `--amend` | Amend last commit instead of new commit. |
| `--no-push` | Skip the push question after commit. |
| `--auto-push` | Push immediately after commit without asking. |
| `--deploy` | Force Step 11.5 DEPLOY → CANARY after commit, even if no auto-trigger matches. Still gated by explicit deploy approval (governs git ≠ prod). |
| `--no-deploy` | Hard-disable Step 11.5 DEPLOY → CANARY even when a deploy trigger matches. |
| `--dry-run` | Run pipeline through Step 10 DONE GATE, surface diff + judge verdict, then halt and save state. `/assay resume` picks up at Step 11 COMMIT. Inspection sandbox — no files committed. |
| `resume` | Resume the most recent interrupted /assay session (special positional arg). |

If `--force` and `--no-judges` are both set and risk tier is HIGH/CRITICAL, refuse: "HIGH/CRITICAL changes cannot bypass judge-panel. Drop --no-judges or accept lower risk classification."

## Pipeline: The 14 Steps

### Step 1: PARSE

**Id resolution order.** A ticket-id (`<slug>-<date>-NN`) also matches the spec-id pattern, since the slice suffix is indistinguishable from a spec collision suffix. So resolve by **lookup, not by regex**: check the configured ticket directory first for an exact filename match, and only if none exists treat the argument as a spec-id. When both exist — a spec collision `-02` and a slice `-02` of the same spec — surface both and ask; never guess, because the two run very differently.

**Spec-id resolution.** If the first positional argument matches the pattern `<slug>-\d{4}-\d{2}-\d{2}(-\d+)?` (e.g. `parallelize-walkforward-2026-05-17` or `add-sharpe-engine-2026-05-17-2`), treat it as a spec-id from the `spec-builder` skill:

1. Detect namespace using the same rules as project-memory (`.claude/project-name` → git remote → cwd → `personal`).
2. Resolve to `$HOME/.claude/memory/projects/<ns>/specs/<spec-id>.md`. If not found in current namespace, search across all namespaces and surface the match.
3. Load the spec's YAML frontmatter (`spec-id`, `title`, `namespace`, `created`, `status`, `risk-tier`, `shipped-at`, `shipped-commit`) and 7 sections (Problem, Hypothesis, Success criteria, Non-goals, Constraints, Risks, Plan sketch).
4. Status gate:
   - `draft` — refuse: "Spec `<spec-id>` is still draft. Run `/spec approve <spec-id>` first."
   - `shipped` — warn: "Spec `<spec-id>` already shipped on `<shipped-at>` as commit `<shipped-commit>`. Re-ship with `--force` or write a new spec."
   - `approved` — proceed.
5. Snapshot the spec into the session state directory (`$HOME/.claude/memory/sessions/<YYYY-MM-DD>-<session-id>/spec-snapshot.md`). Lock for the duration of this /assay run.
6. Use the spec's `title` as task description, `risk-tier` as the locked risk tier (skip Step 4 RISK CLASSIFY unless `--risk=` overrides), and Success criteria as inputs to done-gate Check 1.

**Ticket-id resolution.** If the first positional argument resolves to a file in the configured ticket directory, treat it as a ticket from the `ticket-board` skill:

1. Resolve the ticket backend and path from `~/.claude/assay.config.json` (`tickets.backend`, `tickets.path`) via `scripts/assay_config.py`. Never hardcode.
2. Load the ticket's frontmatter (`ticket-id`, `spec`, `title`, `status`, `kind`, `tier`, `blocked_by`, `seam`, `branch`) and its Slice / Acceptance / Out of scope sections.
3. Refuse if any id in `blocked_by` is not `done`: "Ticket `<id>` is blocked by `<ids>`. Run those first, or `/to-tickets board` to see the graph." A `needs-qa` blocker is still a blocker.
4. Refuse if status is `done`. Warn if `in-progress` — a previous run may still hold the branch.
5. Use `title` as the task description, `tier` as the locked risk tier (skip Step 4 unless `--risk=` overrides), Acceptance bullets as done-gate Check 1 inputs, and `seam` as the target for the Step 7 TDD loop.
6. Mark the ticket `in-progress` and check out its `branch`, creating it if absent. Never run a ticket on a branch that already carries another ticket's work.
7. If the ticket names a `spec`, load that spec's Implementation choices and Non-goals as constraints — the slice inherits them.

If the first argument is neither a spec-id nor a ticket-id, fall through to task-description parsing below.

**Task-description parsing (default).** Parse the task description. Extract:
- Primary verb (build, fix, refactor, research, design, ship, deploy).
- Subject (what is being changed).
- Project context (auto-co, margin-invest, personal, or unspecified — infer from cwd).
- Explicit scope hints (file paths, function names, ticket numbers mentioned).

Output a structured task spec used by later steps.

**Spec escalation gate.** A bare task description carries no measurable success criteria and no testing seam. That is not a cosmetic gap: done-gate Check 1 then has nothing to check against and asks Brandon to state criteria *after* the work exists — the one moment he is guaranteed to agree with whatever got built — and Step 7's TDD loop has to invent its own seam, which is the improvisation the loop exists to prevent.

So test the parsed task on two questions:

1. **Observable outcome?** Does the task name something checkable from outside the code — a number, a test that passes, a behavior someone can watch? "Fix the retry backoff so a failed fetch stops after 3 attempts" passes. "Improve error handling" does not.
2. **Nameable seam?** Can you point at the function, endpoint, CLI, or fixture a test would drive? If the answer requires reading the repo first, it is a no at this stage.

Combine with a tier pre-estimate from the parsed verb, subject, and scope hints (the same estimate Step 2 uses for its context-load gate):

| Pre-estimate | Both answers yes | Either answer no |
|--------------|------------------|------------------|
| TRIVIAL / LOW | Proceed. | Proceed — ask one clarifying question if the task is under 8 words with no explicit scope. |
| MEDIUM+ | Proceed. | **Escalate**: recommend `/spec` and default to yes. |

Escalation prompt:

```
This is a <tier> change and the task has no <measurable outcome | testing seam>.
Without one, done-gate Check 1 has nothing to verify and the TDD loop has no
seam to write its first failing test against.

Recommend: /spec "<task>"   — a grill, then /assay <spec-id>
  spec    run the grill now, then come back here  (recommended)
  proceed continue without a spec; criteria get stated at the gate
  abort
```

Default is `spec`. `proceed` is one word away — this is a recommendation with a good default, not a wall.

Bypass with `--no-spec`, which is logged to the run record alongside the tier so the escape rate is visible in `/assay-stats`. Never escalate when the run was invoked with a spec-id or a ticket-id: both already carry criteria and a seam. Never escalate more than once per run.

Escalation is a **judgment**, not a regex. A well-formed one-line task at MEDIUM tier that names its outcome and its seam proceeds; a 40-word paragraph that names neither does not.

### Step 2: CONTEXT LOAD

Context load is **conditional**, not paid on every run. The triple-memory load (lessons + recall + prefs) is a fixed token tax whose payoff lands on maybe 1 ship in 5; gate it so cheap/isolated work skips it.

1. **operator-model** — ALWAYS load. Cheap, high-value, applies to every change. Apply the Things Brandon Hates filter to suppress patterns he has rejected.
1b. **context-glossary** — ALWAYS load, all tiers. Read the project glossary at `glossary.path` (default `CONTEXT.md`). It is small and it prevents this run from coining a second name for a concept the project already named. Above ~150 lines, load the headings plus each entry's `Is:` line and read full entries on demand.
2. **project-memory** — load `lessons.md` and surface 3-5 relevant lessons ONLY when tier ≥ MEDIUM, OR the task names a subsystem with known prior lessons. TRIVIAL/LOW skip.
3. **session-recall** — search past sessions (3-tier fallback: episodic-memory MCP → project-memory grep → ripgrep) ONLY when the task signals prior art: keywords like "again", "like we did", "continue", "same as", or an explicit ticket/PR/spec reference. Otherwise skip.

Note Step 1 RISK CLASSIFY (Step 4) runs before this gate can fully evaluate tier; in practice the lead does a quick tier pre-estimate from the parsed task to decide the gate, and reconciles after Step 4. When in doubt at the MEDIUM boundary, load.

Invoke whatever is gated-in **in parallel**. Output: a context bundle (always prefs; lessons + recall hits when loaded) used by PLAN and EXECUTE steps.

### Step 3: PLAN

Generate a plan for the task.

- For TRIVIAL/LOW tasks: a 3-bullet plan inline.
- For MEDIUM tasks: a 5-10 step plan inline.
- For HIGH/CRITICAL tasks: a structured plan with risk analysis, fallback paths, and test strategy. Use the `Plan` agent for the design pass when the surface is unfamiliar.

The plan must include:
- Approach (1-2 sentences).
- Affected files (best guess).
- Test strategy — the seam the first failing test drives, not "unit tests". At or above `tdd.min_tier` this is the input to Step 7's red-green loop, so a plan whose test strategy names no seam is incomplete.
- Estimated tool call count (rough budget).

**Vertical-slice constraint (all tiers).** A plan whose steps are layer names — "add the schema", "then the service methods", "then the endpoint" — is horizontal, and horizontal work hides every integration failure until the last step. Order the plan so the first step is the thinnest path that crosses every layer the change touches, and every later step widens something that already runs.

If the plan cannot be arranged that way in one reviewable diff, that is the signal the task is more than one commit: stop and say so. Route to `/to-tickets <spec-id>` for slicing rather than building it horizontally under one commit. When this run was invoked with a ticket-id, the slicing already happened — the constraint is already satisfied and this paragraph is a no-op.

**Breadth-First Heuristic (HIGH/CRITICAL).** Anthropic finding: agents default to overly long, specific queries that return few results. For HIGH/CRITICAL plans, force a breadth-first pass first:

1. Start wide. Enumerate the affected surface (files, callers, dependent skills, downstream consumers) before drilling into any one area.
2. Evaluate what exists. Don't write changes until the existing surface is mapped.
3. Narrow progressively. Pick the smallest viable slice once the landscape is known.

Plans that skip straight to a specific file edit on HIGH/CRITICAL get a one-shot revise prompt: "Plan jumped to specifics. Show the broader surface first."

Show plan to Brandon. Accept: ship, revise, abort.
- ship — proceed to Step 4.
- revise — incorporate Brandon's feedback, regenerate, show again.
- abort — halt pipeline, save state.

### Step 4: RISK CLASSIFY

Classify the change into one of 5 risk tiers (from CLAUDE.md):

- **TRIVIAL** — typo fix, comment edit, doc-only change, formatting.
- **LOW** — single-file change, <30 lines, isolated.
- **MEDIUM** — single feature, 1-3 files, no schema/API change.
- **HIGH** — multi-file change, schema/API impact, security-adjacent, or financial.
- **CRITICAL** — irreversible (data migration, prod deploy, payment flow, auth change).

Classification signals:
- File count and diff size (from plan).
- File paths (anything under `auth/`, `payments/`, `migrations/`, `schema/`, `infra/` is HIGH+).
- Keywords in task description (deploy, migrate, delete, drop table, force, rotate keys = HIGH+).
- Project-specific overrides (margin-invest financial calc = HIGH minimum).

If `--risk=<tier>` flag is set, override. Show the override to Brandon and confirm before continuing.

**Effort Budget by Tier.** Risk tier locks a ceiling on subagent count and per-subagent tool calls. Pattern adapted from the Anthropic multi-agent research system: scale agent effort to query complexity, embed budgets in the prompt to prevent overinvestment in simple work. Ceilings are calibrated for /assay's code-orchestrator task shape, not research-product fan-out.

TRIVIAL/LOW always execute inline (single agent); no subagent budget applies. Budget table covers MEDIUM+.

| Tier | Max subagents | Max tool calls / subagent | Soft total ceiling |
|------|---------------|---------------------------|---------------------|
| MEDIUM | 2–3 | 15 | 45 |
| HIGH | 3–5 | 20 | 100 |
| CRITICAL | 5–8 | 25 | 200 (logged per call when exceeded) |

The lead tracks **subagent dispatch count** (a real, countable quantity) against the tier's max-subagents ceiling — this is the hard limit. The per-subagent tool-call ceiling is an **advisory budget stated in each Delegation Brief** (Step 5 `boundaries` field); the subagent self-enforces by finalizing and returning an artifact ref (Step 7) when it approaches its cap, rather than continuing. The lead does NOT attempt to self-count its own tool calls — models do not reliably tally their own actions, so there is no `tool_call_tally`; true token-accounting enforcement is deferred to a future Workflow-based rewrite. If the subagent-count ceiling is hit, halt EXECUTE and surface to Brandon: "(a) raise budget, (b) take results so far, (c) abort and save state."

**Model by Tier.** Risk tier selects the *model* each subagent and judge runs on, not just agent count. This is the highest cost-per-quality lever: a cheap-model reviewer costs a fraction of a frontier-model one at near-equal signal for low-stakes work, while high-stakes reasoning still gets the strongest model.

| Tier | Default model | Rationale |
|------|---------------|-----------|
| TRIVIAL / LOW | `haiku` | Mechanical changes; cheap model is sufficient. |
| MEDIUM | `sonnet` | Feature work; balanced cost/quality. |
| HIGH / CRITICAL | `opus` | Schema/auth/financial/irreversible; pay for depth. |

Model names are the Agent tool's `model` aliases, not versioned model IDs — the alias is what the dispatch parameter accepts, and it tracks the current release without an edit here.

The lead dispatches every subagent (Steps 5, 7) with the tier's default model. Judge-panel (Step 8) overrides per-judge — correctness/security/systemic judges run `opus` regardless of tier, nit-class judges run `haiku` (see judge-panel SKILL.md roster `model` column). Brandon can override the tier model with the existing `--risk=` flag (which relocks the tier and its model).

Output: risk tier + effort budget + tier model locked for the rest of the pipeline.

### Step 5: DISPATCH

Decide execution strategy:

- TRIVIAL/LOW: execute inline (single agent).
- MEDIUM: execute inline unless the plan has 3+ independent subtasks → dispatch parallel subagents via the Agent tool.
- HIGH/CRITICAL: always dispatch subagents. Each gets only its slice of context.

Subagents are dispatched with the Agent tool (`general-purpose` unless a specialized type fits). There is no plugin dependency here.

**Structured Delegation Brief (mandatory for every dispatched subagent).** Anthropic finding: vague tasks cause duplicate work, scope gaps, and misinterpretation. Every actual subagent dispatch must include all four fields. Inline lead execution does NOT require a brief — the lead already has the plan and operator-model in context. The brief exists to compress what the lead knows into what a fresh subagent needs.

```
objective:     <one sentence stating the exact outcome. Not "research X" — "produce a list of all callers of function X with file:line refs">
output_format: <exact shape of the return value. e.g. "JSON: {findings: [{file, line, snippet}]}" or "markdown table with columns A|B|C">
tool_list:     <explicit tools/skills/MCPs the subagent may use. Anything not listed is off-limits. e.g. "Grep, Read; do not edit files">
boundaries:    <what is OUT of scope. e.g. "do not touch tests/, do not propose alternative designs, do not exceed 15 tool calls per Step 4 budget">
```

Lead fills the brief from the plan + risk tier's effort budget. Before dispatch, lead validates all four fields are non-empty; if any field is missing, halt and log `BRIEF_INCOMPLETE: <field>` before re-attempting. Subagents that return work outside `boundaries` are rejected; lead re-dispatches with sharpened boundaries. Boundary-violation re-dispatches are capped at 2 per subagent slot; third violation halts EXECUTE and surfaces to Brandon with the offending output.

**Parallel Tool Call Rule.** Subagents and inline lead executions issue 3+ tool calls in a single message when the calls are independent. Sequential tool use is reserved for genuinely dependent operations. This codifies what's already best practice — it's here so the rule is greppable when a slow sequential pattern is observed.

### Step 6: MCP ROUTE

Invoke **mcp-router** with the task spec from Step 1. Router classifies into one of 9 categories and loads relevant MCPs. Honor `--mcps=` and `--no-mcps` flags from Step 0.

Output: loaded MCPs list. Pass to EXECUTE step.

### Step 7: EXECUTE

Run the plan.

- Inline execution: agent executes the plan step by step.
- Subagent execution: dispatch parallel subagents per plan section. Each subagent receives:
  - Its assigned plan section.
  - Its Structured Delegation Brief from Step 5 (objective, output_format, tool_list, boundaries).
  - Loaded MCPs from Step 6.
  - Relevant lessons from Step 2 (filtered to its section).
  - The operator-model summary.

Subagents return results. Orchestrator merges and resolves conflicts.

**Red-green loop (mandatory at or above `tdd.min_tier`).** Before any implementation edit, invoke the **tdd-loop** skill. Read the floor from `~/.claude/assay.config.json` (`tdd.min_tier`, default `MEDIUM`); `--no-tdd` bypasses and is logged.

Per behavior in the plan, one cycle:

1. Write one failing test at the seam — from the ticket's `seam` field, or the spec's Testing seams table.
2. Run it, capture the real failure into `state.json.tdd`, and **inspect the reason**. An `ImportError`, `SyntaxError`, missing fixture, or collection error is a false red: it proves the file did not load, not that the behavior was absent. Fix the test until it fails on its assertion.
3. Write the least implementation that turns that one test green. Do not touch the test during this step — if the test now looks wrong, stop and revise it deliberately with a fresh red proof, because quietly reshaping an assertion to match the code is invisible in the final diff.
4. Run the test, the affected suite, the linter, and the type checker; capture the green proof. Lint and types run per-cycle, not at the end, so an error surfaces while the context that caused it is still live.

One behavior per cycle. Batching tests before implementing collapses back into implement-then-test.

Exempt regardless of tier: docs, config, comment-only diffs, pure renames, dead-code deletion. Bug fixes are never exempt — the failing test is the bug report.

Subagents doing implementation work carry the cycle in their delegation brief and return the proofs in their artifact.

**If a cycle fails twice, do not write a longer prompt.** An agent's ceiling is the quality of the codebase's feedback loops. Ask which loop is inadequate — is the failure message actionable, is the test fast enough to actually be run, does a seam exist at all — and log the answer as a lesson in Step 12. A feedback-loop gap found on one ticket taxes every future ticket in the same area.

**README creation hook.** If the task creates or overhauls a repo's GitHub README (new project homepage, rebrand, visual upgrade), invoke the `beautify-github-readme` skill when available — README mode for whole-homepage work, asset-only mode for a hero/badge/diagram set. Degrade gracefully to plain Markdown if the skill is absent. This never blocks EXECUTE.

If any subagent times out or errors:
- Log the failure.
- Surface to Brandon: "(a) retry that subagent, (b) take over inline, (c) abort and save state."

**Artifact Reference Protocol.** Anthropic finding: routing every subagent result through the lead's context window creates a game of telephone and burns tokens copying large outputs through conversation history. Trigger is structural, not token-counted (token counting at write-time is not reliably available to the subagent): use the protocol for any structured artifact (code patch, table, diff plan, JSON, analysis report) OR any prose output longer than ~10 lines. Short prose findings (≤10 lines) may be inlined.

1. Subagent writes the full output to `$HOME/.claude/memory/sessions/<YYYY-MM-DD>-<session-id>/artifacts/<slug>.md`.
2. Subagent returns to lead a compact ref: `{path: "<artifact path>", summary: "<≤10-line gist>", schema: "<what's in the artifact>"}`.
3. Lead reads `path` and writes the state.json entry `{path, slug, producer: <subagent-id>, created_at: <ISO timestamp>}` from filesystem metadata — the subagent does not need to populate those fields.
4. Lead works from refs; reads the full artifact only when it needs the body (e.g., to merge into changeset, to feed to a judge, to compose final answer).
5. On `--dry-run` halt: full artifact bodies ARE written to disk (refs alone are useless on resume — resume needs the bodies).

Cleanup: session artifacts inherit the 90-day session GC rule from session-recall. Cleanup applies to `artifacts/` and `phase_summaries` together.

**Extended Thinking Guidance.** Anthropic finding: extended thinking acts as a controllable scratchpad and improves instruction-following, reasoning, and efficiency. Use it at two points:

- **Lead, before dispatch.** Think through the plan, tool fit, query complexity, subagent count, and each subagent's role. Output a thinking block that the dispatch step consumes — do not dispatch silently.
- **Subagents, interleaved after tool results.** After each tool call returns, the subagent uses interleaved thinking to evaluate quality, identify gaps, decide the next call. This adapts the subagent to its findings instead of running a pre-baked sequence.

Tier policy: TRIVIAL/LOW — not required. MEDIUM/HIGH — advisory (use when subagents fan out or when the plan is non-obvious). CRITICAL — required for both lead and subagents.

Output: changeset (modified files, new files, deletions) + artifact ref list.

### Step 8: JUDGE PANEL

Invoke **judge-panel** with the changeset and risk tier from Step 4.

**Diff snapshot (before).** Before dispatching any judge, record the changeset's stat line into `state.json.diff_before_review` as `{files, added, deleted}`. Step 14's run record diffs this against the post-review stat to compute whether the panel changed anything. Without the before-snapshot the edit-after-review metric is uncomputable, so take it even when the panel is expected to return `ship`.

**Always invoke the skill.** Tier and flags decide which judges fire; they never
decide whether judge-panel loads. Short-circuiting here is how a caller silently
revokes a callee's guarantees: the skill's own absolute exceptions — Security on
any security-tagged diff, at any tier, under any override — can only run if the
skill runs. Pass the tier and the flags and let it decide.

- TRIVIAL: the skill dispatches no judges, except Security on a security-tagged
  diff (judge-panel SKILL.md, "The Mandatory Set"). `--judges` forces the panel.
- LOW: 1-2 Tier 1 judges based on change type.
- MEDIUM: 3-5 Tier 1 judges.
- HIGH: full Tier 1 + minimum 2 relevant Tier 2 judges.
- CRITICAL: full Tier 1 + full Tier 2 + relevant Tier 3 judges.

Pass `--no-judges` through for TRIVIAL/LOW only; refuse it for HIGH/CRITICAL.
It suppresses the panel, never the Security judge on a security-tagged diff —
that judge is not overridable at any tier, and the skill enforces it.

**Write the receipt (last thing in Step 8, after the final revise cycle).** The
commit gate refuses a security-tagged diff whose receipt carries no security
verdict, and the receipt is keyed to the diff that was actually judged:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/write_judge_receipt.py" "$SESSION_DIR/state.json"
```

It reads `state.json.judges` and hashes `git diff --cached`, so stage the final
changeset before calling it. The state path is required and it refuses to mint a
receipt from a state that records no judges — an empty receipt can only produce a
block, which would route every security-tagged commit to the trailer escape. Write it AFTER Step 9 REVISE has settled: a receipt
minted before the last edit describes a diff that no longer exists, and the gate
will correctly refuse it.

Judges output verdict: `ship` | `revise` | `block`.
- ship — proceed to Step 10.
- revise — go to Step 9.
- block — halt pipeline, surface blocking concerns, save state.

### Step 8.5: BRANCH SURVEY (automatic — the diff's neighborhood)

Runs after the judges report and before REVISE, when `survey.in_pipeline` is
true and the tier is LOW or above. `--no-survey` skips it; `--survey` forces it.
Recorded as the `survey-branch` stage.

Judges see one diff. They do not see the neighborhood the diff landed in — the
module it now depends on that has no tests, the duplicate it just became the
third copy of, the credential sitting two functions away. That gap is the
cheapest thing in this pipeline to close, because the diff is already in hand.

Invoke the **survey** skill in `branch` scope at `quick` effort: files changed
since the merge-base with the default branch, plus their direct importers.
Every finding is tagged:

- **`introduced`** — this diff created it. Merge into the judge concerns and
  send it through REVISE like any other must-address item.
- **`pre-existing`** — it was already in a file this diff touched. Write it to
  the findings queue. These **never block the ship.** A slice does not inherit
  the debt of the file it edited, and blaming it for that is how a two-line fix
  turns into a refactor nobody asked for.

The distinction is the whole value of the step. Without it the survey either
blocks good work over legacy debt, or stays quiet about debt because a slice
happened to touch it.

Findings here are queued, never auto-promoted — a mid-ship survey has the least
context of any survey the system runs, and the board is not the place to find
out it was wrong.

### Step 9: REVISE

Address judge feedback marked `must_address_before_ship`.

- For each must-address item, apply fix (inline or via subagent).
- Re-run affected tests.
- Return to Step 8 for re-review (up to 2 revision cycles).

After 2 revision cycles, if judges still block: STOP and surface to Brandon. Do not enter infinite loop.

### Step 10: DONE GATE

Invoke **done-gate** to run all 9 checks. Risk-tier adjustments from done-gate's SKILL.md apply.

Check 9 (red before green) reads `state.json.tdd` and fails on a missing proof or a false red. It is bypassed by `--no-tdd` and by `tdd.min_tier: NEVER`, both logged.

**Diff snapshot (after).** Record the final changeset stat into `state.json.diff_after_review` as `{files, added, deleted}` — this is the post-judge, post-revise shape of the diff. Also record which judge concerns were actually acted on: for each judge in `state.json.judges`, set `accepted` to the count of that judge's concerns that produced a change in the diff or an explicit "will fix" from Brandon. A concern Brandon waved off is raised-but-not-accepted, and that distinction is the entire point of the judge acceptance metric — do not inflate it.

Honor skip flags: `--skip-tests`, `--skip-lint`, `--skip-types`, `--no-tdd`, `--force`. Each logged.

If any check fails: surface failure, halt pipeline, save state.

### Step 11: COMMIT

If `--dry-run` flag is set: halt pipeline before committing. Surface to Brandon:
- Full diff (file count, +/- lines, changed paths).
- Judge verdict from Step 8.
- Done-gate check results from Step 10.

Save state to `$HOME/.claude/memory/sessions/<YYYY-MM-DD>-<session-id>/` with `state.json` field `dry_run: true` and `next_step: 11`. Skip Steps 12-14. Tell Brandon: "Dry-run complete. Inspect changes, then `/assay resume` to commit, or modify files and re-run."

Otherwise, invoke **commit-protocol** for the 5-step engineer-in-the-loop commit flow.

- Generate commit message (or use `--commit-message=` if provided).
- Show overview to Brandon.
- Wait for explicit approval (ship, y, yes, commit, go).
- Commit (honors `--amend` flag).
- Push decision (honors `--no-push` and `--auto-push` flags).

If commit fails (pre-commit hook rejection): surface, offer auto-fix, do not bypass.

**Spec status flip (only when this /assay was invoked with a spec-id).** On commit success, if `state.json` has a `spec-snapshot` reference:
1. Re-open the spec at `$HOME/.claude/memory/projects/<ns>/specs/<spec-id>.md`.
2. Update frontmatter: `status: shipped`, `shipped-at: <YYYY-MM-DD>`, `shipped-commit: <full SHA>`.
3. Update the matching row in `$HOME/.claude/memory/projects/<ns>/specs/_index.md`.
4. Leave the spec body unchanged — it's the historical record of what was shipped.

If the spec file has been edited since the snapshot (mtime diverges), surface to Brandon: "Spec `<spec-id>` was modified during the ship run. Apply status update anyway? (yes/no/diff)." Default no — abort the status flip but keep the commit.

**Ticket status flip (only when this /assay was invoked with a ticket-id).** On commit success:

1. If `qa.queue` is `true` in `~/.claude/assay.config.json` (the default), set the ticket's status to `needs-qa` and leave it there. `needs-qa` does not unblock its dependents — work does not stack on a slice nobody has laid hands on yet.
2. If `qa.queue` is `false`, set status to `done` directly.
3. Record the commit SHA in the ticket frontmatter and regenerate `_board.md` from the ticket files.
4. If this was the last ticket for its spec and none remain in `todo`, `in-progress`, or `needs-qa`, apply the spec status flip above.

### Step 11.5: DEPLOY → CANARY (optional — deploy tasks only)

Closes the loop to production. Skipped by default: most repos in this tree are frozen (margin_invest decommissioned; aie_roadmap/shadybad non-deploying). Fires ONLY when opted in — any of: `--deploy` set, task primary verb ∈ {deploy, release, land}, or the project defines `.claude/deploy.md`. No trigger → skip silently to Step 12.

**Irreversible-action gate (always).** Deploy is CRITICAL tier by definition (Risk Tiers, CLAUDE.md). It NEVER runs without explicit Brandon approval, regardless of `--auto-push` or `--force` — those govern git, not production. Surface the target (env, project, commit SHA) and wait for explicit "deploy" / "go". `--no-deploy` hard-disables the stage even when a trigger matches.

1. **Preflight.** Confirm Step 11 committed AND pushed — deploy off an unpushed commit is refused. Resolve the deploy target from the project's `.claude/deploy.md` (contract + template: `templates/deploy.md` in the assay repo; required keys `env`, `command`, `health_url`, `expected_status`). No `.claude/deploy.md` → surface "no deploy target — skipping", proceed to Step 12. Do NOT infer a target from directory shape — absence of the file means opt-out.
2. **Deploy.** Run `command` from the contract. `mcp:vercel` → Vercel MCP `deploy_to_vercel`; any other value → run verbatim as a shell command. Capture deployment URL + build logs. Build failure → HALT, surface logs, save state, route to postmortem. Do NOT proceed to canary.
3. **Canary.** Invoke **ecc:canary-watch** against `health_url`. Poll `canary_window` (default 5 min): HTTP status vs `expected_status`, plus — when `metrics` is `posthog`/`sentry` and that MCP is wired — error-rate delta and p95 latency.
4. **Verdict.**
   - `healthy` — record deploy SHA + URL in state, proceed to Step 12.
   - `degraded` / `error-spike` — surface metrics, offer (a) rollback (per the contract's `rollback` key; `manual` surfaces steps without auto-acting), (b) hold and investigate, (c) accept. Rollback is itself an irreversible action — explicit approval.
5. On `--dry-run`: this stage never fires (no commit exists).

Output: deploy record `{sha, url, canary_verdict, metrics}` written to `state.json.deploy`.

### Step 12: LEARN

Skipped on `--dry-run` halts (no commit to learn from). Runs on the eventual `/assay resume` commit instead.

After successful commit:

1. **project-memory** — extract lessons from this run. Append to project's `lessons.md`. Format: `[<date>] <project>: <takeaway>`.
2. **operator-model** — if Brandon corrected, overrode, or rejected anything during the pipeline, update operator-model with the new signal.
3. **session-recall** — write session summary to `$HOME/.claude/memory/sessions/<date>-<session-id>/`.
4. **context-glossary** — scan the shipped diff for concepts the glossary does not name (`/context extract`). Proposals only, capped at 5, never blocking. A term that had to be explained twice during this run is the strongest candidate.

These updates are append-only. Never overwrite existing lessons or operator-model entries.

### Step 12.5: CADENCE SURVEY (post-ship, async — off the critical path)

Same contract as CURATE CHECK below: it fires after the report is delivered, it
is detached, and it NEVER blocks the commit, the report, or Brandon. Recorded as
the `survey-cadence` stage.

Read `$HOME/.claude/memory/projects/<ns>/last-survey-run.txt`. If it is missing
or older than `survey.cadence_days` (default 7), fire the **survey** skill in
`hotspots` scope at `quick` effort as a detached background pass, then stamp
the file. Under the cadence, do nothing — skip entirely.

Findings land in the queue and surface at the next SessionStart. Auto-promotion
applies only if `survey.auto` is `promote`, and is capped by
`survey.max_promote_per_cycle`.

A survey failure is logged in the report and ignored. Discovery that can halt a
ship is worse than no discovery — the same rule the run recorder lives under.

`--no-survey` skips this stage.

### Step 13: CURATE CHECK (post-ship, async — off the critical path)

Curation is skill hygiene, not part of shipping a change. It NEVER blocks commit, the report, or Brandon. The per-run `propose` mode is removed (it taxed every ship for a rare payoff).

After the report is delivered: check `$HOME/.claude/memory/global/last-curator-run.txt`. If missing OR 7+ days old, fire **skill-curator** in `full` mode as a detached background pass and update the timestamp. If skill-curator proposes anything, note the count in the report's `Curator:` line if the pass finished in time, otherwise leave it for the next session. If under 7 days, do nothing — skip entirely.

### Step 14: REPORT (NOTION is now on-demand, not a pipeline prompt)

NOTION ROUTE is removed from the pipeline. /assay no longer prompts "push to Notion?" per artifact at the end of every run — that interrupted every ship for a rarely-taken action. Instead, the report lists eligible artifacts and their local paths; Brandon pushes what he wants with an on-demand `/share <artifact>` (routes through notion-bridge). Default is local-only.

Generate final /assay report:
ASSAY COMPLETE ✓
Task: <task description>
Project: <project>
Risk tier: <tier>
Duration: <elapsed time>
Plan: <one-line summary>
Files changed: <count> (+<adds> -<dels>)
Tests: <pass count>/<total>
Judge verdict: <verdict> (<judge count> judges, <tier>)
Commit: <SHA> <message>
Push: <pushed | local-only>
Lessons captured: <count>
Operator model updates: <count>
Survey: <n introduced (in revise) · n pre-existing queued | skipped>
Findings queue: <n pending> (review with /survey queue)
Curator: <async pass running | N proposals | skipped (<7d)>
Notion-eligible artifacts: <count> (local; push with /share <artifact>)
Next: <suggested next action if applicable>

### Step 14b: RUN RECORD (instrumentation — always, never blocking)

The pipeline is otherwise unmeasured: it runs, the judges opine, and nothing on disk says whether any of it changed the shipped diff. After the report is delivered, append one run record so `/assay-stats` can answer that later.

Assemble the record from `state.json` and pipe it to the recorder:

```bash
echo '<record-json>' | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/assay_record.py"
```

Record shape (only `project`, `risk_tier`, and `outcome` are required; omit what a run genuinely lacks rather than inventing it):

```json
{
  "project": "margin-invest",
  "task": "<one-line task summary>",
  "risk_tier": "HIGH",
  "invocation": "task | spec | ticket",
  "flags": ["--dry-run", "--no-spec"],
  "outcome": "committed",
  "stages_eligible": ["spec-escalation", "context-load", "plan", "tdd-loop", "judge-panel", "judge-vet", "survey-branch", "done-gate", "commit-protocol", "learn"],
  "stages_fired": ["context-load", "plan", "tdd-loop", "judge-panel", "judge-vet", "survey-branch", "done-gate", "commit-protocol", "learn"],
  "judges": [
    {"judge": "security", "model": "opus", "verdict": "block", "concerns": 2, "accepted": 1, "dropped": 3}
  ],
  "survey": {
    "scope": "branch",
    "findings_raw": 9, "findings_after_vet": 4,
    "findings_promoted": 0, "findings_queued": 4, "findings_rejected": 5
  },
  "diff_before_review": {"files": 3, "added": 88, "deleted": 12},
  "diff_after_review":  {"files": 3, "added": 94, "deleted": 12},
  "done_gate_blocked_on": [4],
  "done_gate_skipped": ["tests", "tdd"],
  "brandon_verdict": "approved_first_pass | approved_after_rework | abandoned | unknown",
  "rework_turns": 2,
  "duration_s": 410,
  "tokens_total": 184000,
  "commit": "<short SHA>"
}
```

Rules:

- **Never block on it.** A recorder failure is logged in the report and ignored. Instrumentation that can halt a ship is worse than no instrumentation.
- **Never fabricate a field.** `brandon_verdict` defaults to `unknown` and `unknown` runs are excluded from the approval metric — that is correct behavior, not a gap to paper over. A guessed value silently poisons every later reading.
- **`accepted` ≤ `concerns` per judge**, counting only concerns that changed the diff or drew an explicit "will fix." The recorder rejects records that violate this. `concerns` is the **post-vet** count; `dropped` carries what Step 8's VET pass threw out, and `dropped / (dropped + concerns)` is the number that identifies a judge worth cutting.
- **The survey funnel only narrows.** `findings_after_vet` ≤ `findings_raw`, and promoted + queued ≤ vetted. The recorder rejects a widening funnel, because vetting removes findings and cannot add them — a funnel that grows is a miscount, not a discovery.
- **`stages_eligible` is the honest denominator** — list a stage only if this run's tier and flags meant it *should* have run. A stage skipped by design (judges at TRIVIAL, context-load at LOW) is not eligible and must not be listed.
- **Watch the discovery stages too.** `survey-branch` is eligible on any LOW+ run while `survey.in_pipeline` holds; `survey-cadence` is eligible only when the stamp is actually stale. A vet-survival rate trending to zero means the audit is manufacturing noise and its categories need narrowing — which is a decision to make from the log, not from an argument.
- **The two discipline stages are the ones worth watching.** `spec-escalation` is eligible on any MEDIUM+ task-invocation run and fires only when the gate actually escalated; `tdd-loop` is eligible whenever the tier is at or above `tdd.min_tier` and the diff is not exempt. Eligible-but-never-fired on either is the signal that a gate has quietly become decorative — which is exactly what `/assay-stats` exists to catch.

Read the numbers back with `/assay-stats`.

## State Management

### Saving State on Interrupt

If pipeline is interrupted (Brandon types "stop", subagent times out and Brandon chooses abort, judge-panel returns block, etc.), save:

`$HOME/.claude/memory/sessions/<YYYY-MM-DD>-<session-id>/`
  - `state.json` — current step, completed steps, flag values, classifications. For `--dry-run` halts: also includes `dry_run: true` and `next_step: 11`. Carries `artifacts: [...]` (Step 7 Artifact Reference Protocol), `phase_summaries: {<phase>: <summary>}` (Long-Horizon Hand-off, below), `subagent_dispatch_count: <int>` (Step 4 Effort Budget — real countable hard limit, replaces the former self-counted `tool_call_tally`), `tier_model: <haiku|sonnet|opus>` (Step 4 Model by Tier), `handoff_pending: bool` (Hand-off flag), and `subagent_failures: [{slug, reason, timestamp}]`.
  - `task-spec.md` — parsed task from Step 1.
  - `plan.md` — plan from Step 3.
  - `changeset.md` — partial changes if applicable.
  - `judge-output.md` — last judge verdict if applicable.
  - `artifacts/<slug>.md` — subagent outputs persisted by the Artifact Reference Protocol.
  - `spec-snapshot.md` — spec frozen at pipeline entry (when invoked with a spec-id).

### Resuming

`/assay resume` (or `/assay resume <session-id>` for specific older session):
- Loads most recent session state.
- Shows Brandon the summary: "Resuming from Step <N>. Last action: <description>. Continue? (yes / restart / abort)."
- On yes, picks up at the next step.
- If state has `dry_run: true`, resume re-verifies the working tree matches the saved changeset (warn if drift), then runs Step 11 COMMIT onward as a normal commit. If ANY file changed since the dry-run, Step 8 re-runs in full — the saved verdict describes a diff that no longer exists, and a drift warning is not a substitute for re-judging.

### Long-Horizon Hand-off (context-overflow guard)

Anthropic finding: production agents engage in long conversations that exceed standard context windows; the fix is intelligent compression + memory hand-offs, not larger context. /assay inherits this pattern for long-running sessions (HIGH/CRITICAL with many subagents, or a /assay resume that has accumulated many phases).

Trigger: any of (a) Claude Code emits a compaction or context-pressure warning, (b) the SessionStart context reports token usage in the high band, (c) the lead has dispatched ≥3 subagents in a single HIGH/CRITICAL run with artifacts accumulating in `state.json.artifacts`. If none of these signals are available, the protocol is opt-in — Brandon or the lead invokes it manually when a long run feels close to the limit.

Protocol:

1. **Summarize completed phases.** For each pipeline step already completed (e.g., PARSE, CONTEXT LOAD, PLAN, DISPATCH), write a ≤300-line summary into `state.json.phase_summaries[<step-name>]`. Include: what was decided, what artifacts were produced (paths only, by ref), what was rejected. If a summary exceeds 300 lines, write it in full with a `truncation_marker: false` field AND surface to Brandon: "phase summary for <step> oversize — review before continuing hand-off."
2. **Preserve full artifacts.** The Artifact Reference Protocol already wrote the full bodies to `artifacts/<slug>.md`. Do not duplicate them in summaries — refs are enough.
3. **Fresh subagent, clean context.** When dispatching the next subagent, hand it: (a) its Structured Delegation Brief, (b) the relevant `phase_summaries` entries, (c) the artifact refs it needs by path. Do not pass full prior conversation history.
4. **Lead can also restart its own context.** If lead approaches the threshold, lead writes a `lead_handoff.md` checkpoint into the session dir capturing remaining steps + outstanding subagent results, sets `state.json.handoff_pending: true`, then a fresh lead instance resumes from that checkpoint.
5. **Continuity check on resume.** `/assay resume` ALWAYS checks `state.json.handoff_pending`. If `true`, read `lead_handoff.md` first and reconstruct from `phase_summaries` + `artifacts` + checkpoint; do not replay original conversation. If `false`, resume by the original step pointer.

Hand-offs are append-only: phase_summaries entries never overwrite prior ones; if a phase is re-entered (e.g., revise loop), append `<step>-r1`, `<step>-r2`.

### Pipeline Halt → Postmortem (failure-side learning loop)

Step 12 (LEARN) only fires after a successful commit. Without a counterpart, every aborted, blocked, or halted run produces zero learning — and failures carry the highest-signal lessons.

On any non-success exit from Steps 3, 7, 8, 9, 10, 11, or 11.5 (Brandon abort, subagent timeout chosen abort, judge `block`, revise cycles exceeded, done-gate failure, pre-commit hook rejection with no auto-fix, deploy build failure or canary rollback), and on any `stop`/`abort` input mid-pipeline:

1. Save state per "Saving State on Interrupt" above.
2. Invoke the **postmortem** skill in `auto` mode with `failure_step`, `attempted_action`, `gate_verdict`, and `partial_changeset` pulled from the saved state.
3. The skill surfaces two questions (root cause + change going forward) and routes Brandon's response to project-memory (always proposed), operator-model (when about Brandon/Claude behavior), a skill-description suggestion (when a skill is named), and notion-bridge (when team-relevant).
4. If Brandon types `skip`, the skill logs to `$HOME/.claude/memory/global/postmortem-skipped-log.md` and exits clean. Skipping never blocks the state-save-and-exit.
5. Emit a Step 14b run record with `outcome` set to `halted`, `aborted`, or `blocked` (whichever matches), plus `halt_step: <N>` and whatever stage/judge data the run reached. Halted runs carry the highest-signal instrumentation — a judge that blocks often but whose blocks are never accepted is exactly what the acceptance metric exists to find, and dropping failed runs from the log biases every rate upward.
6. Postmortem skill failures are non-blocking — /assay's own halt path completes regardless.

The skill is opportunistic — it runs after state is already safe on disk. Brandon can also invoke `/postmortem --from-session=<session-id>` later if he skipped at the time and wants to revisit.

## Failure Modes Per Step

| Step | Common failure | Default behavior |
|------|----------------|------------------|
| 1 PARSE | Task too vague | Ask Brandon one clarifying question. |
| 1 PARSE | Spec-id not found in current namespace | Search other namespaces; surface match or refuse with "Spec `<spec-id>` not found." |
| 1 PARSE | Spec status is `draft` | Refuse. Tell Brandon to run `/spec approve <spec-id>` first. |
| 1 PARSE | MEDIUM+ task with no measurable outcome or named seam | Escalate to `/spec`, defaulting to yes. `proceed` continues; `--no-spec` skips the gate. Logged either way. |
| 1 PARSE | Spec status is `shipped` | Warn. Allow only with `--force`. |
| 11 COMMIT | Spec mtime diverged from snapshot | Surface to Brandon. Default: keep commit, skip status flip. |
| 2 CONTEXT | Memory file corrupt | Log warning. Continue with empty context. |
| 3 PLAN | Plan tool unavailable | Generate inline plan. Note degradation. |
| 4 RISK | Cannot classify | Default to MEDIUM. Surface to Brandon. |
| 5 DISPATCH | Subagent plugin missing | Sequential inline. Note. |
| 6 MCP ROUTE | All MCPs disconnected | Surface to Brandon. Offer continue without MCPs or abort. |
| 7 EXECUTE | Subagent times out | Brandon picks: retry, inline, abort. |
| 8 JUDGE | Judge unreachable | Skip that judge and continue, UNLESS it is mandatory under judge-panel Aggregation rule 0 (Security on a security-tagged diff at any tier; Karpathy and Failure Mode on HIGH/CRITICAL; Threat Modeler on a security-tagged HIGH/CRITICAL) — those get one re-dispatch, then the verdict is `block`. If the panel cannot form quorum (≥50% of expected judges), surface to Brandon. |
| 9 REVISE | 2 cycles exceeded | Halt. Surface unresolved blockers. |
| 10 DONE GATE | Any check fails | Halt. Show fix. |
| 11 COMMIT | Hook rejection | Surface. Offer auto-fix. Never bypass. |
| 11 COMMIT | Mandatory-judge gate blocks | The staged diff looks security-tagged and no security verdict covers it. Let judge 2 run and re-write the receipt, or add `Security-Review: skipped -- <reason>` to the commit message. NEVER `--no-verify`. |
| 11 COMMIT | Gate itself errors | It fails closed by design. Fix the gate, or use the trailer. If the gate is broken badly enough to block its own fix, `git -c core.hooksPath=/dev/null commit` scopes the bypass to one commit without disabling it globally. |
| 8.5 SURVEY | Branch survey errors or times out | Log it in the report. Continue to REVISE with the judge concerns alone. Never block. |
| 12.5 SURVEY | Cadence survey fails | Log. Do not re-stamp `last-survey-run.txt`, so the next ship retries. Never block. |
| 12 LEARN | Memory write fails | Retry once. Then log error. Do not block. |
| 13 CURATE | Curator errors | Log. Skip. Do not block. |
| 14 REPORT | Report write fails | Print report to stdout. Log error. Do not block. (Notion is on-demand `/share`, not in-pipeline — no failure mode here.) |
| 14b RUN RECORD | Recorder rejects the record (schema error) | Print the recorder's message in the report. Do not retry with invented values. Do not block. |
| 14b RUN RECORD | Recorder script missing or unreadable | Note "run record skipped" in the report. Do not block. |
| State (Hand-off) | phase_summaries write fails | Retry once. On second failure, surface to Brandon — hand-off cannot proceed safely without persisted summaries. |
| State (Hand-off) | lead_handoff.md missing on resume | Refuse resume with handoff_pending=true. Tell Brandon to inspect session dir or restart. |
| State (Artifacts) | artifact write fails | Subagent retries write; on second failure, returns inline body with `inline_fallback: true` marker. Lead logs the fallback. |

## Hard Constraints

- NEVER skip judge-panel for HIGH/CRITICAL risk, regardless of flags.
- NEVER skip invoking judge-panel at all. Tier and flags select judges inside the skill; they do not gate whether it is consulted. A caller that short-circuits the skill revokes every guarantee the skill makes.
- NEVER return a verdict other than `block` when a judge mandatory under judge-panel Aggregation rule 0 did not run — whether it failed, or was never dispatched.
- NEVER auto-push without `--auto-push` flag.
- NEVER deploy (Step 11.5) without explicit Brandon approval. `--auto-push` and `--force` govern git, NOT production — neither bypasses the deploy gate. Rollback is likewise explicit-approval only.
- NEVER push to protected branches without per-push confirmation.
- NEVER bypass done-gate Check 8 (Brandon approval). Even `--force` does not bypass approval.
- NEVER write to operator-model.md without Brandon's explicit acknowledgment of the change.
- NEVER infinite-loop the revise step. Hard cap at 2 cycles.
- ALWAYS save state on interrupt. Brandon should be able to resume.
- ALWAYS produce the final report, even on partial completion or failure.
- ALWAYS log force-bypass usage. Every `--force` invocation is reviewed by skill-curator weekly.
- ALWAYS emit a Step 14b run record, on success and on halt alike. Logging only successful runs biases every metric upward.
- NEVER fabricate a run-record field to avoid an `unknown`. An honest gap is data; a guess is corruption.
- NEVER let a pre-existing survey finding block a ship. It is queued, not a gate. A slice does not inherit the debt of the files it touched.
- NEVER auto-promote a survey finding to the board unless it clears every condition in the survey skill's promotion bar, and never past `survey.max_promote_per_cycle`.
- NEVER let the cadence survey delay the commit, the report, or Brandon. Detached, or not at all.
- NEVER let a judge concern reach REVISE or Brandon without Step 8's VET pass re-opening its cited location.
- NEVER let the run recorder block, delay, or alter a ship. It is instrumentation, not a gate.
- NEVER run a `/assay <spec-id>` when the spec status is `draft`. Force Brandon through `/spec approve` first.
- NEVER overwrite a spec's `shipped-at` or `shipped-commit` fields once set. Re-shipping with `--force` requires a new spec.
- ALWAYS snapshot the spec into session state on entry. The snapshot is the contract for this ship run; later edits to the spec file do not affect a run in progress.
- NEVER commit when `--dry-run` flag is set. Always save state and surface diff + verdict instead.
- NEVER dispatch a subagent without a Structured Delegation Brief (objective, output_format, tool_list, boundaries). Free-form delegation is rejected — re-dispatch with a brief.
- NEVER inline a subagent output longer than ~200 tokens in lead context. Use the Artifact Reference Protocol — write the body to `sessions/<id>/artifacts/<slug>.md`, return a ref.
- NEVER exceed a tier's per-subagent tool-call ceiling without explicit Brandon override. At the ceiling, the subagent must finalize and return an artifact ref.
- NEVER replay full conversation history into a fresh subagent on Long-Horizon Hand-off. Pass `phase_summaries` + artifact refs only.
- NEVER dispatch a subagent with an incomplete Structured Delegation Brief. Lead validates all four fields are non-empty before dispatch; missing field → halt and log `BRIEF_INCOMPLETE: <field>`.
- NEVER re-dispatch a subagent more than 2 times for boundary violations. Third violation surfaces the offending output to Brandon and halts EXECUTE.
- NEVER resume a session with `handoff_pending: true` by replaying — always read `lead_handoff.md` first.

## Design Influences

- Anthropic Engineering, "How we built our multi-agent research system" (Jun 13, 2025). Effort Budget by Tier (Step 4), Structured Delegation Brief + Parallel Tool Call Rule (Step 5), Breadth-First Heuristic (Step 3), Artifact Reference Protocol + Extended Thinking Guidance (Step 7), Long-Horizon Hand-off (State Management) all adapt patterns from that post. /assay is a single-user code-oriented orchestrator, not a multi-user research product — the patterns are ported as architectural moves, not as performance promises.

## Plugin Compatibility

Required: none — the orchestrator degrades gracefully when plugins are missing.

Planning (Step 3), subagent dispatch (Step 5), and parallel execution (Step 7) run on built-in capability: the `Plan` and `Explore` agents and the Agent tool. They previously delegated to `superpowers:*` plugins; that wiring is removed, not degraded.

Enhanced by (in order of impact):
- `plugin-dev` — used downstream by skill-curator.
- `commit-commands` — commit primitives.
- `github` — PR creation.
- `hookify` — done-gate hook enforcement.
- `pyright-lsp` — done-gate Check 6.
- `caveman` — MCP description compression.
- `beautify-github-readme` — README homepage + GitHub-safe SVG/GIF asset generation. Invoked in EXECUTE (Step 7) when a task creates or overhauls a repo README, and by plugin-packager Step 5.

## Quick Reference
/assay "<task>"                          # Default. Auto risk, judges per tier, ask-before-push.
/assay <spec-id>                         # Consume approved spec. Status, risk-tier, success criteria pre-loaded.
/assay <ticket-id>                       # Execute one vertical slice from the board. Tier, seam, acceptance pre-loaded.
/assay <spec-id> --force                 # Re-ship a previously-shipped spec (rare; usually write a new spec instead).
/assay "<task>" --risk=high              # Force HIGH tier.
/assay "<task>" --no-judges              # Skip judges (TRIVIAL/LOW only).
/assay "<task>" --skip-tests --skip-lint # Bypass selected gates with logging.
/assay "<task>" --force                  # Emergency hotfix. All gates bypassed except approval.
/assay "<task>" --commit-message="..."   # Use exact commit message.
/assay "<task>" --auto-push              # Push immediately after commit.
/assay "<task>" --deploy                 # After commit, run deploy → canary (Step 11.5). Explicit deploy approval still required.
/assay "<task>" --no-deploy              # Suppress deploy → canary even for a deploy-verb task.
/assay "<task>" --dry-run                # Run through done-gate, show diff + verdict, halt before commit. Resume to commit.
/assay "<task>" --no-tdd                 # Skip the red-green loop and Check 9. Logged to the run record.
/assay "<task>" --no-spec                # Skip the Step 1 escalation to /spec on a fuzzy MEDIUM+ task. Logged.
/assay "<task>" --no-survey              # Skip the Step 8.5 branch survey and the Step 12.5 cadence survey.
/assay "<task>" --survey                 # Force the branch survey even at TRIVIAL or with in_pipeline off.
/assay resume                            # Resume last interrupted session (or finish a dry-run).
/assay-stats                             # Read the run log back: stage fire rates, judge acceptance, approval.
