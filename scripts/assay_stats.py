#!/usr/bin/env python3
"""Compute effectiveness metrics from the /assay run log.

Reads the JSONL written by `assay_record.py` and answers the only question
that matters about an orchestration layer: is any of it changing the shipped
result, or is it ceremony?

Four metrics, each with a kill threshold:

  Stage fire rate       — did the stage actually run when eligible?
                          Below 70%: the skill description is broken, not the skill.
  Edit-after-review     — did the diff change after the judges spoke?
                          Below 20%: the panel is theater.
  Judge acceptance      — per judge, how many raised concerns were acted on?
                          Below 15%: that judge is noise; cut it.
  First-pass approval   — how often is the first shipped result accepted?
                          The north star. Read alongside rework turns.

Every metric prints its own n and refuses to render a verdict below the
minimum sample size. A confident number computed from four runs is worse than
no number, because it gets believed.

Usage:
    assay_stats.py
    assay_stats.py --log path/to/assay-runs.jsonl
    assay_stats.py --since 2026-07-01
    assay_stats.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_LOG = Path.home() / ".claude" / "memory" / "global" / "assay-runs.jsonl"

# Minimum sample sizes below which a metric reports "insufficient data" rather
# than a verdict. Judge acceptance is counted in concerns, not runs — one
# HIGH-tier run yields ~10 concerns, so it clears its bar far sooner.
MIN_N_STAGE = 5
MIN_N_EDIT = 5
MIN_N_JUDGE = 10
MIN_N_APPROVAL = 5
MIN_N_SURVEY = 3

KILL_STAGE_FIRE = 0.70
KILL_EDIT_RATE = 0.20
KILL_JUDGE_ACCEPT = 0.15
# Below this, the audit is manufacturing more noise than the vet pass can be
# expected to keep filtering — narrow the categories or raise the effort dial.
KILL_VET_SURVIVAL = 0.15


def load(log_path: Path, since: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Load records, newest last. Returns (records, warnings about bad lines)."""
    if not log_path.exists():
        return [], [f"no run log at {log_path} — nothing recorded yet"]

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for lineno, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"line {lineno}: unparseable, skipped")
            continue
        if since and str(rec.get("ts", "")) < since:
            continue
        records.append(rec)
    return records, warnings


