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


def test_tier_header_counts_sum_to_expected():
    counts = re.findall(r"^### Tier \d+ .*\((\d+)\)", _text(), re.MULTILINE)
    assert counts, "no '### Tier N ... (count)' headers found"
    assert sum(int(c) for c in counts) == EXPECTED_JUDGES


def test_numbered_judge_entries_count():
    entries = re.findall(r"^\d+\.\s+\*\*", _text(), re.MULTILINE)
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


def _section(header: str) -> str:
    """Text from `header` up to the next same-or-higher-level heading."""
    text = _text()
    start = text.index(header)
    rest = text[start + len(header) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


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
