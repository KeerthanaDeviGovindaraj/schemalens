"""SchemaLens command-line interface. Commands are filled in task by task."""

from __future__ import annotations

from pathlib import Path

import typer

from schemalens import __version__

app = typer.Typer(help="Make legacy PostgreSQL databases understandable.", no_args_is_help=True)


def _todo(task: str) -> None:
    typer.echo(f"Not implemented yet (see tasks.md, task {task}).")
    raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Print the SchemaLens version."""
    typer.echo(__version__)


@app.command()
def scan(
    dsn: str = typer.Option(..., help="PostgreSQL connection string (read-only access is enough)."),
    schema: list[str] = typer.Option(None, help="Restrict to these schemas (repeatable)."),
    out: Path = typer.Option(Path("schemalens.db"), help="Metadata store to write."),
) -> None:
    """Scan a database's catalog into the local metadata store."""
    _todo("2.3")


@app.command()
def bench(
    db: Path = typer.Option(Path("schemalens.db")),
    labels: Path = typer.Option(Path("benchmark/labels.yaml")),
    min_f1: float = typer.Option(0.0, help="Exit non-zero if combined F1 is below this."),
) -> None:
    """Score dependency analysis against hand-labeled ground truth."""
    _todo("4.3")


@app.command()
def serve(
    db: Path = typer.Option(Path("schemalens.db")),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8765),
) -> None:
    """Serve the web UI and API locally."""
    _todo("5.2")


@app.command()
def export(
    db: Path = typer.Option(Path("schemalens.db")),
    out: Path = typer.Option(Path("web/public")),
) -> None:
    """Write bundle.json for the static demo."""
    _todo("5.3")


@app.command()
def explain(
    db: Path = typer.Option(Path("schemalens.db")),
    all_routines: bool = typer.Option(False, "--all", help="Explain every routine missing an explanation."),
) -> None:
    """Generate AI explanations (cached)."""
    _todo("8.4")


@app.command()
def mcp(db: Path = typer.Option(Path("schemalens.db"))) -> None:
    """Run the MCP server over stdio."""
    _todo("9.1")


if __name__ == "__main__":
    app()
