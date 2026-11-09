"""Rebuild the public S1000D data (Bike data sets, BREX, flat XSDs) under ``data/``.

Inputs (read-only, never modified): ``S1000D Issue 4.1.zip`` and ``S1000D Issue 4.2.zip``
at the repository root (default: the main checkout). Output (ignored by git)::

    data/s1000d-4.1/{bike,brex,schemas}
    data/s1000d-4.2/{bike,brex,schemas}

Layout of the archives (checked with ``zipfile`` listings), matched case-insensitively:

* Bike data set 4.1: ``.../Bike data set/S1000D_4-1_Bike_Samples.zip`` (nested zip, all files).
* Bike data set 4.2: files in ``.../Bike Sample Data Set/Bike Data Set for Issue 4.2/``.
* BREX: the bike ``*-022A-D_*.XML`` is copied to ``brex/`` too (it stays in ``bike/``); the default
  BREX is the XML found in the nested zip (or directly) in ``.../Default BREX data module/``.
* Schemas: ``*.xsd`` of the folder named ``xml_schema_flat`` (not the copies under ``Patches`` or
  ``Data Dictionary``).

Files are flattened (base name only). Members with an absolute path, a drive letter or ``..`` are
refused (zip-slip) before anything is written. Re-running is idempotent. ``--dry-run`` lists only.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import privacy  # noqa: E402

ARCHIVES = {"4.1": "S1000D Issue 4.1.zip", "4.2": "S1000D Issue 4.2.zip"}
BREX_NAME = re.compile(r"-022[A-Z]-[A-Z]_.*\.xml$", re.IGNORECASE)


class UnsafeArchiveError(ValueError):
    """An archive member would be extracted outside the destination."""


@dataclass
class Item:
    dest: Path
    read: Callable[[], bytes]
    src: str


def _parts(name: str) -> list[str]:
    return name.replace("\\", "/").split("/")


def check_member(name: str) -> None:
    """Refuse absolute paths, drive letters and parent references."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise UnsafeArchiveError(f"absolute path in archive: {name!r}")
    if ".." in _parts(normalized):
        raise UnsafeArchiveError(f"parent reference in archive: {name!r}")


def _folder(name: str) -> str:
    parts = _parts(name)
    return parts[-2].lower() if len(parts) > 1 else ""


def _is_file(name: str) -> bool:
    return not name.endswith(("/", "\\"))


def _base(name: str) -> str:
    return _parts(name)[-1]


class _Plan:
    def __init__(self, version_dir: Path) -> None:
        self.dirs = {kind: version_dir / kind for kind in ("bike", "brex", "schemas")}
        self.items: dict[Path, Item] = {}

    def add(self, kind: str, member: str, read: Callable[[], bytes], src: str) -> None:
        check_member(member)
        dest = self.dirs[kind] / _base(member)
        if dest in self.items:
            raise ValueError(f"two archive members map to {dest.name}: {src}")
        self.items[dest] = Item(dest, read, src)


def _add_bike_file(plan: _Plan, member: str, read: Callable[[], bytes], src: str) -> None:
    plan.add("bike", member, read, src)
    if BREX_NAME.search(_base(member)):
        plan.add("brex", member, read, src)


def _reader(zf: zipfile.ZipFile, member: str) -> Callable[[], bytes]:
    return lambda: zf.read(member)


def build_plan(archive: Path, version: str, data_dir: Path) -> _Plan:
    plan = _Plan(data_dir / f"s1000d-{version}")
    outer = zipfile.ZipFile(archive)
    for name in outer.namelist():
        if not _is_file(name):
            continue
        low = [p.lower() for p in _parts(name)]
        in_patches = any(p.startswith("patch") or p == "data dictionary" for p in low)
        folder = _folder(name)
        src = f"{archive.name}:{name}"
        if folder == "xml_schema_flat" and name.lower().endswith(".xsd") and not in_patches:
            plan.add("schemas", name, _reader(outer, name), src)
        elif folder == "bike data set" and name.lower().endswith(".zip"):
            check_member(name)
            inner = zipfile.ZipFile(io.BytesIO(outer.read(name)))
            for member in inner.namelist():
                if _is_file(member):
                    _add_bike_file(plan, member, _reader(inner, member), f"{src}!{member}")
        elif folder.startswith("bike data set for issue") and not in_patches:
            _add_bike_file(plan, name, _reader(outer, name), src)
        elif folder == "default brex data module" and not in_patches:
            if name.lower().endswith(".zip"):
                check_member(name)
                inner = zipfile.ZipFile(io.BytesIO(outer.read(name)))
                for member in inner.namelist():
                    if _is_file(member) and member.lower().endswith(".xml"):
                        plan.add("brex", member, _reader(inner, member), f"{src}!{member}")
            elif name.lower().endswith(".xml"):
                plan.add("brex", name, _reader(outer, name), src)
    return plan


def run(archives_dir: Path, data_dir: Path, dry_run: bool = False) -> dict[str, Counter]:
    """Extract what the available archives provide. Returns counts per destination folder."""
    plans = []
    for version, filename in ARCHIVES.items():
        archive = archives_dir / filename
        if archive.is_file():
            plans.append(build_plan(archive, version, data_dir))  # all plans built before writing
    summary: dict[str, Counter] = {}
    for plan in plans:
        for kind_dir in plan.dirs.values():
            summary.setdefault(kind_dir.relative_to(data_dir).as_posix(), Counter())
        for dest, item in plan.items.items():
            counts = summary[dest.parent.relative_to(data_dir).as_posix()]
            data = item.read()
            if not dest.exists():
                counts["new"] += 1
            elif dest.read_bytes() == data:
                counts["unchanged"] += 1
                continue
            else:
                counts["updated"] += 1
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
    return summary


def format_summary(summary: dict[str, Counter], dry_run: bool) -> str:
    lines = ["dry run, nothing written:" if dry_run else "extracted:"]
    for folder in sorted(summary):
        c = summary[folder]
        lines.append(
            f"  data/{folder}: {c['new']} new, {c['updated']} updated, {c['unchanged']} unchanged"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild data/ from the two public S1000D archives.")
    parser.add_argument("--archives-dir", type=Path, help="folder with the two zips (main checkout)")
    parser.add_argument("--data-dir", type=Path, help="output folder (<main checkout>/data)")
    parser.add_argument("--dry-run", action="store_true", help="list what would be extracted")
    args = parser.parse_args(argv)

    root = privacy.main_checkout()
    archives_dir = args.archives_dir or root
    data_dir = args.data_dir or (root / "data" if root else None)
    if archives_dir is None or data_dir is None:
        print("setup_data: cannot find the main checkout; pass --archives-dir and --data-dir")
        return 1
    present = [f for f in ARCHIVES.values() if (archives_dir / f).is_file()]
    if not present:
        print(f"setup_data: no archive found in {archives_dir} (expected {list(ARCHIVES.values())})")
        return 1
    try:
        summary = run(archives_dir, data_dir, args.dry_run)
    except UnsafeArchiveError as exc:
        print(f"setup_data: refused, nothing written: {exc}")
        return 2
    print(format_summary(summary, args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
