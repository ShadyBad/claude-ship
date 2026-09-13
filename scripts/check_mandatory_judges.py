"""Decide whether a commit may proceed without a mandatory judge's verdict.

Spec: judge-enforcement-model-2026-09-12.

The pipeline's Hard Constraints are absolutes ("NEVER skip the Security
Reviewer ... regardless of tier or override") enforced entirely by prose that
an agent reads. Five review rounds found five distinct live paths from a
security-relevant diff to a commit with judge 2 never dispatched, because prose
enforcing prose has no failure signal.

This module is the check that does. It is pure: the git hook gathers the three
inputs and acts on the Verdict, so every rule below is testable from a table.

Threat model is an agent that skipped a step, NOT one that forges a receipt.
A receipt keyed to the staged diff defeats the former completely and the latter
not at all, which is the honest claim.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys
from dataclasses import dataclass

#: Judge that must have reported when the detector fires. Judge 2 in the roster.
MANDATORY_JUDGE = "security"

#: Verdicts that license a commit. `block` is deliberately NOT here: this hook
#: is the only place the floor is actually enforced, so treating a recorded
#: block as "attended, therefore proceed" would enforce attendance instead of
#: outcome. Aggregation rule 0 asks "did it report"; the gate asks "may this
#: commit".
REPORTED = frozenset({"approve", "nit"})

#: Panel-level words that may leak into a per-judge verdict field, mapped to the
#: per-judge vocabulary. state.json has carried `revise` in a judge slot before.
#:
#: `revise` deliberately maps to `block`, not `nit`: it means the security judge
#: asked for changes. Since the receipt is hash-keyed to the staged diff, a
#: `revise` that still matches means those changes were never made -- so letting
#: it through would contradict this module's own outcome-not-attendance rule.
VERDICT_ALIASES = {"ship": "approve", "revise": "block"}

#: Path fragments that make a diff security-relevant. Deliberately broad: this
#: detector is meant to be dumber and more conservative than judge-panel's
#: pre-pass, because it must work when that pre-pass never ran.
SECURITY_PATHS = (
    "auth",
    "session",
    "secret",
    "credential",
    "login",
    "oauth",
    "token",
    "crypto",
    "permission",
    "migrations",
    "payment",
    "billing",
)

#: Content appearing on ADDED lines. Removals do not trip the gate -- deleting a
#: credential is the fix, not the defect.
#: `_` is a word character, so `\b(api[_-]?key)\b` never matches `new_api_key`
#: -- and a prefixed identifier is how this appears in real code. A judge
#: reproduced a leaked key committed straight past the gate because of it. The
#: lookarounds below treat `_` as a separator, which `\b` does not.
SECURITY_CONTENT = re.compile(
    r"(?<![A-Za-z0-9])(password|passwd|api[_-]?key|secret|token|authorization"
    r"|bearer|jwt|credential|private[_-]?key|access[_-]?key|signing[_-]?key)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

#: camelCase is the same hole in the other direction: the lookbehind above
#: requires a non-alphanumeric before the keyword, and `clientSecret` has `t`.
#: A judge reproduced `clientSecret = 'sk_live_...'` and `authToken = 'ghp_...'`
#: sailing through after the snake_case fix landed. Case-SENSITIVE by
#: necessity -- an ignorecase pass here would match every occurrence of the
#: bare word again and double-report. The lookbehind admits uppercase so
#: `AWSSecretKey`, `JWTToken` and `DBPassword` are caught too; `hits` is a
#: set keyed on the lowered match, so nothing double-reports.
SECURITY_CAMEL = re.compile(
    r"(?<=[A-Za-z0-9])(Password|Passwd|ApiKey|Secret|Token|Authorization|Bearer"
    r"|Jwt|Credential|PrivateKey|AccessKey|SigningKey)(?![a-z])"
)

#: Known and accepted: `token_limit`, `max_token_count`, and `session_token_ttl`
#: trip `content:token`. That is deliberate. Missing `auth_token` is a
#: fail-open and a stray `token_limit` is an annoyance the trailer clears in one
#: line, so the asymmetry is priced in favour of coverage. The trailer rate in
#: `git log --grep` is what decides whether this judgement was right.

#: Credential shapes that carry no keyword at all. A secret pasted without a
#: variable name -- a bare `ghp_...` in a config line, a PEM header, a JWT --
#: matched nothing above, which is a whole class of leak the keyword scan
#: cannot see by construction. These are prefix/format matches, so they are
#: high precision and effectively never fire on prose.
SECURITY_SHAPES = re.compile(
    r"(ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|sk_live_[A-Za-z0-9]{16,}|rk_live_[A-Za-z0-9]{16,}"
    r"|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}"
    r"|glpat-[A-Za-z0-9_-]{16,})"
)

#: Semantic weakenings that carry none of the words above. A lexical detector
#: cannot be complete -- these are the cheap, common ones, added because a judge
#: named each as a diff that would have sailed through: a permissive CORS
#: default, a disabled TLS check, a digest compared with `==`, a suppression
#: comment over a validation call, a default flipped from deny to allow.
SECURITY_SEMANTICS = re.compile(
    r"(verify\s*=\s*False|check_hostname\s*=\s*False|CERT_NONE"
    r"|allow_origins?\s*=\s*\[?\s*[\"']\*|Access-Control-Allow-Origin"
    r"|#\s*nosec|#\s*type:\s*ignore|eval\(|exec\(|shell\s*=\s*True"
    r"|verify_signature\s*=\s*False|\bdeny\b\s*->|default\s*=\s*[\"']?allow)",
    re.IGNORECASE,
)

_TRAILER = re.compile(r"^Security-Review:\s*skipped\s*--\s*(?P<reason>\S.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Verdict:
    """Outcome of the check. `ok` False means the commit is refused."""

    ok: bool
    reason: str


def _added_lines(staged_diff: str) -> list[str]:
    return [
        ln[1:] for ln in staged_diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")
    ]


def _changed_paths(staged_diff: str) -> list[str] | None:
    r"""Paths in the diff, or None when the header cannot be parsed.

    None is not "no files". Under `diff.noprefix=true`, or for a path containing
    a space, the conventional `^diff --git a/(\S+)` pattern matches nothing --
    and a detector that silently sees zero files inside a fail-closed gate is a
    fail-open. The caller treats None as "assume security-relevant".
    """
    headers = re.findall(r"^diff --git (.+)$", staged_diff, re.MULTILINE)
    if not headers:
        return None if staged_diff.strip() else []

    paths: list[str] = []
    for header in headers:
        # `a/x b/x`, or `x x` under diff.noprefix. Take the first half, which is
        # exactly half the header when both sides name the same path.
        match = re.match(r"^(?:a/)?(.+?) (?:b/)?\1$", header)
        if not match:
            return None
        paths.append(match.group(1))
    return paths


#: Shape -> human name. The evidence string is printed to stderr from a git
#: hook, so it lands in terminal scrollback and CI logs. A secret scanner that
#: echoes even a prefix of the value it found is leaking the thing it exists to
#: protect, so evidence names the pattern and never quotes the match.
_SHAPE_NAMES = (
    ("ghp_", "github-pat"),
    ("gho_", "github-oauth"),
    ("github_pat_", "github-pat"),
    ("sk_live_", "stripe-live-key"),
    ("rk_live_", "stripe-restricted-key"),
    ("AKIA", "aws-access-key"),
    ("ASIA", "aws-temp-key"),
    ("xox", "slack-token"),
    ("-----BEGIN", "private-key-block"),
    ("eyJ", "jwt"),
    ("glpat-", "gitlab-pat"),
)


def _shape_name(match: str) -> str:
    for prefix, name in _SHAPE_NAMES:
        if match.startswith(prefix):
            return name
    return "credential-shape"


def detect_security_relevance(staged_diff: str) -> set[str]:
    """Evidence that this diff is security-relevant, as human-readable strings.

    Never consults a receipt or an agent-supplied tag set. Trusting those is the
    defect this exists to close: a detector that failed emits no tags, so a
    floor conditioned on tags evaporates exactly when detection broke.
    """
    hits: set[str] = set()
    paths = _changed_paths(staged_diff)
    if paths is None:
        return {"unparseable diff header -- assuming security-relevant"}
    for path in paths:
        lowered = path.lower()
        for fragment in SECURITY_PATHS:
            if fragment in lowered:
                hits.add(f"path:{fragment} ({path})")
    for line in _added_lines(staged_diff):
        for match in SECURITY_CONTENT.findall(line):
            hits.add(f"content:{match.lower()}")
        for match in SECURITY_CAMEL.findall(line):
            hits.add(f"content:{match.lower()}")
        for match in SECURITY_SHAPES.findall(line):
            hits.add(f"shape:{_shape_name(match)}")
        for match in SECURITY_SEMANTICS.findall(line):
            hits.add(f"semantic:{match.strip().lower()}")

    # Escalation, only when the cheap scan found nothing: gitleaks costs a
    # subprocess, and there is nothing to add once the diff is already flagged.
    if not hits and _gitleaks_flags(staged_diff):
        hits.add("gitleaks flagged the staged diff")
    return hits


def _gitleaks_flags(staged_diff: str) -> bool:
    """True when gitleaks says this diff carries a secret. False when absent.

    Optional by design: the regex floor above is unconditional, so a machine
    without gitleaks keeps every guarantee this module claims. gitleaks only
    ever ADDS coverage.

    It exits 1 both for "leaks found" and for its own internal errors, which
    cannot be told apart from the exit code. A fail-closed gate resolves that
    the conservative way: treat 1 as security-relevant either way, so an error
    over-detects and the trailer clears it.

    Measured cost on the commit path: ~16ms for a small diff, ~1.2s for a
    3.5MB one. The 20s timeout is only ever charged by a genuine hang.

    Known and unfixable from here: a `gitleaks` shim earlier on PATH that exits
    0 without reading stdin returns False, which is indistinguishable from the
    binary being absent. Verifying the identity of a binary is out of scope for
    a commit hook.
    """
    import shutil
    import subprocess

    if not shutil.which("gitleaks"):
        return False
    try:
        done = subprocess.run(
            ["gitleaks", "stdin", "--no-banner"],
            input=staged_diff,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
        )
    except Exception:  # noqa: BLE001
        # Deliberately bare. `(OSError, SubprocessError)` missed
        # UnicodeDecodeError, which `text=True` raises when the binary writes
        # non-UTF-8 to stdout -- that escaped to the module handler and printed
        # a recovery block naming a corrupt receipt, sending the operator to
        # delete a healthy one. Every way this subprocess can misbehave must
        # land on the same over-detect branch; `errors="replace"` above makes
        # that path unreachable, and this makes the next one harmless too.
        return True  # could not run it: assume the worst, never the best
    return done.returncode != 0


def skip_trailer(commit_msg: str) -> str | None:
    """The recorded escape. Returns the stated reason, or None.

    A trailer with no reason is not an escape -- the whole point is that
    `git log --grep` later shows why, so an empty one buys nothing and is
    refused.
    """
    match = _TRAILER.search(commit_msg or "")
    if not match:
        return None
    reason = match.group("reason").strip()
    return reason or None


def _check_receipt(staged_diff: str, receipt: dict | None) -> Verdict:
    if receipt is None:
        return Verdict(False, "no judge receipt for this commit")
    if not isinstance(receipt, dict):
        return Verdict(False, "receipt is not an object")

    digest = receipt.get("diff_sha256")
    if not isinstance(digest, str) or not digest:
        return Verdict(False, "receipt has no usable diff_sha256")

    judges = receipt.get("judges")
    if not isinstance(judges, list):
        return Verdict(False, "receipt has no judges list")

    actual = hashlib.sha256(staged_diff.encode()).hexdigest()
    if digest != actual:
        return Verdict(False, "receipt is stale: it describes a different diff")

    seen_security: str | None = None
    for entry in judges:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("judge", "")).lower()
        raw = str(entry.get("verdict", "")).lower()
        verdict = VERDICT_ALIASES.get(raw, raw)
        # `\b` is not enough: `-` is a non-word character, so `\bsecurity\b`
        # happily matches "app-security-docs". Requiring whitespace delimiting
        # rejects that. It does NOT narrow to judge 2 alone -- "Data Security
        # Auditor" would also satisfy this, and a hyphenated
        # "security-reviewer" is refused. Neither is reachable from the current
        # roster, where judge 2 is the only entry carrying the word; stated
        # exactly rather than claimed broadly, because a comment promising more
        # than its code is the drift this whole gate exists to stop.
        if re.search(rf"(?:^|\s){MANDATORY_JUDGE}(?:\s|$)", name):
            if verdict in REPORTED:
                return Verdict(True, f"security judge reported: {verdict}")
            # Receipt-controlled and printed to stderr: clamp it so a long or
            # multi-line value cannot forge a banner inside the real one. A
            # forged receipt is outside the threat model, but cheap to bound.
            seen_security = (verdict or "(no verdict)").split("\n")[0][:40]

    if seen_security:
        # "no security judge verdict" would describe the wrong state: the judge
        # ran and refused. The receipt is hash-keyed, so a refusal that still
        # matches means the requested changes were never made.
        return Verdict(
            False, f"security judge verdict is {seen_security}, which does not license a commit"
        )
    return Verdict(False, "no security judge verdict in receipt")


def check_commit(staged_diff: str, receipt: dict | None, commit_msg: str) -> Verdict:
    """Gate one commit. Pure -- the hook supplies the inputs and acts on this.

    Order matters: the receipt is consulted before the trailer so that a trailer
    only counts when it actually rescued a commit. That keeps the
    `git log --grep` false-positive rate honest, which is the measurement the
    spec uses to decide whether this detector survives.
    """
    hits = detect_security_relevance(staged_diff)
    if not hits:
        return Verdict(True, "no security-relevant content in the staged diff")

    verdict = _check_receipt(staged_diff, receipt)
    if verdict.ok:
        return verdict

    reason = skip_trailer(commit_msg)
    if reason:
        return Verdict(True, f"security review skipped by trailer: {reason}")

    evidence = ", ".join(sorted(hits)[:4])
    return Verdict(False, f"{verdict.reason}. Detected: {evidence}")


# --- CLI entry point (git commit-msg hook) -----------------------------------


def _main(argv: list[str]) -> int:
    """Gather the three inputs and act on the Verdict.

    Lives here rather than in a separate module: the sh wrapper exists to catch
    interpreter-absence, and a third file between it and this one would be an
    abstraction for exactly one caller.
    """
    import json
    import subprocess

    if len(argv) < 2:
        print("mandatory-judge gate: no commit message file given", file=sys.stderr)
        return 1

    # Every decode path in this module carries `errors=`, not just the ones that
    # were caught leaking. Relying on the handler's type-name-only print as the
    # sole defence is one layer; this is the other. The missed-twin pattern has
    # recurred twice here, so the rule is now all of them, always.
    root = pathlib.Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            errors="replace",
            check=True,
        ).stdout.strip()
    )
    # `errors="replace"` is not cosmetic. Without it one non-UTF-8 byte in the
    # staged diff raises UnicodeDecodeError, whose repr embeds the ENTIRE
    # offending bytes object -- so the handler below would print the whole
    # staged diff, live credentials and all, to stderr. The gitleaks call above
    # already learned this; this is its twin, missed on the first pass.
    diff = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    ).stdout
    receipt_path = root / ".assay" / "judge-receipt.json"
    receipt = (
        json.loads(receipt_path.read_text(encoding="utf-8", errors="replace"))
        if receipt_path.exists()
        else None
    )

    verdict = check_commit(
        diff, receipt, pathlib.Path(argv[1]).read_text(encoding="utf-8", errors="replace")
    )
    if verdict.ok:
        return 0

    stale = "stale" in verdict.reason
    print(
        "\nBLOCKED by the mandatory-judge gate."
        f"\n  {verdict.reason}\n"
        "\nEither let the security judge run, or record why it was not needed:"
        "\n\n  Security-Review: skipped -- <reason>\n"
        + (
            "\nIf you used `git commit -a` or passed a path, the hook hashes a"
            "\ndifferent index than the receipt does. Re-stage with `git add -A`"
            "\nand re-mint the receipt.\n"
            if stale
            else ""
        ),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    try:
        sys.exit(_main(sys.argv))
    except Exception as exc:  # noqa: BLE001 - fail closed, loudly
        # Exit 2, not 1: the sh wrapper reads 1 as "gate ran and refused" and
        # suppresses its escape text. An internal error must reach that text --
        # a truncated receipt would otherwise block every commit in the repo
        # with a bare JSONDecodeError and no way out.
        # Type name only. An exception's repr can embed whatever payload it was
        # constructed from -- UnicodeDecodeError carries the entire offending
        # byte string -- so printing `{exc!r}` from a gate that inspects secrets
        # is a disclosure channel. Never widen this to repr or str.
        print(
            f"mandatory-judge gate errored, failing closed: {type(exc).__name__}",
            file=sys.stderr,
        )
        sys.exit(2)
