# Implementation Plan: SchemaLens MVP (14 days)

Rules: each task ends with passing tests and a commit. If a day slips, cut UI polish (tasks 7–8), never the analyzer or benchmark (tasks 2–5).

- [ ] 1. Day 1: Foundation and parser spike
  - [ ] 1.1 Create a virtualenv, `pip install -e ".[dev]"`, confirm `schemalens --help` runs
  - [ ] 1.2 Run `scripts/get_pagila.sh`, then `docker compose up -d`; confirm Pagila and the `bench` schema loaded
  - [ ] 1.3 Run `python scripts/spike_plpgsql.py` and `pytest tests/test_analyzer.py`; fix the starter analyzer until every test passes (this validates pglast's JSON shapes, the riskiest assumption in the project)
  - [ ] 1.4 Push to GitHub; confirm CI is green
  - _Requirements: 2.1, 2.2, 9.2_

- [ ] 2. Day 2: Scanner and metadata store
  - [ ] 2.1 Implement `store.py` with the schema from design.md and atomic temp-file replacement
  - [ ] 2.2 Implement `scanner.py` with the catalog queries from design.md, read-only connection, 30s timeout
  - [ ] 2.3 Implement `schemalens scan --dsn --schema --out` with summary counts and redacted errors (exit code 2)
  - [ ] 2.4 Integration test: scanning Pagila yields the expected relation count and no partitions
  - _Requirements: 1.1–1.7_

- [ ] 3. Days 3–4: Dependency analysis wired into the scan
  - [ ] 3.1 Implement the resolver: qualified names, search path, `unresolved_ref` flags
  - [ ] 3.2 Run the analyzer for every routine during scan; store dependencies, flags, and trigger edges
  - [ ] 3.3 Add unit tests for every case in `docker/initdb/03-bench-fixtures.sql` (CTE, writable CTE, UPDATE…FROM, IF EXISTS, assignment, dynamic SQL, unqualified names, SQL-language functions)
  - [ ] 3.4 Integration test: known Pagila dependencies appear in the store
  - _Requirements: 2.1–2.8_

- [ ] 4. Day 5: Benchmark
  - [ ] 4.1 Read the source of every Pagila routine and label reads/writes in `benchmark/labels.yaml` before looking at analyzer output
  - [ ] 4.2 Write 30–40 more fixture functions in `03-bench-fixtures.sql` covering patterns you have not tested yet; label them the same way
  - [ ] 4.3 Implement `schemalens bench` with precision, recall, F1 (reads, writes, combined; with and without dynamic SQL), FP/FN listing, and `RESULTS.md`
  - [ ] 4.4 Record the baseline; add `--min-f1 <baseline - 0.02>` to CI
  - _Requirements: 3.1–3.6_

- [ ] 5. Day 6: Bundle, API, CLI
  - [ ] 5.1 Implement Pydantic bundle models and `build_bundle(store, cache)`
  - [ ] 5.2 Implement FastAPI `GET /api/bundle` and static UI serving; `schemalens serve` binds to 127.0.0.1
  - [ ] 5.3 Implement `schemalens export --out <dir>` writing `bundle.json`
  - [ ] 5.4 Unit test the bundle against a fixture SQLite file
  - _Requirements: 4.1–4.3, 8.1_

- [ ] 6. Day 7: Web UI core
  - [ ] 6.1 Scaffold `web/` with Vite React-TS; strict TypeScript; mirror the bundle types in `web/src/types.ts`
  - [ ] 6.2 Data layer with API and static modes (`VITE_DATA_MODE`)
  - [ ] 6.3 Search page with grouped results; relation page; routine page with highlighted source
  - _Requirements: 5.1–5.3, 5.5_

- [ ] 7. Day 8: Lineage graph
  - [ ] 7.1 Build the adjacency map from the bundle
  - [ ] 7.2 Lineage route with `@xyflow/react` + dagre layout, depth 1 with expand to 2, distinct read/write/trigger edge styles
  - [ ] 7.3 Light/dark theme and 390px layout check
  - _Requirements: 5.4, 5.6_

- [ ] 8. Day 9: AI explanations
  - [ ] 8.1 Provider interface and one provider; key from environment
  - [ ] 8.2 Prompt v1, JSON validation with one retry, cache keyed by (definition hash, model, prompt version)
  - [ ] 8.3 Cross-check LLM reads/writes against the analyzer and store disagreements
  - [ ] 8.4 `POST /api/routines/{id}/explain`, `schemalens explain --all` with a concurrency limit, `--no-ai`
  - [ ] 8.5 UI: explanation panel with a visible disagreement warning
  - [ ] 8.6 Tests with a fake provider (no network in CI)
  - _Requirements: 6.1–6.6_

- [ ] 9. Day 10: MCP server
  - [ ] 9.1 Implement the four tools with FastMCP over stdio, reading only the store and cache
  - [ ] 9.2 Ambiguous names return candidates
  - [ ] 9.3 Register it in Kiro and test real questions ("which functions write to rental?"); save a screen recording for launch
  - _Requirements: 7.1–7.4_

- [ ] 10. Day 11: Static demo and README
  - [ ] 10.1 Scan Pagila, run `explain --all`, export the bundle into `web/public/`
  - [ ] 10.2 Deploy the static build to Vercel
  - [ ] 10.3 README: pitch, demo link, GIF, quickstart, benchmark table, privacy model, limitations
  - _Requirements: 8.2, 8.3, 9.4_

- [ ] 11. Day 12: Hardening
  - [ ] 11.1 Work through every false positive and false negative in `RESULTS.md`; fix analyzer bugs, never labels
  - [ ] 11.2 Test on a second public sample database to catch overfitting to Pagila
  - [ ] 11.3 Fresh-machine test: clone, install, scan, serve, following only the README
  - _Requirements: 2.x, 3.x_

- [ ] 12. Day 13: Packaging and design doc
  - [ ] 12.1 Bundle the built UI into the wheel; publish to TestPyPI, then PyPI
  - [ ] 12.2 Write `docs/design-doc.md`: problem, goals and non-goals, design, alternatives considered (regex vs. parser, GraphQL vs. REST, hosted vs. local), evaluation results
  - [ ] 12.3 Tag v0.1.0 and write the changelog
  - _Requirements: 9.1_

- [ ] 13. Day 14: Launch
  - [ ] 13.1 LinkedIn post with the demo video (repo link in the first comment)
  - [ ] 13.2 Show HN and r/PostgreSQL posts
  - [ ] 13.3 Reply to every comment; turn feedback into GitHub issues
