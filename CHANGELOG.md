# Changelog

All notable changes to SchemaLens are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Pending for the 0.1.0 launch
- Public static demo deployed to Vercel.
- README demo GIF and live link.
- Published to PyPI.
- Full hand-labeling of the Pagila `public` schema for a broader accuracy number.

## [0.1.0] - 2026-11-01

First feature-complete release. Everything runs end to end against a real
PostgreSQL database.

### Added
- **Read-only scanner** (`schemalens scan`): catalog-only queries over a
  read-only connection with a 30s statement timeout. Collects relations
  (partitions excluded), columns with types/nullability/defaults/comments,
  primary and foreign keys, routines (`plpgsql` and `sql`, extension-owned
  excluded), and non-internal triggers. Redacts the DSN password on error and
  exits with code 2 on connection failure.
- **Dependency analyzer**: parses PL/pgSQL and SQL with PostgreSQL's own parser
  (pglast). Classifies DML targets as writes and every other relation reference
  as a read; ignores CTE names and `SELECT…INTO`; flags `dynamic_sql`,
  `parse_error`, and `unresolved_ref` without ever aborting a scan.
- **Metadata store** (`store.py`): a single SQLite snapshot written atomically,
  plus a separate explanation cache that survives rescans.
- **Benchmark** (`schemalens bench`): micro-averaged precision/recall/F1 over
  (routine, relation, access) triples, reads/writes/combined, with and without
  dynamic SQL; lists every false positive and false negative; writes
  `benchmark/RESULTS.md`; gates CI with `--min-f1`.
- **Bundle + API** (`schemalens serve`): one `bundle.json` contract shared by
  the UI, the API, and the static export. FastAPI serves `GET /api/bundle`,
  `POST /api/routines/{id}/explain`, and the built UI; binds to localhost.
- **Static export** (`schemalens export`): writes `bundle.json` for a
  backend-free demo.
- **AI explanations** (`schemalens explain`): provider interface with a Gemini
  provider and a fake provider for tests; JSON validation with one retry;
  caching by (definition hash, model, prompt version); cross-checks the LLM's
  reads/writes against the analyzer and surfaces disagreements.
- **MCP server** (`schemalens mcp`): four stdio tools (`search_schema`,
  `describe_table`, `explain_function`, `get_lineage`) answered only from the
  store and cache; ambiguous names return candidates.
- **Web UI** (`web/`): Vite + React + strict TypeScript. Search with grouped
  results and overview stats, relation and routine detail pages, highlighted
  SQL, an explanation panel with a disagreement warning, and a lineage graph
  (`@xyflow/react` + dagre) with distinct read/write/trigger edges. Light/dark
  theme and a 390px layout.
- **Benchmark fixtures**: 16 hand-labeled PL/pgSQL and SQL routines covering
  CTEs, writable and recursive CTEs, `UPDATE…FROM`, correlated subqueries,
  `MERGE`, `TRUNCATE`, `INSERT…ON CONFLICT`, dynamic SQL, view reads, FOR loops,
  and unqualified-name resolution. Combined F1 is 1.000.
- CI: lint, unit tests, integration tests against Pagila, a benchmark gate, and
  a strict-TypeScript web build.

[Unreleased]: https://github.com/your-org/schemalens/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/schemalens/releases/tag/v0.1.0
