# SchemaLens

**Make legacy PostgreSQL databases understandable, for people and for AI coding assistants.**

Point SchemaLens at a database and get searchable documentation, a map of which functions read and write which tables, plain-English explanations of each function, and an MCP server so tools like Kiro write correct SQL against your schema.

> Status: under active development (v0.1 in progress). Demo link, GIF, and benchmark results land at launch.

## Why

New developers on a team with a large legacy database lose weeks working out what tables mean and what stored logic does. Existing documentation tools describe tables well but treat functions as opaque text. SchemaLens parses them with PostgreSQL's own parser and tells you what they touch.

## Privacy model

- Only system catalogs are queried. Row data is never read, stored, or sent anywhere.
- Only function source and catalog metadata go to the LLM, and only if you enable it.
- Runs entirely on your machine. Credentials are never saved.

## Quickstart (development)

```bash
pip install -e ".[dev]"
bash scripts/get_pagila.sh
docker compose up -d
pytest                       # unit + integration
python scripts/spike_plpgsql.py
```

## Accuracy

Dependency analysis is scored against hand-labeled ground truth in [`benchmark/`](benchmark/). Results: _coming with v0.1_.

## Roadmap

- v0.1: PostgreSQL scan, dependency analysis, benchmark, web UI, AI explanations, MCP server, static demo
- v0.2: SQL Server support (ScriptDom), routine-to-routine call graph

## How this is built

Spec-first with Kiro: see [`.kiro/specs/schemalens-mvp/`](.kiro/specs/schemalens-mvp/) for requirements, design, and the task plan.

## License

MIT
