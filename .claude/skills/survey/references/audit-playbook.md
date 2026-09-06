# Audit Playbook

What to look for, per category, plus the finding format every auditor returns
and the rubric that orders the results. Each audit subagent receives the path to
this file and the headings it must read — **always including "## Finding
format"**. Handing over the path costs a fraction of pasting the sections, and
a subagent that cannot confirm it read the file is a subagent whose findings
are unusable.

Adapt depth to repo size. A 2K-line CLI gets a lighter pass than a uv workspace
with three members.

**A finding is only a finding with evidence.** "Probably has an N+1 somewhere"
is not a finding. `engine/scoring/api.py:142 issues one query per holding
inside a loop` is. Every finding carries `file:line` or it does not ship.

---

## 1. Correctness / Bugs

Highest-trust category — real bugs found by reading, not speculation.

- Error handling: swallowed exceptions, bare `except:`, `except Exception:
  pass` on a critical path, missing error states.
- Async hazards: unawaited coroutines, races on shared state, missing
  cancellation or cleanup, tasks nobody holds a reference to.
- Null/None flows: values asserted non-None that can be None, `.get()` results
  used without a check, unchecked indexing.
- Boundary conditions: off-by-one, empty-collection handling, timezone and
  locale assumptions, integer overflow in counters or ids.
- State machines: impossible states the types permit, status enums with an
  unhandled branch, an `else` that silently no-ops.
- Concurrency: check-then-act on shared resources, multi-write operations with
  no transaction, retried operations that are not idempotent.
- Type escape hatches: `Any`, `cast()`, `# type: ignore` clusters. Each one is
  a place the checker was overruled.
- Resource leaks: unclosed handles, connections, subscriptions; missing
  `finally` or context manager.

## 2. Security

Review only what code evidence directly supports. Frame findings as defensive
maintenance: name the pattern, explain the production impact, describe the
remediation. Keep it at the level of code changes, configuration changes, and
tests. Do not include runnable demonstration strings or step-by-step misuse
detail.

**Handling rule — never copy a secret value into a finding, a ticket, or a
plan.** Those files get committed, and a survey that leaks a live token has
done more damage than the finding was worth. Reference the `file:line` and the
credential type only ("Stripe live key at `config.py:12`"). The fix sketch
always includes rotation, not just removal: a committed secret is burned even
after it is deleted.

**By-design is not a finding.** Standard platform conventions are intentional:
honoring `https_proxy`/`NO_PROXY`, reading `~/.netrc`, a local dev tool
shelling out to a configured package manager. A tradeoff recorded in an ADR
under `glossary.adr_path`, or pinned in a spec's Implementation choices, is
settled. Flag these only when the *implementation* adds risk beyond the
convention itself.

**But a stale ADR is itself a finding.** If the code has drifted from what the
decision record says, report the drift. One of the two is wrong and the
operator should know which. Never use a decision doc to suppress a discrepancy
with the code it describes.

- Credential hygiene: hardcoded keys, tokens, or passwords; credentials in a
  committed `.env`; credentials logged or persisted into a history store.
- Data crossing into interpreters or privileged APIs: SQL or shell operations
  assembled from request data, HTML sinks fed by user-controlled content,
  dynamic execution with runtime input, filesystem paths derived from request
  data. Name the safer API or the validation boundary.
- Access control: endpoints missing a server-side identity check, authorization
  enforced only client-side, object access by id with no ownership or tenant
  check, state-changing routes with no request-authenticity check.
- Input contracts: API boundaries that trust a request body without schema
  validation, uploads with no type/size/storage constraint, broad object
  assignment from request data into a persistence model.
