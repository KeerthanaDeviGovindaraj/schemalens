"""SchemaLens command-line interface."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from schemalens import __version__

app = typer.Typer(help="Make legacy PostgreSQL databases understandable.", no_args_is_help=True)


def _require_store(db: Path) -> None:
    if not db.exists():
        typer.secho(f"No metadata store at {db}. Run `schemalens scan` first.", fg="red", err=True)
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
    search_path: str = typer.Option("public", help="Comma-separated search path for unqualified names."),
) -> None:
    """Scan a database's catalog into the local metadata store."""
    from schemalens.scanner import ScanError, redact_dsn, summary_counts
    from schemalens.scanner import scan as run_scan
    from schemalens.store import write_snapshot

    paths = [p.strip() for p in search_path.split(",") if p.strip()]
    try:
        snapshot = run_scan(dsn, schema or None, paths)
    except ScanError as exc:
        typer.secho(f"Scan failed: {exc}", fg="red", err=True)
        typer.secho(f"(DSN: {redact_dsn(dsn)})", fg="red", err=True)
        raise typer.Exit(code=2) from exc

    write_snapshot(snapshot, out)
    counts = summary_counts(snapshot)
    typer.secho(f"Scanned {snapshot.meta.get('db_name')} -> {out}", fg="green")
    for key in ("relations", "columns", "routines", "triggers", "dependencies"):
        typer.echo(f"  {key}: {counts[key]}")
    flagged = len({f["routine_id"] for f in snapshot.flags})
    if flagged:
        typer.echo(f"  routines with flags: {flagged}")


@app.command()
def bench(
    db: Path = typer.Option(Path("schemalens.db")),
    labels: Path = typer.Option(Path("benchmark/labels.yaml")),
    out: Path = typer.Option(Path("benchmark/RESULTS.md"), help="Markdown results file."),
    min_f1: float = typer.Option(0.0, help="Exit non-zero if combined F1 is below this."),
) -> None:
    """Score dependency analysis against hand-labeled ground truth."""
    _require_store(db)
    from schemalens.bench import render_markdown, run_bench

    result = run_bench(db, labels)
    markdown = render_markdown(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown)

    c = result.combined
    cn = result.combined_nodyn
    typer.echo(f"combined  F1={c.f1:.3f}  P={c.precision:.3f}  R={c.recall:.3f}")
    typer.echo(f"excl.dyn  F1={cn.f1:.3f}  P={cn.precision:.3f}  R={cn.recall:.3f}")
    typer.echo(f"wrote {out}")
    if c.f1 < min_f1:
        typer.secho(f"combined F1 {c.f1:.3f} below --min-f1 {min_f1}", fg="red", err=True)
        raise typer.Exit(code=1)


@app.command()
def serve(
    db: Path = typer.Option(Path("schemalens.db")),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8765),
    no_ai: bool = typer.Option(False, "--no-ai", help="Disable explanation generation."),
) -> None:
    """Serve the web UI and API locally."""
    _require_store(db)
    import uvicorn

    from schemalens.api import create_app

    appl = create_app(db, enable_ai=not no_ai)
    typer.secho(f"Serving SchemaLens on http://{host}:{port}", fg="green")
    uvicorn.run(appl, host=host, port=port, log_level="info")


@app.command()
def export(
    db: Path = typer.Option(Path("schemalens.db")),
    out: Path = typer.Option(Path("web/public"), help="Directory to write bundle.json into."),
) -> None:
    """Write bundle.json for the static demo."""
    _require_store(db)
    from schemalens.bundle import build_bundle

    bundle = build_bundle(db)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "bundle.json"
    target.write_text(bundle.to_json())
    typer.secho(
        f"Wrote {target} ({len(bundle.relations)} relations, {len(bundle.routines)} routines)",
        fg="green",
    )


@app.command()
def explain(
    db: Path = typer.Option(Path("schemalens.db")),
    all_routines: bool = typer.Option(False, "--all", help="Explain every routine missing an explanation."),
    no_ai: bool = typer.Option(False, "--no-ai", help="Do nothing without a provider (no error)."),
    concurrency: int = typer.Option(4, help="Max concurrent explanation requests."),
) -> None:
    """Generate AI explanations (cached)."""
    _require_store(db)
    from concurrent.futures import ThreadPoolExecutor

    from schemalens.bundle import build_bundle
    from schemalens.explain import PROMPT_VERSION, AIDisabled, ProviderError, get_or_create, get_provider
    from schemalens.store import cache_get, definition_hash, open_cache

    provider = get_provider()
    if provider is None:
        msg = "No LLM provider configured (set GEMINI_API_KEY)."
        if no_ai:
            typer.echo(msg + " Skipping (--no-ai).")
            return
        typer.secho(msg, fg="red", err=True)
        raise typer.Exit(code=1)

    bundle = build_bundle(db)
    relations_by_id = {r.id: r for r in bundle.relations}

    with open_cache() as cache:
        todo = []
        for r in bundle.routines:
            if not all_routines:
                continue
            def_hash = definition_hash(r.definition)
            if cache_get(cache, def_hash, provider.name, PROMPT_VERSION) is not None:
                continue
            todo.append(r)

        if not todo:
            typer.echo("Nothing to explain (all cached).")
            return

        def work(r):
            relation_meta = {
                rid: [{"name": c.name, "data_type": c.data_type} for c in relations_by_id[rid].columns]
                for rid in set(r.reads) | set(r.writes)
                if rid in relations_by_id
            }
            try:
                get_or_create(
                    cache,
                    provider,
                    {"definition": r.definition},
                    relation_meta,
                    set(r.reads),
                    set(r.writes),
                )
                return (r.name, None)
            except (AIDisabled, ProviderError) as exc:
                return (r.name, str(exc))

        done = 0
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for name, err in pool.map(work, todo):
                done += 1
                status = "ok" if err is None else f"ERROR {err}"
                typer.echo(f"  [{done}/{len(todo)}] {name}: {status}")
    typer.secho(f"Explained {done} routine(s).", fg="green")


@app.command()
def mcp(db: Path = typer.Option(Path("schemalens.db"))) -> None:
    """Run the MCP server over stdio."""
    if not db.exists():
        print(f"No metadata store at {db}. Run `schemalens scan` first.", file=sys.stderr)
        raise typer.Exit(code=1)
    from schemalens.mcp_server import run

    run(db)


if __name__ == "__main__":
    app()
