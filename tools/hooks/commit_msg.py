"""commit-msg hook: scan the commit message file (git comment lines are ignored)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import privacy  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: commit_msg.py <message-file>", file=sys.stderr)
        return 2
    raw = Path(argv[1]).read_text(encoding="utf-8", errors="replace")
    text = "\n".join(line for line in raw.splitlines() if not line.startswith("#"))
    code = privacy.check(lambda t, a: privacy.scan_text(text, t, a, source="commit message"))
    if code:
        print("privacy: commit message refused.", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
