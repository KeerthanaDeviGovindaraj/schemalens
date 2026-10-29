# Design: SchemaLens MVP

## Overview

SchemaLens is a local-first Python tool. One CLI (`schemalens`) runs every stage: scan the catalog, analyze routines, generate explanations, serve the UI, export the static demo, and run the MCP server. Everything after the scan reads from a local SQLite metadata store, so the target database is touched exactly once, read-only, and only through system catalogs.

```
                 ┌──────────────────────────────────────────────┐
 PostgreSQL ───▶ │ scanner  (psycopg, read-only, catalogs only) │
 (target DB)     └──────────────────┬───────────────────────────┘
                                    ▼
                 ┌──────────────────────────────────────────────┐
                 │ analyzer (pglast: PL/pgSQL + SQL parsers)    │
                 └──────────────────┬───────────────────────────┘
                                    ▼
                         schemalens.db (SQLite)        .schemalens/cache.db
                          snapshot of one scan    ◀──▶  LLM explanation cache
                                    │                        ▲
        ┌───────────────┬──────────┴──────┬─────────────────┤
        ▼               ▼                 ▼                 │
   bench (labels)   serve (FastAPI)   mcp (stdio)    explain (LLM provider)
                        │
                        ▼
              React UI ◀── bundle.json ──▶ export (static demo on Vercel)
```

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Parsing | pglast (libpg_query) | PostgreSQL's real parser, including PL/pgSQL. Regex cannot handle CTEs, subqueries, or quoting correctly. |
| Metadata store | SQLite via stdlib `sqlite3`, no ORM | Zero setup, one portable file, small schema. |
| Explanation cache | Separate SQLite file | Rescans replace the snapshot; paid LLM calls must survive. |
| UI data contract | One `bundle.json` | API mode and static demo use identical code paths; search runs client-side. Fine for databases up to a few thousand objects (known limitation, see below). |
| API | REST (FastAPI) | Two endpoints are enough; GraphQL adds no value at this size. |
| LLM trust | Cross-check LLM reads/writes against the analyzer | The deterministic analysis is the source of truth; the LLM is a narrator that gets audited. |

## Components

### 1. Scanner (`schemalens/scanner.py`)

Connects with `psycopg`, sets `conn.read_only = True` and `SET statement_timeout = '30s'`, runs the catalog queries below, and returns plain dataclasses. It never runs a query against a user relation.

**Relations** (partitions excluded so partitioned tables appear once):
```sql
SELECT c.oid, n.nspname AS schema, c.relname AS name,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'table'
                      WHEN 'v' THEN 'view'  WHEN 'm' THEN 'matview' END AS kind,
       obj_description(c.oid, 'pg_class') AS comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','v','m')
  AND NOT c.relispartition
  AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND n.nspname NOT LIKE 'pg_toast%';
```

**Columns:**
```sql
SELECT a.attrelid, a.attnum, a.attname,
       format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS nullable,
       pg_get_expr(d.adbin, d.adrelid) AS default_expr,
       col_description(a.attrelid, a.attnum) AS comment
FROM pg_attribute a
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE a.attnum > 0 AND NOT a.attisdropped AND a.attrelid = ANY(%(oids)s);
```

**Keys** (map `conkey`/`confkey` attnums to names in Python):
```sql
SELECT conname, contype, conrelid, confrelid, conkey, confkey
FROM pg_constraint
WHERE contype IN ('p','f') AND conrelid = ANY(%(oids)s);
```

**Routines** (extension-owned functions excluded):
```sql
SELECT p.oid, n.nspname AS schema, p.proname AS name,
       pg_get_function_identity_arguments(p.oid) AS args,
       pg_get_function_result(p.oid) AS returns,
       p.prokind, l.lanname AS language, p.prosrc,
       pg_get_functiondef(p.oid) AS definition
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language  l ON l.oid = p.prolang
WHERE p.prokind IN ('f','p')
  AND l.lanname IN ('plpgsql','sql')
  AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND NOT EXISTS (SELECT 1 FROM pg_depend d
                  WHERE d.objid = p.oid AND d.deptype = 'e');
```
Note: SQL-standard bodies (`BEGIN ATOMIC`) have an empty `prosrc`; for those, parse `definition` instead.

**Triggers:**
```sql
SELECT t.tgname, t.tgrelid, t.tgfoid, pg_get_triggerdef(t.oid) AS definition
FROM pg_trigger t
WHERE NOT t.tgisinternal AND t.tgrelid = ANY(%(oids)s);
```

### 2. Analyzer (`schemalens/analyzer/deps.py`)

A starter implementation is in the repo. Algorithm:

