"""Extract table reads and writes from PostgreSQL routines.

Starter implementation for Day 1. Its assumptions about pglast's JSON output
are verified by tests/test_analyzer.py and scripts/spike_plpgsql.py; run those
first and fix anything they expose.

Semantics (must match benchmark labels, see design.md section 2):
- target of INSERT/UPDATE/DELETE/MERGE and TRUNCATE relations -> write
- every other relation reference -> read
- unqualified names matching a CTE are not relations
- SELECT ... INTO is ignored (in PL/pgSQL it targets variables)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pglast.parser import ParseError, parse_plpgsql_json, parse_sql_json

DML_STMTS = ("InsertStmt", "UpdateStmt", "DeleteStmt", "MergeStmt")
DYNAMIC_STMTS = ("PLpgSQL_stmt_dynexecute", "PLpgSQL_stmt_dynfors")


@dataclass(frozen=True, order=True)
class TableRef:
    schema: str | None
    name: str

    def __str__(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name


@dataclass(frozen=True)
class Flag:
    kind: str  # dynamic_sql | parse_error
    detail: str


@dataclass
class RoutineDeps:
    reads: set[TableRef] = field(default_factory=set)
    writes: set[TableRef] = field(default_factory=set)
    flags: list[Flag] = field(default_factory=list)

    def merge(self, other: RoutineDeps) -> None:
        self.reads |= other.reads
        self.writes |= other.writes
        self.flags.extend(other.flags)


def analyze_routine(definition: str, language: str, body: str | None = None) -> RoutineDeps:
    """Analyze one routine. Never raises; failures become flags.

    definition: output of pg_get_functiondef (full CREATE FUNCTION text).
    language:   'plpgsql' or 'sql'.
    body:       prosrc; used for 'sql' routines (falls back to definition when empty).
    """
    try:
        if language == "plpgsql":
            return _analyze_plpgsql(definition)
        if language == "sql":
            return analyze_sql(body if body and body.strip() else definition)
        return RoutineDeps(flags=[Flag("parse_error", f"unsupported language: {language}")])
    except Exception as exc:  # last-resort guard: one bad routine must not abort a scan
        return RoutineDeps(flags=[Flag("parse_error", f"{type(exc).__name__}: {exc}")])


def analyze_sql(sql: str) -> RoutineDeps:
    """Analyze plain SQL text (one or more statements, or a PL/pgSQL fragment)."""
    tree = _parse_fragment(sql)
    if tree is None:
        return RoutineDeps(flags=[Flag("parse_error", _snippet(sql))])
    return _extract(tree)


# ---------------------------------------------------------------- PL/pgSQL


def _analyze_plpgsql(definition: str) -> RoutineDeps:
    tree = json.loads(parse_plpgsql_json(definition))
    queries: list[str] = []
    dynamic: list[str] = []
    _collect_plpgsql(tree, queries, dynamic)

    result = RoutineDeps()
    for stmt_kind in sorted(set(dynamic)):
        result.flags.append(Flag("dynamic_sql", stmt_kind))
    for query in queries:
        result.merge(analyze_sql(query))
    return result


def _collect_plpgsql(node: Any, queries: list[str], dynamic: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in DYNAMIC_STMTS:
                dynamic.append(key)
            if key == "PLpgSQL_expr" and isinstance(value, dict) and isinstance(value.get("query"), str):
                queries.append(value["query"])
            _collect_plpgsql(value, queries, dynamic)
    elif isinstance(node, list):
        for item in node:
            _collect_plpgsql(item, queries, dynamic)


# ---------------------------------------------------------------- SQL


def _parse_fragment(text: str) -> dict[str, Any] | None:
    """Parse SQL, retrying the shapes PL/pgSQL expressions come in."""
    candidates = [text]
    if ":=" in text:
        candidates.append("SELECT " + text.split(":=", 1)[1])
    candidates.append("SELECT " + text)
    for candidate in candidates:
        try:
            return json.loads(parse_sql_json(candidate))
        except ParseError:
            continue
    return None


def _extract(tree: Any) -> RoutineDeps:
    ctes: set[str] = set()
    _collect_ctes(tree, ctes)
    result = RoutineDeps()
    _walk(tree, result, ctes)
    return result


def _collect_ctes(node: Any, ctes: set[str]) -> None:
    if isinstance(node, dict):
        cte = node.get("CommonTableExpr")
        if isinstance(cte, dict) and "ctename" in cte:
            ctes.add(cte["ctename"])
        for value in node.values():
            _collect_ctes(value, ctes)
    elif isinstance(node, list):
        for item in node:
            _collect_ctes(item, ctes)


def _walk(node: Any, result: RoutineDeps, ctes: set[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk(item, result, ctes)
        return
    if not isinstance(node, dict):
        return

    for key, value in node.items():
        if key in DML_STMTS and isinstance(value, dict):
            ref = _table_ref(value.get("relation"))
            if ref is not None:
                result.writes.add(ref)
            # Walk everything except the target so it is not also counted as a read.
            _walk({k: v for k, v in value.items() if k != "relation"}, result, ctes)
        elif key == "TruncateStmt" and isinstance(value, dict):
            for rel in value.get("relations", []):
                ref = _table_ref(rel)
                if ref is not None:
                    result.writes.add(ref)
        elif key == "IntoClause":
            continue  # SELECT ... INTO <variable> in PL/pgSQL
        elif key == "RangeVar" and isinstance(value, dict):
            ref = _table_ref(value)
            if ref is not None and not (ref.schema is None and ref.name in ctes):
                result.reads.add(ref)
        else:
            _walk(value, result, ctes)


def _table_ref(node: Any) -> TableRef | None:
    """Accept a RangeVar either wrapped ({"RangeVar": {...}}) or bare."""
    if not isinstance(node, dict):
        return None
    if "RangeVar" in node:
        node = node["RangeVar"]
    name = node.get("relname")
    if not name:
        return None
    return TableRef(node.get("schemaname"), name)


def _snippet(text: str, limit: int = 120) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
