---
name: skill-curator
description: Reviews all installed skills weekly to detect duplicates, stale, broken, and low-quality skills. Proposes consolidations, archives, and new skills from observed multi-step task patterns. Never auto-installs or auto-modifies — all changes are proposals that Brandon reviews. Tracks skill invocation counts in skill-stats.json. Delegates skill validation to plugin-dev plugin's skill-reviewer and plugin-validator agents when available. Use when /curate is invoked manually, when 7+ days have passed since last curator run (checked at end of every /assay), when Brandon asks "what skills do I have" or "audit my skills", or after a task that took 5+ tool calls and produced a generalizable pattern (proposes a new skill draft). Pinned skills are protected: judge-panel, project-memory, session-recall, operator-model, skill-curator, done-gate, commit-protocol, notion-bridge, mcp-router, spec-builder, postmortem, ticket-board, tdd-loop, qa-queue, context-glossary, architecture-scan. Never archives or modifies pinned skills.
---

# Skill Curator: Weekly Self-Curation Loop

This is the self-learning keystone. The curator makes the system get more capable over time by detecting cruft, proposing consolidations, and capturing new patterns as draft skills.

## Core Principle: Propose, Never Execute

Every action the curator takes is a proposal. Brandon reviews and promotes. The curator NEVER:
- Auto-archives a skill.
- Auto-deletes a skill.
- Auto-modifies a skill's description or behavior.
- Auto-installs a proposed new skill.

The curator ALWAYS:
- Writes proposals to $HOME/.claude/skills/_proposed/.
- Generates reports to $HOME/.claude/memory/global/curator-report-<YYYY-MM-DD>.md.
- Surfaces proposals to Brandon for review.

## Pinned Skills (Off-Limits)

These are protected from all archive/modify proposals. They are the system's foundation.

- judge-panel
- project-memory
- session-recall
- operator-model
- skill-curator
- done-gate
- commit-protocol
- notion-bridge
- mcp-router
- spec-builder
- postmortem
- ticket-board
- tdd-loop
- qa-queue
- context-glossary
- architecture-scan

Proposals affecting these are silently dropped with a log entry. Brandon can modify these manually if needed.

This list is mirrored in `$HOME/.claude/CLAUDE.md` under `## Pinned Custom Skills` as a second source of truth. Keep them in sync.

## Skill Inventory Scope

The curator reviews skills in three locations:

1. $HOME/.claude/skills/<name>/SKILL.md — custom skills (this layer).
2. Plugin-shipped skills — discovered via `claude plugin list` and inspection of each plugin's skills/ directory.
3. $HOME/.claude/skills/_proposed/<name>/SKILL.md — pending proposals (curator-generated, awaiting Brandon review).

Plugin-shipped skills are inventoried but only flagged. The curator NEVER modifies plugin-shipped skills directly — those are upstream. Brandon disables them via `/plugin disable` if not needed.

## Detection Categories

### 1. Duplicates

Two skills are duplicate candidates when:
- Description fields overlap in trigger phrases (e.g., both fire on "create a chart").
- Trigger phrases overlap by 50%+ measured by keyword overlap.
- They cover the same domain (compared by category metadata if present, otherwise by description analysis).

Action: propose consolidation. Write a proposal to `_proposed/_consolidations/<date>-<topic>.md` describing the duplicate pair, the recommended merge (which to keep, which to archive, what changes the survivor needs), and the migration path for any references.

### 2. Stale

A skill is stale when:
- It has not been invoked in 60+ days (per skill-stats.json).
- AND it is not a recently installed skill (< 30 days old per skill file mtime).
- AND it is not pinned.

Action: propose archive. Write to `_proposed/_archives/<date>-<skill-name>.md` with usage history, last invocation date, and recommended action (archive vs delete vs leave-alone-but-flag).

**Scope of "invocation" in skill-stats.json.** The `skill-stats-tracker.js` PostToolUse hook only counts explicit `Skill` tool calls — i.e., times Claude chose to invoke the skill mid-conversation. SessionStart-loaded skills (`superpowers:using-superpowers`, `caveman:*`, anything auto-activated via hooks or system reminders) bypass the `Skill` tool path and are NOT counted. This is intentional: those are infrastructure, not "used" skills. Stale-detection therefore measures *deliberate Claude invocation*, which is the right usage signal. An empty `skill-stats.json` after a session means zero `Skill` tool calls occurred — not a broken hook.

