"""Resolve raw table references against scanned relations (Task 3.1)."""

from __future__ import annotations

from collections.abc import Iterable

from schemalens.analyzer.deps import TableRef


def resolve(ref: TableRef, known: set[str], search_path: Iterable[str] = ("public",)) -> str | None:
    """Return 'schema.name' if the reference matches a scanned relation, else None.

    known: set of 'schema.name' ids from the scan.
    """
    if ref.schema is not None:
        qualified = f"{ref.schema}.{ref.name}"
        return qualified if qualified in known else None
    for schema in search_path:
        qualified = f"{schema}.{ref.name}"
        if qualified in known:
            return qualified
    return None
