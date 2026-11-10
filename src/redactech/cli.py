"""Command line interface (SPEC section 13).

Implemented: ``workspace``, ``index``, ``baseline``, ``request``, ``review``, ``write``,
``check``, ``eval`` and ``render`` (no stub left).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

app = typer.Typer(help="RedacTech: local assistant for S1000D documentation updates.")
workspace_app = typer.Typer(help="Manage the workspace (sources).")
app.add_typer(workspace_app, name="workspace")


def _stub() -> None:
    typer.echo("not implemented yet")
    raise typer.Exit(code=2)


WorkspaceOpt = Annotated[
    Path | None,
    typer.Option("--workspace", "-w", help="Workspace file (default: config.toml [workspace])."),
]


def _workspace_file(option: Path | None) -> Path:
    from redactech.config import load_config

    return option if option is not None else Path(load_config().workspace.file)


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


def _load(option: Path | None):
    from redactech.sources import workspace

    file = _workspace_file(option)
    if not file.is_file():
        _fail(f"no workspace file {file}; run 'redactech workspace init' first")
    try:
        return workspace.load_workspace(file), file
    except (ValueError, OSError) as exc:
        _fail(f"invalid workspace {file}: {exc}")


@workspace_app.command("init")
def workspace_init(
    workspace: WorkspaceOpt = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
) -> None:
    """Create a workspace.toml from the example."""
    from redactech.sources import workspace as ws_mod

    file = _workspace_file(workspace)
    try:
        ws_mod.init_workspace(file, force=force)
    except FileExistsError:
        _fail(f"{file} already exists (use --force to overwrite)")
    typer.echo(f"created {file}")


@workspace_app.command("add")
def workspace_add(
    path: Annotated[Path, typer.Argument(help="Source folder to add.")],
    source_id: Annotated[str | None, typer.Option("--id", help="Source identifier.")] = None,
    brex_dir: Annotated[
        list[Path] | None, typer.Option("--brex-dir", help="BREX folder (repeatable).")
    ] = None,
    workspace: WorkspaceOpt = None,
) -> None:
    """Add a source to the workspace."""
    from redactech.sources import workspace as ws_mod

    ws, file = _load(workspace)
    try:
        source = ws_mod.add_source(ws, path, id=source_id, brex_dirs=brex_dir or [])
    except (ValueError, OSError) as exc:
        _fail(f"cannot add source: {exc}")
    ws_mod.save_workspace(ws, file)
    typer.echo(f"added {source.id}: {source.path}")


@workspace_app.command("list")
def workspace_list(workspace: WorkspaceOpt = None) -> None:
    """List the sources of the workspace."""
    ws, _ = _load(workspace)
    if not ws.sources:
        typer.echo("no sources")
    for src in ws.sources:
        flags = "writable" if src.writable else "read-only"
        typer.echo(f"{src.id}\t{src.issue or '-'}\t{flags}\t{src.path}")
        for folder in src.brex_dirs:
            typer.echo(f"\tbrex: {folder}")


@app.command()
def index(workspace: WorkspaceOpt = None) -> None:
    """Index the workspace: number of files per source and per role."""
    from redactech.s1000d import index as index_mod

    ws, _ = _load(workspace)
    idx = index_mod.build_index(ws)
    counts = idx.counts()
    total = 0
    for src in ws.sources:
        per_role = counts.get(src.id, {})
        n = sum(per_role.values())
        total += n
        roles = ", ".join(f"{role}={per_role[role]}" for role in sorted(per_role))
        typer.echo(f"{src.id}: {n} files ({roles})")
    typer.echo(
        f"total: {total} files, {len(idx.parts)} part numbers, {len(idx.figures)} figures"
    )
    for key in sorted(idx.unreadable):
        typer.echo(f"unreadable: {key}: {idx.unreadable[key]}", err=True)


@app.command()
def baseline(workspace: WorkspaceOpt = None) -> None:
    """Run the baseline checks and print the pre-existing problems per data module."""
    from redactech.agents import a1_indexer
    from redactech.s1000d.index import ref_key

    ws, _ = _load(workspace)
    idx, results = a1_indexer.run(ws)
    found = a1_indexer.problems(results)
    errors = warnings = 0
    for key in sorted(k for k, d in idx.docs.items() if d.role == "dm"):
        mine = [r for r in found if r.ref is not None and ref_key(r.ref) == key]
        e = sum(1 for r in mine if r.severity == "error")
        w = len(mine) - e
        errors, warnings = errors + e, warnings + w
        typer.echo(f"{key}: {e} error(s), {w} warning(s) pre-existing")
    no_schemas = [s.id for s in ws.sources if s.schemas_dir is None]
    if no_schemas:
        names = ", ".join(no_schemas)
        typer.echo(f"note: no schemas folder for source(s) {names}: XSD not checked")
    n_dm = sum(1 for d in idx.docs.values() if d.role == "dm")
    typer.echo(
        f"baseline: {n_dm} data modules, {errors} error(s), {warnings} warning(s) pre-existing"
    )


MODES = ("none", "in_work", "new_issue")


def _policy(value: str | None) -> str | None:
    if value is not None and value not in MODES:
        _fail(f"unknown version policy {value!r} (expected one of: {', '.join(MODES)})")
    return value


def _open_run(run_dir: Path):
    from redactech.pipeline import orchestrator

    if not (run_dir / orchestrator.STATE_FILE).is_file():
        _fail(f"{run_dir} is not a run folder (no {orchestrator.STATE_FILE})")
    return orchestrator.load(run_dir)


def _echo_proposals(run) -> None:
    from redactech.s1000d.index import ref_key

    zones = {z.id: z for z in run.state.zones}
    if not run.state.proposals:
        typer.echo("no proposal")
    for p in run.state.proposals:
        zone = zones.get(p.zone_id)
        certainty = zone.certainty if zone else "?"
        kind = zone.kind if zone else "?"
        problems = [c for c in p.checks if not c.ok and c.origin == "introduced"]
        flag = f" attempt={p.attempt}" if p.attempt > 1 else ""
        typer.echo(
            f"{p.id}\t{p.status}\t{kind}/{certainty}\t{ref_key(p.ref)}\t"
            f"{len(problems)} introduced problem(s){flag}"
        )
    for op in run.state.operations:
        for question in op.questions:
            typer.echo(f"question ({op.id}): {question}")
    for question in run.free_text_questions():
        typer.echo(f"question (free text): {question}")


def _echo_policy(run) -> None:
    suggestion = run.suggestion()
    typer.echo(f"suggested version policy: {suggestion.suggested}")
    for reason in suggestion.reasons:
        typer.echo(f"  - {reason}")
    chosen = run.state.version_policy
    typer.echo(f"chosen version policy: {chosen.mode if chosen else 'not chosen yet'}")


def _pending(run) -> list[str]:
    flags = {z.id for z in run.state.zones if z.kind != "content"}
    return [p.id for p in run.state.proposals if p.status == "proposed" and p.zone_id not in flags]


@app.command()
def request(
    mapping: Annotated[Path | None, typer.Option("--mapping", help="Mapping CSV/XLSX.")] = None,
    text: Annotated[
        str | None,
        typer.Option("--text", help="Request in plain French or English (needs the local model)."),
    ] = None,
    version_policy: Annotated[
        str | None, typer.Option("--version-policy", help="none | in_work | new_issue")
    ] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Runs folder.")] = None,
    workspace: WorkspaceOpt = None,
    auto_accept: Annotated[bool, typer.Option("--auto-accept", hidden=True)] = False,
) -> None:
    """Create a run from a change request and stop at the proposals checkpoint."""
    from redactech.agents.a2_mapping import MappingError
    from redactech.pipeline import orchestrator

    if (mapping is None) == (text is None):
        _fail("give --mapping FILE (CSV or XLSX), or --text \"...\", but not both")
    if mapping is not None and not mapping.is_file():
        _fail(f"no mapping file {mapping}")
    _policy(version_policy)
    file = _workspace_file(workspace)
    if not file.is_file():
        _fail(f"no workspace file {file}; run 'redactech workspace init' first")
    req = orchestrator.RunRequest(
        mapping=str(mapping) if mapping is not None else None,
        free_text=text,
        version_policy=version_policy,
        auto_accept=auto_accept,
    )
    try:
        run = orchestrator.start(req, file, out or Path("runs"))
        run.run_to_review()
    except (MappingError, orchestrator.PipelineError, ValueError, OSError) as exc:
        _fail(f"cannot create the run: {exc}")
    typer.echo(f"run: {run.run_dir}")
    if auto_accept:
        accepted = run.auto_accept()
        typer.echo(f"auto-accepted: {', '.join(accepted) or 'none'}")
    _echo_proposals(run)
    _echo_policy(run)
    left = _pending(run)
    if auto_accept and run.state.version_policy is not None and not left:
        try:
            result = run.write()
        except orchestrator.PipelineError as exc:
            _fail(f"cannot write: {exc}")
        typer.echo(f"written: {', '.join(p.name for p in result.written) or 'nothing'}")
        _echo_open_questions(result)
        for path in run.delivery_files:
            typer.echo(f"delivery {path}")
    elif left:
        typer.echo(f"{len(left)} proposal(s) to decide: redactech review {run.run_dir}")


@app.command()
def review(
    run_dir: Annotated[Path, typer.Argument(help="runs/<id>")],
    accept: Annotated[list[str] | None, typer.Option("--accept", help="Proposal id.")] = None,
    reject: Annotated[list[str] | None, typer.Option("--reject", help="Proposal id.")] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Why (with --reject).")] = None,
    pending: Annotated[
        list[str] | None, typer.Option("--pending", help="Ask the customer: proposal id.")
    ] = None,
    comment: Annotated[str | None, typer.Option("--comment", help="With --pending.")] = None,
    accept_all: Annotated[
        bool, typer.Option("--accept-all", help="Accept the certain and clean proposals.")
    ] = False,
    reopen: Annotated[
        list[str] | None, typer.Option("--reopen", help="Take a decision back: proposal id.")
    ] = None,
) -> None:
    """List the proposals of a run, or record decisions."""
    from redactech.pipeline import orchestrator

    run = _open_run(run_dir)
    try:
        for proposal_id in reopen or []:
            reopened = run.reopen(proposal_id)
            typer.echo(f"reopened {proposal_id}: {reopened.status}")
        for proposal_id in accept or []:
            run.decide(proposal_id, "accepted")
            typer.echo(f"accepted {proposal_id}")
        for proposal_id in reject or []:
            alternative = run.reject(proposal_id, reason)
            if alternative is not None:
                typer.echo(f"rejected {proposal_id}; alternative {alternative.id}")
            else:
                typer.echo(f"rejected {proposal_id}; no alternative: needs manual edit")
        for proposal_id in pending or []:
            run.decide(proposal_id, "pending_client", comment)
            typer.echo(f"pending_client {proposal_id}")
        if accept_all:
            done = run.accept_all()
            typer.echo(f"accepted: {', '.join(done) or 'none'}")
    except orchestrator.PipelineError as exc:
        _fail(str(exc))
    _echo_proposals(run)
    left = _pending(run)
    if left:
        typer.echo(f"{len(left)} proposal(s) still to decide")


@app.command()
def write(
    run_dir: Annotated[Path, typer.Argument(help="runs/<id>")],
    version_policy: Annotated[
        str | None, typer.Option("--version-policy", help="none | in_work | new_issue")
    ] = None,
) -> None:
    """Write the accepted changes into <run>/out."""
    from redactech.pipeline import orchestrator

    run = _open_run(run_dir)
    _policy(version_policy)
    try:
        chosen = run.state.version_policy
        if version_policy is not None:
            chosen = run.suggestion().model_copy(update={"mode": version_policy})
        if chosen is None:
            _fail("no versioning policy chosen: give --version-policy none|in_work|new_issue")
        # the policy is saved only if the write succeeds: a refused command changes nothing
        result = run.write(policy=chosen)
    except orchestrator.PipelineError as exc:
        _fail(str(exc))
    for path in result.written:
        typer.echo(f"written {path}")
    for entry in result.skipped:
        typer.echo(f"skipped {entry['proposal']}: {entry['reason']}")
    typer.echo(f"{len(result.written)} file(s) written to {run.run_dir / 'out'}")
    _echo_open_questions(result)
    for path in run.delivery_files:
        typer.echo(f"delivery {path}")


def _echo_open_questions(result: Any) -> None:
    """The warning about the customer questions still open (the write itself is allowed)."""
    if result.warning:
        typer.echo(f"warning: {result.warning}")
        for line in result.open_questions:
            typer.echo(f"  - {line}")


@app.command()
def check(out_dir: Annotated[Path, typer.Argument(help="runs/<id>/out")]) -> None:
    """Check the produced documents (introduced vs pre-existing problems)."""
    from redactech.agents import a7_checker
    from redactech.models import SourceRef
    from redactech.s1000d import io as xio

    run = _open_run(out_dir.resolve().parent)
    if not out_dir.is_dir():
        _fail(f"no output folder {out_dir}")
    originals: dict[str, str] = {}
    for event in run.state.decisions_log:
        if event.get("event") == "written":
            for entry in event.get("log", []):
                originals[entry["new_name"]] = entry["doc"]
    introduced = 0
    files = sorted(f for f in out_dir.iterdir() if f.suffix.lower() == ".xml")
    for file in files:
        key = originals.get(file.name)
        source = run.index.docs.get(key) if key else None
        if source is None:
            typer.echo(f"{file.name}: not produced by this run, not checked", err=True)
            continue
        ref = SourceRef(source_id=source.ref.source_id, doc_key=file.stem)
        failures = a7_checker.check_doc(
            xio.load(file), run.index, run.state.baseline, original=source.ref, ref=ref
        )
        new = [f for f in failures if f.origin == "introduced"]
        introduced += sum(1 for f in new if f.severity == "error")
        typer.echo(f"{file.name}: {len(new)} introduced, {len(failures) - len(new)} pre-existing")
        for failure in new:
            typer.echo(f"  {failure.severity} {failure.name}: {failure.details}")
    typer.echo(f"checked {len(files)} file(s), {introduced} introduced error(s)")
    if introduced:
        raise typer.Exit(code=1)


@app.command()
def render(
    doc: Annotated[Path, typer.Argument(help="Document to render.")],
    view: Annotated[str, typer.Option("--view", help="xml | published | both")] = "both",
    show_deleted: Annotated[
        bool, typer.Option("--show-deleted/--hide-deleted", help="Show deleted elements struck.")
    ] = True,
    out: Annotated[Path | None, typer.Option("--out", help="Write the page here.")] = None,
) -> None:
    """Render a data module as a self-contained HTML page (stdout, or --out FILE)."""
    from lxml import etree

    from redactech.render.side_by_side import render_page
    from redactech.s1000d import io as xio

    if view not in ("xml", "published", "both"):
        _fail(f"unknown view {view!r} (expected xml, published or both)")
    if not doc.is_file():
        _fail(f"no document {doc}")
    try:
        xdoc = xio.load(doc)
        page = render_page(xdoc, view, show_deleted, title=doc.name)
    except (etree.LxmlError, ValueError, OSError) as exc:
        _fail(f"cannot render {doc}: {exc}")
    if out is None:
        typer.echo(page, nl=False)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        typer.echo(f"written {out}")


@app.command("eval")
def eval_(
    scenarios: Annotated[Path, typer.Argument(help="tests/scenarios/")],
    out: Annotated[Path | None, typer.Option("--out", help="Folder of the report.")] = None,
) -> None:
    """Run every available scenario and write runs/eval_<date>.md; exit 1 if one fails."""
    import datetime
    import tempfile

    from redactech.pipeline import scenarios as sc

    if not scenarios.is_dir():
        _fail(f"no scenarios folder {scenarios}")
    root = scenarios.resolve().parents[1]
    results = []
    for directory in sc.discover(scenarios):
        for variant in sc.variants_of(directory):
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                result = sc.run_scenario(directory, Path(tmp) / "work", variant, repo_root=root)
            results.append(result)
            if result.skipped:
                typer.echo(f"SKIP {result.label}: {result.skipped}")
            else:
                typer.echo(f"{'PASS' if result.passed else 'FAIL'} {result.label}")
                for message in result.failures:
                    typer.echo(f"  - {message}")
    folder = out or Path("runs")
    folder.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today()
    report = folder / f"eval_{today.isoformat()}.md"
    report.write_text(sc.report_markdown(results, today), encoding="utf-8")
    ran = [r for r in results if not r.skipped]
    failed = [r for r in ran if not r.passed]
    typer.echo(f"{len(ran)} scenario(s) run, {len(failed)} failed, report: {report}")
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
