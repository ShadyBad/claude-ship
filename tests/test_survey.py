"""Guard the survey stage, the judge vet pass, and the rejection ledger.

The survey stage is automatic: it fires from inside the pipeline and from a
cadence check, not from Brandon remembering to type a command. That makes it
exactly the kind of thing that can quietly stop working — nobody notices a
background pass that no longer runs. These tests hold the wiring, and the
recorder vocabulary that makes the stage measurable once it does run.
"""

from __future__ import annotations

import importlib.util
import json

import pytest
from conftest import COMMANDS_DIR, ROOT, SKILLS_DIR, parse_frontmatter

SCRIPTS = ROOT / "scripts"
SURVEY_SKILL = SKILLS_DIR / "survey" / "SKILL.md"
SURVEY_PLAYBOOK = SKILLS_DIR / "survey" / "references" / "audit-playbook.md"
SURVEY_CMD = COMMANDS_DIR / "survey.md"

# The nine audit dimensions. A category silently dropped from the playbook is a
# blind spot nobody sees, because the survey still reports success.
CATEGORIES = (
    "correctness",
    "security",
    "performance",
    "test coverage",
    "tech debt",
    "dependencies",
    "dx",
    "docs",
    "direction",
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader, f"cannot load scripts/{name}.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cfg_mod = _load("assay_config")
rec_mod = _load("assay_record")
stats_mod = _load("assay_stats")


# --------------------------------------------------------------------------
# A. the survey skill and its command


def test_survey_skill_exists():
    assert SURVEY_SKILL.is_file(), "survey skill is missing"


def test_survey_playbook_is_a_separate_reference_file():
    """The playbook is handed to subagents by path, so it must be its own file."""
    assert SURVEY_PLAYBOOK.is_file(), "survey has no references/audit-playbook.md"


def test_survey_skill_points_subagents_at_the_playbook():
    text = SURVEY_SKILL.read_text()
    assert "references/audit-playbook.md" in text
    assert "Finding format" in text, "subagent brief must name the finding format"


@pytest.mark.parametrize("category", CATEGORIES)
def test_playbook_covers_every_audit_category(category):
    assert category in SURVEY_PLAYBOOK.read_text().lower(), f"playbook drops {category}"


def test_playbook_requires_evidence():
    """A finding without file:line is a vibe, and vibes flood the queue."""
    assert "file:line" in SURVEY_PLAYBOOK.read_text()


def test_survey_command_exists():
    assert SURVEY_CMD.is_file(), "/survey is missing"
    fm = parse_frontmatter(SURVEY_CMD.read_text())
    assert fm and fm.get("name") == "survey"


def test_survey_never_edits_source():
    """Advisory/execution separation is the whole safety argument."""
    text = SURVEY_SKILL.read_text()
    assert "NEVER edit" in text or "NEVER modif" in text


# --------------------------------------------------------------------------
# B. the judge vet pass


def test_judge_panel_has_a_vet_pass():
    text = (SKILLS_DIR / "judge-panel" / "SKILL.md").read_text()
    assert "VET" in text, "judge-panel has no vet pass"
    assert "over-report" in text, "the vet pass must state why it exists"


def test_vet_pass_runs_before_aggregation():
    """Vetting after aggregation would let a false positive reach the verdict."""
    text = (SKILLS_DIR / "judge-panel" / "SKILL.md").read_text()
    assert text.index("## Vet Pass") < text.index("## Aggregation Rules")


# --------------------------------------------------------------------------
# C. the rejection ledger


def test_project_memory_owns_the_rejection_ledger():
    text = (SKILLS_DIR / "project-memory" / "SKILL.md").read_text()
    assert "rejected.md" in text, "no rejection ledger"


def test_survey_reads_the_ledger_before_reporting():
    """Without this, a rejected finding respawns on every cadence run."""
    assert "rejected.md" in SURVEY_SKILL.read_text()


# --------------------------------------------------------------------------
# D. executor-grade tickets


@pytest.mark.parametrize("marker", ["planned_at", "STOP conditions", "Current state"])
def test_ticket_format_carries_executor_context(marker):
    text = (SKILLS_DIR / "ticket-board" / "SKILL.md").read_text()
    assert marker in text, f"ticket format has no {marker}"


def test_thick_tickets_are_tier_gated():
    """A LOW ticket does not need a novel; the cost has to be bounded."""
    text = (SKILLS_DIR / "ticket-board" / "SKILL.md").read_text()
    assert "--parallel" in text, "thickness must key off zero-context execution"


# --------------------------------------------------------------------------
# E. reconcile


def test_ticket_board_reconciles():
    text = (SKILLS_DIR / "ticket-board" / "SKILL.md").read_text()
    assert "reconcile" in text


def test_to_tickets_exposes_reconcile():
    assert "reconcile" in (COMMANDS_DIR / "to-tickets.md").read_text()


# --------------------------------------------------------------------------
# F. automatic triggers


def test_assay_runs_the_branch_survey_in_pipeline():
    text = (COMMANDS_DIR / "assay.md").read_text()
    assert "Step 8.5" in text, "/assay has no in-pipeline survey step"
    assert "pre-existing" in text, "branch survey must separate introduced from pre-existing"


def test_pre_existing_findings_never_block_the_ship():
    text = (COMMANDS_DIR / "assay.md").read_text()
    assert "never block" in text.lower()


def test_implement_surveys_instead_of_idling():
    text = (COMMANDS_DIR / "implement.md").read_text()
    assert "survey" in text.lower(), "/implement still idles on an empty board"


def test_spec_loads_standing_findings():
    assert "finding" in (COMMANDS_DIR / "spec.md").read_text().lower()


# --------------------------------------------------------------------------
# G. config


def test_survey_config_ships_with_auto_queue():
    """Auto-promotion stays off until the instrumentation says precision is real."""
    assert cfg_mod.DEFAULTS["survey"]["auto"] == "queue"


def test_survey_config_keys(tmp_path):
    cfg = cfg_mod.load(tmp_path / "c.json")
    for key in ("auto", "cadence_days", "in_pipeline", "max_promote_per_cycle"):
        assert key in cfg["survey"], f"survey.{key} missing"


def test_validate_rejects_unknown_survey_auto(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"survey": {"auto": "yolo"}}))
    assert any("survey.auto" in p for p in cfg_mod.validate(path))


