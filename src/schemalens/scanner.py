"""Read-only catalog scanner (design.md section 1).

Opens the target database read-only, sets a 30s statement timeout, runs only
system-catalog queries (never user row data), analyzes every routine, and
returns a Snapshot ready for the store.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime

import psycopg

from schemalens import __version__
from schemalens.analyzer import analyze_routine
from schemalens.analyzer.resolve import resolve
from schemalens.store import (
    Snapshot,
    cols_to_json,
    definition_hash,
    relation_id,
    routine_id,
)

EXCLUDED_SCHEMAS = ("pg_catalog", "information_schema")

RELATIONS_SQL = """
SELECT c.oid, n.nspname AS schema, c.relname AS name,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'table'
                      WHEN 'v' THEN 'view'  WHEN 'm' THEN 'matview' END AS kind,
       obj_description(c.oid, 'pg_class') AS comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','v','m')
  AND NOT c.relispartition
  AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND n.nspname NOT LIKE 'pg_toast%%'
  {schema_filter}
ORDER BY n.nspname, c.relname;
"""

COLUMNS_SQL = """
SELECT a.attrelid, a.attnum, a.attname,
       format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS nullable,
       pg_get_expr(d.adbin, d.adrelid) AS default_expr,
       col_description(a.attrelid, a.attnum) AS comment
FROM pg_attribute a
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE a.attnum > 0 AND NOT a.attisdropped AND a.attrelid = ANY(%(oids)s)
ORDER BY a.attrelid, a.attnum;
"""

KEYS_SQL = """
SELECT conname, contype, conrelid, confrelid, conkey, confkey
FROM pg_constraint
WHERE contype IN ('p','f') AND conrelid = ANY(%(oids)s);
"""

ROUTINES_SQL = """
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
  {schema_filter}
  AND NOT EXISTS (SELECT 1 FROM pg_depend d
                  WHERE d.objid = p.oid AND d.deptype = 'e')
