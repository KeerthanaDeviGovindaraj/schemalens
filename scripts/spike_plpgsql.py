"""Day 1 spike: confirm pglast parses PL/pgSQL the way the analyzer expects.

Usage:
    python scripts/spike_plpgsql.py                 # analyze every routine
    python scripts/spike_plpgsql.py film_title      # also dump raw JSON for one routine

Requires `docker compose up -d`. Override the DSN with SCHEMALENS_TEST_DSN.
"""

from __future__ import annotations

import json
import os
import sys

import psycopg
from pglast.parser import parse_plpgsql_json

from schemalens.analyzer import analyze_routine

DSN = os.environ.get("SCHEMALENS_TEST_DSN", "postgresql://postgres:postgres@localhost:5433/pagila")

SQL = """
SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid),
       l.lanname, p.prosrc, pg_get_functiondef(p.oid)
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language l ON l.oid = p.prolang
WHERE p.prokind IN ('f','p') AND l.lanname IN ('plpgsql','sql')
  AND n.nspname NOT IN ('pg_catalog','information_schema')
ORDER BY 1, 2
"""


def main() -> None:
    dump = sys.argv[1] if len(sys.argv) > 1 else None
    with psycopg.connect(DSN) as conn:
        conn.read_only = True
        rows = conn.execute(SQL).fetchall()

    for schema, name, args, lang, body, definition in rows:
        deps = analyze_routine(definition, lang, body)
        print(f"\n{schema}.{name}({args})  [{lang}]")
        print(f"  reads : {sorted(map(str, deps.reads))}")
        print(f"  writes: {sorted(map(str, deps.writes))}")
        for flag in deps.flags:
            print(f"  FLAG  : {flag.kind}: {flag.detail}")
        if dump == name and lang == "plpgsql":
            print(json.dumps(json.loads(parse_plpgsql_json(definition)), indent=2))

    print(f"\n{len(rows)} routines analyzed.")


if __name__ == "__main__":
    main()
