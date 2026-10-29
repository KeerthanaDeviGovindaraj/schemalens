# Requirements: SchemaLens MVP

## Introduction

SchemaLens makes legacy PostgreSQL databases understandable to humans and AI coding assistants. It scans a database's catalog (never its row data), works out which tables each function reads and writes, explains each function in plain English, and serves the result as a searchable web UI, a lineage graph, and an MCP server.

This spec covers the 2-week MVP. Scope is PostgreSQL only; SQL Server support is v2.

**Success criteria for the MVP**
- Dependency analysis measured against a hand-labeled benchmark, with precision and recall published in the README.
- A live static demo built from the Pagila sample database.
- `pip install schemalens` works, and `schemalens scan` + `schemalens serve` run end to end on a fresh machine.
- The MCP server answers schema questions inside Kiro.

## Glossary

- **Routine**: a PostgreSQL function or procedure written in `plpgsql` or `sql`.
- **Relation**: a table, partitioned table, view, or materialized view.
- **Dependency**: a (routine, relation, access) triple where access is `read` or `write`.
- **Metadata store**: the local SQLite file SchemaLens writes scan results to.
- **Bundle**: a single JSON document containing everything the UI needs.

## Requirements

### Requirement 1: Read-only database scanning

**User story:** As a developer joining a team, I want to scan our database's structure without risk to production, so that I can explore it safely.

**Acceptance criteria**
1. WHEN the user runs `schemalens scan --dsn <dsn>` THE SYSTEM SHALL open the connection in read-only mode and set a statement timeout of 30 seconds.
2. THE SYSTEM SHALL query only PostgreSQL system catalogs and SHALL NOT select rows from user relations.
3. WHEN scanning, THE SYSTEM SHALL collect relations (excluding partitions), columns with types, nullability, defaults and comments, primary keys, foreign keys, routines (`plpgsql` and `sql`, excluding extension-owned ones), and non-internal triggers.
4. THE SYSTEM SHALL exclude `pg_catalog`, `information_schema`, and `pg_toast*` schemas, and SHALL support `--schema` (repeatable) to restrict the scan.
5. WHEN a scan completes THE SYSTEM SHALL replace the previous snapshot in the metadata store and print counts of relations, columns, routines, triggers, and dependencies.
6. IF the connection fails THEN THE SYSTEM SHALL print a readable error with the DSN password redacted and exit with code 2.
7. THE SYSTEM SHALL NOT write the DSN or any credential to the metadata store or logs.

### Requirement 2: Dependency analysis

**User story:** As a developer, I want to know which tables each function reads and writes, so that I can judge the impact of a change.

**Acceptance criteria**
1. WHEN analyzing a `plpgsql` routine THE SYSTEM SHALL parse its full definition with PostgreSQL's own PL/pgSQL parser (via pglast) and analyze every embedded SQL expression.
2. WHEN analyzing a `sql` routine THE SYSTEM SHALL parse its body with PostgreSQL's SQL parser.
3. THE SYSTEM SHALL record the target relation of `INSERT`, `UPDATE`, `DELETE`, `MERGE`, and `TRUNCATE` as a `write`, and every other relation reference as a `read`.
4. THE SYSTEM SHALL NOT count references to CTE names as relations.
5. THE SYSTEM SHALL resolve unqualified names using a configurable search path (default `public`) against the scanned relations, and SHALL flag references that do not resolve as `unresolved_ref`.
6. IF a routine contains `EXECUTE` or other dynamic SQL THEN THE SYSTEM SHALL flag it `dynamic_sql` and still report the dependencies it can see statically.
7. IF an embedded expression cannot be parsed THEN THE SYSTEM SHALL flag the routine `parse_error` with the failing snippet, continue with the remaining expressions, and never abort the scan.
8. THE SYSTEM SHALL record trigger relationships (relation → trigger routine) as a separate edge type, not as reads or writes.

### Requirement 3: Accuracy benchmark

**User story:** As a maintainer, I want to measure how accurate the dependency analysis is, so that I can make honest claims and catch regressions.

**Acceptance criteria**
1. THE SYSTEM SHALL read ground-truth labels from `benchmark/labels.yaml`, each entry naming a routine signature and its expected `reads` and `writes`.
2. WHEN the user runs `schemalens bench` THE SYSTEM SHALL compute micro-averaged precision, recall, and F1 over (routine, relation, access) triples, separately for reads and writes and combined.
3. THE SYSTEM SHALL report scores both including and excluding routines flagged `dynamic_sql`.
4. THE SYSTEM SHALL list every false positive and false negative per routine.
5. THE SYSTEM SHALL write results as a Markdown table to `benchmark/RESULTS.md`.
6. WHEN run with `--min-f1 <x>` THE SYSTEM SHALL exit non-zero if combined F1 is below `x`, so CI can block regressions.

