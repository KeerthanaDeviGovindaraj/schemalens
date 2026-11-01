# SchemaLens design doc

## Problem

Developers joining a team with a large, legacy PostgreSQL database spend weeks
reconstructing what tables mean and what stored procedures actually do.
Documentation tools describe tables competently but treat functions as opaque
blobs of text, so the logic that moves data between tables stays invisible. AI
coding assistants have the same blind spot and happily write SQL against tables
that do not exist or miss the side effects of a function.

## Goals

- Produce searchable documentation of a database's relations, columns, keys, and routines.
- Determine, statically and accurately, which tables each routine reads and writes.
- Explain routines in plain English, with the explanation audited against the static analysis.
- Serve the result as a local web UI, a lineage graph, and an MCP server for AI assistants.
- Measure dependency-analysis accuracy against a hand-labeled benchmark and publish it.

## Non-goals (v1)

- Reading or storing row data. Only system catalogs are queried.
- Tracing routine-to-routine call graphs.
- Analyzing the contents of dynamic SQL (it is flagged instead).
- Databases other than PostgreSQL. SQL Server is v2.
- A hosted, multi-tenant service. SchemaLens runs locally.

## Design

One CLI runs every stage. The target database is touched exactly once, read-only,
through system catalogs; everything after that reads a local SQLite snapshot.

```
PostgreSQL --> scanner (psycopg, catalogs only) --> analyzer (pglast) --> schemalens.db
                                                                              |
      bench · serve (FastAPI) · mcp (stdio) · explain (LLM) · export (bundle.json)
                                                                              |
                                                               React UI / static demo
```

- **Scanner** (`scanner.py`): opens a read-only connection with a 30s statement
  timeout, runs the catalog queries for relations, columns, keys, routines, and
  triggers, and never selects from a user relation.
- **Analyzer** (`analyzer/deps.py`): parses PL/pgSQL with PostgreSQL's own
  parser via pglast, walks every embedded SQL expression, and classifies each
  relation reference as a read or a write. DML targets are writes; everything
  else is a read; CTE names are not relations; `SELECT…INTO` targets variables,
  not tables. Dynamic SQL and parse failures become flags, never exceptions.
- **Store** (`store.py`): a single SQLite snapshot written atomically (temp file
  + rename). A separate cache file holds LLM explanations so rescans never
  discard paid calls.
- **Bundle** (`bundle.py`): one Pydantic-defined JSON document that the UI, the
  API, and the static export all consume, so there is exactly one data contract.
- **Explanations** (`explain.py`): a provider returns JSON only; it is validated
  (one retry), cached by `(definition hash, model, prompt version)`, and its
  claimed reads/writes are cross-checked against the analyzer. The analyzer is
  the source of truth; the LLM is a narrator that gets audited.
- **MCP server** (`mcp_server.py`): four tools (`search_schema`,
  `describe_table`, `explain_function`, `get_lineage`) answered only from the
  store and cache. Ambiguous names return candidates instead of guessing.
- **Web UI** (`web/`): Vite + React + strict TypeScript. All data derives from
  the bundle in memory (search index, reads/writes maps, lineage adjacency).
  The lineage graph uses `@xyflow/react` with a dagre left-to-right layout and
  distinct read/write/trigger edge styles.

## Alternatives considered

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Parsing | pglast (libpg_query) | regex / hand-written parser | Regex cannot handle CTEs, nested subqueries, dollar-quoting, or PL/pgSQL control flow. Using PostgreSQL's real parser removes a whole class of silent errors. |
| Metadata store | SQLite via stdlib | Postgres sidecar / an ORM | Zero setup, one portable file, a tiny fixed schema. An ORM adds weight for no benefit at this size. |
| Explanation cache | separate SQLite file | same file as the snapshot | Rescans replace the snapshot; paid LLM output must survive them. |
| UI data contract | one `bundle.json` | paginated REST per view | API mode and the static demo share identical code paths, and client-side search is instant for schemas up to a few thousand objects. Pagination is a known v2 need for larger schemas. |
| API | REST (two endpoints) | GraphQL | Two endpoints is the whole surface; GraphQL adds machinery with no payoff here. |
| LLM trust | cross-check against the analyzer | trust the LLM's reads/writes | Deterministic analysis is auditable and benchmarkable; the LLM is treated as a narrator and its disagreements are surfaced in the UI. |

## Evaluation

Accuracy is measured with `schemalens bench`: micro-averaged precision, recall,
and F1 over `(routine, relation, access)` triples, computed separately for reads
and writes and combined, both including and excluding dynamic-SQL routines.
Labels are written by reading each routine's source *before* looking at analyzer
output, and a label is never edited to match a bug.

On the current fixture set — eight PL/pgSQL and SQL routines chosen to exercise
CTEs, writable CTEs, `UPDATE…FROM`, `MERGE`, `TRUNCATE`, dynamic SQL,
unqualified-name resolution, and `SELECT…INTO` — combined P/R/F1 are all 1.000.
The next step is labeling the full Pagila `public` schema for a broader headline
number and to surface cases the fixtures miss. CI gates every change with
`schemalens bench --min-f1 0.90`.

## Testing

- Unit tests run with no database or network: analyzer behavior on SQL strings,
  the resolver, the store/bundle round-trip, benchmark metrics, the API (via
  `TestClient`), the MCP tools, and explanations against a fake provider.
- Integration tests scan Pagila plus the bench fixtures in a Postgres service
  container and assert that the analyzer's output on real `pg_get_functiondef`
  text matches the labels.
- The web build is type-checked under strict TypeScript in CI.
