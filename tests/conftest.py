"""Shared fixtures and helpers for the Assay plugin-structure tests.

Assay ships markdown commands + skills + shell hooks, not importable
Python. These tests validate the plugin's own structure so that drift — a
miscounted skill, malformed frontmatter, a broken doc link — fails CI instead
of shipping silently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# scripts/ holds the executable helpers the hooks call; make them importable.
sys.path.insert(0, str(ROOT / "scripts"))
SKILLS_DIR = ROOT / ".claude" / "skills"
COMMANDS_DIR = ROOT / ".claude" / "commands"
MANIFEST = ROOT / ".claude-plugin" / "plugin.json"


def parse_frontmatter(text: str) -> dict | None:
    """Parse a markdown frontmatter block into a flat dict, or None if absent.

    Deliberately line-based (``key: value``) rather than a strict YAML load:
    Claude Code's own frontmatter loader is lenient and permits unquoted
    descriptions containing colons and quotation marks. A strict ``yaml.safe_load``
    would reject frontmatter that Claude Code accepts, so this mirrors the real
    contract — split each line on the first ``": "`` and strip optional wrapping
    quotes from the value.
    """
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    fm: dict[str, str] = {}
    for raw in parts[1].splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ": " in line:
            key, _, value = line.partition(": ")
        elif line.endswith(":"):
            key, value = line[:-1], ""
        else:
            continue
        fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def skill_dirs() -> list[Path]:
    """Every skill directory under .claude/skills/."""
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def command_files() -> list[Path]:
    """Every command markdown file under .claude/commands/."""
    return sorted(COMMANDS_DIR.glob("*.md"))


@pytest.fixture(scope="session")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text())
