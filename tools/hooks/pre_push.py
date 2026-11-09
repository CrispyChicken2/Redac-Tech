"""pre-push hook: scan what is about to leave the machine.

Reads git's stdin lines ``<local ref> <local sha> <remote ref> <remote sha>``. For each pushed
ref it scans the ref names and, for the new commits, their messages and diffs. Works with no
remote configured.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import privacy  # noqa: E402

ZERO = "0" * 40


def _new_commits(local_sha: str, remote_sha: str) -> list[str]:
    if set(remote_sha) != {"0"}:
        known = subprocess.run(
            ["git", "cat-file", "-e", f"{remote_sha}^{{commit}}"], capture_output=True
        )
        if known.returncode == 0:
            out = privacy.run_git("rev-list", f"{remote_sha}..{local_sha}")
            return privacy._decode(out).split()
    out = privacy.run_git("rev-list", local_sha, "--not", "--remotes")
    return privacy._decode(out).split()


def scan_push(lines: list[str], terms, allow) -> list[privacy.Match]:
    hits: list[privacy.Match] = []
    seen: set[str] = set()
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts
        for ref in (local_ref, remote_ref):
            hits.extend(privacy.scan_named_content(ref, None, terms, allow))
        if set(local_sha) == {"0"}:  # deletion: nothing to scan
            continue
        if local_ref.startswith("refs/tags/"):  # annotated tag message
            kind = privacy._decode(privacy.run_git("cat-file", "-t", local_sha, check=False))
            if kind.strip() == "tag":
                body = privacy._decode(privacy.run_git("cat-file", "tag", local_sha))
                hits.extend(privacy.scan_text(body, terms, allow, source="tag object"))
        for sha in _new_commits(local_sha, remote_sha):
            if sha in seen:
                continue
            seen.add(sha)
            label = f"commit {sha[:8]}"
            message = privacy._decode(privacy.run_git("log", "-1", "--format=%B", sha))
            hits.extend(privacy.scan_text(message, terms, allow, source=f"{label} message"))
            diff = privacy.run_git("show", "--format=", "--patch", "--root", "--no-color", sha)
            hits.extend(privacy.scan_text(privacy._decode(diff), terms, allow, source=f"{label} diff"))
    return hits


def main() -> int:
    lines = sys.stdin.read().splitlines()
    code = privacy.check(lambda terms, allow: scan_push(lines, terms, allow))
    if code:
        print("privacy: push refused.", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
