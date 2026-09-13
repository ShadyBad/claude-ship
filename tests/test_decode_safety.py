"""Every text-decoding call in scripts/ must declare an error handler.

Three times in one session a decode hazard was fixed on one call and left in
its twin a few lines away -- once leaking a live credential into stderr,
because UnicodeDecodeError's repr embeds the entire offending bytes object.
A judge found two of them and an AST sweep found the third, which is the
argument for this being a test rather than a review habit.
"""

from __future__ import annotations

import ast

from conftest import SKILLS_DIR

ROOT = SKILLS_DIR.parent.parent
# rglob over two roots: a scripts/<subdir>/ file or a future Python hook under
# hooks/ (all shell today) would otherwise be silently uncovered, which is the
# same missed-twin shape this guard exists to prevent.
SWEEP_ROOTS = (ROOT / "scripts", ROOT / "hooks")


def _decode_calls():
    paths = sorted(p for root in SWEEP_ROOTS if root.exists() for p in root.rglob("*.py"))
    for path in paths:
        # This read is itself the pattern under test; guard it too rather than
        # exempting the auditor from its own rule.
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            kwargs = {k.arg for k in node.keywords}
            decodes = name.endswith("read_text") or (
                name.endswith("subprocess.run") and "text" in kwargs
            )
            if decodes:
                yield path.relative_to(ROOT), node.lineno, name, kwargs


def test_every_decoding_call_declares_an_error_handler():
    gaps = [
        f"{f}:{line} {name}" for f, line, name, kwargs in _decode_calls() if "errors" not in kwargs
    ]
    assert not gaps, (
        "decoding calls without errors=: "
        + ", ".join(gaps)
        + " -- an unguarded decode can put raw file or diff bytes into an "
        "exception repr, which this gate prints"
    )


def test_the_sweep_actually_finds_calls():
    """A vacuous sweep would pass forever after a refactor renames things."""
    assert list(_decode_calls()), "AST sweep matched nothing; the guard is inert"