### 3. Broken

A skill is broken when ANY of:
- YAML frontmatter does not parse.
- `name` field missing or does not match directory name.
- `description` field missing, empty, or over 1024 chars.
- References to files that do not exist.
- References to plugins that are not installed AND skill does not declare graceful degradation.

Action: propose fix. Write to `_proposed/_fixes/<date>-<skill-name>.md` with the specific brokenness and the minimum fix. Tag as urgent if the skill is invoked by other skills.

### 4. Low-Quality

A skill is low-quality when:
- Description is under 50 characters (likely too vague to trigger reliably).
- Description does not contain any trigger phrases (no "when", "use when", or imperative verbs).
- Description does not match observed invocations (per skill-stats.json: invoked rarely or invoked for wrong patterns).
- Skill has been invoked but its output was repeatedly corrected (signal from session-recall).

Action: propose rewrite of description. Write to `_proposed/_quality/<date>-<skill-name>.md` with the current description, observed invocation patterns, and a proposed rewrite.

## Skill Stats Tracking

The curator maintains `$HOME/.claude/memory/global/skill-stats.json`:

```json
{
  "<skill-name>": {
    "invocations": <count>,
    "last_invoked": "<ISO-timestamp>",
    "first_invoked": "<ISO-timestamp>",
    "corrections": <count>,
    "blocked_outputs": <count>,
    "user_overrides": <count>
  }
}
```

Stats update mechanism:
- Increment `invocations` and update `last_invoked` whenever a skill fires (via hook or end-of-task report).
- Increment `corrections` when Brandon corrects a skill's output in-session.
- Increment `blocked_outputs` when done-gate blocks a commit due to this skill's output.
- Increment `user_overrides` when Brandon overrides this skill's decision (e.g., /assay --no-judges after the skill said to invoke).

Stats are append-update only. Never decrement. Brandon can manually edit if needed.

## Self-Creation: Proposing New Skills

After any task that meets ALL of these conditions:

1. Used 5+ tool calls.
2. Produced a generalizable pattern (not project-specific implementation).
3. Brandon did not explicitly say "do not log this".
4. No existing skill covers this pattern (curator checks descriptions for overlap).

The curator proposes a new skill draft at `$HOME/.claude/skills/_proposed/<proposed-name>/SKILL.md`.

The proposal must include:
- Full YAML frontmatter (name, description).
- Skill body explaining when to use, what it does, hard constraints.
- A `_proposal_metadata.md` sibling file with: trigger task, lessons that motivated the proposal, expected invocation frequency, plugin dependencies, suggested location (custom skills vs plugin), Brandon-action options (promote / refine / reject).

The curator NEVER moves the proposal out of _proposed/ on its own. Brandon promotes by:
- Moving the directory: `mv $HOME/.claude/skills/_proposed/<name>/ $HOME/.claude/skills/<name>/`
- Or running `/curate promote <name>` (if Brandon has set up a slash command for this).

## Plugin-Dev Delegation

When `plugin-dev` plugin is installed, the curator delegates validation:

| Curator action | Delegate to |
|----------------|-------------|
| Validate proposed skill YAML and structure | plugin-dev: plugin-validator agent |
| Review proposed skill description for trigger quality | plugin-dev: skill-reviewer agent |
| Suggest skill structure for ambiguous patterns | plugin-dev: agent-creator agent |

If plugin-dev is missing, the curator does the validation inline with hardcoded rules. Performance is identical but feedback is less nuanced.

## Curator Report Format

After a run, the curator generates `$HOME/.claude/memory/global/curator-report-<YYYY-MM-DD>.md`:

```markdown
# Skill Curator Report: <date>

Run triggered by: <manual | scheduled | post-task>
Total skills inventoried: <count>
Custom skills: <count> | Plugin skills: <count>

## Summary
- Duplicates proposed: <count>
- Stale archives proposed: <count>
- Fixes proposed: <count>
- Quality rewrites proposed: <count>
- New skills proposed: <count>

## Action Required from Brandon
- [ ] Review duplicates: <list of proposal files>
- [ ] Review archives: <list>
- [ ] Apply fixes: <list>
- [ ] Approve rewrites: <list>
- [ ] Promote or reject new proposals: <list>
- [ ] Review regressions detected by Tool-Testing Proposal Flow: <list>

## Regressions Detected
- <skill>: trigger accuracy dropped <current_pass>/<total> → <proposed_pass>/<total>. Report: <path>. Brandon decision required.

## Top 5 Most-Invoked Skills (last 7 days)
1. <skill>: <count>
2. ...

## Bottom 5 Least-Invoked Skills (excluding new, last 30 days)
1. <skill>: <count> (last invoked: <date>)
2. ...

## Skills with Highest Correction Rate
1. <skill>: <correction count> / <invocation count>
...

## Pinned Skills Verified Healthy
- judge-panel: ✓
- project-memory: ✓
... (etc.)

## Notes
<any narrative observations>
```

