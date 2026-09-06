#!/usr/bin/env python3
"""Append one /assay run record to the local run log.

Assay's own effectiveness is unmeasured: the pipeline runs, the judges opine,
and nothing on disk says whether any of it changed the shipped diff. This
script is the write half of that instrument. `/assay` Step 14 (and the halt
path) pipes a JSON run record here; `assay_stats.py` reads them back.

The log lives outside the repo, under the user's memory tree, because it is
operator data and not plugin source:

    $HOME/.claude/memory/global/assay-runs.jsonl

One JSON object per line, appended, never rewritten. Records are
finding-grained inside run-grained: a single HIGH-tier run carries ~10 judge
entries, so per-judge statistics accumulate an order of magnitude faster than
per-run ones.

Usage:
    assay_record.py < record.json
    echo '{...}' | assay_record.py
    assay_record.py --file record.json
    assay_record.py --validate < record.json   # check schema, write nothing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LOG = Path.home() / ".claude" / "memory" / "global" / "assay-runs.jsonl"

TIERS = {"TRIVIAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
OUTCOMES = {"committed", "dry-run", "halted", "aborted", "blocked"}
VERDICTS = {
    "approved_first_pass",
    "approved_after_rework",
    "abandoned",
    "unknown",
}

# Pipeline stages whose fire rate is worth tracking. Keys are the names /assay
# uses in its own step list; the value is the step number for readability.
STAGES = {
    "spec-escalation": 1,
    "context-load": 2,
    "plan": 3,
    "mcp-route": 6,
    "tdd-loop": 7,
    "judge-panel": 8,
    "judge-vet": 8,
    "survey-branch": 8,
    "revise": 9,
    "done-gate": 10,
    "commit-protocol": 11,
    "learn": 12,
    "survey-cadence": 13,
}

# The survey funnel. Each stage is a subset of the one before it, which is what
# makes the numbers falsifiable: vetting can only remove findings, and only a
# vetted finding can be promoted or queued.
SURVEY_COUNTS = (
    "findings_raw",
    "findings_after_vet",
    "findings_promoted",
    "findings_queued",
    "findings_rejected",
)


class ValidationError(ValueError):
    """Raised when a record cannot be trusted enough to log."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValidationError(msg)


def _validate_diff(label: str, diff: Any) -> None:
    _require(isinstance(diff, dict), f"{label} must be an object")
    for key in ("files", "added", "deleted"):
        _require(key in diff, f"{label}.{key} is required")
        _require(
            isinstance(diff[key], int) and not isinstance(diff[key], bool) and diff[key] >= 0,
            f"{label}.{key} must be a non-negative integer",
        )


def _validate_judge(idx: int, judge: Any) -> None:
    label = f"judges[{idx}]"
    _require(isinstance(judge, dict), f"{label} must be an object")
    name = judge.get("judge")
    _require(isinstance(name, str) and name.strip(), f"{label}.judge is required")

    concerns = judge.get("concerns", 0)
    accepted = judge.get("accepted", 0)
    # Concerns the vet pass dropped before they reached Brandon or the revise
    # loop: false positives, mis-attributed evidence, cross-judge duplicates.
    # `concerns` is the post-vet count, so a judge's real noise level is
    # dropped / (dropped + concerns) — the evidence for cutting it.
    dropped = judge.get("dropped", 0)
    for key, val in (("concerns", concerns), ("accepted", accepted), ("dropped", dropped)):
        _require(
            isinstance(val, int) and not isinstance(val, bool) and val >= 0,
            f"{label}.{key} must be a non-negative integer",
        )
    # The acceptance metric is meaningless if a judge can accept more than it
    # raised, and that inversion is a plausible transcription slip.
    _require(
        accepted <= concerns,
        f"{label}.accepted ({accepted}) exceeds .concerns ({concerns})",
    )


def _validate_survey(survey: Any) -> None:
    """The funnel must narrow. A widening one is a miscount, not a discovery."""
    _require(isinstance(survey, dict), "survey must be an object")
    counts: dict[str, int] = {}
    for key in SURVEY_COUNTS:
        if key not in survey:
            continue
        val = survey[key]
        _require(
            isinstance(val, int) and not isinstance(val, bool) and val >= 0,
            f"survey.{key} must be a non-negative integer",
        )
        counts[key] = val

    raw = counts.get("findings_raw")
    vetted = counts.get("findings_after_vet")
    if raw is not None and vetted is not None:
        _require(
            vetted <= raw,
            f"survey.findings_after_vet ({vetted}) exceeds .findings_raw ({raw}) — "
            "vetting removes findings, it cannot add them",
        )
    if vetted is not None:
        for key in ("findings_promoted", "findings_queued"):
            val = counts.get(key)
            if val is not None:
                _require(
                    val <= vetted,
                    f"survey.{key} ({val}) exceeds .findings_after_vet ({vetted})",
                )
        promoted = counts.get("findings_promoted", 0)
        queued = counts.get("findings_queued", 0)
        _require(
            promoted + queued <= vetted,
            f"survey.findings_promoted + .findings_queued ({promoted + queued}) "
            f"exceeds .findings_after_vet ({vetted})",
        )

    scope = survey.get("scope")
    if scope is not None:
        _require(
            scope in {"branch", "hotspots", "repo", "focus"},
            "survey.scope must be one of ['branch', 'focus', 'hotspots', 'repo']",
        )


