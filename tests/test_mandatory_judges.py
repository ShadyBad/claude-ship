"""The commit gate: a mandatory judge must have actually reported.

Spec: judge-enforcement-model-2026-09-12. The threat is an agent that skipped a
step, not one that forges a receipt, so the receipt is keyed to the staged diff
and an absent or stale one blocks.
"""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib

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


# Credential fixtures are ASSEMBLED AT RUNTIME, never written as literals.
# GitHub push protection classified a literal `sk_live_...` fixture here as a
# real Stripe key and refused the push -- correctly, since a credential-shaped
# literal in a repo is a liability whether or not it is live. Building them
# from parts keeps the detector under test while leaving no scannable token on
# disk. Independent confirmation that the shape matching works, incidentally.
_FAKE = {
    "github": "ghp_" + "F" * 36,
    "aws": "AKIA" + "Q" * 16,
    "stripe": "sk_" + "live_" + "0" * 24,
    "slack": "xoxb-" + "1" * 12 + "-" + "z" * 12,
}


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


@pytest.mark.parametrize(
    "line",
    [
        f'GITHUB_TOKEN = "{_FAKE["github"]}"',
        f'AWS = "{_FAKE["aws"]}"',
        f'S = "{_FAKE["stripe"]}"',
        "-----BEGIN RSA PRIVATE KEY-----",
        f'SLACK = "{_FAKE["slack"]}"',
    ],
)
def test_bare_credential_shapes_are_detected(line):
    """A secret pasted with no identifier name carries none of the keywords.

    `GITHUB_TOKEN = "ghp_..."` happens to contain `token`, but the shape match
    is what catches the case where the variable is called `x` -- an entire
    class of leak the keyword scan cannot see by construction.
    """
    diff = f"diff --git a/c.py b/c.py\n--- a/c.py\n+++ b/c.py\n@@ -1 +1,2 @@\n x\n+{line}\n"
    assert detect_security_relevance(diff), f"missed credential shape: {line}"


def test_credential_shape_survives_an_innocuous_variable_name():
    """The keyword scan cannot help here; only the shape match can."""
    diff = (
        "diff --git a/c.py b/c.py\n--- a/c.py\n+++ b/c.py\n@@ -1 +1,2 @@\n x\n"
        f'+x = "{_FAKE["github"]}"\n'
    )
    hits = detect_security_relevance(diff)
    assert any(h.startswith("shape:") for h in hits), f"shape match did not fire: {hits}"


def test_shapes_do_not_fire_on_prose_or_hashes():
    diff = (
        "diff --git a/a.md b/a.md\n--- a/a.md\n+++ b/a.md\n@@ -1 +1,2 @@\n x\n"
        "+See commit a970ea4 and the BEGIN section of the README.\n"
    )
    assert not detect_security_relevance(diff)


def test_refusing_security_verdict_names_the_actual_state():
    """'no security judge verdict' described the wrong state when judge 2 ran
    and asked for changes. Logged as a nit on the approve round, applied here."""
    r = _receipt(AUTH_DIFF, judges=(("Security Reviewer", "block"),))
    v = check_commit(AUTH_DIFF, r, "feat: x")
    assert not v.ok
    assert "does not license a commit" in v.reason
    assert "no security judge verdict" not in v.reason

    absent = _receipt(AUTH_DIFF, judges=(("Simplicity Judge", "approve"),))
    assert "no security judge verdict" in check_commit(AUTH_DIFF, absent, "feat: x").reason


def test_evidence_never_echoes_credential_material():
    """The evidence string is printed to stderr from a git hook.

    A secret scanner that echoes even a prefix of what it found leaks the thing
    it exists to protect, into terminal scrollback and CI logs.
    """
    secret = _FAKE["github"]
    diff = f'diff --git a/c.py b/c.py\n--- a/c.py\n+++ b/c.py\n@@ -1 +1,2 @@\n x\n+x = "{secret}"\n'
    hits = detect_security_relevance(diff)
    assert hits, "shape not detected at all"
    joined = " ".join(hits)
    assert "shape:github-pat" in joined, f"shape not named: {hits}"
    for size in (12, 8, 6):
        assert secret[:size] not in joined, f"evidence leaks {size} chars of the credential"

    verdict = check_commit(diff, None, "feat: x")
    assert not verdict.ok
    assert secret[:6] not in verdict.reason, "block message leaks credential material"


