---
inclusion: always
---
# Tech stack and conventions

## Backend (Python 3.12, `src/schemalens/`)
- psycopg 3 (scanner), pglast (parsing), stdlib `sqlite3` (store, no ORM), FastAPI + uvicorn (API), Pydantic v2 (bundle models), Typer (CLI), `mcp` SDK (MCP server), PyYAML (benchmark labels).
- Full type hints on every function; `from __future__ import annotations` at the top of each module.
- Prefer small pure functions and dataclasses. Database and network I/O stay at the edges (scanner, api, explain providers).
- Never use string formatting to build SQL; use psycopg parameters.
- Lint and format with ruff (`ruff check`, `ruff format`).

## Tests
- pytest. Unit tests must not need a database or network. Database tests carry `@pytest.mark.integration`.
- LLM code is tested with a fake provider only.
- Every analyzer bug fix starts with a failing test.

## Frontend (`web/`)
- Vite + React + TypeScript (strict). React Router, `@xyflow/react`, `@dagrejs/dagre`.
- All data comes from the bundle; no extra API calls except "generate explanation".
- Colors via CSS variables with a dark-mode override.

## Commands
- Install: `pip install -e ".[dev]"`
- Tests: `pytest -m "not integration"`; all: `pytest`
- Lint: `ruff check . && ruff format --check .`
- Database: `docker compose up -d` (Postgres on localhost:5433, user/password `postgres`)
