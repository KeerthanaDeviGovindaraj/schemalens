"""SQLite metadata store and explanation cache (design.md section 3).

One scan == one snapshot. `scan` writes to a temp file and atomically renames
it over the target so a half-written store never replaces a good one.

IDs are stable across rescans:
- relation.id       = "schema.name"
- routine.id        = "rtn_" + sha1("schema.name(args)")[:10]
- definition_hash   = sha256(definition)
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = """
CREATE TABLE meta        (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE relation    (id TEXT PRIMARY KEY, schema TEXT, name TEXT, kind TEXT, comment TEXT);
CREATE TABLE col         (relation_id TEXT, ordinal INT, name TEXT, data_type TEXT,
                          nullable INT, default_expr TEXT, comment TEXT, is_pk INT,
                          PRIMARY KEY (relation_id, ordinal));
CREATE TABLE foreign_key (name TEXT, from_relation TEXT, from_cols TEXT,
                          to_relation TEXT, to_cols TEXT);
CREATE TABLE routine     (id TEXT PRIMARY KEY, schema TEXT, name TEXT, args TEXT, returns TEXT,
                          kind TEXT, language TEXT, definition TEXT, definition_hash TEXT);
CREATE TABLE dependency  (routine_id TEXT, relation_id TEXT, access TEXT,
                          PRIMARY KEY (routine_id, relation_id, access));
CREATE TABLE trg         (name TEXT, relation_id TEXT, routine_id TEXT, definition TEXT);
CREATE TABLE flag        (routine_id TEXT, kind TEXT, detail TEXT);
"""

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS explanation (
    definition_hash TEXT, model TEXT, prompt_version TEXT,
    body TEXT, created_at TEXT,
    PRIMARY KEY (definition_hash, model, prompt_version)
);
"""


# ---------------------------------------------------------------- id helpers


def relation_id(schema: str, name: str) -> str:
    return f"{schema}.{name}"


def routine_id(schema: str, name: str, args: str) -> str:
    sig = f"{schema}.{name}({args})"
    return "rtn_" + hashlib.sha1(sig.encode()).hexdigest()[:10]


def definition_hash(definition: str) -> str:
    return hashlib.sha256(definition.encode()).hexdigest()


# ---------------------------------------------------------------- snapshot data


@dataclass
class Snapshot:
    """Everything one scan collects, ready to persist."""

    meta: dict[str, str] = field(default_factory=dict)
    relations: list[dict] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)
    foreign_keys: list[dict] = field(default_factory=list)
    routines: list[dict] = field(default_factory=list)
    dependencies: list[dict] = field(default_factory=list)
    triggers: list[dict] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------- writing


def write_snapshot(snapshot: Snapshot, out: Path) -> None:
    """Write the snapshot to `out` atomically (temp file + rename)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(out.parent), suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        conn = sqlite3.connect(tmp)
        try:
            conn.executescript(SCHEMA)
            _insert(conn, snapshot)
            conn.commit()
        finally:
            conn.close()
        os.replace(tmp, out)  # atomic on POSIX and Windows
    finally:
        if tmp.exists():
            tmp.unlink()


def _insert(conn: sqlite3.Connection, s: Snapshot) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        list(s.meta.items()),
    )
    conn.executemany(
        "INSERT INTO relation (id, schema, name, kind, comment) "
        "VALUES (:id, :schema, :name, :kind, :comment)",
        s.relations,
    )
    conn.executemany(
        "INSERT INTO col (relation_id, ordinal, name, data_type, nullable, default_expr, comment, is_pk) "
        "VALUES (:relation_id, :ordinal, :name, :data_type, :nullable, :default_expr, :comment, :is_pk)",
        s.columns,
    )
    conn.executemany(
        "INSERT INTO foreign_key (name, from_relation, from_cols, to_relation, to_cols) "
        "VALUES (:name, :from_relation, :from_cols, :to_relation, :to_cols)",
        s.foreign_keys,
    )
    conn.executemany(
        "INSERT INTO routine (id, schema, name, args, returns, kind, language, definition, definition_hash) "
        "VALUES (:id, :schema, :name, :args, :returns, :kind, :language, :definition, :definition_hash)",
        s.routines,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO dependency (routine_id, relation_id, access) "
        "VALUES (:routine_id, :relation_id, :access)",
        s.dependencies,
    )
    conn.executemany(
        "INSERT INTO trg (name, relation_id, routine_id, definition) "
        "VALUES (:name, :relation_id, :routine_id, :definition)",
        s.triggers,
    )
    conn.executemany(
        "INSERT INTO flag (routine_id, kind, detail) VALUES (:routine_id, :kind, :detail)",
        s.flags,
    )


# ---------------------------------------------------------------- reading


@contextmanager
def open_store(path: Path) -> Iterator[sqlite3.Connection]:
    """Open an existing metadata store read-only-ish. Raises FileNotFoundError if missing."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def known_relation_ids(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT id FROM relation")}


# ---------------------------------------------------------------- cache


def default_cache_path() -> Path:
    return Path(".schemalens") / "cache.db"


@contextmanager
def open_cache(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open (creating if needed) the explanation cache. Survives rescans."""
    path = Path(path) if path is not None else default_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(CACHE_SCHEMA)
        yield conn
    finally:
        conn.commit()
        conn.close()


def cache_get(conn: sqlite3.Connection, def_hash: str, model: str, prompt_version: str) -> dict | None:
    row = conn.execute(
        "SELECT body FROM explanation WHERE definition_hash = ? AND model = ? AND prompt_version = ?",
        (def_hash, model, prompt_version),
    ).fetchone()
    return json.loads(row["body"]) if row else None


def cache_put(
    conn: sqlite3.Connection, def_hash: str, model: str, prompt_version: str, body: dict, created_at: str
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO explanation (definition_hash, model, prompt_version, body, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (def_hash, model, prompt_version, json.dumps(body), created_at),
    )
    conn.commit()


def cache_all(conn: sqlite3.Connection) -> dict[str, dict]:
    """Return every cached explanation keyed by definition_hash (latest wins)."""
    out: dict[str, dict] = {}
    for row in conn.execute("SELECT definition_hash, body FROM explanation ORDER BY created_at"):
        out[row["definition_hash"]] = json.loads(row["body"])
    return out


def cols_to_json(cols: Iterable[str]) -> str:
    return json.dumps(list(cols))