1. **Collect SQL fragments.**
   - `plpgsql`: run `parse_plpgsql_json(definition)` and walk the tree. Every `PLpgSQL_expr` node contributes its `query` string. Any `PLpgSQL_stmt_dynexecute` or `PLpgSQL_stmt_dynfors` node sets the `dynamic_sql` flag.
   - `sql`: the body (`prosrc`) is the only fragment.
2. **Parse each fragment** with `parse_sql_json`. PL/pgSQL expressions are often fragments rather than statements (`v_count > 0`, `x := now()`), so try in order: as-is, `SELECT <right side of :=>`, `SELECT <fragment>`. If all fail, add a `parse_error` flag with the snippet and move on.
3. **Extract references** from each parsed tree:
   - Collect CTE names from `CommonTableExpr.ctename` first.
   - For `InsertStmt`, `UpdateStmt`, `DeleteStmt`, `MergeStmt`: the `relation` field is a write. Walk the rest of the statement (excluding `relation`) for reads.
   - For `TruncateStmt`: every entry in `relations` is a write.
   - Every other `RangeVar` is a read, unless it is unqualified and matches a CTE name.
   - `IntoClause` (`SELECT ... INTO`) is ignored: inside PL/pgSQL it targets variables, not tables.
4. **Resolve** each raw `(schema | None, name)` against the scanned relations: qualified names directly, unqualified names through the search path in order. Unmatched references become `unresolved_ref` flags (often temp tables).

**Labeling semantics** (the benchmark must follow these exactly):
- The target of `UPDATE`/`DELETE` counts as a write only, even though rows are read to find them.
- A table referenced in a `WHERE`, `FROM`, `USING`, join, or subquery is a read, including the same table as the write target if referenced explicitly in a subquery.
- Triggers are not reads or writes.
- Writes hidden inside dynamic SQL count in the ground truth. The analyzer is expected to miss them; that is what the "excluding dynamic" score isolates.

### 3. Metadata store (`schemalens/store.py`)

One snapshot per file. `scan` writes to a temp file and atomically renames it over `schemalens.db`.

```sql
CREATE TABLE meta       (key TEXT PRIMARY KEY, value TEXT);  -- scanned_at, db_name, server_version, search_path
CREATE TABLE relation   (id TEXT PRIMARY KEY, schema TEXT, name TEXT, kind TEXT, comment TEXT);
CREATE TABLE col        (relation_id TEXT, ordinal INT, name TEXT, data_type TEXT,
                         nullable INT, default_expr TEXT, comment TEXT, is_pk INT,
                         PRIMARY KEY (relation_id, ordinal));
CREATE TABLE foreign_key(name TEXT, from_relation TEXT, from_cols TEXT, to_relation TEXT, to_cols TEXT);  -- cols as JSON arrays
CREATE TABLE routine    (id TEXT PRIMARY KEY, schema TEXT, name TEXT, args TEXT, returns TEXT,
                         kind TEXT, language TEXT, definition TEXT, definition_hash TEXT);
CREATE TABLE dependency (routine_id TEXT, relation_id TEXT, access TEXT,   -- 'read' | 'write'
                         PRIMARY KEY (routine_id, relation_id, access));
CREATE TABLE trg        (name TEXT, relation_id TEXT, routine_id TEXT, definition TEXT);
CREATE TABLE flag       (routine_id TEXT, kind TEXT, detail TEXT);  -- dynamic_sql | parse_error | unresolved_ref
```

IDs are stable across rescans: `relation.id = "schema.name"`; `routine.id = "rtn_" + sha1("schema.name(args)")[:10]`; `definition_hash = sha256(definition)`.

Cache file (`.schemalens/cache.db`):
```sql
CREATE TABLE explanation (definition_hash TEXT, model TEXT, prompt_version TEXT,
                          body TEXT, created_at TEXT,
                          PRIMARY KEY (definition_hash, model, prompt_version));
```

### 4. Bundle contract (`schemalens/bundle.py`)

The single data contract for the UI, the API, and the static export. Defined as Pydantic models; the TypeScript types in `web/src/types.ts` mirror them.

```jsonc
{
  "meta": { "db_name": "pagila", "scanned_at": "...", "server_version": "16.4", "schemalens_version": "0.1.0" },
  "relations": [{ "id": "public.film", "schema": "public", "name": "film", "kind": "table", "comment": null,
                  "columns": [{ "name": "film_id", "data_type": "integer", "nullable": false, "is_pk": true, "default_expr": "...", "comment": null }],
                  "foreign_keys": [{ "name": "...", "from_cols": ["language_id"], "to_relation": "public.language", "to_cols": ["language_id"] }] }],
  "routines": [{ "id": "rtn_ab12cd34ef", "schema": "public", "name": "film_in_stock", "args": "p_film_id integer, ...",
                 "returns": "SETOF integer", "kind": "function", "language": "sql", "definition": "...",
                 "reads": ["public.inventory"], "writes": [],
                 "flags": [{ "kind": "dynamic_sql", "detail": "..." }],
                 "explanation": null }],
  "triggers": [{ "name": "last_updated", "relation_id": "public.film", "routine_id": "rtn_..." }]
}
```

