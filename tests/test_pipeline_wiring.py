"""Guard the cross-references that hold the pipeline together.

Assay is markdown that instructs a model, so its "compile errors" are dangling
references: a command naming a skill that does not exist, a step citing a
done-gate check that was renumbered, or a delegation to a plugin that is no
longer installed. None of those fail at runtime — they quietly degrade into the
model improvising. These tests fail the build instead.
"""

from __future__ import annotations

import re

import pytest
from conftest import COMMANDS_DIR, ROOT, command_files, parse_frontmatter, skill_dirs

# Plugins that were uninstalled. A surviving delegation to one of these is a
# step that silently does nothing.
DEAD_PLUGINS = (
    "superpowers:",
    "pr-review-toolkit:",
    "ecc:prp-prd",
    "ecc:security-reviewer",
    "ecc:vulnerability-scanner",
    "ecc:threat-modeler",
)

# Commands allowed to still name a dead plugin, and why.
DEAD_PLUGIN_ALLOWLIST = {
    # The changelog records that the wiring was removed.
    "CHANGELOG.md",
}

LIFECYCLE = ["spec", "to-tickets", "implement", "qa"]


def _skill_names() -> set[str]:
    return {d.name for d in skill_dirs()}


def _command_names() -> set[str]:
    return {p.stem for p in command_files()}


@pytest.mark.parametrize("name", LIFECYCLE)
def test_lifecycle_command_exists(name):
    """The Grill -> Slice -> Implement -> QA loop must be complete."""
    assert (COMMANDS_DIR / f"{name}.md").is_file(), f"/{name} is missing"


@pytest.mark.parametrize(
    "skill",
    [
        "spec-builder",
        "ticket-board",
        "tdd-loop",
        "qa-queue",
        "context-glossary",
        "architecture-scan",
        "judge-panel",
        "done-gate",
        "commit-protocol",
    ],
)
def test_pipeline_skill_exists(skill):
    assert skill in _skill_names(), f"{skill} skill is missing"


@pytest.mark.parametrize(
    "doc",
    sorted(
        [*command_files(), *(d / "SKILL.md" for d in skill_dirs())],
        key=str,
    ),
    ids=lambda p: p.name if p.name != "SKILL.md" else p.parent.name,
)
def test_no_live_reference_to_uninstalled_plugin(doc):
    """A delegation to a removed plugin is a step that does nothing.

    Only *instructions* count. Prose that records the removal, or that names a
    dead plugin as an example of something the system does not do, is fine — a
    line telling the model to invoke one is not.
    """
    invocation = re.compile(
        r"\b(invoke|delegate|delegates|delegating|dispatch|call|calls|run|"
        r"fall back to|hand off to)\b",
        re.I,
    )
    exonerating = re.compile(r"previously|no longer|uninstalled|removed|is gone|not counted", re.I)
    offenders = []
    for line in doc.read_text().splitlines():
        if not any(p in line for p in DEAD_PLUGINS):
            continue
        if exonerating.search(line) or not invocation.search(line):
            continue
        offenders.append(line.strip())
    assert not offenders, f"{doc}: live reference to a removed plugin: {offenders}"


def test_done_gate_documents_nine_checks():
    text = (ROOT / ".claude" / "skills" / "done-gate" / "SKILL.md").read_text()
    numbers = {int(n) for n in re.findall(r"^### Check (\d+):", text, re.MULTILINE)}
    assert numbers == set(range(1, 10)), f"done-gate checks are {sorted(numbers)}"


def test_assay_invokes_the_tdd_check():
    """Check 9 is only real if /assay's done-gate step actually runs 9 checks."""
    text = (COMMANDS_DIR / "assay.md").read_text()
    assert "all 9 checks" in text
    assert "tdd-loop" in text, "/assay never invokes the TDD loop"


@pytest.mark.parametrize("cmd", command_files(), ids=lambda p: p.name)
def test_command_frontmatter_has_argument_hint_when_it_takes_args(cmd):
    fm = parse_frontmatter(cmd.read_text()) or {}
    body = cmd.read_text()
    if "## Invocation" not in body:
        pytest.skip("command documents no invocation forms")
    assert fm.get("argument-hint", "").strip(), f"{cmd.name}: missing argument-hint"


def test_config_keys_are_documented():
    """Every config key the reader ships must appear in CONFIG.md.

    A key nobody can discover is a key nobody sets, and the default silently
    becomes the only behavior.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "assay_config", ROOT / "scripts" / "assay_config.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    doc = (ROOT / "CONFIG.md").read_text()
    missing = [
        f"{section}.{key}"
        for section, body in mod.DEFAULTS.items()
        for key in body
        if f"{section}.{key}" not in doc
    ]
    assert not missing, f"CONFIG.md does not document: {missing}"
