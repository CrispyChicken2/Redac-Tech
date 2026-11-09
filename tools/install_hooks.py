"""Install the privacy git hooks into ``<git-common-dir>/hooks/`` (shared by all worktrees).

Each hook is a small ``#!/bin/sh`` wrapper that finds the current worktree, then runs the
Python hook with the first working interpreter among ``py -3``, ``python3``, ``python``.
Idempotent; a foreign hook already present is kept as ``<name>.orig``.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import privacy  # noqa: E402

MARKER = "# redactech-privacy-hook"
HOOKS = {
    "pre-commit": "pre_commit.py",
    "commit-msg": "commit_msg.py",
    "pre-push": "pre_push.py",
}

TEMPLATE = """#!/bin/sh
{marker}
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
hook="$root/tools/hooks/{script}"
if [ ! -f "$hook" ]; then
  echo "privacy hook: $hook not found, check skipped" >&2
  exit 0
fi
if command -v py >/dev/null 2>&1 && py -3 -c "" >/dev/null 2>&1; then
  exec py -3 "$hook" "$@"
fi
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c "" >/dev/null 2>&1; then
    exec "$py" "$hook" "$@"
  fi
done
echo "privacy hook: no Python interpreter found (py -3, python3, python); refusing." >&2
exit 1
"""


def install(cwd: Path | str | None = None) -> list[Path]:
    common = privacy.git_common_dir(cwd)
    if common is None:
        raise SystemExit("install_hooks: not inside a git repository")
    hooks_dir = common / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, script in HOOKS.items():
        target = hooks_dir / name
        if target.exists():
            current = target.read_text(encoding="utf-8", errors="replace")
            if MARKER not in current:
                target.replace(hooks_dir / f"{name}.orig")
        target.write_text(
            TEMPLATE.format(marker=MARKER, script=script), encoding="utf-8", newline="\n"
        )
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(target)
    return written


def main() -> int:
    for path in install():
        print(f"installed {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
