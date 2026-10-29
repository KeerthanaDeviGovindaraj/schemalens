# Benchmark

`labels.yaml` holds hand-written ground truth for which tables each routine reads and writes. `schemalens bench` scores the analyzer against it and writes `RESULTS.md`.

How labels are made:
1. Read the routine's source (`docker/initdb/03-bench-fixtures.sql` or `pg_get_functiondef`).
2. Write down reads and writes using the semantics in `.kiro/specs/schemalens-mvp/design.md` section 2.
3. Only then run the analyzer. If they disagree, the analyzer is wrong until proven otherwise.

Coverage goal for v0.1: every Pagila routine plus 40+ fixtures, one pattern each (CTEs, writable CTEs, UPDATE…FROM, DELETE…USING, MERGE, TRUNCATE, INSERT…SELECT, subqueries in WHERE/IF/assignments, RETURN QUERY, cursors, FOR loops over queries, quoted and mixed-case identifiers, unqualified names, dynamic SQL, triggers, SQL-language functions, procedures).
