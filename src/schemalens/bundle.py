"""The bundle: one JSON document the UI, API, and static export all share.

Pydantic models (design.md section 4). `build_bundle` reads a metadata store
and the explanation cache and assembles the whole thing in memory.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from schemalens.store import cache_all, open_cache, open_store

# "schema" is a BaseModel method name, so the field is stored as `schema_`
# and aliased to "schema" in the JSON the UI consumes.
_ALIAS = ConfigDict(populate_by_name=True)


class Column(BaseModel):
    name: str
    data_type: str
    nullable: bool
    is_pk: bool
    default_expr: str | None = None
    comment: str | None = None


class ForeignKey(BaseModel):
    name: str
    from_cols: list[str]
    to_relation: str
    to_cols: list[str]


class Relation(BaseModel):
    model_config = _ALIAS

    id: str
    schema_: str = Field(alias="schema")
    name: str
    kind: str
    comment: str | None = None
    columns: list[Column] = []
    foreign_keys: list[ForeignKey] = []


class Flag(BaseModel):
    kind: str
    detail: str


class Routine(BaseModel):
    model_config = _ALIAS

    id: str
    schema_: str = Field(alias="schema")
    name: str
    args: str
    returns: str | None = None
    kind: str
    language: str
    definition: str
    reads: list[str] = []
    writes: list[str] = []
    flags: list[Flag] = []
    explanation: dict | None = None


class Trigger(BaseModel):
    name: str
    relation_id: str
    routine_id: str | None = None


class Meta(BaseModel):
    db_name: str | None = None
    scanned_at: str | None = None
    server_version: str | None = None
    schemalens_version: str | None = None
    search_path: str | None = None


class Bundle(BaseModel):
    meta: Meta
    relations: list[Relation]
    routines: list[Routine]
    triggers: list[Trigger]

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, indent=2)


def build_bundle(store_path: Path, cache_path: Path | None = None) -> Bundle:
    """Assemble the bundle from a metadata store and (optionally) cached explanations."""
    with open_store(store_path) as conn:
        meta = _load_meta(conn)
        relations = _load_relations(conn)
        explanations = _load_cache(cache_path)
        routines = _load_routines(conn, explanations)
        triggers = _load_triggers(conn)
    return Bundle(meta=meta, relations=relations, routines=routines, triggers=triggers)


def _load_cache(cache_path: Path | None) -> dict[str, dict]:
    try:
        with open_cache(cache_path) as cache:
            return cache_all(cache)
    except Exception:
        return {}


def _load_meta(conn: sqlite3.Connection) -> Meta:
    rows = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    return Meta(
        db_name=rows.get("db_name"),
        scanned_at=rows.get("scanned_at"),
        server_version=rows.get("server_version"),
        schemalens_version=rows.get("schemalens_version"),
        search_path=rows.get("search_path"),
    )


def _load_relations(conn: sqlite3.Connection) -> list[Relation]:
    cols_by_rel: dict[str, list[Column]] = {}
    for row in conn.execute(
        "SELECT relation_id, name, data_type, nullable, default_expr, comment, is_pk "
        "FROM col ORDER BY relation_id, ordinal"
    ):
        cols_by_rel.setdefault(row["relation_id"], []).append(
            Column(
                name=row["name"],
                data_type=row["data_type"],
                nullable=bool(row["nullable"]),
                is_pk=bool(row["is_pk"]),
                default_expr=row["default_expr"],
                comment=row["comment"],
            )
        )

    fks_by_rel: dict[str, list[ForeignKey]] = {}
    for row in conn.execute("SELECT name, from_relation, from_cols, to_relation, to_cols FROM foreign_key"):
        fks_by_rel.setdefault(row["from_relation"], []).append(
            ForeignKey(
                name=row["name"],
                from_cols=json.loads(row["from_cols"]),
                to_relation=row["to_relation"],
                to_cols=json.loads(row["to_cols"]),
            )
        )

    relations = []
    for row in conn.execute("SELECT id, schema, name, kind, comment FROM relation ORDER BY schema, name"):
        relations.append(
            Relation(
                id=row["id"],
                schema=row["schema"],
                name=row["name"],
                kind=row["kind"],
                comment=row["comment"],
                columns=cols_by_rel.get(row["id"], []),
                foreign_keys=fks_by_rel.get(row["id"], []),
            )
        )
    return relations


def _load_routines(conn: sqlite3.Connection, explanations: dict[str, dict]) -> list[Routine]:
    reads: dict[str, list[str]] = {}
    writes: dict[str, list[str]] = {}
    for row in conn.execute("SELECT routine_id, relation_id, access FROM dependency"):
        target = reads if row["access"] == "read" else writes
        target.setdefault(row["routine_id"], []).append(row["relation_id"])

    flags: dict[str, list[Flag]] = {}
    for row in conn.execute("SELECT routine_id, kind, detail FROM flag"):
        flags.setdefault(row["routine_id"], []).append(Flag(kind=row["kind"], detail=row["detail"]))

    routines = []
    for row in conn.execute(
        "SELECT id, schema, name, args, returns, kind, language, definition, definition_hash "
        "FROM routine ORDER BY schema, name"
    ):
        routines.append(
            Routine(
                id=row["id"],
                schema=row["schema"],
                name=row["name"],
                args=row["args"],
                returns=row["returns"],
                kind=row["kind"],
                language=row["language"],
                definition=row["definition"],
                reads=sorted(reads.get(row["id"], [])),
                writes=sorted(writes.get(row["id"], [])),
                flags=flags.get(row["id"], []),
                explanation=explanations.get(row["definition_hash"]),
            )
        )
    return routines


def _load_triggers(conn: sqlite3.Connection) -> list[Trigger]:
    return [
        Trigger(name=row["name"], relation_id=row["relation_id"], routine_id=row["routine_id"])
        for row in conn.execute("SELECT name, relation_id, routine_id FROM trg")
    ]
