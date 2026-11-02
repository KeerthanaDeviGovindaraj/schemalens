# SchemaLens

**Make legacy PostgreSQL databases understandable, for people and for AI coding assistants.**

[![CI](https://github.com/KeerthanaDeviGovindaraj/schemalens/actions/workflows/ci.yml/badge.svg)](https://github.com/KeerthanaDeviGovindaraj/schemalens/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Point SchemaLens at a database and get searchable documentation, a map of which functions read and write which tables, plain-English explanations of each function, and an MCP server so tools like Kiro write correct SQL against your schema.

> Status: v0.1 feature-complete. Scan, dependency analysis, benchmark, web UI, AI explanations, and the MCP server all work end to end. Public demo link lands at launch.

## Screenshots

Browse and search the whole schema:

![SchemaLens search and overview](docs/img/home.png)

See exactly what each function reads and writes, with the source highlighted:

![Routine detail with reads, writes, and highlighted source](docs/img/routine.png)

Explore lineage as a graph — distinct read, write, and trigger edges:

![Lineage graph centered on a table](docs/img/lineage.png)

## What you get

- **Searchable docs** — every table, column, view, and function in one place, with instant client-side search.
- **Read/write lineage** — for each function, exactly which tables it reads and which it writes, parsed from the real SQL, plus a graph to explore it.
- **Plain-English explanations** — optional LLM summaries, with every claim cross-checked against the static analysis so you can trust them.
- **An MCP server** — your AI assistant answers schema questions ("which functions write to `rental`?") from the scan instead of guessing.
- **A measured accuracy number** — analysis is scored against a hand-labeled benchmark, so the claims are honest and regressions are caught in CI.

## Why

New developers on a team with a large legacy database lose weeks working out what tables mean and what stored logic does. Existing documentation tools describe tables well but treat functions as opaque text. SchemaLens parses them with PostgreSQL's own parser and tells you what they touch.

## Privacy model

- Only system catalogs are queried. Row data is never read, stored, or sent anywhere.
- Only function source and catalog metadata go to the LLM, and only if you enable it.
- Runs entirely on your machine. Credentials are never saved.

## Quickstart (development)

```bash
# backend
pip install -e ".[dev]"
bash scripts/get_pagila.sh
docker compose up -d                 # Postgres with Pagila + bench fixtures on :5433
pytest -m "not integration"          # unit tests (no DB)
pytest -m integration                # needs the DB above

# scan a database and explore it
schemalens scan --dsn "postgresql://postgres:postgres@localhost:5433/pagila" --search-path "public,bench"
schemalens bench                     # writes benchmark/RESULTS.md

# web UI
cd web && npm install && npm run build && cd ..
cp -r web/dist/* src/schemalens/web_dist/ && rm -f src/schemalens/web_dist/bundle.json
schemalens serve                     # http://127.0.0.1:8765
```

Point it at your own database with a read-only connection string; only system
catalogs are queried.

## Commands

| Command | What it does |
|---|---|
| `schemalens scan --dsn <dsn>` | Read-only catalog scan into `schemalens.db` |
| `schemalens bench` | Score dependency analysis vs. `benchmark/labels.yaml` |
| `schemalens serve` | Local web UI + API on `127.0.0.1:8765` |
| `schemalens export --out <dir>` | Write `bundle.json` for the static demo |
| `schemalens explain --all` | Generate AI explanations (needs `GEMINI_API_KEY`) |
| `schemalens mcp` | MCP server over stdio for AI assistants |

## Accuracy

Dependency analysis is scored against hand-labeled ground truth in
[`benchmark/`](benchmark/). The current fixture set is 16 PL/pgSQL and SQL
routines chosen to stress the parser — CTEs, writable and recursive CTEs,
`UPDATE…FROM`, correlated subqueries, `MERGE`, `TRUNCATE`, `INSERT…ON CONFLICT`,
dynamic SQL, view reads, FOR loops, unqualified-name resolution, and
`SELECT…INTO`:

| Metric | Precision | Recall | F1 |
|---|---|---|---|
| reads | 1.000 | 1.000 | 1.000 |
| writes | 1.000 | 1.000 | 1.000 |
| combined (28 triples) | 1.000 | 1.000 | 1.000 |

Scores hold both including and excluding dynamic-SQL routines. Labels are
written by reading each routine's source *before* looking at analyzer output,
and a label is never edited to match a bug. Run `schemalens bench` to regenerate
[`benchmark/RESULTS.md`](benchmark/RESULTS.md); CI gates every change with
`--min-f1 0.90`. Labeling the full Pagila `public` schema is the next step
toward a broader headline number.

## Use it in Kiro (MCP)

After a scan, add this to `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "schemalens": {
      "command": "schemalens",
      "args": ["mcp", "--db", "./schemalens.db"]
    }
  }
}
```

Then ask your assistant things like "which functions write to the rental
table?" — it answers from the scanned metadata, never touching the live DB.

## Limitations

- Dynamic SQL (`EXECUTE`) is flagged, not analyzed; writes hidden inside it are missed on purpose.
- Routine-to-routine call graphs are not traced in v1.
- The whole schema is shipped as one `bundle.json`; very large schemas will need paginated endpoints (v2).
- PostgreSQL only. SQL Server (via ScriptDom) is planned for v2.

## Roadmap

- v0.1: PostgreSQL scan, dependency analysis, benchmark, web UI, AI explanations, MCP server, static demo
- v0.2: SQL Server support (ScriptDom), routine-to-routine call graph

## Project layout

```
src/schemalens/
  scanner.py     read-only catalog scan
  analyzer/      dependency extraction (deps.py) + name resolution (resolve.py)
  store.py       SQLite snapshot + explanation cache
  bundle.py      the one JSON contract for the UI/API/export
  bench.py       accuracy metrics + RESULTS.md
  api.py         FastAPI app (also serves the built UI)
  explain.py     LLM providers, prompt, validation, cross-check
  mcp_server.py  four MCP tools over stdio
  cli.py         the `schemalens` command
web/             Vite + React + TypeScript UI
benchmark/       labels.yaml, RESULTS.md
docker/initdb/   Pagila + benchmark fixtures
docs/            design doc, packaging guide
```

## Development notes

- Tests: `pytest -m "not integration"` (no DB) and `pytest -m integration` (needs the compose DB). 49 unit tests, lint with `ruff check . && ruff format --check .`.
- Building the UI into the package: `cd web && npm run build`, then copy `web/dist/*` into `src/schemalens/web_dist/` (details in [`docs/packaging.md`](docs/packaging.md)). The wheel ships this so `schemalens serve` works after `pip install`.
- Editable installs use a src layout; a fresh `python3.12 -m venv .venv && pip install -e ".[dev]"` is the supported setup. A root `conftest.py` also puts `src/` on the path so tests run regardless of install state.

## How this is built

Spec-first with Kiro: see [`.kiro/specs/schemalens-mvp/`](.kiro/specs/schemalens-mvp/) for requirements, design, and the task plan, and [`docs/design-doc.md`](docs/design-doc.md) for the problem, alternatives considered, and evaluation.

## License

MIT