## Tool-Testing Proposal Flow

Anthropic finding: dedicating an agent to test tool descriptions against synthetic invocations surfaced bugs and nuance that improved task completion time ~40% for downstream agents. The skill-curator inherits this pattern in proposal-only form — never auto-rewrites a skill description, only surfaces the data to Brandon.

Trigger: any time the curator generates a proposal (new skill, quality rewrite, broken-fix) that includes a `description:` field change.

Procedure:

1. **Generate synthetic invocations.** From the current/proposed description, derive 5–10 trigger phrases that should fire the skill. Source: the imperative verbs and "use when" clauses in the description. Example: a description containing "use when reviewing pull requests for security issues" generates `["review this PR for security", "check for OWASP issues", "audit auth code for vulnerabilities"]`.
2. **Score current description.** For each synthetic phrase, judge whether the current description would plausibly trigger the skill. Pass = the description's keywords/verbs match the phrase. Record pass count `current_pass / total`.
3. **Score proposed description.** Same scoring against the proposed description. Record `proposed_pass / total`.
4. **Generate distractor phrases.** Derive 3–5 phrases that should NOT fire the skill but are topically adjacent (e.g., for a security-PR-reviewer skill: "review my PR for typos", "check this commit message"). Score both descriptions against distractors — *low* match is the desired outcome (false-positive avoidance).
5. **Bug detection.** Flag any of:
   - Description trigger phrases that the description itself fails to match (self-inconsistency).
   - Description over 1024 chars (skill-stats hook + Claude Code limit).
   - Description without any imperative verb or "use when" clause (Anthropic-style: agents need explicit usage heuristics).
   - Description that overlaps >70% by keyword with another skill's description (duplicate risk — surface both).
6. **Report.** Append a `_test_report.md` sibling to the proposal:

   ```markdown
   # Tool-Testing Report: <skill-name>
   
   Generated: <ISO timestamp>
   Mode: <new-skill | quality-rewrite | broken-fix>
   
   ## Trigger accuracy
   - Current description: <current_pass>/<total> on trigger phrases, <distractor_pass>/<distractor_total> false-positives.
   - Proposed description: <proposed_pass>/<total> on trigger phrases, <distractor_pass>/<distractor_total> false-positives.
   - Delta: +<n> trigger / -<n> false-positive (positive = better).
   
   ## Bugs found
   - <bug 1>
   - <bug 2>
   
   ## Brandon decision
   - [ ] Adopt proposed
   - [ ] Keep current
   - [ ] Refine further (notes below)
   ```

Constraints:

- This flow NEVER edits the skill in place. Proposal + report only.
- Synthetic phrases are derived from the description itself; the scorer is therefore partially self-referential — a description that is internally consistent but wrong about real triggers will pass. Brandon's review is the second check; the score is one input, not a verdict.
- If `plugin-dev:skill-reviewer` agent is installed, delegate scoring to it — stronger heuristics than the curator's inline scorer. If skill-reviewer errors or times out, fall back to inline scoring and annotate the report with `scorer: inline (skill-reviewer unavailable)`.
- A proposal where `proposed_pass < current_pass` AND distractor accuracy did not improve is flagged as a regression. Flag is surfaced inline to Brandon at proposal-generation time (not just in the background curator report) AND noted in the curator report's "Regressions Detected" section.

Run cadence: every time a description proposal is generated. Not a standalone weekly pass — it piggybacks on existing proposal triggers.

Limitation acknowledged: this flow does NOT routinely test installed pinned skills (judge-panel, done-gate, etc.) because those generate no proposals. To audit a pinned skill's trigger accuracy, Brandon manually invokes `/curate test <skill-name>` (slash command to be defined separately).

## Postmortem Skip Analytics

