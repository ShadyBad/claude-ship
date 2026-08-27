---
name: done-gate
description: Enforces the completion contract from CLAUDE.md before any commit can proceed. Checks success criteria, tests, lint, type check, no TODO/debug leftovers, a captured red-before-green TDD proof, judge-panel verdict, and Brandon's commit approval. If any check fails, blocks the commit with the specific failure and the minimum fix. Use at the end of every /assay before invoking commit-protocol, when Brandon asks "is this ready to commit", or when any agent attempts to commit code. Nine checks total, all must pass.
---

# Done Gate Skill

Enforces the completion contract from CLAUDE.md. This is the last line of defense before any commit. If a check fails, the gate blocks and explains exactly what failed and the minimum fix.

## The Nine Checks

The completion contract from CLAUDE.md, enforced as 9 sequential checks. ALL must pass.

### Check 1: Success Criteria

- Task has stated success criteria, in plain language.
- Success criteria are measurable (testable, observable, or decidable by inspection).

This check operationalizes "end-state evaluation" — the appendix recommendation from Anthropic's multi-agent research post: judge whether the final state is correct rather than whether intermediate steps matched a prescribed path. /assay runs are allowed many valid execution paths; Check 1 is the contract that the outcome lands.

**Spec-driven path.** If the /assay run was invoked with a spec-id (state.json has a `spec-snapshot` reference), Check 1 reads the Success criteria section from the snapshot at `$HOME/.claude/memory/sessions/<YYYY-MM-DD>-<session-id>/spec-snapshot.md`:

1. Parse each bullet under the `## Success criteria` heading.
2. For each bullet, show Brandon the criterion and ask: "Met? (yes/no/partial/skip-with-reason)".
3. All bullets must be `yes` or `partial` (with note) for Check 1 to pass.
4. Any `no` or unjustified `skip-with-reason` blocks the gate.
5. Log the bullet-by-bullet verdict to `state.json` under `success-criteria-verdict` for the session record.

Fail mode (spec-driven): "Spec `<spec-id>` success criteria not met:
- [no] <bullet>
- [skipped without reason] <bullet>
Address before commit, or invoke `/spec revise <spec-id>` to update the criteria first."

**Task-only path.** If no spec snapshot present, fall back to the original behavior: confirm criteria are stated and measurable based on the task description.

Fail mode (task-only): "No measurable success criteria stated. Cannot verify completion. State criteria, e.g., 'X function returns Y for input Z' or 'page renders without errors at /path'."

### Check 2: Tests

- Tests exist for the changed code, OR
- A written note explains why tests were skipped AND Brandon has acknowledged.

Fail mode: "No tests for the changed code, and no skip-note. Either write tests or add a note like `// SKIP-TESTS: <reason>` and confirm with Brandon."

### Check 3: Tests Pass

- All tests in the affected scope pass when run.
- If using pytest: `pytest <path>` exits 0.
- If using other framework: equivalent green status.

Fail mode: "Test suite failing. Failing tests: <list>. Fix or update tests before commit."

### Check 4: No Leftover Debug Code

Scan the diff for:
- `print(` statements that look like debug output (not legitimate output).
- `console.log(` for JS files.
- `pdb.set_trace()`, `breakpoint()`, `debugger;`.
- Commented-out code blocks (3+ consecutive lines starting with `#` or `//` that look like code).
- TODO comments without a tracking issue ID (Linear or GitHub issue number).

Fail mode: "Debug code or untracked TODOs found:
- <file>:<line>: <content>
Remove before commit, or for TODOs add issue ID."

### Check 5: Lint Passes

For the changed files, run the project's linter:
- Python: `ruff check <files>` or `pylint <files>` (whichever is configured).
- JS/TS: `eslint <files>`.
- Markdown: `markdownlint <files>` if configured.

Fail mode: "Lint errors:
<file>:<line>: <error>
Fix before commit. Run `<lint command>` to verify."

### Check 6: Type Check Passes

For Python files in the diff, invoke pyright-lsp plugin's type checking:

If pyright-lsp plugin is installed:
- Use its checking interface to validate the changed files.

If pyright-lsp not available:
- Fallback: `pyright <files>` or `mypy <files>` if installed.
- If no type checker available: skip check, note in report.

Fail mode: "Type errors:
<file>:<line>: <error>
Fix before commit."

### Check 7: Judge Panel Verdict

- Judge panel has reviewed the diff at the appropriate risk tier.
- Verdict is `ship` (or `revise` with all `must_address_before_ship` items resolved).
- Verdict is NOT `block`.

Fail mode: "Judge panel verdict: <block | revise with unresolved items>.
Blocking concerns:
- <judge>: <concern>
Address before commit, or override with `/assay --no-judges` (requires Brandon explicit override)."

### Check 9: Red Before Green

Applies when the run's risk tier is at or above `tdd.min_tier` in
`~/.claude/assay.config.json` (default `MEDIUM`), and the diff is not
docs-only, config-only, comment-only, a pure rename, or a deletion.

Read `state.json.tdd`. For every behavior in the diff:

1. An entry exists.
2. The entry has a `red` proof with a non-zero exit code.
3. The red's `reason` is an **assertion failure**, not an `ImportError`,
   `SyntaxError`, `fixture not found`, `NameError`, or collection error. Those
   are false reds — they prove the file did not load, not that the behavior was
   absent.
4. The entry has a `green` proof with exit code 0, plus clean lint and types.
5. No entry has `green: null` without an explanation.

This is the check that makes test-first real. Without it, "tests exist and
pass" (Checks 2 and 3) is satisfiable by writing the implementation first and
then writing a test shaped to agree with it — which asserts the implementation
rather than the requirement, and will keep passing straight through the
regression it was meant to catch.

