"""Privacy scan: keep private terms out of git and out of GitHub.

The denylist is a LOCAL, untracked file (``<main checkout>/.agents/denylist.txt``):
one term or regex per line, ``#`` comments, case-insensitive, whole-word match.
``<main checkout>/.agents/allowlist.txt`` lists exact strings that are exempted.

Overrides: ``REDACTECH_DENYLIST`` (newline-separated terms, used by CI),
``REDACTECH_DENYLIST_FILE`` (path), ``REDACTECH_ALLOWLIST`` (newline-separated).

Content with a NUL byte in its first 8 KiB (binary, UTF-16) is not scanned; names always are.

Every report is masked: a matched term is replaced by ``***`` and never printed.

CLI::

    python tools/privacy.py scan [--staged | --tracked | --text-file FILE]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

MASK = "***"
ENV_TERMS = "REDACTECH_DENYLIST"
ENV_FILE = "REDACTECH_DENYLIST_FILE"
ENV_ALLOW = "REDACTECH_ALLOWLIST"
MAX_EXCERPT = 160
NO_DENYLIST_NOTICE = (
    "privacy: NOTICE - no denylist available (set REDACTECH_DENYLIST, REDACTECH_DENYLIST_FILE "
    "or create .agents/denylist.txt in the main checkout); scan skipped."
)


@dataclass(frozen=True)
class Match:
    """One hit. ``source`` and ``excerpt`` are already masked."""

    source: str
    line: int
    excerpt: str

    def __str__(self) -> str:
        return f"{self.source}:{self.line}: {self.excerpt}"


# --- git helpers -----------------------------------------------------------------


def run_git(*args: str, cwd: Path | str | None = None, check: bool = True) -> bytes:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=cwd,
        capture_output=True,
    )
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.decode('utf-8', 'replace')}")
    return res.stdout


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def git_common_dir(cwd: Path | str | None = None) -> Path | None:
    base = Path(cwd) if cwd else Path.cwd()
    res = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=base, capture_output=True
    )
    if res.returncode != 0:
        return None
    # Decode as UTF-8 explicitly: the Windows locale codec would garble accented paths.
    common = Path(_decode(res.stdout).strip())
    return (common if common.is_absolute() else base / common).resolve()


def main_checkout(cwd: Path | str | None = None) -> Path | None:
    """Root of the main checkout (parent of the git common dir), from any worktree."""
    common = git_common_dir(cwd)
    return common.parent if common else None


# --- loading -----------------------------------------------------------------------


def _parse_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _read_lines(path: Path) -> list[str]:
    return _parse_lines(path.read_text(encoding="utf-8"))


def load_denylist(cwd: Path | str | None = None) -> list[str] | None:
    """Return the terms, or ``None`` if no denylist is available."""
    env = os.environ.get(ENV_TERMS)
    if env is not None:
        terms = _parse_lines(env)
        return terms or None
    file_env = os.environ.get(ENV_FILE)
    if file_env:
        path = Path(file_env)
        return _read_lines(path) if path.is_file() else None
    root = main_checkout(cwd)
    if root is None:
        return None
    path = root / ".agents" / "denylist.txt"
    return _read_lines(path) if path.is_file() else None


def load_allowlist(cwd: Path | str | None = None) -> list[str]:
    env = os.environ.get(ENV_ALLOW)
    if env is not None:
        return _parse_lines(env)
    root = main_checkout(cwd)
    if root is None:
        return []
    path = root / ".agents" / "allowlist.txt"
    return _read_lines(path) if path.is_file() else []


# --- scanning ----------------------------------------------------------------------


def _compile(term: str) -> re.Pattern[str]:
    for body in (term, re.escape(term)):
        try:
            # Whole word; "_" counts as a separator (file names such as "x_term.txt").
            return re.compile(rf"(?<![^\W_])(?:{body})(?![^\W_])", re.IGNORECASE)
        except re.error:
            continue
    raise AssertionError("unreachable")  # re.escape always compiles


def _spans(
    line: str, patterns: Sequence[re.Pattern[str]], allow: Sequence[str]
) -> list[tuple[int, int]]:
    allowed: list[tuple[int, int]] = []
    for a in allow:
        start = line.find(a)
        while a and start != -1:
            allowed.append((start, start + len(a)))
            start = line.find(a, start + 1)
    spans = []
    for pat in patterns:
        for m in pat.finditer(line):
            if m.end() == m.start():
                continue
            if any(s <= m.start() and m.end() <= e for s, e in allowed):
                continue
            spans.append((m.start(), m.end()))
    return spans


def _mask_spans(line: str, spans: list[tuple[int, int]]) -> str:
    merged: list[list[int]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    for s, e in reversed(merged):
        line = line[:s] + MASK + line[e:]
    line = line.strip()
    return line if len(line) <= MAX_EXCERPT else line[: MAX_EXCERPT - 1] + "…"


def mask_text(text: str, terms: Sequence[str], allow: Sequence[str] = ()) -> str:
    """Return ``text`` with every denylisted term replaced by ``***``."""
    patterns = [_compile(t) for t in terms]
    return _mask_spans(text, _spans(text, patterns, allow)) if text else text


def scan_text(
    text: str, terms: Sequence[str], allow: Sequence[str] = (), source: str = ""
) -> list[Match]:
    """Scan ``text`` line by line. ``source`` must already be masked."""
    patterns = [_compile(t) for t in terms]
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        spans = _spans(line, patterns, allow)
        if spans:
            hits.append(Match(source, number, _mask_spans(line, spans)))
    return hits


def scan_named_content(
    name: str,
    data: bytes | None,
    terms: Sequence[str],
    allow: Sequence[str] = (),
) -> list[Match]:
    """Scan a file name and, unless it looks binary, its content."""
    name_spans = _spans(name, [_compile(t) for t in terms], allow)
    label = _mask_spans(name, name_spans) if name_spans else name
    hits = []
    if name_spans:
        hits.append(Match(label, 0, label))
    if data is not None and b"\0" not in data[:8192]:
        hits.extend(scan_text(_decode(data), terms, allow, source=label))
    return hits


def scan_paths(
    paths: Iterable[Path | str],
    terms: Sequence[str],
    allow: Sequence[str] = (),
    root: Path | str | None = None,
) -> list[Match]:
    """Scan files on disk (names relative to ``root`` and contents)."""
    base = Path(root) if root else Path.cwd()
    hits: list[Match] = []
    for p in paths:
        path = Path(p)
        full = path if path.is_absolute() else base / path
        try:
            rel = full.relative_to(base).as_posix()
        except ValueError:
            rel = full.name
        data = full.read_bytes() if full.is_file() else None
        hits.extend(scan_named_content(rel, data, terms, allow))
    return hits


def staged_files(cwd: Path | str | None = None) -> list[str]:
    out = run_git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", cwd=cwd)
    return [_decode(p) for p in out.split(b"\0") if p]


def scan_staged(
    cwd: Path | str | None, terms: Sequence[str], allow: Sequence[str] = ()
) -> list[Match]:
    """Scan the staged blobs (index content, not the working tree) and staged names."""
    hits: list[Match] = []
    for name in staged_files(cwd):
        data = run_git("show", f":{name}", cwd=cwd, check=False)
        hits.extend(scan_named_content(name, data, terms, allow))
    return hits


def scan_tracked(
    cwd: Path | str | None, terms: Sequence[str], allow: Sequence[str] = ()
) -> list[Match]:
    root = Path(_decode(run_git("rev-parse", "--show-toplevel", cwd=cwd)).strip())
    names = [_decode(p) for p in run_git("ls-files", "-z", cwd=cwd).split(b"\0") if p]
    return scan_paths(names, terms, allow, root=root)


# --- reporting ---------------------------------------------------------------------


def report(matches: Sequence[Match], stream=None) -> int:
    """Print masked hits; return the exit code (1 if any)."""
    stream = stream or sys.stderr
    if not matches:
        return 0
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure:  # piped stderr uses the locale codec on Windows: never crash on output
        reconfigure(errors="replace")
    print(f"privacy: {len(matches)} hit(s) on denylisted terms (masked):", file=stream)
    for m in matches:
        print(f"  {m}", file=stream)
    return 1


def check(scanner: Callable[[Sequence[str], Sequence[str]], list[Match]], cwd=None) -> int:
    """Load denylist/allowlist, run ``scanner(terms, allow)``, report. 0 if no denylist."""
    terms = load_denylist(cwd)
    if terms is None:
        print(NO_DENYLIST_NOTICE, file=sys.stderr)
        return 0
    return report(scanner(terms, load_allowlist(cwd)))


# --- CLI ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    scan = sub.add_parser("scan", help="scan for denylisted terms")
    group = scan.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="staged blobs and names")
    group.add_argument("--tracked", action="store_true", help="all tracked files (default)")
    group.add_argument("--text-file", metavar="F", help="a text file ('-' for stdin)")
    args = parser.parse_args(argv)

    if args.text_file:
        if args.text_file == "-":
            text = sys.stdin.read()
        else:
            text = Path(args.text_file).read_text(encoding="utf-8", errors="replace")
        label = "<stdin>" if args.text_file == "-" else Path(args.text_file).name
        return check(lambda t, a: scan_text(text, t, a, source=mask_text(label, t, a)))
    if args.staged:
        return check(lambda t, a: scan_staged(None, t, a))
    return check(lambda t, a: scan_tracked(None, t, a))


if __name__ == "__main__":
    sys.exit(main())
