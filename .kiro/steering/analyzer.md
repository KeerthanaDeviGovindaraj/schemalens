---
inclusion: fileMatch
fileMatchPattern: "src/schemalens/analyzer/**"
---
# Analyzer rules

- Follow the labeling semantics in design.md section 2 exactly; the benchmark depends on them.
- DML target (`relation` of Insert/Update/Delete/Merge, `relations` of Truncate) = write. Every other RangeVar = read. Unqualified names matching a CTE are not relations. `IntoClause` is ignored.
- Never raise out of `analyze_routine`; convert failures into flags.
- Add a fixture to `docker/initdb/03-bench-fixtures.sql`, a label to `benchmark/labels.yaml`, and a unit test for every new pattern handled.
- After any change, run `pytest tests/test_analyzer.py` and `schemalens bench`, and report the F1 change.