- Dependency posture: run the ecosystem's audit command read-only (`uv pip
  audit`, `pip-audit`, `npm audit`). Report only critical/high advisories that
  reach runtime or build code. Audit noise is not a finding.
- Production configuration: credentialed CORS with a broad origin, missing
  response hardening where a sensitive browser surface exists, cookies missing
  `HttpOnly`/`Secure`/`SameSite`, debug behavior enabled in production config.
- Data minimization: PII or sensitive operational data in logs, stack traces
  returned to clients, internal error detail exposed through an API.

## 3. Performance

Algorithmic and architectural wins, not micro-optimizations.

- N+1 patterns: a query or fetch per item inside a loop; missing batching.
- Wrong complexity: nested scans over the same collection, a repeated linear
  search inside a hot loop where a dict lookup belongs.
- Caching gaps: the same expensive computation repeated per request; missing
  memoization at a clear function boundary; no caching on stable data.
- Payload size: over-fetching, missing pagination on an unbounded list, large
  payloads shipped where ids would do.
- Backend: synchronous work that belongs in a queue; indexes implied by query
  patterns (flag for verification — never claim one without schema evidence);
  connection-per-request where a pool exists.
- Build/CI: missing caching, redundant pipeline steps, a suite that could
  parallelize.

## 4. Test Coverage

The goal is not a percentage. It is *which untested code is dangerous*.

- Map the critical paths — money, auth, data mutation, the thing the repo
  exists for — and check which have zero or trivial coverage.
- High churn (from `git log`) plus no tests is the top refactor risk. Flag as a
  "characterization tests first" candidate; it becomes a blocking ticket for
  any refactor of the same module.
- Existing test quality: tests that assert nothing meaningful, mocking so heavy
  the test exercises the mock, snapshots nobody reads, flake patterns (real
  timers, real network, order dependence).
- Missing layers: unit-only suites with no integration coverage at an API
  boundary, or slow end-to-end tests doing a unit test's job.
- **Verification infrastructure.** Is there a one-command way to know the
  codebase works? If not, that is finding #1, and it blocks every risky ticket
  behind it. A survey that recommends a refactor into a repo with no green
  suite is recommending an unverifiable change.

## 5. Tech Debt & Architecture

Module-depth findings — shallow clusters, bidirectional coupling, co-change
rate, leaked internals, pass-through layers — belong to the `architecture-scan`
skill. **Invoke it for this category rather than re-deriving it.** It already
owns the import graph, the co-change matrix, the 5-cluster cap, and the
mandatory "what this makes worse" section. What is left for this playbook:

- Duplication: the same logic re-implemented in three or more places;
  divergent copies that have already drifted (a TODO admitting the drift is
  the strongest possible evidence).
- Dead code: unexported and unused modules, fully rolled-out flags still
  branching, commented-out blocks with no explanation, manifest dependencies
  nothing imports.
- God modules: files an order of magnitude larger than the repo median that
  everything touches; functions with double-digit parameters or deep nesting.
- Inconsistent patterns: three ways of doing error handling in one repo. Pick
  the winner — the one the team converged on most recently — and plan the
  consolidation toward it.
- Abstraction mismatches: a premature abstraction with one implementation, or a
  missing abstraction where the same change always touches N files in lockstep.

## 6. Dependencies & Migrations

- Major-version lag on a core framework or runtime — the ones with real cost to
  staying behind (EOL, security-fix cutoff, ecosystem incompatibility), not
  every minor bump.
- Deprecated APIs in use with an announced removal timeline.
- Abandoned dependencies on a critical path.
- Duplicate dependencies solving the same problem.
- Lockfile/manifest drift; pinning inconsistent across workspace members.
- Estimate blast radius (files touched) for every migration candidate. That
  drives effort, and often the answer is "not worth doing."

## 7. DX & Tooling

- Missing or broken: type checker config, lint config, formatter, pre-commit
  hooks.
- Slow feedback loops: a test suite too slow to actually run per cycle, no
  watch mode, CI with no caching. **This category outranks its usual priority
  in Assay**, because the TDD loop's own escalation rule says an agent's
  ceiling is the quality of the feedback loops. A slow or uninformative suite
  taxes every future ticket in the repo.
- Onboarding friction: setup steps that are wrong, undocumented required env
  vars, no `.env.example`.
- Missing `CLAUDE.md`/`AGENTS.md` — high leverage in a repo where agents
  execute the work.
- Error messages and logging: unstructured logs, missing correlation ids,
  debugging that requires editing code.

## 8. Docs

Lowest default priority. Only flag where absence has a concrete cost:

- A published API surface with no reference docs.
- An actively contested decision nobody can reconstruct (why X over Y) — that
  is an ADR-shaped gap, routed to `/context adr`.
- Stale docs that are actively wrong, which is worse than missing.
- A concept the code names two different ways and the glossary names zero
  times. That is a `context-glossary` entry, not a docs rewrite.

## 9. Direction — features and where to take this next

Forward-looking: not what is broken, but what this codebase wants to become.

**Grounding rule: every suggestion must cite evidence from the repo itself.** A
suggestion that could apply to any project in the category — "add dark mode",
"add AI" — is noise, not a finding. Sources of grounded signal:

- **Unfinished intent**: TODO/FIXME clusters around one theme, flags never
  rolled out, stubbed modules, abandoned mid-feature work visible in git
  history.
- **Stated but undelivered**: README or spec promises with no corresponding
  code, CLI flags that are no-ops. An approved spec whose tickets were never
  cut is the strongest grounding signal available in this system — check the
  board before inventing anything.
- **Surface asymmetries**: one-directional pairs (export without import, create
  without bulk-create), an entity with CRUD minus one, an internal API that
  callers clearly hand-rolled around.
- **The adjacent possible**: capabilities the existing architecture makes
  disproportionately cheap — a plugin boundary one interface away, an
  integration the data model already supports.
- **Friction worth absorbing**: things done by hand around the project that the
  project could do itself.

Two adaptations to the finding format: **Impact** is product value (who wants
this and why now), and **Confidence** reflects how grounded the evidence is —
not certainty that it is the right call. Strategy belongs to the operator; the
survey's job is grounded options with honest trade-offs. Effort estimates here
are coarser, and the finding says so.

**Direction findings are never auto-promoted.** They become a `/spec` seed at
most, and only when picked by hand.

---

## Finding format

Every finding, from every category and every subagent, comes back in this
shape. Anything missing a field is incomplete, not a finding.

```markdown
### [CATEGORY-NN] Short imperative title