def validate(record: dict[str, Any]) -> dict[str, Any]:
    """Check required fields, normalize optional ones, return the record to log.

    Mutates a copy, not the caller's dict. Raises ValidationError with a
    message naming the offending field — the caller surfaces it to the operator
    rather than logging a record that will skew every later statistic.
    """
    _require(isinstance(record, dict), "record must be a JSON object")
    rec = dict(record)

    for field in ("project", "risk_tier", "outcome"):
        _require(field in rec, f"{field} is required")

    _require(isinstance(rec["project"], str) and rec["project"].strip(), "project must be a string")

    tier = str(rec["risk_tier"]).upper()
    _require(tier in TIERS, f"risk_tier must be one of {sorted(TIERS)}, got {rec['risk_tier']!r}")
    rec["risk_tier"] = tier

    outcome = str(rec["outcome"]).lower()
    _require(outcome in OUTCOMES, f"outcome must be one of {sorted(OUTCOMES)}, got {outcome!r}")
    rec["outcome"] = outcome

    verdict = str(rec.get("brandon_verdict", "unknown")).lower()
    _require(verdict in VERDICTS, f"brandon_verdict must be one of {sorted(VERDICTS)}")
    rec["brandon_verdict"] = verdict

    rec.setdefault("ts", datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"))
    rec.setdefault("run_id", f"{rec['ts'][:10]}-{uuid.uuid4().hex[:4]}")

    stages = rec.get("stages_fired", [])
    _require(isinstance(stages, list), "stages_fired must be a list")
    unknown = [s for s in stages if s not in STAGES]
    _require(not unknown, f"stages_fired contains unknown stage(s): {unknown}")

    eligible = rec.get("stages_eligible", stages)
    _require(isinstance(eligible, list), "stages_eligible must be a list")
    unknown = [s for s in eligible if s not in STAGES]
    _require(not unknown, f"stages_eligible contains unknown stage(s): {unknown}")
    # A stage cannot fire without being eligible; that would make fire rate
    # exceed 100% and hide a bookkeeping bug.
    stray = sorted(set(stages) - set(eligible))
    _require(not stray, f"stages_fired not marked eligible: {stray}")
    rec["stages_fired"] = stages
    rec["stages_eligible"] = eligible

    judges = rec.get("judges", [])
    _require(isinstance(judges, list), "judges must be a list")
    for idx, judge in enumerate(judges):
        _validate_judge(idx, judge)
    rec["judges"] = judges

    if "survey" in rec and rec["survey"] is not None:
        _validate_survey(rec["survey"])

    for label in ("diff_before_review", "diff_after_review"):
        if label in rec and rec[label] is not None:
            _validate_diff(label, rec[label])

    rework = rec.get("rework_turns")
    if rework is not None:
        _require(
            isinstance(rework, int) and not isinstance(rework, bool) and rework >= 0,
            "rework_turns must be a non-negative integer",
        )

    tokens = rec.get("tokens_total")
    if tokens is not None:
        _require(
            isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0,
            "tokens_total must be a non-negative integer",
        )

    return rec


def append(record: dict[str, Any], log_path: Path) -> None:
    """Append one record as a single line. Creates the log and parents if absent."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":"), sort_keys=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--file", type=Path, help="Read the record from this file, not stdin.")
    parser.add_argument(
        "--log",
        type=Path,
        default=Path(os.environ.get("ASSAY_RUN_LOG", DEFAULT_LOG)),
        help=f"Run log to append to (default: {DEFAULT_LOG}).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate and echo the normalized record without writing.",
    )
    args = parser.parse_args(argv)

    raw = args.file.read_text(encoding="utf-8") if args.file else sys.stdin.read()
    if not raw.strip():
        print("assay_record: no input", file=sys.stderr)
        return 2

    try:
        record = validate(json.loads(raw))
    except json.JSONDecodeError as exc:
        print(f"assay_record: input is not valid JSON: {exc}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        print(f"assay_record: {exc}", file=sys.stderr)
        return 2

    if args.validate:
        print(json.dumps(record, indent=2, sort_keys=True))
        return 0

    append(record, args.log)
    print(f"assay_record: logged {record['run_id']} -> {args.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
