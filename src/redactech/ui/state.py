"""Session helpers of the UI: the project (workspace, index, baseline), uploads, runs.

No streamlit import and no business logic here: every step calls the pipeline (A0), the A1
indexer or the workspace module. The UI keeps one ``Project`` per browser session; uploaded
files live in a session folder under ``runs/_ui/`` (an ``uploads`` source added to a copy of the
workspace file, the original workspace file is never written).
"""

from __future__ import annotations

import datetime
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from redactech.agents import a1_indexer
from redactech.models import CheckResult, SourceRef
from redactech.pipeline import orchestrator as orch
from redactech.s1000d import io as xio
from redactech.s1000d.index import CorpusIndex, ref_key
from redactech.sources import workspace as wsmod

DEFAULT_WORKSPACES = ("workspace.toml", "workspace.example.toml")
SESSION_ROOT = Path("runs") / "_ui"
UPLOAD_SOURCE = "uploads"
MODES = ("none", "in_work", "new_issue")


@dataclass
class Upload:
    """A file the user dropped into the project, and what it was recognised as."""

    name: str
    role: str  # dm | brex | upf | icn | pm | ddn | other
    saved: bool = True
    problem: str = ""


@dataclass
class DocIssues:
    """Pre-existing problems of one data module (counts and the list)."""

    key: str
    name: str
    errors: int = 0
    warnings: int = 0
    items: list[CheckResult] = field(default_factory=list)


@dataclass
class Project:
    base_file: Path
    session_dir: Path
    ws: wsmod.Workspace
    index: CorpusIndex
    baseline: list[CheckResult]
    uploads: list[Upload] = field(default_factory=list)
    brex_swaps: list[Path] = field(default_factory=list)

    @property
    def uploads_dir(self) -> Path:
        return self.session_dir / "uploads"

    @property
    def workspace_file(self) -> Path:
        """The workspace file to start runs with (the session copy once files were added)."""
        copy = self.session_dir / "workspace.toml"
        return copy if copy.is_file() else self.base_file


def default_workspace_path(root: Path | str | None = None) -> str:
    """``workspace.toml`` if it exists, else ``workspace.example.toml`` (else the first name)."""
    base = Path(root) if root is not None else Path.cwd()
    for name in DEFAULT_WORKSPACES:
        if (base / name).is_file():
            return name
    return DEFAULT_WORKSPACES[0]


def new_session_dir(root: Path | str = SESSION_ROOT, now: datetime.datetime | None = None) -> Path:
    """A fresh folder for the uploads and requests of one browser session."""
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    folder = Path(root) / f"{stamp}-{secrets.token_hex(2)}"
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def safe_name(name: str) -> str:
    """The file name only: no folder, nothing hidden (an upload never leaves its folder)."""
    cleaned = Path(str(name).replace("\\", "/")).name.strip()
    return "" if cleaned in ("", ".", "..") or cleaned.startswith(".") else cleaned


# --- project ---------------------------------------------------------------------------------


def load_project(base_file: Path | str, session_dir: Path | str | None = None) -> Project:
    """Load a workspace, index it and compute its baseline (A1)."""
    file = Path(base_file)
    if not file.is_file():
        raise FileNotFoundError(f"no workspace file {file}")
    ws = wsmod.load_workspace(file)
    index, baseline = a1_indexer.run(ws)
    session = Path(session_dir) if session_dir is not None else new_session_dir()
    session.mkdir(parents=True, exist_ok=True)
    return Project(file.resolve(), session, ws, index, baseline)


def _rebuild(project: Project) -> None:
    """Index and baseline again (after files were added), keeping the BREX swaps."""
    index, baseline = a1_indexer.run(project.ws)
    for swapped in project.brex_swaps:
        baseline = a1_indexer.swap_brex(project.ws, index, swapped)
    project.index, project.baseline = index, baseline


def _ensure_upload_source(project: Project) -> None:
    """Add the ``uploads`` source (it uses the schemas and BREX folders of the first source)."""
    if any(source.id == UPLOAD_SOURCE for source in project.ws.sources):
        return
    first = project.ws.sources[0] if project.ws.sources else None
    source = wsmod.add_source(
        project.ws,
        project.uploads_dir,
        id=UPLOAD_SOURCE,
        brex_dirs=list(first.brex_dirs) if first else [],
    )
    if first is not None:
        source.issue = source.issue or first.issue
        source.schemas_dir = source.schemas_dir or first.schemas_dir