The curator reads `$HOME/.claude/memory/global/postmortem-skipped-log.md` on every full run. Format per line: `<ISO-timestamp> | <failure_step> | <reason>`. The file is append-only and written by the `postmortem` skill when Brandon explicitly skips a postmortem.

For each curator pass:

1. **Read the log** — load all entries from the last 14 days. If file is missing, treat as empty (not an error).
2. **Count by failure step** — bucket entries by their `failure_step` field (PLAN, EXECUTE, JUDGE, REVISE, DONE_GATE, COMMIT, or user-stopped).
3. **Threshold check** — if total skips ≥ 3 in the 14-day window, flag in the curator report under a new section:

   ```
   ## Postmortem Skip Rate Elevated
   Window: last 14 days
   Total skips: <count>
   By failure step:
     - JUDGE: <count>
     - DONE_GATE: <count>
     - (etc.)
   Recent skip reasons: <up to 5 most recent reason strings>
   Possible causes (Brandon picks):
     - Postmortem prompts too long → consider tuning postmortem skill's auto-mode flow.
     - Root-cause questions too vague → consider tightening question 1/2 wording.
     - Postmortem feels redundant for a specific failure_step → consider auto-skipping that step.
     - Brandon hasn't seen value yet → consider surfacing a sample report.
   ```

4. **Per-step pattern detection** — if a single failure_step accounts for 3+ skips, propose a postmortem skill description tweak to lower friction for that step (e.g., skip the routing menu for JUDGE blocks since judge feedback is already structured). Proposal goes to `_proposed/_quality/<date>-postmortem-skip-pattern.md`.
5. **No data, no flag** — if total skips < 3, do not include this section in the report. Avoids noise during low-volume periods.

The skip log itself is never modified by the curator. Read-only.

## Run Triggers

The curator runs in these scenarios:

1. **Manual** — Brandon runs `/curate` (slash command defined separately).
2. **Scheduled** — At end of every `/assay`, check `$HOME/.claude/memory/global/last-curator-run.txt`. If 7+ days have passed (or file does not exist), trigger a background curator pass after the ship completes.
3. **Post-task proposal** — After any task meeting the self-creation criteria above, run only the propose-new-skill flow (not full audit).

`last-curator-run.txt` contains a single ISO timestamp updated at the end of each full run.

## Invocation Contract

Modes:

- `full` — runs all detection categories. Writes full report. Default when triggered by /curate or schedule.
- `propose` — runs only the self-creation flow. Triggered post-task.
- `stats_update` — updates skill-stats.json. Triggered on every skill invocation (lightweight, no analysis).
- `quick_check` — checks only for broken skills. Fast. Triggered at session start.

## Integration with Other Skills

- **session-recall** — curator queries past sessions to verify a proposed new skill's pattern is genuinely recurring.
- **project-memory** — curator scans lessons.md across projects to find patterns that should become skills (3+ similar lessons across projects = candidate skill).
- **operator-model** — curator updates Brandon's preferences when patterns indicate (e.g., "Brandon dismissed accessibility nits 5 times → update operator-model under Things Brandon Hates: low-stakes accessibility nags").
- **judge-panel** — curator tracks judge dismissal patterns and proposes weight adjustments.

## Plugin Compatibility

Required: none. Curator runs with pure filesystem + skill-stats.json.
Enhanced by:
- `plugin-dev` (validator/reviewer/agent-creator agents).
- `claude-md-management` (cross-references project CLAUDE.md files for project-specific skill candidates).
- ripgrep (fast skill content search).

## Hard Constraints

- NEVER auto-install a proposal. Proposals stay in _proposed/ until Brandon promotes.
- NEVER archive, delete, or modify a pinned skill. Pinned list is hardcoded above.
- NEVER modify plugin-shipped skills. Those are upstream.
- NEVER run full audit more than once per 7 days unless Brandon explicitly invokes /curate.
- ALWAYS write the curator report, even if no actions are needed (negative result is informative).
- ALWAYS preserve skill-stats.json's history. Append-update only.
- ALWAYS validate _proposed/ proposals against plugin-dev's plugin-validator before surfacing if the plugin is installed.

## Failure Modes

- skill-stats.json missing or corrupt → recreate as `{}`. Log warning. Continue.
- plugin-dev missing → use inline hardcoded validation rules. Note degradation in report.
- _proposed/ directory missing → create it. Continue.
- Curator report write fails → retry once, then log error and surface to Brandon. Do not silently swallow.