def test_validate_rejects_negative_cadence(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"survey": {"cadence_days": -1}}))
    assert any("cadence_days" in p for p in cfg_mod.validate(path))


def test_survey_auto_helper(tmp_path):
    path = tmp_path / "c.json"
    assert cfg_mod.survey_promotes(path) is False
    path.write_text(json.dumps({"survey": {"auto": "promote"}}))
    assert cfg_mod.survey_promotes(path) is True


# --------------------------------------------------------------------------
# H. instrumentation


@pytest.mark.parametrize("stage", ["survey-branch", "survey-cadence", "judge-vet"])
def test_new_stages_are_recordable(stage):
    assert stage in rec_mod.STAGES, f"{stage} is not a recordable stage"


def _base(**extra):
    rec = {"project": "personal", "risk_tier": "MEDIUM", "outcome": "committed"}
    rec.update(extra)
    return rec


def test_record_accepts_a_survey_funnel():
    rec = rec_mod.validate(
        _base(
            survey={
                "scope": "branch",
                "findings_raw": 9,
                "findings_after_vet": 4,
                "findings_promoted": 1,
                "findings_queued": 3,
            }
        )
    )
    assert rec["survey"]["findings_after_vet"] == 4


def test_record_rejects_vetting_that_adds_findings():
    """More findings after vetting than before means the funnel is miscounted."""
    with pytest.raises(rec_mod.ValidationError):
        rec_mod.validate(_base(survey={"findings_raw": 2, "findings_after_vet": 5}))


def test_record_rejects_promoting_more_than_survived_vetting():
    with pytest.raises(rec_mod.ValidationError):
        rec_mod.validate(
            _base(survey={"findings_raw": 5, "findings_after_vet": 2, "findings_promoted": 3})
        )


def test_record_tracks_concerns_dropped_by_the_vet_pass():
    rec = rec_mod.validate(
        _base(judges=[{"judge": "security", "concerns": 2, "accepted": 1, "dropped": 3}])
    )
    assert rec["judges"][0]["dropped"] == 3


def test_stats_reports_the_survey_funnel():
    records = [
        {
            "project": "p",
            "risk_tier": "MEDIUM",
            "outcome": "committed",
            "survey": {
                "findings_raw": 10,
                "findings_after_vet": 4,
                "findings_promoted": 2,
                "findings_queued": 2,
            },
        },
    ]
    report = stats_mod.build_report(records)
    assert "survey_funnel" in report
    assert report["survey_funnel"]["findings_raw"] == 10
    assert report["survey_funnel"]["vet_survival_rate"] == pytest.approx(0.4)


def test_stats_reports_judge_drop_rate():
    records = [
        {
            "project": "p",
            "risk_tier": "HIGH",
            "outcome": "committed",
            "stages_fired": ["judge-panel"],
            "stages_eligible": ["judge-panel"],
            "judges": [{"judge": "naming", "concerns": 1, "accepted": 0, "dropped": 9}],
        },
    ]
    report = stats_mod.build_report(records)
    assert report["judge_acceptance"]["naming"]["dropped"] == 9
    assert report["judge_acceptance"]["naming"]["drop_rate"] == pytest.approx(0.9)


def test_stats_renders_without_survey_records():
    """Every metric must degrade to 'no data', never to a traceback."""
    out = stats_mod.render(stats_mod.build_report([]), [])
    assert "No runs recorded" in out


# --------------------------------------------------------------------------
# I. surfacing hooks


def test_finding_hooks_exist():
    for name in ("finding-count.sh", "finding-watcher.sh"):
        assert (ROOT / "hooks" / name).is_file(), f"hooks/{name} is missing"


def test_statusline_surfaces_findings():
    assert "finding-count.sh" in (ROOT / "hooks" / "composed-statusline.sh").read_text()