### Requirement 4: Local API

**User story:** As a user, I want to browse the scan in my browser, so that I don't have to read raw catalog output.

**Acceptance criteria**
1. WHEN the user runs `schemalens serve` THE SYSTEM SHALL start a local server on `127.0.0.1:8765` (configurable) serving the API and the built UI.
2. THE SYSTEM SHALL expose `GET /api/bundle` returning the full bundle, and `POST /api/routines/{id}/explain` returning an explanation.
3. THE SYSTEM SHALL bind to localhost only by default.

### Requirement 5: Web UI

**User story:** As a developer, I want to search, browse, and visualize the database, so that I can learn it quickly.

**Acceptance criteria**
1. THE SYSTEM SHALL provide a search box matching relation names, column names, routine names, and comments, with results grouped by type.
2. WHEN the user opens a relation THE SYSTEM SHALL show its columns, keys, foreign keys in both directions, routines that read it, routines that write it, and its triggers.
3. WHEN the user opens a routine THE SYSTEM SHALL show its signature, language, source with syntax highlighting, reads, writes, flags, and its explanation if available.
4. THE SYSTEM SHALL provide a lineage graph centered on a chosen relation or routine, showing neighbors at depth 1 (expandable to 2), with distinct styles for read, write, and trigger edges.
5. THE SYSTEM SHALL work identically in API mode and static demo mode.
6. THE SYSTEM SHALL be usable at 1280px and 390px widths.

### Requirement 6: AI explanations

**User story:** As a developer, I want plain-English explanations of complex functions, so that I understand them without decoding every line.

**Acceptance criteria**
1. WHEN an explanation is requested THE SYSTEM SHALL send the LLM only the routine definition and catalog metadata for the relations it references, never row data.
2. THE SYSTEM SHALL request structured JSON (summary, purpose, parameters, reads, writes, side effects, caveats) and validate it; IF validation fails THEN THE SYSTEM SHALL retry once and otherwise return an error.
3. THE SYSTEM SHALL cache explanations by (definition hash, model, prompt version) in a cache file separate from the metadata store, so that rescans do not discard them.
4. THE SYSTEM SHALL compare the LLM's claimed reads and writes with the static analysis and flag any mismatch in the UI as "explanation disagrees with analysis."
5. THE SYSTEM SHALL read the API key from an environment variable, support `--no-ai`, and work fully without a key.
6. WHEN `schemalens explain --all` runs THE SYSTEM SHALL generate missing explanations for every routine, with a concurrency limit.

### Requirement 7: MCP server

**User story:** As a developer using an AI coding assistant, I want the assistant to understand our schema, so that it writes correct SQL.

**Acceptance criteria**
1. WHEN the user runs `schemalens mcp --db <path>` THE SYSTEM SHALL start an MCP server over stdio.
2. THE SYSTEM SHALL expose tools `search_schema(query, limit)`, `describe_table(name)`, `explain_function(name)`, and `get_lineage(name)`.
3. THE SYSTEM SHALL answer from the metadata store and cache only, and SHALL NOT connect to the target database.
4. IF a name is ambiguous THEN THE SYSTEM SHALL return the candidates instead of guessing.

### Requirement 8: Static demo export

**User story:** As a recruiter or prospective user, I want to try SchemaLens in my browser instantly, without installing anything.

**Acceptance criteria**
1. WHEN the user runs `schemalens export --out <dir>` THE SYSTEM SHALL write the bundle, including cached explanations, as `bundle.json`.
2. WHEN the UI is built with `VITE_DATA_MODE=static` THE SYSTEM SHALL load `bundle.json` and disable explanation generation, showing cached ones only.
3. THE demo SHALL be deployable as static files.

### Requirement 9: Quality and distribution

**Acceptance criteria**
1. THE SYSTEM SHALL be installable with `pip install schemalens` and expose a `schemalens` command.
2. CI SHALL run linting, unit tests, and the benchmark gate on every pull request.
3. Integration tests against Pagila SHALL run in CI using a PostgreSQL service container.
4. THE README SHALL include a demo GIF, quickstart, benchmark results, privacy model, and limitations.
