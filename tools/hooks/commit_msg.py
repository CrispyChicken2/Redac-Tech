"""commit-msg hook: scan the whole commit message file."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import privacy  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: commit_msg.py <message-file>", file=sys.stderr)
        return 2
    # Whole file: `git commit -m/-F` keeps lines starting with "#" (e.g. "#12 ..."), so no filter.
    text = Path(argv[1]).read_text(encoding="utf-8", errors="replace")
    code = privacy.check(lambda t, a: privacy.scan_text(text, t, a, source="commit message"))
    if code:
        print("privacy: commit message refused.", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
