---
name: tdd-loop
description: Enforces a strict red-green-refactor cycle during /assay execution so the agent cannot implement first and then write loose tests that agree with whatever it built. Requires a captured failing-test run (the red proof) before any implementation edit, then a passing run plus lint and types (the green proof), recorded to the session state for done-gate Check 9. Use whenever /assay executes a code change at or above the configured tdd.min_tier, when Brandon asks for TDD explicitly, or when a ticket names a testing seam. Reads tdd.min_tier from ~/.claude/assay.config.json. Does not apply to docs, config, or comment-only diffs.
---

# tdd-loop

An agent asked for a feature and a test writes the feature first, then writes
a test shaped to whatever it produced. Everything passes. The test asserts the
implementation rather than the requirement, and it will keep passing through
the exact regression it was supposed to catch.

The only reliable fix is order: **the test must be observed failing, for the
right reason, before the implementation exists.** A test that has never failed
has never been proven to test anything.

## Applicability

Read `tdd.min_tier` from `~/.claude/assay.config.json` (default `MEDIUM`).
Mandatory when the run's risk tier is at or above that floor. `NEVER` disables
enforcement entirely.

Exempt regardless of tier:

- Docs, comments, and config-only diffs.
- Pure renames and mechanical refactors with no behavior change — an existing
  test suite is the proof here, and it must be run.
- Deletions of dead code.

Not exempt: bug fixes. A bug fix is the strongest TDD case there is — the
failing test *is* the bug report, and without it nothing proves the bug is
gone rather than merely unobserved.

## The cycle

### 1. RED — write one failing test

Write **one** test for **one** behavior. From the ticket's `seam` field when a
ticket drives the run, otherwise from the spec's Testing seams table.

The test asserts the requirement in the requirement's own terms. Bad: asserting
that a helper was called. Good: asserting the observable outcome the acceptance
criterion names.

### 2. RED PROOF — run it and capture the failure

Run the test. It **must** fail. Capture the runner's actual output — command,
exit code, and the failure line — into the session state:

```json
"tdd": [
  {
    "behavior": "worker failure fails the run cleanly",
    "test": "engine/tests/test_walkforward.py::test_worker_failure_propagates",
    "red": {
      "command": "uv run pytest engine/tests/test_walkforward.py::test_worker_failure_propagates",
      "exit_code": 1,
      "reason": "AssertionError: expected RunFailed, got None"
    },
    "green": null
  }
]
```

**Inspect the failure reason before continuing.** A test that fails with
`ImportError`, `SyntaxError`, `fixture not found`, or a typo'd symbol has not
demonstrated anything about the behavior — it has demonstrated that the file
does not load. That is a **false red**. Fix the test until it fails on its
assertion, then re-capture.

The distinction is the whole check. A false red plus a later green proves only
that the import got fixed.

### 3. GREEN — the minimal implementation

Write the least code that makes that one test pass. Not the design you intend
to end at — the smallest thing that turns this test green. Extra code written
now is untested code, because the test that justified it does not exist yet.

Do not touch the test during this step. If the test looks wrong once
implementation starts, that is a real finding: stop, say so, and revise the
test deliberately with the red proof re-captured. Quietly adjusting an
assertion to match what the code does is the failure mode this skill exists to
prevent, and it is invisible in the final diff.

### 4. GREEN PROOF — run it, plus the feedback loops

Run: the test (must pass), the affected suite (no new failures), the linter,
and the type checker. Capture into the same state entry:

```json
"green": {
  "command": "uv run pytest engine/tests/test_walkforward.py",
  "exit_code": 0,
  "passed": 14,
  "lint": "clean",
  "types": "clean"
}
```

Lint and types belong in the green step, not at the end of the run. They are
feedback loops; running them per-cycle catches the error while the context that
caused it is still live.

### 5. REFACTOR — optional, tests stay green

Clean up with the tests running. Any red during refactor reverts the refactor,
never the test.

Then loop to the next behavior. **One behavior per cycle.** Batching three
tests before implementing collapses back into implement-then-test, because
nothing was observed failing in isolation.

## When the agent is stuck

If a cycle fails twice, the instinct is a longer prompt. That is the wrong
lever. **An agent's ceiling is the quality of the codebase's feedback loops.**
Before a third attempt, ask which loop is inadequate:

- Is the failure message specific enough to act on, or does it just say `False
  is not True`? Improve the assertion.
- Does the test take long enough that the loop is not being run? Find a
  narrower seam.
- Is there a seam at all, or is the behavior reachable only through six layers
  of setup? That is a design finding — surface it; it may be a `groundwork`
  ticket or an `/architecture` proposal.
- Do lint and types actually run on this path?

Log the answer as a lesson through project-memory. A feedback-loop gap found
during one ticket costs every future ticket in the same area.

## Escape hatches

- `--no-tdd` on `/assay` skips enforcement for that run. Logged like
  `--skip-tests`: to `state.json` and to the run record, so `/assay-stats` can
  show how often the discipline is actually bypassed.
- Setting `tdd.min_tier` to `NEVER` disables it globally. Also visible in the
  run record.

Neither is silent. A bypass nobody can count is a bypass that becomes the norm.

## Output

`state.json.tdd` — one entry per behavior, each with a red proof and a green
proof. done-gate Check 9 reads this array. An entry with `green: null` means an
abandoned cycle: report it, do not delete it.

## Integration

- **`/assay` Step 7 EXECUTE** — runs this loop per behavior when the tier
  requires it. Subagents doing implementation work receive the cycle as part of
  their delegation brief, and return the proofs in their artifact.
- **done-gate Check 9** — verifies every behavior has a real red before its
  green, and that no red is a false red.
- **`/to-tickets`** — supplies the `seam` the first test is written against.
- **judge-panel** — the Test Architect judge reads the red proofs, and is the
  backstop against a test that fails for the wrong reason but was recorded
  anyway.

## Hard constraints

- NEVER write implementation code before a captured, inspected red proof.
- NEVER accept an import, syntax, or fixture error as a red proof.
- NEVER edit a test during the green step. Revise deliberately, re-capture, or
  do not revise.
- NEVER batch behaviors. One test, one implementation, one cycle.
- NEVER fabricate a proof. The captured `command` and `exit_code` are real
  runner output or the entry does not exist.
