# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.2.0 — Discovery

Assay could execute an idea well and could not find one. Every stage was
downstream of a goal Brandon already had: `/spec` grills a goal, `/to-tickets`
cuts it, `/implement` works the board. Nothing asked what was worth doing.
`/architecture` was the one upstream capability, and it covered a single
dimension — module depth — behind a written "every few days" cadence that
nothing automated.

### Added

- **`/survey` + the `survey` skill.** Audits the repo across nine categories
  (correctness, security, performance, tests, tech debt, dependencies, DX,
  docs, direction) with parallel read-only `Explore` subagents, each carrying a
  Structured Delegation Brief and the playbook path. Recon ingests the
  glossary, ADRs, approved specs, the board, and the rejection ledger, so
  decided tradeoffs never come back as findings. Read-only on source, always.
- **Automatic triggers.** Branch-scoped at `/assay` Step 8.5 after the judges;
  hotspot-scoped at Step 12.5 post-ship on a cadence stamp; repo-scoped when
  `/implement` finds an empty board. Findings surface via a SessionStart banner
  and a `🔍 N` statusline segment. A survey you have to remember to run is a
  survey that stops running.
- **The vet pass in `judge-panel` (stage `VET`).** Judges over-report, so the
  lead now re-opens every cited `file:line` before a concern reaches Brandon or
  the revise loop: by-design concerns dropped, mis-attributed evidence
  corrected, cross-judge duplicates merged. Drops are counted per judge.
- **The rejection ledger in `project-memory`** (`rejected.md`). What was
  considered and declined, with the reason and the evidence ref. Read by survey
  recon and by the vet pass; re-opening requires new evidence. Without it, a
  cadence survey re-derives the same rejected finding every week until nobody
  reads the queue.
- **`/to-tickets reconcile`.** Verifies `done` against HEAD, flags stale
  `needs-qa` and crashed `in-progress`, re-slices or retires `blocked`, and
  drift-checks every `todo` against its `planned_at` SHA — re-verifying the work
  is still needed before refreshing it.
- **Executor-grade tickets.** MEDIUM+ and every `--parallel`-eligible ticket now
  carry `planned_at`, a Current state excerpt with an exemplar file, a verified
  Commands table, a drift check, and slice-specific STOP conditions. A worktree
  subagent has no session context and cannot ask a question.
- **`survey.*` config** — `auto` (`off`/`queue`/`promote`), `cadence_days`,
  `in_pipeline`, `max_promote_per_cycle`. Ships as `queue`.
- **Survey instrumentation.** New recordable stages `survey-branch`,
  `survey-cadence`, `judge-vet`; a `survey` funnel block on the run record; a
  `dropped` count per judge. `/assay-stats` reports the funnel's vet-survival
  and action rates, and each judge's drop rate.

### Changed

- The run recorder rejects a survey funnel that widens. Vetting removes
  findings and cannot add them, so a growing funnel is a miscount, not a
  discovery.
- `judge-panel` aggregation now operates on post-vet counts. `concerns` means
  what survived vetting; `dropped` carries the rest.
- Plugin manifest: 18 skills, 14 commands, 5 hooks.

### Notes

`survey.auto` ships as `queue` deliberately. Auto-promotion is the line between
the machine finding work and the machine choosing work; flip it only after
`/assay-stats` shows the funnel's precision is real. A board full of
machine-generated noise is not recoverable by improving the audit afterwards.

