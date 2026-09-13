"""Mint the judge receipt the commit gate checks.

Called at the end of /assay Step 8, after the final revise cycle. The receipt is
keyed to `git diff --cached`, so the changeset must already be staged: a receipt
minted before the last edit describes a diff that no longer exists, and the gate
will correctly refuse it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

RECEIPT = pathlib.Path(".assay/judge-receipt.json")


def main(state_path: str) -> int:
    """Mint a receipt from a run's state. The state path is required.

    It was briefly optional, and the no-argument branch minted a valid-hash
    receipt carrying `judges: []` -- which can only ever produce a block, so
    every security-tagged commit would be routed to the trailer escape and the
    gate would measure itself as a 100% false-positive detector. Two judges
    caught it. A receipt that cannot testify to anything is worse than no
    receipt, because it looks like one.
    """
    state = json.loads(pathlib.Path(state_path).read_text(encoding="utf-8", errors="replace"))
    judges = [
        {"judge": j.get("judge", ""), "verdict": j.get("verdict", "")}
        for j in state.get("judges", [])
    ]
    if not judges:
        print(
            f"write_judge_receipt: {state_path} records no judges; "
            "refusing to mint an empty receipt",
            file=sys.stderr,
        )
        return 1

    # Third instance of this call in the tree. Without `errors=` a staged diff
    # containing one non-UTF-8 byte crashes here, so a receipt could never be
    # minted for it -- the gate would then refuse that commit forever with no
    # way forward but the trailer.
    diff = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    ).stdout
    if not diff:
        print("write_judge_receipt: nothing staged; stage the changeset first", file=sys.stderr)
        return 1

    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(
        json.dumps(
            {
                "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
                "judges": judges,
                "ts": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"write_judge_receipt: {len(judges)} judge(s) -> {RECEIPT}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: write_judge_receipt.py <path to session state.json>", file=sys.stderr)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
