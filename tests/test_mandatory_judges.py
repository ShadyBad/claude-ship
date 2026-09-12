"""The commit gate: a mandatory judge must have actually reported.

Spec: judge-enforcement-model-2026-09-12. The threat is an agent that skipped a
step, not one that forges a receipt, so the receipt is keyed to the staged diff
and an absent or stale one blocks.
"""

from __future__ import annotations

import dataclasses
import hashlib

import pytest
from check_mandatory_judges import Verdict, check_commit, detect_security_relevance

CLEAN_DIFF = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Project
+A sentence about nothing in particular.
"""

AUTH_DIFF = """diff --git a/app/auth/session.py b/app/auth/session.py
--- a/app/auth/session.py
+++ b/app/auth/session.py
@@ -1 +1,3 @@
 import os
+def check(token):
+    return token == os.environ["API_KEY"]
"""


def _receipt(diff: str, judges=(("Security Reviewer", "approve"),)):
    return {
        "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        "judges": [{"judge": j, "verdict": v} for j, v in judges],
        "ts": "2026-09-12T00:00:00Z",
    }


def test_clean_diff_needs_no_receipt():
    assert check_commit(CLEAN_DIFF, None, "docs: tidy readme").ok


def test_security_diff_without_receipt_blocks():
    v = check_commit(AUTH_DIFF, None, "feat: add session check")
    assert not v.ok
    assert "receipt" in v.reason.lower()


def test_security_diff_with_matching_receipt_passes():
    assert check_commit(AUTH_DIFF, _receipt(AUTH_DIFF), "feat: add session check").ok


def test_stale_receipt_blocks():
    v = check_commit(AUTH_DIFF, _receipt(CLEAN_DIFF), "feat: add session check")
    assert not v.ok
    assert "stale" in v.reason.lower()


def test_receipt_without_security_judge_blocks():
    stale = _receipt(AUTH_DIFF, judges=(("Simplicity Judge", "approve"),))
    v = check_commit(AUTH_DIFF, stale, "feat: add session check")
    assert not v.ok
    assert "security" in v.reason.lower()


def test_security_judge_present_but_unreachable_blocks():
    r = _receipt(AUTH_DIFF, judges=(("Security Reviewer", "unreachable"),))
    v = check_commit(AUTH_DIFF, r, "feat: add session check")
    assert not v.ok


def test_trailer_rescues_a_blocked_commit():
    msg = "docs: rubric wording\n\nSecurity-Review: skipped -- rubric prose, not code"
    v = check_commit(AUTH_DIFF, None, msg)
    assert v.ok
    assert "trailer" in v.reason.lower()


def test_trailer_requires_a_reason():
    v = check_commit(AUTH_DIFF, None, "docs: x\n\nSecurity-Review: skipped")
    assert not v.ok


@pytest.mark.parametrize(
    "receipt",
    [{}, {"judges": []}, {"diff_sha256": 123}, {"diff_sha256": "abc", "judges": "nope"}],
)
def test_malformed_receipt_fails_closed(receipt):
    assert not check_commit(AUTH_DIFF, receipt, "feat: add session check").ok


def test_detector_reports_its_evidence():
    hits = detect_security_relevance(AUTH_DIFF)
    assert hits, "detector found nothing in an auth diff"
    assert not detect_security_relevance(CLEAN_DIFF)


def test_verdict_is_immutable():
    # The hook acts on this object; a check that could be edited after the fact
    # is not a verdict.
    v = Verdict(ok=True, reason="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.ok = False


# --- findings from the HIGH panel on the gate itself -------------------------


def test_block_verdict_does_not_license_a_commit():
    """The gate asks 'may this commit', not 'did a judge attend'.

    Aggregation rule 0 counts `block` as having reported. The hook is the only
    place the floor is actually enforced, so a recorded block must not sail.
    """
    r = _receipt(AUTH_DIFF, judges=(("Security Reviewer", "block"),))
    assert not check_commit(AUTH_DIFF, r, "feat: x").ok


def test_panel_vocabulary_is_normalized():
    """state.json has carried panel-level words in a per-judge verdict slot."""
    r = _receipt(AUTH_DIFF, judges=(("Security Reviewer", "ship"),))
    assert check_commit(AUTH_DIFF, r, "feat: x").ok


def test_judge_name_matches_on_a_word_not_a_substring():
    """A 'security-adjacent' reviewer must not satisfy the mandatory set."""
    r = _receipt(AUTH_DIFF, judges=(("Security Documentation Auditor", "approve"),))
    assert check_commit(AUTH_DIFF, r, "feat: x").ok, "word-boundary match should still hit"
    r2 = _receipt(AUTH_DIFF, judges=(("Insecurity Theatre", "approve"),))
    assert not check_commit(AUTH_DIFF, r2, "feat: x").ok


@pytest.mark.parametrize(
    "line",
    [
        "    response = requests.get(url, verify=False)",
        '    allow_origins=["*"],',
        "    if digest == expected:  # nosec",
        "    subprocess.run(cmd, shell=True)",
        "    ctx.check_hostname = False",
    ],
)
def test_semantic_weakenings_are_detected(line):
    """None of these carry a security word, and all of them are the defect.

    A lexical detector cannot be complete; these are the cheap common ones a
    judge named as diffs that would otherwise have sailed through.
    """
    diff = (
        "diff --git a/app/client.py b/app/client.py\n"
        "--- a/app/client.py\n+++ b/app/client.py\n@@ -1 +1,2 @@\n"
        f" interesting\n+{line}\n"
    )
    assert detect_security_relevance(diff), f"missed semantic weakening: {line}"


def test_unparseable_diff_header_fails_closed():
    """A detector that silently sees zero files inside a fail-closed gate is a
    fail-open. `diff.noprefix=true` and paths with spaces both defeat the
    conventional header pattern."""
    weird = "diff --git some totally unexpected header shape\n+password = 1\n"
    assert detect_security_relevance(weird), "unparseable header did not fail closed"
    assert not check_commit(weird, None, "feat: x").ok


def test_noprefix_diff_still_yields_paths():
    """`diff.noprefix=true` emits `diff --git app/auth.py app/auth.py`."""
    diff = "diff --git app/auth/session.py app/auth/session.py\n@@ -1 +1,2 @@\n+x = 1\n"
    hits = detect_security_relevance(diff)
    assert any("path:auth" in h for h in hits), f"noprefix path not detected: {hits}"


@pytest.mark.parametrize(
    "line",
    [
        "new_api_key = 'LEAK2'",
        "my_token = get()",
        "user_password = input()",
        "SERVICE_ACCESS_KEY = os.environ['X']",
        "self._secret = v",
    ],
)
def test_prefixed_identifiers_are_detected(line):
    """`_` is a word char, so \\b(api_key)\\b never matched `new_api_key`.

    A judge reproduced a real leaked key committing straight past the gate
    through this hole. Prefixed identifiers are how these names appear in code.
    """
    diff = f"diff --git a/e.txt b/e.txt\n--- a/e.txt\n+++ b/e.txt\n@@ -1 +1,2 @@\n b\n+{line}\n"
    assert detect_security_relevance(diff), f"missed prefixed identifier: {line}"


def test_detector_does_not_fire_on_embedded_words():
    """`tokenize` and `secretary` are not security terms."""
    diff = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1,2 @@\n b\n"
        "+words = tokenize(secretary_notes)\n"
    )
    assert not detect_security_relevance(diff)


@pytest.mark.parametrize(
    "line",
    [
        "export const clientSecret = 'sk_live_9f2b';",
        "const authToken = 'ghp_realtoken';",
        "this.dbPassword = env.DB_PW;",
        "let signingKey = load();",
    ],
)
def test_camelcase_identifiers_are_detected(line):
    """The snake_case fix left camelCase live: `clientSecret` has `t` before
    `Secret`, so the lookbehind never fires. A judge reproduced both of these
    committing past the gate after the first fix landed."""
    diff = (
        "diff --git a/src/config.ts b/src/config.ts\n"
        "--- a/src/config.ts\n+++ b/src/config.ts\n@@ -1 +1,2 @@\n x\n"
        f"+{line}\n"
    )
    assert detect_security_relevance(diff), f"missed camelCase identifier: {line}"


def test_camelcase_pattern_does_not_fire_on_prose():
    diff = (
        "diff --git a/a.md b/a.md\n--- a/a.md\n+++ b/a.md\n@@ -1 +1,2 @@\n x\n"
        "+The Secretary tokenized the document.\n"
    )
    assert not detect_security_relevance(diff)


def test_only_a_judge_named_security_satisfies_the_floor():
    """`\\b` is not enough: `-` is a non-word char, so `\\bsecurity\\b` matches
    "app-security-docs". The mandatory set must not be satisfiable by a
    documentation reviewer whose name happens to contain the word."""
    impostor = _receipt(AUTH_DIFF, judges=(("app-security-docs", "approve"),))
    assert not check_commit(AUTH_DIFF, impostor, "feat: x").ok
    real = _receipt(AUTH_DIFF, judges=(("Security Reviewer", "approve"),))
    assert check_commit(AUTH_DIFF, real, "feat: x").ok


@pytest.mark.parametrize(
    "line", ["AWSSecretKey = 'x'", "JWTToken = 'x'", "DBPassword = 'x'", "XApiKey = 'x'"]
)
def test_uppercase_run_identifiers_are_detected(line):
    """`(?<=[a-z0-9])` missed `AWSSecretKey` -- the char before `Secret` is `S`."""
    diff = f"diff --git a/c.py b/c.py\n--- a/c.py\n+++ b/c.py\n@@ -1 +1,2 @@\n x\n+{line}\n"
    assert detect_security_relevance(diff), f"missed uppercase-run identifier: {line}"


def test_revise_verdict_does_not_license_a_commit():
    """`revise` means the judge asked for changes, and the hash proves none were
    made -- letting it through would contradict outcome-not-attendance."""
    r = _receipt(AUTH_DIFF, judges=(("Security Reviewer", "revise"),))
    assert not check_commit(AUTH_DIFF, r, "feat: x").ok