def stage_fire_rates(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per stage: how often it fired out of the runs where it was eligible."""
    fired: dict[str, int] = defaultdict(int)
    eligible: dict[str, int] = defaultdict(int)
    for rec in records:
        for stage in rec.get("stages_eligible", []):
            eligible[stage] += 1
        for stage in rec.get("stages_fired", []):
            fired[stage] += 1

    out: dict[str, dict[str, Any]] = {}
    for stage, n in sorted(eligible.items()):
        rate = fired[stage] / n if n else 0.0
        out[stage] = {
            "fired": fired[stage],
            "eligible": n,
            "rate": rate,
            "verdict": _verdict(n, MIN_N_STAGE, rate, KILL_STAGE_FIRE, "not firing reliably"),
        }
    return out


def edit_after_review(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Fraction of judged runs whose diff changed after the panel reported."""
    judged = 0
    changed = 0
    for rec in records:
        if "judge-panel" not in rec.get("stages_fired", []):
            continue
        before, after = rec.get("diff_before_review"), rec.get("diff_after_review")
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        judged += 1
        if any(before.get(k) != after.get(k) for k in ("files", "added", "deleted")):
            changed += 1

    rate = changed / judged if judged else 0.0
    return {
        "changed": changed,
        "judged": judged,
        "rate": rate,
        "verdict": _verdict(
            judged, MIN_N_EDIT, rate, KILL_EDIT_RATE, "panel is not changing diffs"
        ),
    }


def judge_acceptance(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per judge: concerns acted on / concerns raised, plus block counts."""
    raised: dict[str, int] = defaultdict(int)
    accepted: dict[str, int] = defaultdict(int)
    dropped: dict[str, int] = defaultdict(int)
    invocations: dict[str, int] = defaultdict(int)
    blocks: dict[str, int] = defaultdict(int)

    for rec in records:
        for judge in rec.get("judges", []):
            name = judge.get("judge")
            if not name:
                continue
            invocations[name] += 1
            raised[name] += int(judge.get("concerns", 0) or 0)
            accepted[name] += int(judge.get("accepted", 0) or 0)
            dropped[name] += int(judge.get("dropped", 0) or 0)
            if judge.get("verdict") == "block":
                blocks[name] += 1

    out: dict[str, dict[str, Any]] = {}
    for name in sorted(invocations, key=lambda j: (-raised[j], j)):
        n = raised[name]
        rate = accepted[name] / n if n else 0.0
        surfaced = n + dropped[name]
        out[name] = {
            "invocations": invocations[name],
            "concerns": n,
            "accepted": accepted[name],
            "dropped": dropped[name],
            "blocks": blocks[name],
            "rate": rate,
            # Share of everything this judge raised that the vet pass threw out
            # before Brandon saw it. A judge with a high drop rate is not
            # reviewing, it is generating work for the vetter.
            "drop_rate": (dropped[name] / surfaced) if surfaced else 0.0,
            "verdict": _verdict(
                n, MIN_N_JUDGE, rate, KILL_JUDGE_ACCEPT, "noise — consider cutting"
            ),
        }
    return out


def survey_funnel(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the survey funnel: raw findings -> vetted -> promoted/queued.

    This is the calibration the audit cannot get any other way. A high raw
    count with a low survival rate means the subagents are guessing; a healthy
    survival rate with nothing ever promoted or queued means the findings are
    real but not worth doing, which is a reason to narrow the categories.
    """
    totals: dict[str, int] = defaultdict(int)
    surveys = 0
    scopes: dict[str, int] = defaultdict(int)
    for rec in records:
        survey = rec.get("survey")
        if not isinstance(survey, dict):
            continue
        surveys += 1
        scope = survey.get("scope")
        if scope:
            scopes[str(scope)] += 1
        for key in (
            "findings_raw",
            "findings_after_vet",
            "findings_promoted",
            "findings_queued",
            "findings_rejected",
        ):
            val = survey.get(key)
            if isinstance(val, int) and not isinstance(val, bool):
                totals[key] += val

    raw = totals["findings_raw"]
    vetted = totals["findings_after_vet"]
    survival = vetted / raw if raw else 0.0
    acted = totals["findings_promoted"] + totals["findings_queued"]
    return {
        "surveys": surveys,
        "scopes": dict(sorted(scopes.items())),
        "findings_raw": raw,
        "findings_after_vet": vetted,
        "findings_promoted": totals["findings_promoted"],
        "findings_queued": totals["findings_queued"],
        "findings_rejected": totals["findings_rejected"],
        "vet_survival_rate": survival,
        "action_rate": (acted / vetted) if vetted else 0.0,
        "verdict": _verdict(
            surveys, MIN_N_SURVEY, survival, KILL_VET_SURVIVAL, "audit is mostly noise"
        ),
    }


def approval(records: list[dict[str, Any]]) -> dict[str, Any]:
    """First-pass approval rate and rework-turn distribution."""
    known = [r for r in records if r.get("brandon_verdict", "unknown") != "unknown"]
    first_pass = sum(1 for r in known if r["brandon_verdict"] == "approved_first_pass")
    abandoned = sum(1 for r in known if r["brandon_verdict"] == "abandoned")
    reworks = [r["rework_turns"] for r in records if isinstance(r.get("rework_turns"), int)]
    tokens = [r["tokens_total"] for r in records if isinstance(r.get("tokens_total"), int)]

    n = len(known)
    rate = first_pass / n if n else 0.0
    return {
        "n": n,
        "first_pass": first_pass,
        "abandoned": abandoned,
        "rate": rate,
        "insufficient_data": n < MIN_N_APPROVAL,
        "median_rework_turns": statistics.median(reworks) if reworks else None,
        "rework_n": len(reworks),
        "median_tokens": int(statistics.median(tokens)) if tokens else None,
        "tokens_n": len(tokens),
    }


def _verdict(n: int, min_n: int, rate: float, kill: float, failure_msg: str) -> str:
    if n < min_n:
        return f"insufficient data (n={n}, need {min_n})"
    return failure_msg if rate < kill else "ok"


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes: dict[str, int] = defaultdict(int)
    tiers: dict[str, int] = defaultdict(int)
    for rec in records:
        outcomes[str(rec.get("outcome", "unknown"))] += 1
        tiers[str(rec.get("risk_tier", "unknown"))] += 1
    return {
        "runs": len(records),
        "outcomes": dict(sorted(outcomes.items())),
        "tiers": dict(sorted(tiers.items())),
        "stage_fire_rates": stage_fire_rates(records),
        "edit_after_review": edit_after_review(records),
        "judge_acceptance": judge_acceptance(records),
        "survey_funnel": survey_funnel(records),
        "approval": approval(records),
    }


def _pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def render(report: dict[str, Any], warnings: list[str]) -> str:
    lines: list[str] = []
    add = lines.append

    add("ASSAY EFFECTIVENESS")
    add("=" * 62)
    runs = report["runs"]
    add(f"Runs logged: {runs}")
    if runs:
        add(f"  outcomes: {report['outcomes']}")
        add(f"  tiers:    {report['tiers']}")
    if not runs:
        add("")
        add("No runs recorded. Metrics populate as /assay Step 14 fires.")
        for warn in warnings:
            add(f"  ! {warn}")
        return "\n".join(lines)

    add("")
    add("STAGE FIRE RATE       fired/eligible          verdict")
    add("-" * 62)
    for stage, s in report["stage_fire_rates"].items():
        add(f"  {stage:<20} {s['fired']:>3}/{s['eligible']:<3} {_pct(s['rate'])}   {s['verdict']}")

    add("")
    add("EDIT AFTER REVIEW")
    add("-" * 62)
    ear = report["edit_after_review"]
    add(f"  diffs changed post-panel: {ear['changed']}/{ear['judged']}  {_pct(ear['rate'])}")
    add(f"  verdict: {ear['verdict']}")

    add("")
    add("JUDGE ACCEPTANCE      acc/raised   rate   dropped  verdict")
    add("-" * 62)
    ja = report["judge_acceptance"]
    if not ja:
        add("  (no judge records yet)")
    for name, j in ja.items():
        add(
            f"  {name:<20} {j['accepted']:>3}/{j['concerns']:<4} {_pct(j['rate'])} "
            f"{j['dropped']:>5} ({_pct(j['drop_rate']).strip()})  {j['verdict']}"
        )

    add("")
    add("SURVEY FUNNEL")
    add("-" * 62)
    sf = report["survey_funnel"]
    if not sf["surveys"]:
        add("  (no surveys recorded yet)")
    else:
        add(f"  surveys: {sf['surveys']}  scopes: {sf['scopes']}")
        add(
            f"  raw {sf['findings_raw']} -> vetted {sf['findings_after_vet']} "
            f"({_pct(sf['vet_survival_rate']).strip()} survive) -> "
            f"promoted {sf['findings_promoted']} + queued {sf['findings_queued']}"
        )
        add(f"  action rate on vetted findings: {_pct(sf['action_rate']).strip()}")
        add(f"  verdict: {sf['verdict']}")

    add("")
    add("APPROVAL")
    add("-" * 62)
    ap = report["approval"]
    if ap["insufficient_data"]:
        add(
            f"  first-pass approval: {ap['first_pass']}/{ap['n']} — insufficient data "
            f"(need {MIN_N_APPROVAL})"
        )
    else:
        add(f"  first-pass approval: {ap['first_pass']}/{ap['n']}  {_pct(ap['rate'])}")
    add(f"  abandoned runs:      {ap['abandoned']}")
    if ap["median_rework_turns"] is not None:
        add(f"  median rework turns: {ap['median_rework_turns']} (n={ap['rework_n']})")
    if ap["median_tokens"] is not None:
        add(f"  median tokens/run:   {ap['median_tokens']:,} (n={ap['tokens_n']})")

    if warnings:
        add("")
        for warn in warnings:
            add(f"  ! {warn}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path(os.environ.get("ASSAY_RUN_LOG", DEFAULT_LOG)),
        help=f"Run log to read (default: {DEFAULT_LOG}).",
    )
    parser.add_argument("--since", help="Only include runs with ts >= this ISO date/timestamp.")
    parser.add_argument("--json", action="store_true", help="Emit the raw report as JSON.")
    args = parser.parse_args(argv)

    records, warnings = load(args.log, args.since)
    report = build_report(records)

    if args.json:
        print(json.dumps({"report": report, "warnings": warnings}, indent=2))
    else:
        print(render(report, warnings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