ORDER BY n.nspname, p.proname;
"""

TRIGGERS_SQL = """
SELECT t.tgname, t.tgrelid, t.tgfoid, pg_get_triggerdef(t.oid) AS definition
FROM pg_trigger t
WHERE NOT t.tgisinternal AND t.tgrelid = ANY(%(oids)s);
"""


def redact_dsn(dsn: str) -> str:
    """Hide the password in a DSN for safe logging."""
    dsn = re.sub(r"(://[^:/@]+:)[^@/]+(@)", r"\1***\2", dsn)
    dsn = re.sub(r"(password=)\S+", r"\1***", dsn, flags=re.IGNORECASE)
    return dsn


class ScanError(Exception):
    """Raised for connection/auth failures. CLI redacts and exits with code 2."""


def scan(
    dsn: str,
    schemas: Iterable[str] | None = None,
    search_path: Iterable[str] = ("public",),
) -> Snapshot:
    """Scan the catalog of the database at `dsn`. Row data is never touched."""
    schemas = list(schemas) if schemas else None
    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except psycopg.Error as exc:
        raise ScanError(str(exc)) from exc

    try:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '30s'")
        return _scan_catalog(conn, schemas, search_path)
    except psycopg.Error as exc:
        raise ScanError(str(exc)) from exc
    finally:
        conn.close()


def _schema_filter(schemas: list[str] | None, alias: str = "n") -> tuple[str, dict]:
    if not schemas:
        return "", {}
    return f"AND {alias}.nspname = ANY(%(schemas)s)", {"schemas": schemas}


def _scan_catalog(
    conn: psycopg.Connection, schemas: list[str] | None, search_path: Iterable[str]
) -> Snapshot:
    snap = Snapshot()

    # --- meta ---
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_setting('server_version')")
        db_name, server_version = cur.fetchone()
    snap.meta = {
        "scanned_at": datetime.now(UTC).isoformat(),
        "db_name": db_name,
        "server_version": server_version,
        "search_path": ",".join(search_path),
        "schemalens_version": __version__,
    }

    sfilter, sparams = _schema_filter(schemas)

    # --- relations ---
    oid_to_id: dict[int, str] = {}
    with conn.cursor() as cur:
        cur.execute(RELATIONS_SQL.format(schema_filter=sfilter), sparams)
        for oid, schema, name, kind, comment in cur.fetchall():
            rid = relation_id(schema, name)
            oid_to_id[oid] = rid
            snap.relations.append(
                {"id": rid, "schema": schema, "name": name, "kind": kind, "comment": comment}
            )
    oids = list(oid_to_id.keys())

    # --- columns ---
    ordinal_by_relation: dict[str, int] = {}
    attr_names: dict[tuple[int, int], str] = {}
    if oids:
        with conn.cursor() as cur:
            cur.execute(COLUMNS_SQL, {"oids": oids})
            for attrelid, attnum, attname, data_type, nullable, default_expr, comment in cur.fetchall():
                rid = oid_to_id[attrelid]
                attr_names[(attrelid, attnum)] = attname
                ordinal = ordinal_by_relation.get(rid, 0)
                ordinal_by_relation[rid] = ordinal + 1
                snap.columns.append(
                    {
                        "relation_id": rid,
                        "ordinal": ordinal,
                        "name": attname,
                        "data_type": data_type,
                        "nullable": 1 if nullable else 0,
                        "default_expr": default_expr,
                        "comment": comment,
                        "is_pk": 0,  # set below
                    }
                )

    # --- keys (primary + foreign) ---
    if oids:
        _scan_keys(conn, oids, oid_to_id, attr_names, snap)

    # --- routines + dependency analysis ---
    known_ids = {rel["id"] for rel in snap.relations}
    rtn_oid_to_id: dict[int, str] = {}
    with conn.cursor() as cur:
        cur.execute(ROUTINES_SQL.format(schema_filter=sfilter), sparams)
        routine_rows = cur.fetchall()

    for oid, schema, name, args, returns, prokind, language, prosrc, definition in routine_rows:
        rid = routine_id(schema, name, args or "")
        rtn_oid_to_id[oid] = rid
        kind = "procedure" if prokind == "p" else "function"
        snap.routines.append(
            {
                "id": rid,
                "schema": schema,
                "name": name,
                "args": args or "",
                "returns": returns,
                "kind": kind,
                "language": language,
                "definition": definition,
                "definition_hash": definition_hash(definition or ""),
            }
        )
        deps = analyze_routine(definition or "", language, prosrc)
        _record_dependencies(snap, rid, deps, known_ids, search_path)

    # --- triggers ---
    if oids:
        _scan_triggers(conn, oids, oid_to_id, rtn_oid_to_id, snap)

    return snap


def _scan_keys(conn, oids, oid_to_id, attr_names, snap: Snapshot) -> None:
    pk_cols: set[tuple[str, int]] = set()  # (relation_id, ordinal) -> is pk
    pk_attnums: dict[str, set[str]] = {}
    with conn.cursor() as cur:
        cur.execute(KEYS_SQL, {"oids": oids})
        rows = cur.fetchall()
    for conname, contype, conrelid, confrelid, conkey, confkey in rows:
        from_rid = oid_to_id.get(conrelid)
        if from_rid is None:
            continue
        from_cols = [attr_names.get((conrelid, num), str(num)) for num in (conkey or [])]
        if contype == "p":
            pk_attnums.setdefault(from_rid, set()).update(from_cols)
        elif contype == "f" and confrelid in oid_to_id:
            to_rid = oid_to_id[confrelid]
            to_cols = [attr_names.get((confrelid, num), str(num)) for num in (confkey or [])]
            snap.foreign_keys.append(
                {
                    "name": conname,
                    "from_relation": from_rid,
                    "from_cols": cols_to_json(from_cols),
                    "to_relation": to_rid,
                    "to_cols": cols_to_json(to_cols),
                }
            )
    # mark pk columns
    for col in snap.columns:
        if col["name"] in pk_attnums.get(col["relation_id"], set()):
            col["is_pk"] = 1
    _ = pk_cols  # unused placeholder kept for clarity


def _scan_triggers(conn, oids, oid_to_id, rtn_oid_to_id, snap: Snapshot) -> None:
    with conn.cursor() as cur:
        cur.execute(TRIGGERS_SQL, {"oids": oids})
        rows = cur.fetchall()
    for tgname, tgrelid, tgfoid, definition in rows:
        rel_id = oid_to_id.get(tgrelid)
        rtn_id = rtn_oid_to_id.get(tgfoid)
        if rel_id is None:
            continue
        snap.triggers.append(
            {
                "name": tgname,
                "relation_id": rel_id,
                "routine_id": rtn_id,
                "definition": definition,
            }
        )


def _record_dependencies(snap: Snapshot, rid: str, deps, known_ids, search_path) -> None:
    for ref in sorted(deps.reads, key=str):
        resolved = resolve(ref, known_ids, search_path)
        if resolved is None:
            snap.flags.append({"routine_id": rid, "kind": "unresolved_ref", "detail": str(ref)})
        else:
            snap.dependencies.append({"routine_id": rid, "relation_id": resolved, "access": "read"})
    for ref in sorted(deps.writes, key=str):
        resolved = resolve(ref, known_ids, search_path)
        if resolved is None:
            snap.flags.append({"routine_id": rid, "kind": "unresolved_ref", "detail": str(ref)})
        else:
            snap.dependencies.append({"routine_id": rid, "relation_id": resolved, "access": "write"})
    for flag in deps.flags:
        snap.flags.append({"routine_id": rid, "kind": flag.kind, "detail": flag.detail})


def summary_counts(snap: Snapshot) -> dict[str, int]:
    return {
        "relations": len(snap.relations),
        "columns": len(snap.columns),
        "routines": len(snap.routines),
        "triggers": len(snap.triggers),
        "dependencies": len(snap.dependencies),
    }


def meta_json(snap: Snapshot) -> str:
    return json.dumps(snap.meta)