def test_gitleaks_escalation_is_actually_wired(monkeypatch):
    """This escalation shipped as dead code once: defined, documented, never
    called. A control that does not execute is the failure this module exists
    to close, so the wiring itself is asserted rather than assumed."""
    import check_mandatory_judges as mod

    clean = (
        "diff --git a/notes.md b/notes.md\n--- a/notes.md\n+++ b/notes.md\n@@ -1 +1,2 @@\n x\n"
        "+an ordinary sentence\n"
    )
    assert not detect_security_relevance(clean), "fixture is not keyword-clean"

    monkeypatch.setattr(mod, "_gitleaks_flags", lambda _diff: True)
    assert detect_security_relevance(clean) == {"gitleaks flagged the staged diff"}

    monkeypatch.setattr(mod, "_gitleaks_flags", lambda _diff: False)
    assert not detect_security_relevance(clean)


def test_gitleaks_is_not_consulted_once_the_diff_is_already_flagged(monkeypatch):
    """It costs a subprocess and adds nothing to an already-flagged diff."""
    import check_mandatory_judges as mod

    called = []
    monkeypatch.setattr(mod, "_gitleaks_flags", lambda d: called.append(d) or True)
    detect_security_relevance(AUTH_DIFF)
    assert not called, "gitleaks ran even though the regex floor already fired"


def test_gitleaks_absent_binary_is_not_a_hit(monkeypatch):
    """Optional by design: a machine without gitleaks keeps the regex floor."""
    import check_mandatory_judges as mod

    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert mod._gitleaks_flags("+anything at all") is False


def test_gitleaks_misbehaviour_always_over_detects(monkeypatch):
    """Every way the subprocess can fail must land on the same branch.

    `(OSError, SubprocessError)` missed UnicodeDecodeError, which escaped to the
    module-level handler and printed a recovery block naming a corrupt receipt —
    sending the operator to delete a healthy one.
    """
    import subprocess

    import check_mandatory_judges as mod

    monkeypatch.setattr("shutil.which", lambda _n: "/usr/bin/gitleaks")
    for boom in (
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
        OSError("no such binary"),
        subprocess.TimeoutExpired(cmd="gitleaks", timeout=20),
        RuntimeError("something else entirely"),
    ):

        def raise_it(*_a, _e=boom, **_k):
            raise _e

        monkeypatch.setattr(subprocess, "run", raise_it)
        assert mod._gitleaks_flags("+x") is True, f"{type(boom).__name__} did not over-detect"


def test_binary_diff_never_reaches_the_handler_or_stderr(tmp_path):
    """One non-UTF-8 byte in a staged diff must not dump the diff to stderr.

    UnicodeDecodeError's repr embeds the entire offending bytes object, so a
    `text=True` read without `errors=` turns a decode failure into full
    disclosure of the staged diff — credentials included.
    """
    import subprocess

    secret = _FAKE["stripe"]
    repo = tmp_path / "r"
    repo.mkdir()
    root = pathlib.Path(__file__).resolve().parent.parent
    run = lambda *a: subprocess.run(a, cwd=repo, capture_output=True, text=True)  # noqa: E731
    run("git", "init", "-q", ".")
    run("git", "config", "user.email", "t@t.t")
    run("git", "config", "user.name", "t")
    (repo / "seed.txt").write_text("seed\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "seed\n\nSecurity-Review: skipped -- fixture")
    (repo / "bin.dat").write_bytes(b"\xff cfg = " + secret.encode() + b"\n")
    run("git", "add", "-A")

    done = subprocess.run(
        ["python3", str(root / "scripts" / "check_mandatory_judges.py"), "/dev/null"],
        cwd=repo,
        capture_output=True,
        text=True,
        errors="replace",
    )
    assert secret not in done.stderr, "staged credential was echoed to stderr"
    assert secret not in done.stdout
    assert "UnicodeDecodeError" not in done.stderr, "decode error escaped to the handler"
