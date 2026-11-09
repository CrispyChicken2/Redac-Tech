"""Command line interface (SPEC section 13).

Implemented: ``workspace init|add|list``, ``index`` and ``baseline``. The other commands are
still stubs (message ``not implemented yet``, exit code 2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

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


@app.command()
def request(
    mapping: Annotated[Path | None, typer.Option("--mapping", help="Mapping CSV/XLSX.")] = None,
    version_policy: Annotated[
        str | None, typer.Option("--version-policy", help="none | in_work | new_issue")
    ] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Runs folder.")] = None,
) -> None:
    """Create a run from a change request."""
    _stub()


@app.command()
def review(run_dir: Annotated[Path, typer.Argument(help="runs/<id>")]) -> None:
    """Review the proposals of a run."""
    _stub()


@app.command()
def write(run_dir: Annotated[Path, typer.Argument(help="runs/<id>")]) -> None:
    """Write the accepted changes."""
    _stub()


@app.command()
def check(out_dir: Annotated[Path, typer.Argument(help="runs/<id>/out")]) -> None:
    """Check the produced documents."""
    _stub()


@app.command()
def render(
    doc: Annotated[Path, typer.Argument(help="Document to render.")],
    view: Annotated[str, typer.Option("--view", help="xml | published | both")] = "both",
    show_deleted: Annotated[bool, typer.Option("--show-deleted")] = False,
) -> None:
    """Render a document."""
    _stub()


@app.command("eval")
def eval_(scenarios: Annotated[Path, typer.Argument(help="tests/scenarios/")]) -> None:
    """Evaluate the scenarios."""
    _stub()


if __name__ == "__main__":
    app()
