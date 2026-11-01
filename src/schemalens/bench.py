"""Accuracy benchmark (design.md section 9, requirement 3).

Compares the analyzer's dependencies in a metadata store against hand-labeled
ground truth in benchmark/labels.yaml. Computes micro-averaged precision,
recall, and F1 over (routine, relation, access) triples, reports FP/FN, writes
benchmark/RESULTS.md, and can gate CI with --min-f1.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from schemalens.store import open_store, routine_id


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class RoutineDiff:
    routine: str
    false_positives: list[str] = field(default_factory=list)
    false_negatives: list[str] = field(default_factory=list)


@dataclass
class BenchResult:
    reads: Score
    writes: Score
    combined: Score
    reads_nodyn: Score
    writes_nodyn: Score
    combined_nodyn: Score
    diffs: list[RoutineDiff]
    unlabeled: list[str]
    unmatched_labels: list[str]


def _parse_signature(sig: str) -> tuple[str, str, str]:
    """'schema.name(args)' -> (schema, name, args)."""
    head, _, rest = sig.partition("(")
    args = rest[:-1] if rest.endswith(")") else rest
    schema, _, name = head.rpartition(".")
    return schema, name, args


def load_labels(path: Path) -> dict[str, dict]:
    entries = yaml.safe_load(Path(path).read_text()) or []
    return {e["routine"]: e for e in entries}


def _store_deps(conn: sqlite3.Connection) -> tuple[dict, set[str]]:
    """Return {routine_id: {'read': set, 'write': set}} and the set of dynamic routine ids."""
    deps: dict[str, dict[str, set[str]]] = {}
    for row in conn.execute("SELECT routine_id, relation_id, access FROM dependency"):
        d = deps.setdefault(row["routine_id"], {"read": set(), "write": set()})
        d[row["access"]].add(row["relation_id"])
    dynamic = {
        row["routine_id"] for row in conn.execute("SELECT routine_id FROM flag WHERE kind = 'dynamic_sql'")
    }
    return deps, dynamic


def run_bench(store_path: Path, labels_path: Path) -> BenchResult:
    labels = load_labels(labels_path)
    with open_store(store_path) as conn:
        deps, dynamic = _store_deps(conn)
        routine_meta = {
            row["id"]: (row["schema"], row["name"], row["args"])
            for row in conn.execute("SELECT id, schema, name, args FROM routine")
        }

    reads = Score()
    writes = Score()
    reads_nodyn = Score()
    writes_nodyn = Score()
    diffs: list[RoutineDiff] = []
    matched_ids: set[str] = set()
    unmatched_labels: list[str] = []

    for sig, label in labels.items():
        schema, name, args = _parse_signature(sig)
        rid = routine_id(schema, name, args)
        if rid not in routine_meta:
            unmatched_labels.append(sig)
            continue
        matched_ids.add(rid)
        is_dynamic = rid in dynamic
        actual = deps.get(rid, {"read": set(), "write": set()})

        expected_reads = set(label.get("reads") or [])
        expected_writes = set(label.get("writes") or [])

        diff = RoutineDiff(routine=sig)
        _score(reads, expected_reads, actual["read"], diff, "read")
        _score(writes, expected_writes, actual["write"], diff, "write")
        if not is_dynamic:
            _score(reads_nodyn, expected_reads, actual["read"])
            _score(writes_nodyn, expected_writes, actual["write"])
        if diff.false_positives or diff.false_negatives:
            diffs.append(diff)

    unlabeled = [f"{s}.{n}({a})" for rid, (s, n, a) in routine_meta.items() if rid not in matched_ids]

    combined = _combine(reads, writes)
    combined_nodyn = _combine(reads_nodyn, writes_nodyn)
    return BenchResult(
        reads=reads,
        writes=writes,
        combined=combined,
        reads_nodyn=reads_nodyn,
        writes_nodyn=writes_nodyn,
        combined_nodyn=combined_nodyn,
        diffs=diffs,
        unlabeled=sorted(unlabeled),
        unmatched_labels=sorted(unmatched_labels),
    )


def _score(
    score: Score,
    expected: set[str],
    actual: set[str],
    diff: RoutineDiff | None = None,
    access: str = "",
) -> None:
    tp = expected & actual
    fp = actual - expected
    fn = expected - actual
    score.tp += len(tp)
    score.fp += len(fp)
    score.fn += len(fn)
    if diff is not None:
        diff.false_positives.extend(f"{access}:{r}" for r in sorted(fp))
        diff.false_negatives.extend(f"{access}:{r}" for r in sorted(fn))


def _combine(a: Score, b: Score) -> Score:
    return Score(tp=a.tp + b.tp, fp=a.fp + b.fp, fn=a.fn + b.fn)


def render_markdown(result: BenchResult) -> str:
    def row(label: str, s: Score) -> str:
        return f"| {label} | {s.precision:.3f} | {s.recall:.3f} | {s.f1:.3f} | {s.tp} | {s.fp} | {s.fn} |"

    lines = [
        "# Benchmark results",
        "",
        "Micro-averaged over (routine, relation, access) triples.",
        "",
        "## Including dynamic-SQL routines",
        "",
        "| Metric | Precision | Recall | F1 | TP | FP | FN |",
        "|---|---|---|---|---|---|---|",
        row("reads", result.reads),
        row("writes", result.writes),
        row("combined", result.combined),
        "",
        "## Excluding dynamic-SQL routines",
        "",
        "| Metric | Precision | Recall | F1 | TP | FP | FN |",
        "|---|---|---|---|---|---|---|",
        row("reads", result.reads_nodyn),
        row("writes", result.writes_nodyn),
        row("combined", result.combined_nodyn),
        "",
    ]

    if result.diffs:
        lines += ["## Disagreements", ""]
        for d in result.diffs:
            lines.append(f"### {d.routine}")
            if d.false_positives:
                lines.append(f"- false positives: {', '.join(d.false_positives)}")
            if d.false_negatives:
                lines.append(f"- false negatives: {', '.join(d.false_negatives)}")
            lines.append("")
    else:
        lines += ["## Disagreements", "", "None. ", ""]

    if result.unlabeled:
        lines += ["## Unlabeled routines in the store", ""]
        lines += [f"- {r}" for r in result.unlabeled]
        lines.append("")
    if result.unmatched_labels:
        lines += ["## Labels with no matching routine", ""]
        lines += [f"- {r}" for r in result.unmatched_labels]
        lines.append("")

    return "\n".join(lines)
