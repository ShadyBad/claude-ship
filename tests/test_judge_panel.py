"""Validate judge-panel roster integrity: the '29 judges' claim must hold."""

from __future__ import annotations

import re

from conftest import SKILLS_DIR, parse_frontmatter

JUDGE_PANEL = SKILLS_DIR / "judge-panel" / "SKILL.md"
EXPECTED_JUDGES = 29
# The Agent tool's `model` aliases — the values dispatch actually accepts.
MODELS = ("opus", "sonnet", "haiku")


def _text() -> str:
    return JUDGE_PANEL.read_text()


def _section(header: str) -> str:
    """Text from `header` up to the next same-or-higher-level heading."""
    text = _text()
    start = text.index(header)
    rest = text[start + len(header) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def test_tier_header_counts_sum_to_expected():
    counts = re.findall(r"^### Tier \d+ .*\((\d+)\)", _text(), re.MULTILINE)
    assert counts, "no '### Tier N ... (count)' headers found"
    assert sum(int(c) for c in counts) == EXPECTED_JUDGES


def test_numbered_judge_entries_count():
    # Scoped to the roster: numbered bold entries elsewhere (the aggregation
    # rules, for one) are not judges and must not inflate the count.
    entries = re.findall(r"^\d+\.\s+\*\*", _section("## Judge Roster"), re.MULTILINE)
    assert len(entries) == EXPECTED_JUDGES, f"found {len(entries)} numbered judges"


def test_description_claims_expected_count():
    fm = parse_frontmatter(_text())
    assert re.search(rf"\b{EXPECTED_JUDGES}\b", fm["description"]), (
        f"description should state {EXPECTED_JUDGES} as a standalone number"
    )


def _model_assignment_section() -> str:
    """The text between '## Per-Judge Model Assignment' and the next '## ' header."""
    text = _text()
    start = text.index("## Per-Judge Model Assignment")
    rest = text[start + 1 :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def test_model_assignment_covers_all_tiers():
    section = _model_assignment_section()
    missing = [m for m in MODELS if f"**{m}**" not in section]
    assert not missing, f"models absent from model-assignment section: {missing}"


def test_model_assignment_uses_aliases_not_versioned_ids():
    """A pinned model ID is rejected by the Agent tool's `model` param and rots."""
    # Both ID shapes Anthropic has shipped: name-then-version (claude-opus-4-8)
    # and version-then-name (claude-3-5-sonnet-20241022).
    stale = re.findall(r"claude-(?:[a-z]+-[\d.]|\d[\d.-]*-[a-z])[\w.-]*", _text())
    assert not stale, f"versioned model IDs in judge-panel: {sorted(set(stale))}"


def _judge_numbers(blob: str) -> set[int]:
    """Every judge number named in a blob, ignoring markdown list numbering."""
    return {int(n) for n in re.findall(r"\b(\d{1,2})\b", blob) if 1 <= int(n) <= EXPECTED_JUDGES}


def test_every_judge_has_a_selection_path():
    """A judge no selection rule can reach is roster decoration, not review.

    The pre-pass intersects detected tags with the tier template, so a Tier 1 or
    Tier 2 judge absent from the tag map, the always-on list, and the gating
    floor can never fire. Tier 3 is exempt from the tag intersection and is
    reached only through the CRITICAL change-type map. Union the four and every
    judge on the roster must appear.
    """
    reachable = _judge_numbers(_section("## Concern-Detection Pre-Pass")) | _judge_numbers(
        _section("### CRITICAL")
    )
    orphans = sorted(set(range(1, EXPECTED_JUDGES + 1)) - reachable)
    assert not orphans, f"judges with no selection path: {orphans}"


def test_dispatch_table_routes_every_judge_through_a_subagent():
    """A judge routed through the `Skill` tool runs in the lead's context.

    That is the lead reviewing the diff it just wrote, which the fresh-context
    Hard Constraint forbids. Every row of the dispatch table must name the
    subagent type explicitly \u2014 matching the bare word "subagent" would also
    accept a row reading "not a subagent".
    """
    table = _section("## Judge Dispatch")
    rows = [
        r
        for r in re.findall(r"^\|(?!\s*Judge\s*\|)(?!-).*\|$", table, re.MULTILINE)
        if "---" not in r
    ]
    assert rows, "no dispatch table rows found"
    bad = [r for r in rows if "`general-purpose` subagent" not in r]
    assert not bad, f"dispatch rows not routed through a general-purpose subagent: {bad}"


def test_no_plugin_is_named_as_a_dependency():
    """Zero plugins are installed, so ANY plugin dependency here is a dead path.

    Naming specific uninstalled plugins would pass vacuously for every plugin
    not on the list. The real rule is categorical: this skill may not depend on
    a plugin at all.
    """
    named = re.findall(r"`([a-z][\w:-]*)` plugin|\b([a-z][\w-]*) plugin's", _text())
    hits = sorted({a or b for a, b in named})
    assert not hits, f"judge-panel names plugin dependencies: {hits}"


def test_mandatory_judge_cannot_ride_unreachable_to_ship():
    """A mandatory judge that never ran is indistinguishable from one skipped.

    The protocol records a failed judge as `unreachable`; if the aggregation
    rules never mention that state, a silently dead Security judge rides an
    otherwise-clean panel to `ship` while still meeting quorum.
    """
    rules = _section("## Aggregation Rules")
    assert "unreachable" in rules, "aggregation rules never handle an unreachable judge"

    constraints = _section("## Hard Constraints")
    assert "unreachable" in constraints, "no Hard Constraint covers an unreachable judge"
    assert "time out" not in constraints and "timeout" not in constraints, (
        "Hard Constraints still use the removed timeout vocabulary"
    )


def test_security_judge_floor_is_not_tier_conditional():
    """Security must fire on a security-tagged diff at ANY tier.

    The Hard Constraint forbids skipping Security for auth/secrets/user-data/
    financial changes "regardless of tier", but the pre-pass intersects tags
    with the tier template -- and no MEDIUM template row lists judge 2 except
    "New endpoint". Without an any-tier floor, a MEDIUM business-logic diff
    touching auth silently loses its security review.
    """
    floor = _section("## Concern-Detection Pre-Pass")
    marker = floor[floor.index("Gating floor") :]
    assert "Any tier" in marker, "gating floor states no any-tier rule for Security"


def test_hard_constraints_name_every_mandatory_judge():
    """Aggregation rule 0's mandatory set must not outrun the Hard Constraints."""
    constraints = _section("## Hard Constraints")
    for judge in ("Security", "Karpathy", "Failure Mode Analyst", "Threat Modeler"):
        assert judge in constraints, f"no Hard Constraint covers mandatory judge {judge}"


def test_output_block_reports_unreachable_judges():
    """A constraint that mandates naming a failure needs a field to name it in."""
    fmt = _text()[_text().index("Output format to Brandon") :][:900]
    assert "Unreachable judges:" in fmt, "output block has no unreachable-judges field"
    assert "All judges approved." not in fmt, (
        "SHIP banner still claims all judges approved without qualifying dispatch"
    )


def test_prepass_failure_assumes_every_tag_present():
    """A missing tag set is not evidence of a missing concern.

    Every floor above is tag-conditional, so falling back to the tag-free tier
    template would delete each guarantee at exactly the moment the detector
    broke.
    """
    prepass = _section("## Concern-Detection Pre-Pass")
    fallback = prepass[prepass.index("If the pre-pass itself fails") :]
    assert "every tag as present" in fallback, "pre-pass failure does not assume all tags"


def test_security_survives_every_override_path():
    """TRIVIAL and --no-judges both return a verdict without dispatching judges.

    The Hard Constraint says Security is never skipped "regardless of tier or
    override", so each bypass must name the exception explicitly.
    """
    assert "2 Security fires anyway" in _section("### TRIVIAL"), (
        "TRIVIAL branch does not exempt Security"
    )
    overrides = _section("## Override Flags")
    assert "not overridable" in overrides, "--no-judges does not exempt Security"


def test_threat_modeler_tag_set_is_stated_consistently():
    """Rule 0, the tag row, and the Hard Constraint must name the same tags."""
    expected = {"auth", "secrets", "user-input", "pii"}

    def tags(blob: str) -> set[str]:
        return {tag for tag in expected if tag in blob}

    # Slice to the end of rule 0's list item rather than a character count, so
    # the test does not silently clip when the rule is reworded.
    rules = _section("## Aggregation Rules")
    rule0 = re.search(r"18 Threat Modeler.*?(?=\n\d+\.\s)", rules, re.S)
    assert rule0, "rule 0 does not mention the Threat Modeler"
    rule0 = rule0.group(0)
    constraint = [
        line for line in _section("## Hard Constraints").splitlines() if "Threat Modeler" in line
    ]
    assert constraint, "no Hard Constraint names the Threat Modeler"
    assert tags(rule0) == expected, f"rule 0 tag set differs: {tags(rule0)}"
    assert tags(constraint[0]) == expected, f"constraint tag set differs: {tags(constraint[0])}"
    # `financial` is judge 20's concern. It may appear here only to be excluded.
    assert "financial" not in rule0 or "not `financial`" in rule0, (
        "rule 0 appears to grant judge 18 the `financial` tag"
    )


def test_judge_numbers_are_contiguous_and_unique():
    """A duplicated or skipped number silently drops a judge from every map."""
    numbers = [int(n) for n in re.findall(r"^(\d+)\.\s+\*\*", _section("## Judge Roster"), re.M)]
    assert numbers == list(range(1, EXPECTED_JUDGES + 1)), f"roster numbering broken: {numbers}"


def test_every_judge_has_exactly_one_model():
    """Two model rows claiming the same judge makes dispatch ambiguous."""
    section = _model_assignment_section()
    seen: dict[int, str] = {}
    dupes = []
    for model in MODELS:
        row = re.search(rf"\*\*{model}\*\*[^|]*\|([^|]*)\|", section)
        assert row, f"no table row for model {model}"
        cell = row.group(1)
        # "all Tier 3 (22-29)" is a range, and the literal "3" in "Tier 3" is a
        # tier label, not judge 3 -- consume the phrase before counting numbers.
        nums: set[int] = set()
        span = re.search(r"all Tier 3 \((\d+)[\u2013-](\d+)\)", cell)
        if span:
            nums |= set(range(int(span.group(1)), int(span.group(2)) + 1))
            cell = cell[: span.start()] + cell[span.end() :]
        nums |= {
            int(n) for n in re.findall(r"\b(\d{1,2})\b", cell) if 1 <= int(n) <= EXPECTED_JUDGES
        }
        for n in nums:
            if n in seen:
                dupes.append((n, seen[n], model))
            seen[n] = model
    assert not dupes, f"judges assigned to more than one model: {dupes}"
    missing = sorted(set(range(1, EXPECTED_JUDGES + 1)) - set(seen))
    assert not missing, f"judges with no model assignment: {missing}"


def test_every_judge_carries_an_operative_rubric():
    """A one-line persona is not a rubric.

    Dispatch hands each judge its roster entry verbatim, so an entry that only
    names a domain ("code quality, maintainability") gives a fresh subagent
    nothing to apply and it returns generic prose. Every entry must say what to
    look for concretely.
    """
    roster = _section("## Judge Roster")
    entries = re.findall(
        r"^\d+\.\s+\*\*(.+?)\*\*(?:\s*\([^)]*\))?\s*—\s*(.+?)(?=\n\d+\.|\n###|\n##|\Z)",
        roster,
        re.S | re.M,
    )
    assert len(entries) == EXPECTED_JUDGES, f"parsed {len(entries)} entries"
    # A domain label alone ("code quality, maintainability, abstraction level")
    # runs ~50 chars; a rubric naming two concrete things to look for runs well
    # past 120. The cutoff separates those two shapes, not good prose from bad.
    min_rubric_chars = 120
    thin = [n for n, body in entries if len(" ".join(body.split())) < min_rubric_chars]
    assert not thin, f"judges with no operative rubric: {thin}"


def test_tier_three_judges_are_named_for_their_question():
    """A prompt that says only "be Bezos" returns generic prose in a famous name.

    The named operator is cited as the source of the lens; the judge's own name
    must be the question it asks, so the rubric is what gets applied.
    """
    tier3 = _section("### Tier 3")
    names = re.findall(r"^\d+\.\s+\*\*(.+?)\*\*", tier3, re.M)
    assert len(names) == 8, f"expected 8 Tier 3 judges, found {len(names)}"
    surnames = {"Hormozi", "Naval", "Bezos", "Buffett", "Munger", "Thiel", "Graham", "Ive"}
    bare = [n for n in names if n in surnames]
    assert not bare, f"Tier 3 judges named only for a person: {bare}"


def test_orchestrator_never_short_circuits_the_panel():
    """A caller that skips the skill revokes every guarantee the skill makes.

    judge-panel's absolute exceptions -- Security on a security-tagged diff at
    any tier, under any override -- can only run if the skill is invoked at all.
    /assay Step 8 previously skipped it outright at TRIVIAL and under
    --no-judges, so hardening the callee alone changed nothing on those paths.
    """
    assay = (SKILLS_DIR.parent / "commands" / "assay.md").read_text()
    step8 = assay[assay.index("### Step 8: JUDGE PANEL") : assay.index("### Step 8.5")]
    assert "Always invoke the skill" in step8, "Step 8 does not mandate invoking judge-panel"

    constraints = assay[assay.index("## Hard Constraints") :]
    assert "NEVER skip invoking judge-panel at all" in constraints, (
        "no Hard Constraint stops the orchestrator short-circuiting the panel"
    )


def test_orchestrator_unreachable_judge_defers_to_rule_zero():
    """assay.md's failure table must not contradict Aggregation rule 0."""
    assay = (SKILLS_DIR.parent / "commands" / "assay.md").read_text()
    row = [ln for ln in assay.splitlines() if "| 8 JUDGE |" in ln]
    assert row, "no Step 8 row in the failure-mode table"
    assert "rule 0" in row[0], "unreachable-judge row does not defer to Aggregation rule 0"