- **Evidence**: `path/file.py:123` — one sentence on what is there. Repeat per
  location; two to five strongest, then "and ~N similar sites" if widespread.
- **Impact**: What goes wrong, or what is being paid. Concrete: "every
  portfolio render issues 1+N queries", not "suboptimal".
- **Effort**: S (hours) / M (a day-ish) / L (multi-day), for the *fix*,
  including tests.
- **Risk**: What the fix could break. LOW/MED/HIGH plus one line why.
- **Confidence**: HIGH (read the code, certain) / MED (strong signal, needs
  verification) / LOW (smell, needs investigation).
- **Seam**: The function, endpoint, CLI, or fixture a test would drive, and the
  test file it would live in. `none` if you could not name one.
- **Fix sketch**: One to three sentences. Not the plan — just enough to judge
  the effort honestly.
```

The **Seam** field is Assay-specific and load-bearing. A finding with no seam
cannot start a TDD loop, so it can never be auto-promoted and it can never
become a ticket directly — it becomes a `/spec` seed, where the grill's job is
to find the seam. Do not invent one to make a finding look actionable.

## Prioritization rubric

Order by **leverage = impact ÷ effort, discounted by confidence and fix-risk**.

Tiebreakers, in order:

1. Anything that unblocks other findings floats up. A verification baseline or
   a characterization-test ticket is worth more than the refactor it enables,
   because the refactor is unshippable without it.
2. HIGH-confidence security findings float above equal-leverage non-security.
3. Prefer findings with a clean verification story. They are the ones an
   unattended `/implement` run can actually finish.
4. **"Not worth doing" is a valid verdict.** Record it in the rejection ledger
   with one line of reasoning, so the next cadence run does not re-derive it.

A short list of high-confidence, high-leverage findings beats a long one. The
queue is read by a human on a Tuesday morning; twenty entries means zero get
acted on.
