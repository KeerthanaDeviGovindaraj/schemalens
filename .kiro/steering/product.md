---
inclusion: always
---
# Product: SchemaLens

SchemaLens makes legacy PostgreSQL databases understandable to developers and AI coding assistants: searchable docs, table-to-function lineage, plain-English explanations, and an MCP server.

## Principles (apply to every change)
- **Privacy first.** Only system catalogs are ever queried. Row data is never read, stored, logged, or sent to an LLM. Credentials are never persisted.
- **Accuracy over coverage.** The deterministic analyzer is the source of truth. When unsure, flag (`dynamic_sql`, `parse_error`, `unresolved_ref`) rather than guess.
- **The LLM narrates; the analyzer decides.** LLM output is validated, cached, and cross-checked against the analyzer.
- **Local-first.** Everything runs on the user's machine. The only hosted piece is the static demo.
- **Measured claims.** Accuracy claims in the README must come from `benchmark/RESULTS.md`.

## Scope
The MVP scope is defined in `.kiro/specs/schemalens-mvp/`. Do not add features outside it (SQL Server support, accounts, billing, hosted scanning) without updating the spec first.