def add_uploads(project: Project, files: list[tuple[str, bytes]]) -> list[Upload]:
    """Save dropped files into the session ``uploads`` source and classify them."""
    project.uploads_dir.mkdir(parents=True, exist_ok=True)
    results: list[Upload] = []
    for name, data in files:
        cleaned = safe_name(name)
        if not cleaned:
            results.append(Upload(str(name), "other", saved=False, problem="invalid file name"))
            continue
        path = project.uploads_dir / cleaned
        path.write_bytes(data)
        role = wsmod.classify(path, source_id=UPLOAD_SOURCE).role
        results.append(Upload(cleaned, role))
    if any(upload.saved for upload in results):
        _ensure_upload_source(project)
        wsmod.save_workspace(project.ws, project.session_dir / "workspace.toml")
        _rebuild(project)
        project.uploads.extend(u for u in results if u.saved)
    return results


def swap_project_brex(project: Project, name: str, data: bytes) -> Path:
    """Swap a BREX (same DMC) into the index; chains re-resolved, baseline recomputed.

    Raises ``ValueError`` when the file is not a BREX data module name; the original BREX
    file of the source is never touched.
    """
    cleaned = safe_name(name)
    if not cleaned:
        raise ValueError("invalid file name")
    folder = project.session_dir / "brex_swap"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / cleaned
    path.write_bytes(data)
    try:
        project.baseline = a1_indexer.swap_brex(project.ws, project.index, path)
    except ValueError:
        path.unlink(missing_ok=True)
        raise
    project.brex_swaps.append(path)
    return path


# --- views of the project ----------------------------------------------------------------------


def source_rows(project: Project) -> list[tuple[str, str, bool, dict[str, int]]]:
    """(source id, folder, writable, number of documents per role) for each source."""
    counts = project.index.counts()
    return [
        (s.id, str(s.path), s.writable, dict(sorted(counts.get(s.id, {}).items())))
        for s in project.ws.sources
    ]


def document_choices(project: Project) -> list[tuple[str, str]]:
    """(document key, file name) of every data module, sorted by name."""
    return sorted(
        ((key, Path(doc.path).name) for key, doc in project.index.docs.items() if doc.role == "dm"),
        key=lambda item: item[1],
    )


def baseline_summary(project: Project) -> list[DocIssues]:
    """Pre-existing problems per data module (only the modules that have some)."""
    per_doc: dict[str, DocIssues] = {}
    for result in project.baseline:
        if result.ok or result.ref is None:
            continue
        key = ref_key(result.ref)
        doc = project.index.docs.get(key)
        name = Path(doc.path).name if doc is not None else key
        entry = per_doc.setdefault(key, DocIssues(key, name))
        entry.items.append(result)
        if result.severity == "error":
            entry.errors += 1
        else:
            entry.warnings += 1
    return sorted(per_doc.values(), key=lambda item: item.name)


def load_document(project: Project, key: str) -> Any:
    """The parsed data module (read-only use)."""
    return xio.load(project.index.docs[key].path)


def doc_ref(project: Project, key: str) -> SourceRef:
    return project.index.docs[key].ref


# --- runs --------------------------------------------------------------------------------------


def start_run(
    project: Project,
    *,
    mapping: tuple[str, bytes] | None = None,
    forms: list[dict[str, Any]] | None = None,
    runs_dir: Path | str = "runs",
) -> orch.Run:
    """Create a run from a mapping file or from forms; it stops at ``ops_proposed``.

    ``auto_accept`` is never set from the UI. The versioning policy is chosen afterwards
    (``confirm_policy``), before any proposal is prepared.
    """
    swaps = [str(p) for p in project.brex_swaps]
    if mapping is not None:
        name, data = mapping
        cleaned = safe_name(name) or "mapping.csv"
        folder = project.session_dir / "requests"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / cleaned
        path.write_bytes(data)
        request = orch.RunRequest(mapping=str(path), brex_swaps=swaps, auto_accept=False)
    elif forms:
        request = orch.RunRequest(form=forms, brex_swaps=swaps, auto_accept=False)
    else:
        raise ValueError("give a mapping file or at least one operation")
    return orch.start(request, project.workspace_file, runs_dir)


def confirm_policy(run: orch.Run, mode: str) -> None:
    """Store the chosen policy in the run state, then prepare the proposals (A4, A5, A7)."""
    if mode not in MODES:
        raise ValueError(f"unknown version policy {mode!r}")
    run.set_policy(run.suggestion().model_copy(update={"mode": mode}))
    run.run_to_review()


def highlight_ids(run: orch.Run, key: str) -> list[str]:
    """Element ids of the zones of the proposals of one document (for the XML view)."""
    zones = {z.id: z for z in run.state.zones}
    found: list[str] = []
    for proposal in run.state.proposals:
        zone = zones.get(proposal.zone_id)
        if ref_key(proposal.ref) == key and zone is not None and zone.element_id:
            found.append(zone.element_id)
    return list(dict.fromkeys(found))
