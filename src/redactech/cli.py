"""Command line interface (SPEC section 13). Every command is a stub for now."""

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


@workspace_app.command("init")
def workspace_init() -> None:
    """Create a workspace.toml from the example."""
    _stub()


@workspace_app.command("add")
def workspace_add(
    path: Annotated[Path, typer.Argument(help="Source folder to add.")],
    source_id: Annotated[str | None, typer.Option("--id", help="Source identifier.")] = None,
) -> None:
    """Add a source to the workspace."""
    _stub()


@workspace_app.command("list")
def workspace_list() -> None:
    """List the sources of the workspace."""
    _stub()


@app.command()
def index() -> None:
    """Index the workspace."""
    _stub()


@app.command()
def baseline() -> None:
    """Run the baseline checks (pre-existing issues)."""
    _stub()


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