Fail mode: "TDD proof missing or invalid:
- <behavior>: no red proof captured
- <behavior>: red was `ImportError: cannot import name 'Pool'` — a false red;
  the test never exercised the behavior
Re-run the cycle for these behaviors, or bypass with `/assay --no-tdd` (logged
to the run record)."

Bypassed by `--no-tdd` and by `tdd.min_tier: NEVER`. Both are logged to
`state.json` and to the Step 14b run record — a bypass nobody can count becomes
the norm.

### Check 8: Brandon Approval

- commit-protocol skill has shown Brandon a brief commit overview.
- Brandon has typed "ship" or "y" or equivalent explicit approval.

Fail mode: "Awaiting Brandon's approval. Showing commit overview now."

## Check Sequence

Run checks 1-7 and 9 in order — 9 runs after 7, immediately before the approval flow. If any fail, STOP and surface the failure. Do not run later checks.

Check 8 is the final step: only after the others pass does the gate hand off to commit-protocol for the approval flow. It is numbered 8 because Brandon's approval has always been the last thing that happens, and the completion contract in CLAUDE.md refers to it by that number.

## Output Format

If all 9 pass:
DONE GATE: ALL CHECKS PASSED ✓

Criteria: stated and measurable
Tests: <count> pass, 0 fail
Debug code: none
Lint: clean
Type check: clean (<N> files)
Judge panel: <verdict> (<tier>)
TDD: <N> behaviors, each red-then-green
Approval: received from Brandon

Ready to commit.

If any fail:
DONE GATE: BLOCKED at Check <N> — <Check Name>
<Specific failure details>
Minimum fix:
<Concrete steps>
To proceed:

Apply the fix
Re-run /assay to re-verify, OR run /done-gate to re-check just this gate


## Hookify Integration

When `hookify` plugin is installed, done-gate registers hooks for deterministic enforcement OUTSIDE the /assay pipeline:

- **PreToolUse** hook on `bash` calls matching `git commit*` — runs done-gate quick check before any git commit shell command.
- **PreToolUse** hook on Edit/Write tools targeting protected paths — blocks edits to operator-model.md, judge-panel/SKILL.md without explicit Brandon override.

These hooks fire even when /assay is not in use. Brandon cannot bypass with raw bash unless he explicitly disables hookify rules.

Hook configuration lives at `$HOME/.claude/hooks/done-gate-rules.md` (managed by hookify plugin).

## Override Flags

For when Brandon needs to bypass specific checks (rare, high-trust situations):

- `/assay --skip-tests "<task>"` — bypasses Check 2/3. Requires note explaining why.
- `/assay --skip-lint "<task>"` — bypasses Check 5. Rare.
- `/assay --skip-types "<task>"` — bypasses Check 6.
- `/assay --no-judges "<task>"` — bypasses Check 7 (only for TRIVIAL/LOW changes; HIGH/CRITICAL still enforces).
- `/assay --no-tdd "<task>"` — bypasses Check 9. Logged to the run record alongside the tier, so the bypass rate is measurable.
- `/assay --force "<task>"` — bypasses ALL checks except 8 (Brandon approval). Logged loudly. Used for emergency hotfixes only.

`--force` bypass is logged to `$HOME/.claude/memory/global/force-bypass-log.md` with timestamp, project, task, and reason. Reviewed by skill-curator weekly.

## Risk-Tier Adjustments

Some checks are skipped automatically by risk tier (matching CLAUDE.md's risk tier guidance):

- TRIVIAL: only Checks 4, 5, 8 (debug code, lint, approval). Skip tests, types, judges, TDD.
- LOW: Checks 1, 4, 5, 6, 7, 8. Skip test requirement if change is comment-only. TDD not enforced at the default floor.
- MEDIUM: all 9 checks.
- HIGH: all 9 checks + enforce that judge-panel result is signed (verdict logged with judge list).
- CRITICAL: all 9 checks + require commit-protocol to show Brandon the full judge panel report before approval.

Check 9's floor is configurable independently of these: `tdd.min_tier` moves it up or down, or `NEVER` removes it.

## Integration with Other Skills

- **/assay** — invokes done-gate after judge-panel returns, before commit-protocol.
- **judge-panel** — feeds verdict into Check 7. Its Test Architect judge is the backstop for a red proof that was captured but is weak.
- **tdd-loop** — writes `state.json.tdd`, which Check 9 reads.
- **commit-protocol** — receives handoff after Check 7 passes; manages Check 8.
- **hookify** — provides deterministic enforcement at the hook layer.
- **skill-curator** — reviews force-bypass-log weekly; if same kind of bypass repeats 3+ times, proposes adjustment.

## Plugin Compatibility

Enhanced by:
- `pyright-lsp` — type checking for Python (Check 6).
- `hookify` — hook-layer enforcement.
- `commit-commands` — used by commit-protocol downstream.

Required: none. Without pyright-lsp, Check 6 falls back to system pyright/mypy or skips.

## Hard Constraints

- NEVER allow a commit to proceed if any of Checks 1-7 or 9 fail without explicit Brandon override.
- NEVER accept a red proof whose failure is an import, syntax, fixture, or collection error. That is a false red and Check 9 must fail on it.
- NEVER skip Check 7 (judge-panel) for HIGH or CRITICAL changes, even with --no-judges flag.
- NEVER skip Check 8 (Brandon approval). The engineer-in-the-loop pattern is non-negotiable.
- NEVER silently bypass checks. Every skip is logged.
- ALWAYS show the exact check that failed and the minimum fix.
- ALWAYS run checks in order; do not parallelize. The order matters because later checks depend on earlier ones (e.g., judges need tests to have run).