Design influence: [shadcn/improve](https://github.com/shadcn/improve) (MIT) —
the audit → vet → leverage-rank shape, the evidence requirement, the grounding
rule on direction findings, and the standard that work handed to a zero-context
executor must be self-contained.


## [Unreleased]

### Added
- **The lifecycle layer.** Four commands above `/assay`, splitting the work
  where it actually divides: `/spec` (grill), `/to-tickets` (vertical slices),
  `/implement` (batch execution), `/qa` (hands-on pass). `/assay` becomes the
  per-ticket executor and gains a ticket-id invocation form.
- **`tdd-loop` skill and done-gate Check 9.** A captured, inspected failing-test
  run is now required before any implementation edit at or above
  `tdd.min_tier`. Import and fixture errors are rejected as false reds.
- **`ticket-board` skill.** Vertical slices with a `blocked_by` DAG, validated
  acyclic before writing. Horizontal slice sets are rejected and re-sliced.
- **`qa-queue` skill.** Shipped slices land in `needs-qa`, which does not
  unblock dependents. Findings become tickets, never in-session fixes.
- **`context-glossary` skill and `/context`.** A `CONTEXT.md` glossary loaded on
  every `/assay` run, plus ADR capture.
- **`architecture-scan` skill and `/architecture`.** Deep-vs-shallow module scan
  with proposal-only output.
- **Per-install config** at `~/.claude/assay.config.json` (`scripts/assay_config.py`),
  covering ticket backend, glossary paths, TDD floor, and QA queueing.
- **Spec escalation gate** in `/assay` Step 1. A MEDIUM+ task with no
  observable outcome or nameable seam now recommends `/spec` first, defaulting
  to yes. Without it, done-gate Check 1 asks for success criteria after the
  work exists, and the TDD loop has to invent its own seam. `--no-spec`
  bypasses; both the escalation and the bypass are logged.
- `spec-escalation` and `tdd-loop` are recordable stages, so a gate that goes
  decorative shows up in `/assay-stats` as eligible-but-never-fired.
- `tests/test_config.py` and `tests/test_pipeline_wiring.py` — the latter fails
  the build on dangling cross-references and live delegations to uninstalled
  plugins.

### Changed
- `spec-builder` replaces its batch seven-question interrogation with a
  one-question-at-a-time grill (minimum 8, target 12-20), and the spec template
  gains Implementation choices and Testing seams.
- `judge-panel` judges now run as fresh-context subagents on built-in
  capability, and answer on two axes (standards and spec).
- `/assay` Step 3 enforces a vertical-slice constraint; Step 2 loads the
  glossary; Step 12 proposes new glossary terms.

### Removed
- All live delegation to uninstalled plugins: `superpowers:brainstorming`,
  `superpowers:writing-plans`, `superpowers:subagent-driven-development`,
  `ecc:prp-prd`, and the `pr-review-toolkit` / `ecc` judge reviewer agents.
  These were steps that silently did nothing.

## [0.1.1] - 2026-06-29

### Added
- Python test harness (`tests/`) validating the plugin's own structure: manifest
  integrity, skill/command frontmatter, judge-panel roster count, doc-link
  resolution, and hook executability.
- GitHub Actions CI (`.github/workflows/ci.yml`) running ruff + pytest on every
  push and pull request.
- `CONTRIBUTING.md` and this `CHANGELOG.md`.
- Architecture diagram and demo scaffold (`demo/`) in the README.
- YAML frontmatter for the `/eod`, `/morning`, and `/weekly` commands, matching
  the other commands.

### Fixed
- `plugin.json` description claimed 11 supporting skills; the repo ships 12. The
  manifest test now prevents this count from drifting again.

### Removed
- Placeholder `main.py` Hello-World stub left over from `uv init`.

### Changed
- `pyproject.toml` is now a real, described, virtual (non-package) project with a
  pinned dev-dependency group and ruff/pytest config.
- `.gitignore` now covers `.venv/` and Python tool caches.

## [0.1.0] - 2026-05-18

### Added
- Initial extraction of the `/assay` 14-step orchestrator and supporting skills
  from a personal Claude Code configuration into an installable plugin.
- 7 commands (`/assay`, `/spec`, `/postmortem`, `/morning`, `/eod`, `/weekly`,
  `/cross-learn`), 12 skills, and 3 proposal-surfacing hooks.

[Unreleased]: https://github.com/shadybad/assay/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/shadybad/assay/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/shadybad/assay/releases/tag/v0.1.0