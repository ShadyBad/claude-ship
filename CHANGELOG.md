# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
