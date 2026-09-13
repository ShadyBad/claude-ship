#!/usr/bin/env python3
"""Read (and initialize) the per-install Assay config.

Assay ships as one plugin but runs on one operator's machine, against that
operator's repos. Where tickets live, what the glossary is called, and how hard
TDD is enforced are install-level choices, not plugin-level ones — so they live
outside the repo:

    $HOME/.claude/assay.config.json

Every command that needs a path asks this module rather than hardcoding one.
Missing file, missing key, and malformed JSON all resolve to the shipped
defaults: a fresh install works with no config at all, and a half-written
config degrades to defaults per key rather than failing the pipeline.

Usage:
    assay_config.py --show                 # effective config as JSON
    assay_config.py --init                 # write defaults (never clobbers)
    assay_config.py --init --force         # overwrite with defaults
    assay_config.py get tickets.backend    # one value, bare, for shell use
    assay_config.py --validate             # exit 1 on an unusable config
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path.home() / ".claude" / "assay.config.json"

# Shipped defaults. Also the schema: a key absent from here is an unknown key,
# and `--validate` says so rather than silently honoring a typo.
DEFAULTS: dict[str, dict[str, Any]] = {
    "tickets": {
        # repo-files  — docs/tickets/*.md inside the repo being worked on.
        # memory-dir  — $HOME/.claude/memory/projects/<ns>/tickets/.
        "backend": "repo-files",
        "path": "docs/tickets",
    },
    "glossary": {
        "path": "CONTEXT.md",
        "adr_path": "docs/adr",
    },
    "tdd": {
        # Lowest risk tier at which the red-green loop is mandatory.
        # "NEVER" disables enforcement entirely.
        "min_tier": "MEDIUM",
    },
    "qa": {
        # After commit, park the ticket in needs-qa instead of closing it.
        "queue": True,
    },
    "survey": {
        # off      — the survey stage never fires on its own.
        # queue    — findings are written to the queue and surfaced; nothing
        #            reaches the board without a human pick.
        # promote  — findings that clear the auto-promotion bar become tickets
        #            directly. Only turn this on once /assay-stats shows the
        #            survey's precision is real; a board full of machine noise
        #            is a board nobody trusts again.
        "auto": "queue",
        # Days between cadence surveys. The post-ship check compares this
        # against last-survey-run.txt.
        "cadence_days": 7,
        # Run the branch-scoped survey inside /assay at Step 8.5.
        "in_pipeline": True,
        # Ceiling on auto-promoted tickets per cadence cycle, so one bad audit
        # cannot flood the board.
        "max_promote_per_cycle": 3,
    },
}

TICKET_BACKENDS = {"repo-files", "memory-dir"}
TIER_ORDER = ["TRIVIAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
TDD_TIERS = {*TIER_ORDER, "NEVER"}
SURVEY_AUTO = {"off", "queue", "promote"}


def load_raw(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    """Parse the config file, or return {} if it is absent or unreadable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def load(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    """The effective config: shipped defaults with the user's file merged over.

    Merge is one level deep — sections merge key-by-key, so a config that sets
    only ``tickets.backend`` keeps the default ``tickets.path``.
    """
    raw = load_raw(path)
    merged: dict[str, Any] = {}
    for section, defaults in DEFAULTS.items():
        merged[section] = dict(defaults)
        override = raw.get(section)
        if isinstance(override, dict):
            merged[section].update({k: v for k, v in override.items() if k in defaults})
    return merged


def get(dotted: str, path: Path = DEFAULT_PATH) -> Any:
    """Look up one ``section.key`` value from the effective config."""
    section, _, key = dotted.partition(".")
    if not key:
        raise KeyError(f"expected 'section.key', got {dotted!r}")
    cfg = load(path)
    if section not in cfg or key not in cfg[section]:
        raise KeyError(f"unknown config key: {dotted}")
    return cfg[section][key]


def tdd_required(tier: str, path: Path = DEFAULT_PATH) -> bool:
    """Whether the red-green loop is mandatory at ``tier``."""
    floor = str(get("tdd.min_tier", path)).upper()
    if floor == "NEVER" or tier.upper() not in TIER_ORDER:
        return False
    return TIER_ORDER.index(tier.upper()) >= TIER_ORDER.index(floor)


def survey_promotes(path: Path = DEFAULT_PATH) -> bool:
    """Whether a surveyed finding may become a ticket without a human pick."""
    return str(get("survey.auto", path)).lower() == "promote"


def survey_enabled(path: Path = DEFAULT_PATH) -> bool:
    """Whether the survey stage fires at all."""
    return str(get("survey.auto", path)).lower() in {"queue", "promote"}


def validate(path: Path = DEFAULT_PATH) -> list[str]:
    """Return human-readable problems with the config file. Empty means fine."""
    problems: list[str] = []
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            return [f"{path}: not valid JSON ({exc})"]
        except OSError as exc:
            return [f"{path}: unreadable ({exc})"]
        if not isinstance(parsed, dict):
            return [f"{path}: top level must be a JSON object"]
        for section, body in parsed.items():
            if section not in DEFAULTS:
                problems.append(f"unknown section: {section}")
                continue
            if not isinstance(body, dict):
                problems.append(f"{section}: must be an object")
                continue
            for key in body:
                if key not in DEFAULTS[section]:
                    problems.append(f"unknown key: {section}.{key}")

    cfg = load(path)
    backend = cfg["tickets"]["backend"]
    if backend not in TICKET_BACKENDS:
        problems.append(f"tickets.backend {backend!r} is not one of {sorted(TICKET_BACKENDS)}")
    tier = str(cfg["tdd"]["min_tier"]).upper()
    if tier not in TDD_TIERS:
        problems.append(f"tdd.min_tier {tier!r} is not one of {sorted(TDD_TIERS)}")
    if not isinstance(cfg["qa"]["queue"], bool):
        problems.append("qa.queue must be true or false")

    auto = str(cfg["survey"]["auto"]).lower()
    if auto not in SURVEY_AUTO:
        problems.append(f"survey.auto {auto!r} is not one of {sorted(SURVEY_AUTO)}")
    cadence = cfg["survey"]["cadence_days"]
    if not isinstance(cadence, int) or isinstance(cadence, bool) or cadence < 1:
        problems.append("survey.cadence_days must be a positive integer")
    if not isinstance(cfg["survey"]["in_pipeline"], bool):
        problems.append("survey.in_pipeline must be true or false")
    cap = cfg["survey"]["max_promote_per_cycle"]
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        problems.append("survey.max_promote_per_cycle must be a non-negative integer")
    return problems


def init(path: Path = DEFAULT_PATH, force: bool = False) -> bool:
    """Write the shipped defaults. Returns False if a config already exists."""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULTS, indent=2) + "\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("get", nargs="?", help="literal 'get'")
    parser.add_argument("key", nargs="?", help="dotted config key, e.g. tickets.backend")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--show", action="store_true", help="print effective config")
    parser.add_argument("--init", action="store_true", help="write shipped defaults")
    parser.add_argument("--force", action="store_true", help="with --init, overwrite")
    parser.add_argument("--validate", action="store_true", help="check the config file")
    args = parser.parse_args(argv)

    if args.init:
        if init(args.path, force=args.force):
            print(f"wrote {args.path}")
        else:
            print(f"{args.path} already exists — use --force to overwrite", file=sys.stderr)
            return 1
        return 0

    if args.validate:
        problems = validate(args.path)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0

    if args.get == "get" and args.key:
        try:
            value = get(args.key, args.path)
        except KeyError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(json.dumps(value) if isinstance(value, bool) else value)
        return 0

    if args.show or args.get is None:
        print(json.dumps(load(args.path), indent=2))
        return 0

    parser.error("unrecognized arguments")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
