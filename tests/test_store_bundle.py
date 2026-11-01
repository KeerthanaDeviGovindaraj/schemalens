"""Unit tests for the store, bundle builder, and benchmark. No database or network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from schemalens.bench import render_markdown, run_bench
from schemalens.bundle import build_bundle
from schemalens.store import (
    Snapshot,
    definition_hash,
    open_cache,
    relation_id,
    routine_id,
    write_snapshot,
)


def _sample_snapshot() -> Snapshot:
    snap = Snapshot()
    snap.meta = {
        "db_name": "pagila",
        "scanned_at": "2026-01-01T00:00:00+00:00",
        "server_version": "16.4",
        "schemalens_version": "0.1.0",
        "search_path": "public",
    }
    film = relation_id("public", "film")
    inventory = relation_id("public", "inventory")
    snap.relations = [
        {"id": film, "schema": "public", "name": "film", "kind": "table", "comment": "films"},
        {"id": inventory, "schema": "public", "name": "inventory", "kind": "table", "comment": None},
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
            "relation_id": film,
            "ordinal": 1,
            "name": "title",
            "data_type": "text",
            "nullable": 0,
            "default_expr": None,
            "comment": None,
            "is_pk": 0,
        },
        {
            "relation_id": inventory,
            "ordinal": 0,
            "name": "inventory_id",
            "data_type": "integer",
            "nullable": 0,
            "default_expr": None,
            "comment": None,
            "is_pk": 1,
        },
        {
            "relation_id": inventory,
            "ordinal": 1,
            "name": "film_id",
            "data_type": "integer",
            "nullable": 0,
            "default_expr": None,
            "comment": None,
            "is_pk": 0,
        },
    ]
    snap.foreign_keys = [
        {
            "name": "inv_film_fk",
            "from_relation": inventory,
            "from_cols": json.dumps(["film_id"]),
            "to_relation": film,
            "to_cols": json.dumps(["film_id"]),
        },
    ]
    rtn = routine_id("public", "rentals_for_film", "integer")
    snap.routines = [
        {
            "id": rtn,
            "schema": "public",
            "name": "rentals_for_film",
            "args": "integer",
            "returns": "bigint",
            "kind": "function",
            "language": "sql",
            "definition": "SELECT count(*) FROM public.inventory WHERE film_id = $1",
            "definition_hash": definition_hash("SELECT count(*) FROM public.inventory WHERE film_id = $1"),
        },
    ]
    snap.dependencies = [
        {"routine_id": rtn, "relation_id": inventory, "access": "read"},
    ]
    snap.triggers = []
    snap.flags = [{"routine_id": rtn, "kind": "dynamic_sql", "detail": "PLpgSQL_stmt_dynexecute"}]
    return snap


@pytest.fixture
def store_file(tmp_path: Path) -> Path:
    path = tmp_path / "schemalens.db"
    write_snapshot(_sample_snapshot(), path)
    return path


def test_write_and_build_bundle(store_file: Path):
    bundle = build_bundle(store_file)
    assert bundle.meta.db_name == "pagila"
    assert len(bundle.relations) == 2
    film = next(r for r in bundle.relations if r.name == "film")
    assert [c.name for c in film.columns] == ["film_id", "title"]
    assert film.columns[0].is_pk is True
    inv = next(r for r in bundle.relations if r.name == "inventory")
    assert inv.foreign_keys[0].to_relation == "public.film"

    routine = bundle.routines[0]
    assert routine.reads == ["public.inventory"]
    assert routine.writes == []
    assert [f.kind for f in routine.flags] == ["dynamic_sql"]


def test_bundle_json_uses_schema_alias(store_file: Path):
    bundle = build_bundle(store_file)
    data = json.loads(bundle.to_json())
    assert "schema" in data["relations"][0]
    assert "schema_" not in data["relations"][0]
    assert "schema" in data["routines"][0]


def test_atomic_write_overwrites(tmp_path: Path):
    path = tmp_path / "schemalens.db"
    write_snapshot(_sample_snapshot(), path)
    first = build_bundle(path)
    # second scan with fewer objects replaces the snapshot cleanly
    smaller = Snapshot()
    smaller.meta = dict(_sample_snapshot().meta, db_name="other")
    write_snapshot(smaller, path)
    second = build_bundle(path)
    assert first.meta.db_name == "pagila"
    assert second.meta.db_name == "other"
    assert second.relations == []


def test_bundle_includes_cached_explanation(tmp_path: Path, monkeypatch):
    store_path = tmp_path / "schemalens.db"
    snap = _sample_snapshot()
    write_snapshot(snap, store_path)
    cache_path = tmp_path / "cache.db"
    def_hash = snap.routines[0]["definition_hash"]
    with open_cache(cache_path) as cache:
        from schemalens.store import cache_put

        cache_put(cache, def_hash, "fake", "v1", {"summary": "counts rentals"}, "2026-01-01")

    bundle = build_bundle(store_path, cache_path)
    assert bundle.routines[0].explanation == {"summary": "counts rentals"}


# ---------------------------------------------------------------- benchmark


def test_bench_perfect_score(tmp_path: Path):
    store_path = tmp_path / "schemalens.db"
    write_snapshot(_sample_snapshot(), store_path)
    labels = tmp_path / "labels.yaml"
    labels.write_text(
        "- routine: public.rentals_for_film(integer)\n  reads: [public.inventory]\n  writes: []\n"
    )
    result = run_bench(store_path, labels)
    assert result.combined.f1 == 1.0
    assert result.reads.tp == 1
    assert result.diffs == []
    # the routine is flagged dynamic, so excluding-dynamic has no triples
    assert result.combined_nodyn.tp == 0
    md = render_markdown(result)
    assert "Benchmark results" in md


def test_bench_reports_false_positive_and_negative(tmp_path: Path):
    store_path = tmp_path / "schemalens.db"
    write_snapshot(_sample_snapshot(), store_path)
    labels = tmp_path / "labels.yaml"
    # label expects a read of public.film which the analyzer did NOT find (FN),
    # and does NOT expect public.inventory which the analyzer DID find (FP)
    labels.write_text("- routine: public.rentals_for_film(integer)\n  reads: [public.film]\n  writes: []\n")
    result = run_bench(store_path, labels)
    assert result.reads.fp == 1
    assert result.reads.fn == 1
    assert len(result.diffs) == 1
    diff = result.diffs[0]
    assert "read:public.inventory" in diff.false_positives
    assert "read:public.film" in diff.false_negatives
