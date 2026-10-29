---
inclusion: always
---
# Repository structure

```
src/schemalens/
  cli.py            Typer entry point (scan, bench, serve, export, explain, mcp)
  scanner.py        catalog queries, read-only connection
  store.py          SQLite metadata store + explanation cache
  analyzer/
    deps.py         dependency extraction from PL/pgSQL and SQL
    resolve.py      name resolution against scanned relations
  bundle.py         Pydantic bundle models + builder (the UI's data contract)
  api.py            FastAPI app
  explain.py        LLM providers, prompt, validation, cross-check
  mcp_server.py     MCP tools
  bench.py          benchmark metrics + RESULTS.md
web/                React UI (Vite)
benchmark/          labels.yaml, RESULTS.md
docker/initdb/      Pagila + bench fixture SQL (loaded by docker compose)
tests/              unit + integration tests
docs/               design doc, Kiro hook setup
```

New modules go in `src/schemalens/`; keep one responsibility per module.