### 5. API (`schemalens/api.py`)

- `GET /api/bundle` returns the bundle.
- `POST /api/routines/{id}/explain` returns the cached explanation or generates one; `409` if AI is disabled; `502` on provider failure.
- `GET /` and static assets serve the built UI from the package's `web_dist/` directory.

### 6. Explanations (`schemalens/explain.py`)

Provider interface with one method, `complete_json(system, user) -> str`. Implement one provider first (Gemini or Claude), selected by `SCHEMALENS_LLM_PROVIDER` and the provider's own API key variable.

**Prompt v1 (system):** You explain PostgreSQL routines to developers new to a codebase. Respond with JSON only, matching this schema: `summary` (max 2 sentences), `purpose`, `parameters` [{name, meaning}], `reads` [schema.table], `writes` [schema.table], `side_effects` [string], `caveats` [string]. Do not guess business meaning you cannot see in the code; say so in caveats.

**Prompt v1 (user):** the routine definition, plus for each relation the analyzer found, its columns and types. Nothing else.

**Cross-check:** compare the LLM's `reads`/`writes` sets to the analyzer's. Any difference is stored in the explanation as `disagreements` and shown in the UI. Over time this doubles as a second signal for finding analyzer bugs.

### 7. MCP server (`schemalens/mcp_server.py`)

Built with the official `mcp` Python SDK (FastMCP), stdio transport, reading `schemalens.db` and the cache.

| Tool | Input | Output |
|---|---|---|
| `search_schema` | `query`, `limit=10` | matching relations, columns, routines with one-line context |
| `describe_table` | `name` (qualified or not) | columns, keys, FKs both ways, routines that read/write it, triggers |
| `explain_function` | `name` | signature, reads, writes, flags, cached explanation if any |
| `get_lineage` | `name` | upstream and downstream neighbors at depth 1 |

Ambiguous names return candidates. Example Kiro config (`.kiro/settings/mcp.json`; check Kiro's docs for the current format):
```json
{ "mcpServers": { "schemalens": { "command": "schemalens", "args": ["mcp", "--db", "./schemalens.db"] } } }
```

### 8. Web UI (`web/`)

Vite + React + TypeScript (strict), React Router, `@xyflow/react` for the graph with `@dagrejs/dagre` for left-to-right layout.

- **Data layer:** `loadBundle()` fetches `/api/bundle` in API mode or `/bundle.json` in static mode (`VITE_DATA_MODE`). Everything else derives from the bundle in memory: a search index, `readsByRelation`, `writesByRelation`, and an adjacency map for lineage.
- **Routes:** `/` (search + overview stats), `/t/:relationId`, `/r/:routineId`, `/lineage/:nodeId`.
- **Graph:** relations as rectangles, routines as rounded pills. Edges: relation → routine (read, solid), routine → relation (write, bold accent), relation ⇢ routine (trigger, dashed).
- **Theming:** CSS variables with a dark-mode override.

### 9. Benchmark (`schemalens/bench.py`)

Loads `benchmark/labels.yaml`, matches entries to routines by `schema.name(args)`, computes the metrics in Requirement 3, and writes `benchmark/RESULTS.md`. Labels are written by reading the source **before** looking at analyzer output; never edit a label to match the analyzer.

## Error handling

| Situation | Behavior |
|---|---|
| Connection or auth failure | Redacted message, exit code 2 |
| One routine fails to analyze | Flag it, continue the scan |
| LLM timeout or invalid JSON | Retry once, then return an error for that routine only |
| Missing metadata store | Commands print "run `schemalens scan` first", exit code 1 |

## Testing strategy

- **Unit (no database):** analyzer behavior on SQL strings and `CREATE FUNCTION` text, resolver, bench metrics, bundle building from a fixture SQLite file.
- **Integration (`-m integration`):** scan Pagila plus the `bench` fixture schema in a Postgres service container; assert counts and known dependencies.
- **Benchmark gate:** CI runs `schemalens bench --min-f1 <baseline - 0.02>`.
- **UI:** a smoke test that loads a fixture bundle and renders each route.

## Known limitations (state these in the README)

- Dynamic SQL is flagged, not analyzed.
- Calls between routines are not traced in v1.
- Bundle size grows with schema size; very large schemas will need paginated API endpoints (v2).
- PostgreSQL only; SQL Server via ScriptDom is planned for v2.
