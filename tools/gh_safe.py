"""Wrapper for ``gh``: privacy-scan every argument and body file before calling it.

On a hit, masked matches are printed and the exit code is 1 (gh is not called).
Without any denylist the call is refused too (publishing is outward-facing), unless
``GH_SAFE_ALLOW_NO_DENYLIST=1``. The gh executable can be replaced with ``GH_SAFE_GH``
(a ``.py`` file is run with the current interpreter), which is how tests inject a fake.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import privacy  # noqa: E402

FILE_FLAGS = ("--body-file", "-F", "--input")


def _gh_command() -> list[str]:
    exe = os.environ.get("GH_SAFE_GH", "gh")
    return [sys.executable, exe] if exe.lower().endswith(".py") else [exe]


def _file_args(args: Sequence[str]) -> tuple[list[str], bool]:
    """Return (paths of files whose content gh will read, stdin_is_read)."""
    files: list[str] = []
    stdin = False
    i = 0
    while i < len(args):
        arg = args[i]
        value = None
        for flag in FILE_FLAGS:
            if arg == flag and i + 1 < len(args):
                value = args[i + 1]
                i += 1
            elif arg.startswith(flag + "="):
                value = arg[len(flag) + 1 :]
        if value is not None:
            if value == "-" or value.endswith("=@-"):
                stdin = True
            elif "=@" in value:  # `gh api -F key=@file`
                files.append(value.split("=@", 1)[1])
            else:
                files.append(value)
        i += 1
    return files, stdin


def run(args: Sequence[str]) -> int:
    terms = privacy.load_denylist()
    if terms is None:
        print(privacy.NO_DENYLIST_NOTICE, file=sys.stderr)
        if os.environ.get("GH_SAFE_ALLOW_NO_DENYLIST") != "1":
            print("gh_safe: refusing to call gh without a denylist.", file=sys.stderr)
            return 1
    allow = privacy.load_allowlist()
    hits: list[privacy.Match] = []
    stdin_data: str | None = None
    if terms is not None:
        for n, arg in enumerate(args):
            hits.extend(privacy.scan_text(arg, terms, allow, source=f"argument {n}"))
        files, wants_stdin = _file_args(args)
        for f in files:
            path = Path(f)
            if path.is_file():
                hits.extend(privacy.scan_named_content(path.name, path.read_bytes(), terms, allow))
        if wants_stdin:
            stdin_data = sys.stdin.read()
            hits.extend(privacy.scan_text(stdin_data, terms, allow, source="stdin"))
    if hits:
        privacy.report(hits)
        print("gh_safe: gh not called.", file=sys.stderr)
        return 1
    result = subprocess.run(
        [*_gh_command(), *args], input=stdin_data, text=stdin_data is not None
    )
    return result.returncode


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
