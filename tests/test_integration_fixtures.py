"""Integration: analyze the real pg_get_functiondef output of the bench fixtures
and compare with benchmark/labels.yaml. Needs `docker compose up -d`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from schemalens.analyzer import analyze_routine
from schemalens.analyzer.resolve import resolve

pytestmark = pytest.mark.integration

DSN = os.environ.get("SCHEMALENS_TEST_DSN", "postgresql://postgres:postgres@localhost:5433/pagila")
LABELS = Path(__file__).parent.parent / "benchmark" / "labels.yaml"

ROUTINES_SQL = """
SELECT n.nspname || '.' || p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS sig,
       l.lanname, p.prosrc, pg_get_functiondef(p.oid)
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language l ON l.oid = p.prolang
WHERE n.nspname = 'bench' AND p.prokind IN ('f','p')
"""

RELATIONS_SQL = """
SELECT n.nspname || '.' || c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','v','m') AND n.nspname NOT IN ('pg_catalog','information_schema')
"""


def test_bench_fixtures_match_labels():
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(DSN) as conn:
        conn.read_only = True
        routines = conn.execute(ROUTINES_SQL).fetchall()
        known = {row[0] for row in conn.execute(RELATIONS_SQL).fetchall()}

    labels = {e["routine"]: e for e in yaml.safe_load(LABELS.read_text())}
    assert routines, "no bench routines found; did 03-bench-fixtures.sql load?"

    for sig, lang, body, definition in routines:
        assert sig in labels, f"unlabeled fixture: {sig}"
        deps = analyze_routine(definition, lang, body)
        reads = {resolve(r, known) for r in deps.reads}
        writes = {resolve(w, known) for w in deps.writes}
        assert reads == set(labels[sig]["reads"]), f"{sig} reads"
        assert writes == set(labels[sig]["writes"]), f"{sig} writes"
        assert not [f for f in deps.flags if f.kind == "parse_error"], f"{sig}: {deps.flags}"
