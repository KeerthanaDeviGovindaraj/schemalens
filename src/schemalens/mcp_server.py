"""MCP server over stdio (design.md section 7, requirement 7).

Four tools, answered only from the metadata store and explanation cache. Never
connects to the target database. Ambiguous names return candidates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from schemalens.bundle import Bundle, build_bundle


def _load(store_path: Path, cache_path: Path | None) -> Bundle:
    return build_bundle(store_path, cache_path)


def _match_relation(bundle: Bundle, name: str):
    """Return (matches) for a qualified or unqualified relation name."""
    if "." in name:
        return [r for r in bundle.relations if r.id == name]
    return [r for r in bundle.relations if r.name == name]


def _match_routine(bundle: Bundle, name: str):
    if "." in name:
        schema, _, routine = name.rpartition(".")
        return [r for r in bundle.routines if r.schema_ == schema and r.name == routine]
    return [r for r in bundle.routines if r.name == name]


def build_server(store_path: Path, cache_path: Path | None = None) -> FastMCP:
    server = FastMCP("schemalens")
    bundle = _load(store_path, cache_path)

    @server.tool()
    def search_schema(query: str, limit: int = 10) -> dict[str, Any]:
        """Search relations, columns, and routines by name or comment."""
        q = query.lower()
        rels, cols, rtns = [], [], []
        for r in bundle.relations:
            if q in r.name.lower() or (r.comment and q in r.comment.lower()):
                rels.append({"id": r.id, "kind": r.kind, "comment": r.comment})
            for c in r.columns:
                if q in c.name.lower():
                    cols.append({"relation": r.id, "column": c.name, "type": c.data_type})
        for r in bundle.routines:
            if q in r.name.lower():
                rtns.append({"id": r.id, "name": f"{r.schema_}.{r.name}", "language": r.language})
        return {
            "relations": rels[:limit],
            "columns": cols[:limit],
            "routines": rtns[:limit],
        }

    @server.tool()
    def describe_table(name: str) -> dict[str, Any]:
        """Columns, keys, FKs both ways, and routines that read/write a relation."""
        matches = _match_relation(bundle, name)
        if not matches:
            return {"error": f"no relation named {name!r}"}
        if len(matches) > 1:
            return {"ambiguous": [r.id for r in matches]}
        rel = matches[0]
        reads = [r.id for r in bundle.routines if rel.id in r.reads]
        writes = [r.id for r in bundle.routines if rel.id in r.writes]
        incoming_fks = [
            {"from": other.id, "fk": fk.name}
            for other in bundle.relations
            for fk in other.foreign_keys
            if fk.to_relation == rel.id
        ]
        triggers = [t.name for t in bundle.triggers if t.relation_id == rel.id]
        return {
            "id": rel.id,
            "kind": rel.kind,
            "comment": rel.comment,
            "columns": [
                {"name": c.name, "type": c.data_type, "nullable": c.nullable, "pk": c.is_pk}
                for c in rel.columns
            ],
            "foreign_keys": [fk.model_dump() for fk in rel.foreign_keys],
            "referenced_by": incoming_fks,
            "read_by": reads,
            "written_by": writes,
            "triggers": triggers,
        }

    @server.tool()
    def explain_function(name: str) -> dict[str, Any]:
        """Signature, reads, writes, flags, and a cached explanation if present."""
        matches = _match_routine(bundle, name)
        if not matches:
            return {"error": f"no routine named {name!r}"}
        if len(matches) > 1:
            return {"ambiguous": [f"{r.schema_}.{r.name}({r.args})" for r in matches]}
        r = matches[0]
        return {
            "id": r.id,
            "signature": f"{r.schema_}.{r.name}({r.args})",
            "returns": r.returns,
            "language": r.language,
            "reads": r.reads,
            "writes": r.writes,
            "flags": [f.model_dump() for f in r.flags],
            "explanation": r.explanation,
        }

    @server.tool()
    def get_lineage(name: str) -> dict[str, Any]:
        """Upstream and downstream neighbors at depth 1 for a relation or routine."""
        rels = _match_relation(bundle, name)
        rtns = _match_routine(bundle, name)
        if len(rels) + len(rtns) == 0:
            return {"error": f"no relation or routine named {name!r}"}
        if len(rels) + len(rtns) > 1:
            return {"ambiguous": [r.id for r in rels] + [f"{r.schema_}.{r.name}" for r in rtns]}
        if rels:
            rel = rels[0]
            return {
                "node": rel.id,
                "type": "relation",
                "read_by": [r.id for r in bundle.routines if rel.id in r.reads],
                "written_by": [r.id for r in bundle.routines if rel.id in r.writes],
                "triggers": [t.routine_id for t in bundle.triggers if t.relation_id == rel.id],
            }
        rtn = rtns[0]
        return {
            "node": rtn.id,
            "type": "routine",
            "reads": rtn.reads,
            "writes": rtn.writes,
        }

    return server


def run(store_path: Path, cache_path: Path | None = None) -> None:
    server = build_server(store_path, cache_path)
    server.run()  # stdio transport
