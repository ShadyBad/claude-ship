"""Validate the per-install config reader.

Every command that touches a ticket, a glossary, or the TDD gate resolves its
paths through `assay_config`. A wrong answer here silently redirects writes, so
the tests concentrate on the degradation path: absent file, partial file,
corrupt file, and unknown keys must all still yield a usable config.
"""

from __future__ import annotations

import importlib.util
import json

import pytest
from conftest import ROOT

SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader, f"cannot load scripts/{name}.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cfg_mod = _load("assay_config")


@pytest.fixture
def cfg_path(tmp_path):
    return tmp_path / "assay.config.json"


def write(path, payload):
    path.write_text(json.dumps(payload))


def test_absent_file_yields_shipped_defaults(cfg_path):
    assert cfg_mod.load(cfg_path) == cfg_mod.DEFAULTS


def test_shipped_default_backend_is_repo_files(cfg_path):
    assert cfg_mod.get("tickets.backend", cfg_path) == "repo-files"
    assert cfg_mod.get("tickets.path", cfg_path) == "docs/tickets"


def test_partial_section_keeps_sibling_defaults(cfg_path):
    write(cfg_path, {"tickets": {"backend": "memory-dir"}})
    cfg = cfg_mod.load(cfg_path)
    assert cfg["tickets"]["backend"] == "memory-dir"
    assert cfg["tickets"]["path"] == "docs/tickets"


def test_corrupt_json_degrades_to_defaults(cfg_path):
    cfg_path.write_text("{not json")
    assert cfg_mod.load(cfg_path) == cfg_mod.DEFAULTS


def test_unknown_key_is_ignored_by_load_but_reported_by_validate(cfg_path):
    write(cfg_path, {"tickets": {"backend": "memory-dir", "bogus": 1}, "nope": {}})
    assert "bogus" not in cfg_mod.load(cfg_path)["tickets"]
    problems = cfg_mod.validate(cfg_path)
    assert any("tickets.bogus" in p for p in problems)
    assert any("nope" in p for p in problems)


def test_validate_rejects_unknown_backend(cfg_path):
    write(cfg_path, {"tickets": {"backend": "jira"}})
    assert any("tickets.backend" in p for p in cfg_mod.validate(cfg_path))


def test_validate_passes_on_shipped_defaults(cfg_path):
    assert cfg_mod.init(cfg_path) is True
    assert cfg_mod.validate(cfg_path) == []


def test_init_does_not_clobber_without_force(cfg_path):
    write(cfg_path, {"tickets": {"backend": "memory-dir"}})
    assert cfg_mod.init(cfg_path) is False
    assert cfg_mod.get("tickets.backend", cfg_path) == "memory-dir"
    assert cfg_mod.init(cfg_path, force=True) is True
    assert cfg_mod.get("tickets.backend", cfg_path) == "repo-files"


def test_unknown_dotted_key_raises(cfg_path):
    with pytest.raises(KeyError):
        cfg_mod.get("tickets.nonesuch", cfg_path)
    with pytest.raises(KeyError):
        cfg_mod.get("tickets", cfg_path)


@pytest.mark.parametrize(
    ("tier", "expected"),
    [("TRIVIAL", False), ("LOW", False), ("MEDIUM", True), ("CRITICAL", True)],
)
def test_tdd_required_respects_default_floor(cfg_path, tier, expected):
    assert cfg_mod.tdd_required(tier, cfg_path) is expected


def test_tdd_never_disables_enforcement(cfg_path):
    write(cfg_path, {"tdd": {"min_tier": "NEVER"}})
    assert cfg_mod.tdd_required("CRITICAL", cfg_path) is False
