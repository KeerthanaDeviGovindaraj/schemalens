"""Unit tests for the API and MCP tools against a fixture store. No DB or network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from schemalens.store import Snapshot, definition_hash, relation_id, routine_id, write_snapshot


def _snapshot() -> Snapshot:
    snap = Snapshot()
    snap.meta = {
        "db_name": "pagila",
        "scanned_at": "t",
        "server_version": "16",
        "schemalens_version": "0.1.0",
        "search_path": "public",
    }
    film = relation_id("public", "film")
    rental = relation_id("public", "rental")
    snap.relations = [
        {"id": film, "schema": "public", "name": "film", "kind": "table", "comment": None},
        {"id": rental, "schema": "public", "name": "rental", "kind": "table", "comment": None},
    ]
    snap.columns = [
        {
            "relation_id": film,
            "ordinal": 0,
            "name": "film_id",
            "data_type": "integer",
            "nullable": 0,
            "default_expr": None,
            "comment": None,
            "is_pk": 1,
        },
        {
            "relation_id": rental,
            "ordinal": 0,
            "name": "rental_id",
            "data_type": "integer",
            "nullable": 0,
            "default_expr": None,
            "comment": None,
            "is_pk": 1,
        },
    ]
    snap.foreign_keys = [
        {
            "name": "fk",
            "from_relation": rental,
            "from_cols": json.dumps(["film_id"]),
            "to_relation": film,
            "to_cols": json.dumps(["film_id"]),
        },
    ]
    r1 = routine_id("public", "writes_rental", "")
    snap.routines = [
        {
            "id": r1,
            "schema": "public",
            "name": "writes_rental",
            "args": "",
            "returns": "void",
            "kind": "function",
            "language": "sql",
            "definition": "INSERT INTO public.rental DEFAULT VALUES",
            "definition_hash": definition_hash("INSERT INTO public.rental DEFAULT VALUES"),
        },
    ]
    snap.dependencies = [{"routine_id": r1, "relation_id": rental, "access": "write"}]
    snap.triggers = []
    snap.flags = []
    return snap


@pytest.fixture
def store_file(tmp_path: Path) -> Path:
    path = tmp_path / "schemalens.db"
    write_snapshot(_snapshot(), path)
    return path


# ---------------------------------------------------------------- API


def test_api_bundle_endpoint(store_file: Path):
    from schemalens.api import create_app

    client = TestClient(create_app(store_file))
    resp = client.get("/api/bundle")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["db_name"] == "pagila"
    assert any(r["schema"] == "public" for r in data["relations"])


def test_api_explain_disabled_returns_409(store_file: Path):
    from schemalens.api import create_app

    client = TestClient(create_app(store_file, enable_ai=False))
    rid = _snapshot().routines[0]["id"]
    resp = client.post(f"/api/routines/{rid}/explain")
    assert resp.status_code == 409


def test_api_explain_unknown_routine_404(store_file: Path):
    from schemalens.api import create_app

    client = TestClient(create_app(store_file))
    resp = client.post("/api/routines/rtn_doesnotexist/explain")
    assert resp.status_code == 404


# ---------------------------------------------------------------- MCP tools


def test_mcp_tools(store_file: Path):
    import asyncio

    from schemalens.mcp_server import build_server

    server = build_server(store_file)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert {"search_schema", "describe_table", "explain_function", "get_lineage"} <= set(tools)


def test_mcp_describe_table(store_file: Path):
    import asyncio

    from schemalens.mcp_server import build_server

    server = build_server(store_file)
    result = asyncio.run(server.call_tool("describe_table", {"name": "rental"}))
    payload = _tool_payload(result)
    assert payload["id"] == "public.rental"
    writer_id = routine_id("public", "writes_rental", "")
    assert writer_id in payload["written_by"]
    # rental has an FK to film
    assert any(fk["to_relation"] == "public.film" for fk in payload["foreign_keys"])


def test_mcp_describe_table_referenced_by(store_file: Path):
    import asyncio

    from schemalens.mcp_server import build_server

    server = build_server(store_file)
    result = asyncio.run(server.call_tool("describe_table", {"name": "film"}))
    payload = _tool_payload(result)
    # film is referenced by rental's FK
    assert any(fk["from"] == "public.rental" for fk in payload["referenced_by"])


def test_mcp_search(store_file: Path):
    import asyncio

    from schemalens.mcp_server import build_server

    server = build_server(store_file)
    result = asyncio.run(server.call_tool("search_schema", {"query": "rental"}))
    payload = _tool_payload(result)
    assert any(r["id"] == "public.rental" for r in payload["relations"])


def _tool_payload(result):
    """FastMCP returns (content_list, structured) or content list depending on version."""
    if isinstance(result, tuple):
        structured = result[1]
        if isinstance(structured, dict):
            return structured
        result = result[0]
    for item in result:
        text = getattr(item, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no payload in {result!r}")
