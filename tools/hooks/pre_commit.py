"""pre-commit hook: scan staged blobs (index content) and staged file names."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import privacy  # noqa: E402


def main() -> int:
    code = privacy.check(lambda terms, allow: privacy.scan_staged(None, terms, allow))
    if code:
        print("privacy: commit refused (unstage or rewrite the masked content).", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
