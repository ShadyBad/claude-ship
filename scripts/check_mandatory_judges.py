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
        for match in SECURITY_SEMANTICS.findall(line):
            hits.add(f"semantic:{match.strip().lower()}")
    return hits


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
        if re.search(rf"(?:^|\s){MANDATORY_JUDGE}(?:\s|$)", name) and verdict in REPORTED:
            return Verdict(True, f"security judge reported: {verdict}")

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

    root = pathlib.Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    diff = subprocess.run(
        ["git", "diff", "--cached"], capture_output=True, text=True, check=True
    ).stdout
    receipt_path = root / ".assay" / "judge-receipt.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None

    verdict = check_commit(diff, receipt, pathlib.Path(argv[1]).read_text())
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
        print(f"mandatory-judge gate errored, failing closed: {exc!r}", file=sys.stderr)
        sys.exit(2)
